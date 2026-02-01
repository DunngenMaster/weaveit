"""
Sprint 17.7 & 17.8: Browserbase Session Manager with Session Reuse + Extraction Reliability

Session Pool:
- Reuse browser sessions per user (TTL 15-30 min)
- Store browser_session_id in Redis user:{id}:browser_session
- Close on error/timeout

Extraction Reliability Ladder (3-tier):
1. Primary: DOM selectors extraction (fast)
2. Fallback: Text snapshot + regex/heuristics (medium)
3. Final fallback: Screenshot-to-text (if available, otherwise skip)

Retry up to 2 times with exponential backoff.
On failure, emit PAGE_EXTRACT_FAILED to stream + DLQ.
"""

import json
import time
import re
from typing import Dict, Any, Optional
from datetime import datetime
from playwright.sync_api import sync_playwright, Page
from app.services.redis_client import redis_client
from app.services.browserbase_client import browserbase_client
from app.core.config import get_settings


class BrowserSessionManager:
    """
    Manages browser sessions with reuse and robust extraction.
    
    Sprint 17.7: Session reuse (15-30 min TTL)
    Sprint 17.8: 3-tier extraction with retries + error emission to stream
    """
    
    def __init__(self, session_ttl: int = 1800):  # 30 minutes
        self.client = redis_client.client
        self.session_ttl = session_ttl
        self.max_retries = 2
        self.settings = get_settings()
    
    def get_or_create_session(self, user_id: str) -> tuple[Optional[str], Optional[str], bool]:
        """
        Get existing browser session or create new one.
        
        Args:
            user_id: User identifier
            
        Returns:
            (session_id, connect_url, is_new) or (None, None, False) on error
        """
        session_key = f"user:{user_id}:browser_session"
        
        # Try to get existing session
        cached = self.client.get(session_key)
        if cached:
            try:
                if isinstance(cached, bytes):
                    cached = cached.decode()
                session_data = json.loads(cached)
                session_id = session_data.get('session_id')
                connect_url = session_data.get('connect_url')
                
                # Validate session is still active
                session_result = browserbase_client.get_session(session_id)
                if session_result.get('ok'):
                    print(f"[SESSION] Reusing session {session_id[:8]}... for user {user_id[:8]}...")
                    return session_id, connect_url, False
                else:
                    print(f"[SESSION] Cached session {session_id[:8]}... is invalid, creating new one")
            except Exception as e:
                print(f"[SESSION] Error loading cached session: {e}")
        
        # Create new session
        try:
            session_result = browserbase_client.create_session(user_id)
            if not session_result.get('ok'):
                print(f"[SESSION] Failed to create session: {session_result.get('error')}")
                return None, None, False
            
            session_id = session_result.get('session_id')
            connect_url = session_result.get('data', {}).get('connectUrl')
            
            if not connect_url:
                print(f"[SESSION] No connect URL in session response")
                return None, None, False
            
            # Store in Redis with TTL
            session_data = {
                'session_id': session_id,
                'connect_url': connect_url,
                'created_at': datetime.now().isoformat()
            }
            self.client.setex(session_key, self.session_ttl, json.dumps(session_data))
            
            print(f"[SESSION] Created new session {session_id[:8]}... for user {user_id[:8]}...")
            return session_id, connect_url, True
            
        except Exception as e:
            print(f"[SESSION] Error creating session: {e}")
            return None, None, False
    
    def close_session(self, user_id: str):
        """Close and remove cached browser session"""
        session_key = f"user:{user_id}:browser_session"
        self.client.delete(session_key)
        print(f"[SESSION] Closed session for user {user_id[:8]}...")
    
    def extract_with_retries(
        self,
        user_id: str,
        url: str,
        extract_type: str = "job_posting"
    ) -> Dict[str, Any]:
        """
        Extract data from URL with 3-tier fallback + retries.
        
        Args:
            user_id: User identifier
            url: URL to extract from
            extract_type: Type of extraction
            
        Returns:
            dict: Extracted data or error info
        """
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                # Exponential backoff: 1s, 2s, 4s...
                wait_time = 2 ** (attempt - 1)
                print(f"[EXTRACT] Retry {attempt}/{self.max_retries} after {wait_time}s...")
                time.sleep(wait_time)
                
                # Clear session to force fresh connection on retry
                self.close_session(user_id)
            
            try:
                # Get or create session
                session_id, connect_url, is_new = self.get_or_create_session(user_id)
                if not session_id or not connect_url:
                    last_error = "Failed to get browser session"
                    continue
                
                # Run extraction with 3-tier ladder
                result = self._extract_with_ladder(connect_url, url, extract_type)
                
                if result.get('ok'):
                    result['session_id'] = session_id
                    return result
                else:
                    last_error = result.get('error', 'Unknown extraction error')
                    
            except Exception as e:
                last_error = str(e)
                print(f"[EXTRACT] Error on attempt {attempt + 1}: {last_error}")
        
        # All retries failed, emit error event
        self._emit_extraction_failed(user_id, url, last_error)
        
        return {
            'ok': False,
            'error': f'Extraction failed after {self.max_retries + 1} attempts: {last_error}',
            'attempts': self.max_retries + 1
        }
    
    def _extract_with_ladder(
        self,
        connect_url: str,
        url: str,
        extract_type: str
    ) -> Dict[str, Any]:
        """
        3-tier extraction ladder:
        1. Primary: DOM selectors
        2. Fallback: Text snapshot + regex
        3. Final: Screenshot (skip for now)
        
        Args:
            connect_url: Browserbase CDP connect URL
            url: URL to extract
            extract_type: Type of extraction
            
        Returns:
            dict: {"ok": True, "data": dict, "method": str} or {"ok": False, "error": str}
        """
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(connect_url)
                contexts = browser.contexts
                
                if not contexts:
                    return {'ok': False, 'error': 'No browser context available'}
                
                context = contexts[0]
                pages = context.pages
                
                if not pages:
                    page = context.new_page()
                else:
                    page = pages[0]
                
                # Navigate to URL
                page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Tier 1: DOM selectors (primary)
                try:
                    if extract_type == "job_posting":
                        data = self._extract_job_dom(page)
                        
                        # Validate extraction quality
                        if data.get('title') and data.get('company'):
                            print(f"[EXTRACT] Tier 1 (DOM) success")
                            browser.close()
                            return {'ok': True, 'data': data, 'method': 'dom'}
                        else:
                            print(f"[EXTRACT] Tier 1 (DOM) incomplete, trying Tier 2...")
                except Exception as e:
                    print(f"[EXTRACT] Tier 1 (DOM) failed: {e}")
                
                # Tier 2: Text snapshot + regex
                try:
                    data = self._extract_job_text_heuristics(page)
                    
                    if data.get('title'):
                        print(f"[EXTRACT] Tier 2 (text heuristics) success")
                        browser.close()
                        return {'ok': True, 'data': data, 'method': 'heuristics'}
                    else:
                        print(f"[EXTRACT] Tier 2 (text heuristics) incomplete")
                except Exception as e:
                    print(f"[EXTRACT] Tier 2 (text heuristics) failed: {e}")
                
                # Tier 3: Screenshot-to-text (skip for now)
                # Could add multimodal LLM extraction here
                
                browser.close()
                return {'ok': False, 'error': 'All extraction tiers failed'}
                
            except Exception as e:
                return {'ok': False, 'error': f'Browser error: {str(e)}'}
    
    def _extract_job_dom(self, page: Page) -> Dict[str, Any]:
        """Tier 1: DOM selector extraction"""
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        
        # Title selectors
        title = ""
        for selector in ["h1", ".job-title", "[class*='job-title']", "[class*='t-24']"]:
            elem = page.locator(selector).first
            if elem.count() > 0:
                title = elem.text_content(timeout=2000) or ""
                if title.strip():
                    break
        
        # Company selectors
        company = ""
        for selector in [".company-name", "[class*='company-name']", "a.ember-view"]:
            elem = page.locator(selector).first
            if elem.count() > 0:
                company = elem.text_content(timeout=2000) or ""
                if company.strip():
                    break
        
        # Description selectors
        description = ""
        for selector in ["[class*='description']", "article", "[id*='job-details']"]:
            elem = page.locator(selector).first
            if elem.count() > 0:
                description = elem.text_content(timeout=2000) or ""
                if description.strip():
                    break
        
        # Location selectors
        location = ""
        for selector in [".location", "[class*='location']", "[class*='bullet']"]:
            elem = page.locator(selector).first
            if elem.count() > 0:
                location = elem.text_content(timeout=2000) or ""
                if location.strip() and "·" not in location:
                    break
        
        return {
            'title': title.strip(),
            'company': company.strip(),
            'description': description.strip()[:5000],
            'location': location.strip(),
            'url': page.url,
            'extracted_at': int(datetime.now().timestamp() * 1000)
        }
    
    def _extract_job_text_heuristics(self, page: Page) -> Dict[str, Any]:
        """Tier 2: Text snapshot with regex/heuristics"""
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        
        # Get full page text
        body_text = page.locator("body").text_content() or ""
        
        # Extract title (usually first h1 or large text at top)
        title = ""
        title_match = re.search(r'^([A-Z][A-Za-z\s&-]{10,100})', body_text[:500])
        if title_match:
            title = title_match.group(1).strip()
        
        # Extract company (look for "at Company" or "Company Inc")
        company = ""
        company_patterns = [
            r'at\s+([A-Z][A-Za-z0-9\s&,.-]{3,50}?)(?:\s|$)',
            r'([A-Z][A-Za-z0-9\s&,.]{3,50}?(?:Inc|LLC|Ltd|Corp))',
        ]
        for pattern in company_patterns:
            match = re.search(pattern, body_text[:1000])
            if match:
                company = match.group(1).strip()
                break
        
        # Extract description (first substantial paragraph)
        description = ""
        paragraphs = re.findall(r'([A-Z][^.!?]{100,}[.!?])', body_text)
        if paragraphs:
            description = paragraphs[0][:5000]
        
        # Extract location (city, state patterns)
        location = ""
        location_patterns = [
            r'([A-Z][a-z]+,\s*[A-Z]{2})',  # City, ST
            r'([A-Z][a-z]+\s+[A-Z][a-z]+,\s*[A-Z]{2})',  # City Name, ST
        ]
        for pattern in location_patterns:
            match = re.search(pattern, body_text[:1000])
            if match:
                location = match.group(1).strip()
                break
        
        return {
            'title': title,
            'company': company,
            'description': description,
            'location': location,
            'url': page.url,
            'extracted_at': int(datetime.now().timestamp() * 1000)
        }
    
    def _emit_extraction_failed(self, user_id: str, url: str, error_msg: str):
        """
        Emit PAGE_EXTRACT_FAILED event to stream + DLQ.
        
        Args:
            user_id: User identifier
            url: Failed URL
            error_msg: Error message
        """
        try:
            event_data = {
                'event_type': 'PAGE_EXTRACT_FAILED',
                'user_id': user_id,
                'url': url,
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            }
            
            # Write to stream
            stream_key = f"stream:events:{user_id}"
            self.client.xadd(stream_key, {'payload': json.dumps(event_data)}, maxlen=1000)
            
            # Write to DLQ
            dlq_key = f"stream:dlq:{user_id}"
            self.client.xadd(dlq_key, event_data, maxlen=500)
            
            print(f"[EXTRACT_FAILED] Emitted error to stream+DLQ for URL: {url[:50]}...")
            
        except Exception as e:
            print(f"[EXTRACT_FAILED] Error emitting failure event: {e}")


# Global instance
browser_session_manager = BrowserSessionManager(session_ttl=1800)  # 30 min
