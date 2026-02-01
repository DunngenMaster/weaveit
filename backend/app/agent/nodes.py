from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.agent.prompts import PLANNER_PROMPT, EXTRACTOR_PROMPT, LINK_SCORER_PROMPT, SUMMARY_PROMPT
from app.services.llm_factory import get_chat_model
from app.services.redis_client import redis_client
from app.services.browserbase_client import browserbase_client
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import re
import json
from datetime import datetime


class PlanOutput(BaseModel):
    search_queries: list[str] = Field(..., min_length=3, max_length=3)
    rubric: Dict[str, float]
    required_sources: list[str]
    extraction_fields: list[str]


class ExtractOutput(BaseModel):
    data: Dict[str, Any]


class LinkScoreItem(BaseModel):
    url: str
    title: str | None = None
    score: float
    reason: str


class LinkScoreOutput(BaseModel):
    scored: list[LinkScoreItem]


class SummaryOutput(BaseModel):
    top_three: list[dict]
    recommendation: dict
    table: list[dict]


def plan_node(state: Dict[str, Any]) -> Dict[str, Any]:
    client = redis_client.get_client()
    run_id = state.get("run_id", "")
    llm = get_chat_model()
    parser = JsonOutputParser(pydantic_object=PlanOutput)
    prompt_delta = state.get("prompt_delta") or {}
    prompt = PromptTemplate(
        template=PLANNER_PROMPT,
        input_variables=["goal", "query", "prompt_delta"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    message = prompt.format(
        goal=state["goal"],
        query=state["query"],
        prompt_delta=json.dumps(prompt_delta) if prompt_delta else "none"
    )
    response = llm.invoke(message)
    content = response.content if hasattr(response, "content") else str(response)
    plan = parser.parse(content)
    plan_dict = plan if isinstance(plan, dict) else plan.model_dump()
    
    trace = state.get("trace", [])
    trace.append({"type": "plan", "payload": plan_dict})
    if run_id:
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "plan_created", "payload": {"status": "completed"}})
        )
        client.expire(f"run:{run_id}:events", 86400)
    return {"plan": plan_dict, "trace": trace}


def browse_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    client = redis_client.get_client()
    run_id = state.get("run_id", "")
    policy = state.get("policy") or {}
    limit = int(policy.get("max_tabs", state.get("limit", 5)))
    min_score = float(policy.get("min_score", 0.0))
    unique_domains = int(policy.get("unique_domains", 1))
    plan = state.get("plan") or {}
    search_queries = plan.get("search_queries") or []
    query = search_queries[0] if search_queries else state.get("query", "")
    tab_id = state.get("tab_id", "")
    
    if not query:
        trace.append({"type": "browse", "payload": {"status": "skipped", "reason": "no_query"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "search_skipped", "payload": {"reason": "no_query"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "candidate_links": []}
    
    client = redis_client.get_client()
    session_key = f"tab:{tab_id}:browserbase_session"
    session_id = client.get(session_key)
    connect_url = None
    live_view_url = None
    
    if not browserbase_client.api_key or not browserbase_client.project_id:
        trace.append({"type": "browse", "payload": {"status": "error", "error": "missing_browserbase_config"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "search_error", "payload": {"error": "missing_browserbase_config"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "candidate_links": []}
    
    if not session_id:
        session_result = browserbase_client.create_session(tab_id or "agent")
        if session_result.get("ok"):
            session_id = session_result.get("session_id")
            session_data = session_result.get("data", {}) or {}
            connect_url = session_data.get("connectUrl")
            live_view_url = session_data.get("liveViewUrl") or session_data.get("live_view_url")
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
            session_data = session_info.get("session", {}) or {}
            connect_url = session_data.get("connectUrl")
            live_view_url = session_data.get("liveViewUrl") or session_data.get("live_view_url")
        if not connect_url:
            session_result = browserbase_client.create_session(tab_id or "agent")
            if session_result.get("ok"):
                session_id = session_result.get("session_id")
                session_data = session_result.get("data", {}) or {}
                connect_url = session_data.get("connectUrl")
                live_view_url = session_data.get("liveViewUrl") or session_data.get("live_view_url")
                if session_id:
                    client.setex(session_key, 86400, session_id)
            else:
                trace.append({
                    "type": "browse",
                    "payload": {"status": "error", "error": session_result.get("error")}
                })
                return {"trace": trace, "candidate_links": []}
    
    if not connect_url:
        trace.append({"type": "browse", "payload": {"status": "error", "error": "missing_connect_url"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "search_error", "payload": {"error": "missing_connect_url"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "candidate_links": []}
    
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    candidates: list[dict] = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(connect_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            if run_id:
                client.rpush(
                    f"run:{run_id}:events",
                    json.dumps({"type": "search_started", "payload": {"query": query}})
                )
                client.expire(f"run:{run_id}:events", 86400)
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
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "search_error", "payload": {"error": str(e)}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "candidate_links": []}
    
    trace.append({
        "type": "browse",
        "payload": {
            "status": "completed",
            "query": query,
            "count": len(candidates)
        }
    })
    if run_id:
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "search_results_found", "payload": {"count": len(candidates)}})
        )
        client.expire(f"run:{run_id}:events", 86400)
    return {
        "trace": trace,
        "candidate_links": candidates,
        "browserbase_session_id": session_id,
        "connect_url": connect_url,
        "live_view_url": live_view_url
    }


def extract_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    client = redis_client.get_client()
    run_id = state.get("run_id", "")
    if state.get("status") == "paused":
        trace.append({"type": "extract", "payload": {"status": "skipped", "reason": "paused"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "extract_skipped", "payload": {"reason": "paused"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "extracted_items": []}
    plan = state.get("plan") or {}
    fields = plan.get("extraction_fields") or []
    candidates = state.get("candidate_links") or []
    connect_url = state.get("connect_url")
    live_view_url = state.get("live_view_url")
    policy = state.get("policy") or {}
    limit = min(len(candidates), int(policy.get("max_tabs", state.get("limit", 5))))
    
    if not connect_url or not candidates:
        trace.append({"type": "extract", "payload": {"status": "skipped", "reason": "no_links"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "extract_skipped", "payload": {"reason": "no_links"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "extracted_items": []}
    
    llm = get_chat_model()
    parser = JsonOutputParser(pydantic_object=ExtractOutput)
    prompt = PromptTemplate(
        template=EXTRACTOR_PROMPT,
        input_variables=["fields", "url", "title", "content"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    
    extracted_items: list[dict] = []
    
    def _ensure_session():
        nonlocal connect_url, live_view_url
        if connect_url:
            return True
        session_result = browserbase_client.create_session(state.get("tab_id") or "agent")
        if session_result.get("ok"):
            session_data = session_result.get("data", {}) or {}
            connect_url = session_data.get("connectUrl")
            live_view_url = session_data.get("liveViewUrl") or session_data.get("live_view_url")
            return True
        return False
    
    if not _ensure_session():
        trace.append({"type": "extract", "payload": {"status": "error", "error": "missing_connect_url"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "extract_error", "payload": {"error": "missing_connect_url"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "extracted_items": [], "connect_url": connect_url, "live_view_url": live_view_url}
    
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(connect_url)
            except Exception:
                # Session may have expired; create a fresh one and retry once
                connect_url = None
                if not _ensure_session():
                    raise
                browser = p.chromium.connect_over_cdp(connect_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            
            for item in candidates[:limit]:
                url = item.get("url", "")
                if not url:
                    continue
                try:
                    if run_id:
                        client.rpush(
                            f"run:{run_id}:events",
                            json.dumps({"type": "extract_started", "payload": {"url": url}})
                        )
                        client.expire(f"run:{run_id}:events", 86400)
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
                    if run_id:
                        client.rpush(
                            f"run:{run_id}:events",
                            json.dumps({"type": "extract_completed", "payload": {"url": url}})
                        )
                        client.expire(f"run:{run_id}:events", 86400)
                except Exception as e:
                    trace.append({"type": "extract:item_error", "payload": {"url": url, "error": str(e)}})
                    if run_id:
                        client.rpush(
                            f"run:{run_id}:events",
                            json.dumps({"type": "extract:item_error", "payload": {"url": url, "error": str(e)}})
                        )
                        client.expire(f"run:{run_id}:events", 86400)
            
            browser.close()
    except Exception as e:
        trace.append({"type": "extract", "payload": {"status": "error", "error": str(e)}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "extract_error", "payload": {"error": str(e)}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "extracted_items": [], "connect_url": connect_url, "live_view_url": live_view_url}
    
    trace.append({
        "type": "extract",
        "payload": {"status": "completed", "count": len(extracted_items)}
    })
    if run_id:
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "extract_summary", "payload": {"count": len(extracted_items)}})
        )
        client.expire(f"run:{run_id}:events", 86400)
    return {"trace": trace, "extracted_items": extracted_items, "connect_url": connect_url, "live_view_url": live_view_url}


def score_links_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    client = redis_client.get_client()
    run_id = state.get("run_id", "")
    plan = state.get("plan") or {}
    candidates = state.get("candidate_links") or []
    required_sources = plan.get("required_sources") or []
    query = state.get("query", "")
    goal = state.get("goal", "")
    policy = state.get("policy") or {}
    limit = int(policy.get("max_tabs", state.get("limit", 5)))
    min_score = float(policy.get("min_score", 0.0))
    unique_domains = int(policy.get("unique_domains", 1))
    
    if not candidates:
        trace.append({"type": "score_links", "payload": {"status": "skipped", "reason": "no_candidates"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "score_links", "payload": {"status": "skipped", "reason": "no_candidates"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"trace": trace, "candidate_links": []}
    
    llm = get_chat_model()
    parser = JsonOutputParser(pydantic_object=LinkScoreOutput)
    prompt = PromptTemplate(
        template=LINK_SCORER_PROMPT,
        input_variables=["goal", "query", "required_sources", "items"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    items = "\n".join(
        [f"- {c.get('title','')}: {c.get('url','')}" for c in candidates]
    )
    message = prompt.format(
        goal=goal,
        query=query,
        required_sources=", ".join(required_sources),
        items=items
    )
    response = llm.invoke(message)
    text = response.content if hasattr(response, "content") else str(response)
    scored = parser.parse(text)
    scored_list = scored.get("scored", []) if isinstance(scored, dict) else scored.model_dump().get("scored", [])
    
    scored_list = [
        {
            "url": item.get("url"),
            "title": item.get("title"),
            "score": float(item.get("score", 0)),
            "reason": item.get("reason", "")
        }
        for item in scored_list
        if item.get("url")
    ]
    min_score = float(policy.get("min_score", 0.0))
    scored_list = [s for s in scored_list if s.get("score", 0) >= min_score]
    scored_list.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    selected = []
    domain_counts = {}
    for item in scored_list:
        domain = urlparse(item.get("url", "")).netloc
        count = domain_counts.get(domain, 0)
        if count >= unique_domains:
            continue
        domain_counts[domain] = count + 1
        selected.append(item)
        if len(selected) >= limit:
            break
    skipped = [s for s in scored_list if s not in selected][:5]
    
    trace.append({"type": "score_links", "payload": {"status": "completed", "count": len(selected)}})
    if run_id:
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "score_links", "payload": {"status": "completed", "count": len(selected)}})
        )
        for item in selected:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "open", "payload": item})
            )
        for item in skipped:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "skip", "payload": item})
            )
        client.expire(f"run:{run_id}:events", 86400)
    
    return {"trace": trace, "candidate_links": selected}


def guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    client = redis_client.get_client()
    run_id = state.get("run_id", "")
    policy = state.get("policy") or {}
    started_at_ms = state.get("started_at_ms") or 0
    max_time_ms = int(policy.get("max_time_ms", 120000))
    candidates = state.get("candidate_links") or []
    required_sources = (state.get("plan") or {}).get("required_sources") or []
    now_ms = int(datetime.now().timestamp() * 1000)
    
    if started_at_ms and now_ms - started_at_ms > max_time_ms:
        reason = "time_limit_exceeded"
        trace.append({"type": "guardrail", "payload": {"status": "paused", "reason": reason}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "pause", "payload": {"reason": reason}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"status": "paused", "status_reason": reason, "trace": trace, "candidate_links": []}
    
    if not candidates:
        reason = "no_candidates"
        trace.append({"type": "guardrail", "payload": {"status": "paused", "reason": reason}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "pause", "payload": {"reason": reason}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"status": "paused", "status_reason": reason, "trace": trace, "candidate_links": []}
    
    if required_sources and len(candidates) < len(required_sources):
        reason = "missing_required_sources"
        trace.append({"type": "guardrail", "payload": {"status": "paused", "reason": reason}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "pause", "payload": {"reason": reason}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"status": "paused", "status_reason": reason, "trace": trace, "candidate_links": []}
    
    trace.append({"type": "guardrail", "payload": {"status": "ok"}})
    if run_id:
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "guardrail_ok", "payload": {}})
        )
        client.expire(f"run:{run_id}:events", 86400)
    return {"trace": trace}


def summarize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    trace = state.get("trace", [])
    client = redis_client.get_client()
    run_id = state.get("run_id", "")
    if state.get("status") == "paused":
        trace.append({"type": "summarize", "payload": {"status": "skipped", "reason": "paused"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "summary_skipped", "payload": {"reason": "paused"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"status": "paused", "status_reason": state.get("status_reason"), "trace": trace, "summary": {}}
    extracted_items = state.get("extracted_items") or []
    goal = state.get("goal", "")
    
    trace.append({"type": "summarize", "payload": {"status": "pending"}})
    if run_id:
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "summary_started", "payload": {"status": "pending"}})
        )
        client.expire(f"run:{run_id}:events", 86400)
    
    if not extracted_items:
        trace.append({"type": "summarize", "payload": {"status": "skipped", "reason": "no_extracted"}})
        if run_id:
            client.rpush(
                f"run:{run_id}:events",
                json.dumps({"type": "summary_skipped", "payload": {"reason": "no_extracted"}})
            )
            client.expire(f"run:{run_id}:events", 86400)
        return {"status": "completed", "trace": trace, "summary": {}}
    
    llm = get_chat_model()
    parser = JsonOutputParser(pydantic_object=SummaryOutput)
    prompt = PromptTemplate(
        template=SUMMARY_PROMPT,
        input_variables=["goal", "items"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    items_payload = json.dumps(extracted_items)[:12000]
    message = prompt.format(goal=goal, items=items_payload)
    response = llm.invoke(message)
    text = response.content if hasattr(response, "content") else str(response)
    summary = parser.parse(text)
    summary_dict = summary if isinstance(summary, dict) else summary.model_dump()
    
    trace.append({"type": "summarize", "payload": {"status": "completed"}})
    if run_id:
        client.rpush(
            f"run:{run_id}:events",
            json.dumps({"type": "summary_created", "payload": {"status": "completed"}})
        )
        client.expire(f"run:{run_id}:events", 86400)
    return {"status": "completed", "trace": trace, "summary": summary_dict}
