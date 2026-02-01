from typing import Dict, List, Tuple
from app.models import RunRequest
from app.services.weave_stub import weave_op


@weave_op()
def build_playbook(payload: RunRequest, preferences: Dict[str, str]) -> Tuple[List[str], List[str]]:
    steps = [
        "Open search engine",
        f"Search for '{payload.query}'",
        "Open top results",
        "Extract title, date posted, and key requirements",
        "Summarize and return top results",
    ]

    notes: List[str] = []

    if "filter" in preferences:
        steps.insert(2, f"Apply filter: {preferences['filter']}")
        notes.append(f"Used preference filter={preferences['filter']}")
    else:
        notes.append("PREF:filter:Remote")  # Demo learning signal

    return steps, notes
