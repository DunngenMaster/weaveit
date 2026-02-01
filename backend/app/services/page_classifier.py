from urllib.parse import urlparse
from typing import Literal


PageType = Literal["ai_chat", "job_posting", "other"]


def classify_page(url: str, title: str | None = None) -> PageType:
    """
    Classify page type based on URL and title using deterministic rules.
    
    Args:
        url: Full URL of the page
        title: Optional page title (not used in current implementation)
    
    Returns:
        One of: "ai_chat", "job_posting", "other"
    """
    
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc
        path = parsed.path
        full_url = url.lower()
        
        # AI Chat platforms
        if "chat.openai.com" in domain or "chatgpt.com" in domain:
            return "ai_chat"
        
        if "claude.ai" in domain:
            return "ai_chat"
        
        if "gemini.google.com" in domain:
            return "ai_chat"
        
        # Job posting sites
        if "linkedin.com/jobs" in full_url:
            return "job_posting"
        
        if "greenhouse.io" in domain or "lever.co" in domain:
            return "job_posting"
        
        # Default
        return "other"
    
    except Exception:
        return "other"
