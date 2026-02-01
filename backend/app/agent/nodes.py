from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.agent.prompts import PLANNER_PROMPT, EXTRACTOR_PROMPT
from app.services.llm_factory import get_chat_model
from app.services.redis_client import redis_client
from app.services.browserbase_client import browserbase_client
from playwright.sync_api import sync_playwright
import re


class PlanOutput(BaseModel):
    search_queries: list[str] = Field(..., min_length=3, max_length=3)
    rubric: Dict[str, float]
    required_sources: list[str]
    extraction_fields: list[str]


class ExtractOutput(BaseModel):
    data: Dict[str, Any]


def plan_node(state: Dict[str, Any]) -> Dict[str, Any]:
    llm = get_chat_model()
    parser = JsonOutputParser(pydantic_object=PlanOutput)
    prompt = PromptTemplate(
        template=PLANNER_PROMPT,
        input_variables=["goal", "query"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    message = prompt.format(goal=state["goal"], query=state["query"])
    response = llm.invoke(message)
    content = response.content if hasattr(response, "content") else str(response)
    plan = parser.parse(content)
    plan_dict = plan if isinstance(plan, dict) else plan.model_dump()
    
    trace = state.get("trace", [])
    trace.append({"type": "plan", "payload": plan_dict})
    return {"plan": plan_dict, "trace": trace}


def browse_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    limit = int(state.get("limit", 5))
    plan = state.get("plan") or {}
    search_queries = plan.get("search_queries") or []
    query = search_queries[0] if search_queries else state.get("query", "")
    tab_id = state.get("tab_id", "")
    
    if not query:
        trace.append({"type": "browse", "payload": {"status": "skipped", "reason": "no_query"}})
        return {"trace": trace, "candidate_links": []}
    
    client = redis_client.get_client()
    session_key = f"tab:{tab_id}:browserbase_session"
    session_id = client.get(session_key)
    connect_url = None
    
    if not session_id:
        session_result = browserbase_client.create_session(tab_id or "agent")
        if session_result.get("ok"):
            session_id = session_result.get("session_id")
            connect_url = session_result.get("data", {}).get("connectUrl")
            if session_id:
                client.setex(session_key, 86400, session_id)
        else:
            trace.append({
                "type": "browse",
                "payload": {"status": "error", "error": session_result.get("error")}
            })
            return {"trace": trace, "candidate_links": []}
    else:
        session_info = browserbase_client.get_session(session_id)
        if session_info.get("ok"):
            connect_url = session_info.get("session", {}).get("connectUrl")
    
    if not connect_url:
        trace.append({"type": "browse", "payload": {"status": "error", "error": "missing_connect_url"}})
        return {"trace": trace, "candidate_links": []}
    
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    candidates: list[dict] = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(connect_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            
            # Handle Google consent if present
            try:
                consent_button = page.get_by_role("button", name=re.compile(r"accept|agree", re.I))
                if consent_button.is_visible(timeout=2000):
                    consent_button.click()
                    page.wait_for_timeout(1200)
            except Exception:
                pass
            
            raw_links = page.evaluate(
                """() => {
                    const results = [];
                    const blocks = document.querySelectorAll('div#search a h3');
                    blocks.forEach(h3 => {
                        const a = h3.closest('a');
                        if (!a) return;
                        results.push({
                            href: a.href || '',
                            text: (h3.innerText || '').trim()
                        });
                    });
                    if (results.length) return results;
                    const links = Array.from(document.querySelectorAll('a'));
                    return links.map(a => ({
                        href: a.href || '',
                        text: (a.innerText || '').trim()
                    }));
                }"""
            )
            
            seen = set()
            for item in raw_links:
                href = item.get("href", "")
                text = item.get("text", "")
                if not href or not href.startswith("http"):
                    continue
                if "google.com" in href or "/search?" in href:
                    continue
                if href.startswith("mailto:"):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                if not text:
                    text = re.sub(r"https?://", "", href)[:80]
                candidates.append({"url": href, "title": text})
                if len(candidates) >= limit:
                    break
            
            browser.close()
    except Exception as e:
        trace.append({"type": "browse", "payload": {"status": "error", "error": str(e)}})
        return {"trace": trace, "candidate_links": []}
    
    trace.append({
        "type": "browse",
        "payload": {
            "status": "completed",
            "query": query,
            "count": len(candidates)
        }
    })
    return {
        "trace": trace,
        "candidate_links": candidates,
        "browserbase_session_id": session_id,
        "connect_url": connect_url
    }


def extract_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    plan = state.get("plan") or {}
    fields = plan.get("extraction_fields") or []
    candidates = state.get("candidate_links") or []
    connect_url = state.get("connect_url")
    limit = min(len(candidates), int(state.get("limit", 5)))
    
    if not connect_url or not candidates:
        trace.append({"type": "extract", "payload": {"status": "skipped", "reason": "no_links"}})
        return {"trace": trace, "extracted_items": []}
    
    llm = get_chat_model()
    parser = JsonOutputParser(pydantic_object=ExtractOutput)
    prompt = PromptTemplate(
        template=EXTRACTOR_PROMPT,
        input_variables=["fields", "url", "title", "content"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    
    extracted_items: list[dict] = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(connect_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            
            for item in candidates[:limit]:
                url = item.get("url", "")
                if not url:
                    continue
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1200)
                    title = page.title() or item.get("title", "")
                    content = page.evaluate(
                        """() => (document.body && document.body.innerText)
                            ? document.body.innerText.slice(0, 6000)
                            : """""
                    )
                    
                    message = prompt.format(
                        fields=", ".join(fields),
                        url=url,
                        title=title,
                        content=content
                    )
                    response = llm.invoke(message)
                    text = response.content if hasattr(response, "content") else str(response)
                    extracted = parser.parse(text)
                    extracted_dict = extracted if isinstance(extracted, dict) else extracted.model_dump()
                    extracted_items.append({
                        "url": url,
                        "title": title,
                        "data": extracted_dict.get("data", {})
                    })
                except Exception as e:
                    trace.append({"type": "extract:item_error", "payload": {"url": url, "error": str(e)}})
            
            browser.close()
    except Exception as e:
        trace.append({"type": "extract", "payload": {"status": "error", "error": str(e)}})
        return {"trace": trace, "extracted_items": []}
    
    trace.append({
        "type": "extract",
        "payload": {"status": "completed", "count": len(extracted_items)}
    })
    return {"trace": trace, "extracted_items": extracted_items}


def summarize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    trace.append({"type": "summarize", "payload": {"status": "pending"}})
    return {"status": "completed", "trace": trace}
