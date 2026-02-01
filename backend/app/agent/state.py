from typing import TypedDict, Optional, List, Dict, Any


class AgentState(TypedDict):
    run_id: str
    goal: str
    query: str
    limit: int
    tab_id: str
    url: Optional[str]
    status: str
    plan: Optional[Dict[str, Any]]
    browserbase_session_id: Optional[str]
    connect_url: Optional[str]
    candidate_links: List[Dict[str, Any]]
    extracted_items: List[Dict[str, Any]]
    trace: List[Dict[str, Any]]
