import httpx
from typing import Dict, Any
from app.core.config import get_settings


class BrowserbaseClient:
    """Client for Browserbase API using direct HTTP calls"""
    
    def __init__(self):
        self.settings = get_settings()
        self.api_key = getattr(self.settings, 'browserbase_api_key', '')
        self.base_url = "https://api.browserbase.com/v1"
    
    def _get_headers(self) -> dict:
        """Get request headers with API key"""
        return {
            "x-bb-api-key": self.api_key,
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
                    json={"metadata": {"user_id": user_id}}
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
    
    def run_extraction(self, session_id: str, url: str, extract_type: str) -> dict:
        """
        Run scripted extraction on a URL.
        
        Args:
            session_id: Browserbase session ID
            url: URL to extract from
            extract_type: Type of extraction (job_posting, ai_chat_turn, etc.)
        
        Returns:
            dict: {"ok": True, "data": dict} on success
                  {"ok": False, "error": str, "status_code": int} on failure
        """
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/sessions/{session_id}/extract",
                    headers=self._get_headers(),
                    json={
                        "url": url,
                        "extract_type": extract_type
                    }
                )
                
                if response.status_code != 200:
                    return self._error_response(
                        f"Extraction failed: {response.text}",
                        response.status_code
                    )
                
                data = response.json()
                return {
                    "ok": True,
                    "data": data
                }
        
        except httpx.TimeoutException:
            return self._error_response("Extraction timeout", None)
        except httpx.RequestError as e:
            return self._error_response(f"Network error: {str(e)}", None)
        except Exception as e:
            return self._error_response(f"Unexpected error: {str(e)}", None)


# Global instance
browserbase_client = BrowserbaseClient()
