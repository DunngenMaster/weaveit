import httpx
from typing import Dict, Any
from datetime import datetime
from app.core.config import get_settings


class BrowserbaseClient:
    """Client for Browserbase API using direct HTTP calls"""
    
    def __init__(self):
        self.settings = get_settings()
        self.api_key = getattr(self.settings, 'browserbase_api_key', '')
        self.project_id = getattr(self.settings, 'browserbase_project_id', '')
        self.base_url = "https://api.browserbase.com/v1"
    
    def _get_headers(self) -> dict:
        """Get request headers with API key"""
        return {
            "X-BB-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def _error_response(self, error: str, status_code: int = None) -> dict:
        """Create standardized error response"""
        return {
            "ok": False,
            "error": error,
            "status_code": status_code
        }
    
    def create_session(self, user_id: str) -> dict:
        """
        Create a new Browserbase session.
        
        Returns:
            dict: {"ok": True, "session_id": str} on success
                  {"ok": False, "error": str, "status_code": int} on failure
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/sessions",
                    headers=self._get_headers(),
                    json={
                        "projectId": self.project_id,
                        "userMetadata": {"user_id": user_id}
                    }
                )
                
                if response.status_code != 200 and response.status_code != 201:
                    return self._error_response(
                        f"Failed to create session: {response.text}",
                        response.status_code
                    )
                
                data = response.json()
                return {
                    "ok": True,
                    "session_id": data.get("id"),
                    "data": data
                }
        
        except httpx.TimeoutException:
            return self._error_response("Request timeout", None)
        except httpx.RequestError as e:
            return self._error_response(f"Network error: {str(e)}", None)
        except Exception as e:
            return self._error_response(f"Unexpected error: {str(e)}", None)
    
    def get_session(self, session_id: str) -> dict:
        """
        Get session details.
        
        Returns:
            dict: {"ok": True, "session": dict} on success
                  {"ok": False, "error": str, "status_code": int} on failure
        """
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.base_url}/sessions/{session_id}",
                    headers=self._get_headers()
                )
                
                if response.status_code != 200:
                    return self._error_response(
                        f"Failed to get session: {response.text}",
                        response.status_code
                    )
                
                data = response.json()
                return {
                    "ok": True,
                    "session": data
                }
        
        except httpx.TimeoutException:
            return self._error_response("Request timeout", None)
        except httpx.RequestError as e:
            return self._error_response(f"Network error: {str(e)}", None)
        except Exception as e:
            return self._error_response(f"Unexpected error: {str(e)}", None)
    
    def run_extraction_sync(self, user_id: str, url: str, extract_type: str) -> dict:
        """
        Run scripted extraction using synchronous Playwright (workaround for Python 3.13 Windows).
        
        Args:
            user_id: User identifier (for session creation)
            url: URL to extract from
            extract_type: Type of extraction (job_posting, ai_chat_turn, etc.)
        
        Returns:
            dict: {"ok": True, "data": dict, "session_id": str} on success
                  {"ok": False, "error": str, "status_code": int} on failure
        """
        from playwright.sync_api import sync_playwright
        
        try:
            print(f"[DEBUG] Starting extraction for user_id={user_id}, url={url}")
            
            # Create a new session to get fresh connect URL
            session_result = self.create_session(user_id)
            print(f"[DEBUG] Session creation result: ok={session_result.get('ok')}")
            
            if not session_result.get("ok"):
                return self._error_response(
                    f"Failed to create session: {session_result.get('error')}",
                    session_result.get("status_code")
                )
            
            session_id = session_result.get("session_id")
            connect_url = session_result.get("data", {}).get("connectUrl")
            print(f"[DEBUG] Session ID: {session_id}, Connect URL: {connect_url[:50] if connect_url else None}...")
            
            if not connect_url:
                return self._error_response("Session connect URL not found in creation response", None)
            
            print(f"[DEBUG] Connecting to Browserbase via CDP (sync)...")
            # Connect to Browserbase session via Playwright (sync)
            with sync_playwright() as p:
                print(f"[DEBUG] Playwright started, connecting to browser...")
                browser = p.chromium.connect_over_cdp(connect_url)
                print(f"[DEBUG] Browser connected, getting contexts...")
                
                # Get the default context and page
                contexts = browser.contexts
                print(f"[DEBUG] Found {len(contexts)} contexts")
                if not contexts:
                    return self._error_response("No browser context available", None)
                
                context = contexts[0]
                pages = context.pages
                print(f"[DEBUG] Found {len(pages)} pages in context")
                
                # Create new page if none exists
                if not pages:
                    print(f"[DEBUG] Creating new page...")
                    page = context.new_page()
                else:
                    page = pages[0]
                
                print(f"[DEBUG] Navigating to {url}...")
                # Navigate to URL
                page.goto(url, wait_until="networkidle", timeout=30000)
                print(f"[DEBUG] Page loaded, extracting data...")
                
                # Extract based on type
                if extract_type == "job_posting":
                    data = self._extract_job_posting_sync(page)
                    print(f"[DEBUG] Extraction complete: {list(data.keys())}")
                else:
                    data = {"error": f"Unknown extract_type: {extract_type}"}
                
                print(f"[DEBUG] Closing browser...")
                browser.close()
                print(f"[DEBUG] Extraction successful!")
                
                return {
                    "ok": True,
                    "data": data,
                    "session_id": session_id
                }
        
        except Exception as e:
            import traceback
            error_details = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            print(f"Extraction exception:\n{error_details}")
            return self._error_response(error_details, None)
    
    def _extract_job_posting_sync(self, page) -> dict:
        """
        Extract job posting data from the page (synchronous version).
        
        Args:
            page: Playwright page object (sync)
        
        Returns:
            dict: Extracted job data with title, company, description, etc.
        """
        try:
            # Wait for page to be fully loaded
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)  # Give JS time to render
            
            print(f"[DEBUG] Extracting from URL: {page.url}")
            
            # Try multiple selectors for title
            title = ""
            title_selectors = [
                "h1",
                ".job-title",
                "[class*='job-details-jobs-unified-top-card__job-title']",
                "[class*='jobs-unified-top-card__job-title']",
                "[class*='t-24']",
                ".jobs-details__main-content h1"
            ]
            for selector in title_selectors:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    title = elem.text_content(timeout=2000) or ""
                    if title.strip():
                        print(f"[DEBUG] Found title with selector: {selector}")
                        break
            
            # Try multiple selectors for company
            company = ""
            company_selectors = [
                "[class*='job-details-jobs-unified-top-card__company-name']",
                "[class*='jobs-unified-top-card__company-name']",
                ".company-name",
                "[class*='t-black']",
                "a.ember-view"
            ]
            for selector in company_selectors:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    company = elem.text_content(timeout=2000) or ""
                    if company.strip():
                        print(f"[DEBUG] Found company with selector: {selector}")
                        break
            
            # Try multiple selectors for description
            description = ""
            description_selectors = [
                "[class*='jobs-description']",
                "[class*='job-description']",
                ".description",
                "[class*='jobs-box__html-content']",
                "article",
                "[id*='job-details']"
            ]
            for selector in description_selectors:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    description = elem.text_content(timeout=2000) or ""
                    if description.strip():
                        print(f"[DEBUG] Found description with selector: {selector} ({len(description)} chars)")
                        break
            
            # Try multiple selectors for location
            location = ""
            location_selectors = [
                "[class*='job-details-jobs-unified-top-card__bullet']",
                "[class*='jobs-unified-top-card__bullet']",
                ".location",
                "[class*='t-black--light']",
                "span.jobs-unified-top-card__subtitle-primary-grouping"
            ]
            for selector in location_selectors:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    location = elem.text_content(timeout=2000) or ""
                    if location.strip() and "·" not in location:  # Skip separator bullets
                        print(f"[DEBUG] Found location with selector: {selector}")
                        break
            
            # Get page URL
            current_url = page.url
            
            print(f"[DEBUG] Extracted - Title: {bool(title)}, Company: {bool(company)}, Desc: {len(description)} chars, Location: {bool(location)}")
            
            return {
                "title": title.strip(),
                "company": company.strip(),
                "description": description.strip()[:5000],  # Limit to 5000 chars
                "location": location.strip(),
                "url": current_url,
                "extracted_at": int(datetime.now().timestamp() * 1000)
            }
        
        except Exception as e:
            import traceback
            error_msg = f"Extraction failed: {str(e)}\n{traceback.format_exc()}"
            print(f"[ERROR] {error_msg}")
            return {
                "title": "",
                "company": "",
                "description": error_msg,
                "location": "",
                "url": page.url,
                "extracted_at": int(datetime.now().timestamp() * 1000)
            }

    async def run_extraction(self, user_id: str, url: str, extract_type: str) -> dict:
        """
        Async wrapper for run_extraction_sync (workaround for Python 3.13 Windows asyncio issue).
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        # Run sync Playwright in a thread pool to avoid blocking the async event loop
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(
                executor,
                self.run_extraction_sync,
                user_id,
                url,
                extract_type
            )
        return result


# Global instance
browserbase_client = BrowserbaseClient()
