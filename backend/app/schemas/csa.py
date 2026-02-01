"""
Story 18.1: Conversation Snapshot Artifact Schema

Strict, versioned schema for conversation handoff artifacts.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any


class ConversationSnapshotArtifact(BaseModel):
    """
    CSA: A complete snapshot of a conversation for handoff to new model/session.
    
    This artifact captures:
    - User intent and goals
    - What was accomplished
    - What worked/failed
    - Learned preferences and constraints
    - Key entities (companies, roles, documents)
    - Artifacts produced (resumes, code, etc.)
    - Next steps and instructions for the next model
    
    Version 1 schema (strict).
    """
    
    # Identity
    csa_id: str = Field(..., description="Unique CSA identifier (uuid4)")
    schema_version: int = Field(default=1, description="Schema version (currently 1)")
    
    # Source tracking
    user_id: str = Field(..., description="User identifier")
    created_ts_ms: int = Field(..., description="Creation timestamp in milliseconds")
    source_provider: str = Field(..., description="Source provider (chatgpt/claude/gemini)")
    source_session_id: str = Field(..., description="Source session identifier")
    
    # High-level conversation summary
    title: str = Field(..., description="Brief title summarizing the conversation")
    user_intent: str = Field(..., description="What the user was trying to accomplish")
    
    # Outcomes
    what_we_did: List[str] = Field(..., description="List of actions/steps taken")
    what_worked: List[str] = Field(..., description="Successful approaches and solutions")
    what_failed: List[str] = Field(..., description="High-level failures (no raw content)")
    
    # Context
    constraints: List[str] = Field(..., description="User constraints (time, budget, requirements)")
    preferences: List[str] = Field(..., description="User preferences and style choices")
    key_entities: Dict[str, Any] = Field(..., description="Important entities (companies, roles, docs, links)")
    
    # Artifacts produced
    artifacts: List[Dict[str, Any]] = Field(..., description="Pointers to resumes, code, documents created")
    
    # Future guidance
    next_steps: List[str] = Field(..., description="Recommended next actions")
    instructions_for_next_model: List[str] = Field(..., description="Instructions for the model taking over")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "csa_id": "abc123-def456-ghi789",
                "schema_version": 1,
                "user_id": "user_123",
                "created_ts_ms": 1706774400000,
                "source_provider": "chatgpt",
                "source_session_id": "session_456",
                "title": "Software Engineer Resume Development",
                "user_intent": "Create a professional resume for senior software engineer positions",
                "what_we_did": [
                    "Analyzed user's 5 years of experience at Google and Startup X",
                    "Created 3 resume variants (technical, leadership, startup-focused)",
                    "Optimized for ATS parsing and human readability"
                ],
                "what_worked": [
                    "Quantified achievements with metrics increased engagement",
                    "Technical skills section organized by category",
                    "Action verb starters for each bullet point"
                ],
                "what_failed": [
                    "First draft was too verbose (rejected)",
                    "Initial skills section lacked categorization"
                ],
                "constraints": [
                    "Resume must be 1 page",
                    "Must highlight Python and distributed systems",
                    "Target: Senior IC roles at FAANG companies"
                ],
                "preferences": [
                    "Clean, minimal design",
                    "No photo or personal details",
                    "Chronological format preferred"
                ],
                "key_entities": {
                    "companies": ["Google", "Startup X", "Microsoft (target)"],
                    "role": "Senior Software Engineer",
                    "technologies": ["Python", "Go", "Kubernetes", "PostgreSQL"],
                    "documents": ["resume_v3_final.pdf", "cover_letter_template.txt"]
                },
                "artifacts": [
                    {
                        "type": "resume",
                        "name": "resume_v3_technical.pdf",
                        "description": "Technical-focused variant for FAANG applications",
                        "quality_score": 0.92
                    },
                    {
                        "type": "resume",
                        "name": "resume_v3_leadership.pdf",
                        "description": "Leadership-focused variant for management track",
                        "quality_score": 0.88
                    }
                ],
                "next_steps": [
                    "Tailor resume for specific job postings",
                    "Prepare behavioral interview responses based on resume bullets",
                    "Update LinkedIn profile to match resume"
                ],
                "instructions_for_next_model": [
                    "User prefers direct, actionable feedback",
                    "Always show before/after when editing resume content",
                    "Use the technical variant (resume_v3_technical.pdf) as the base for future edits",
                    "User is targeting Staff Engineer roles, emphasize system design experience"
                ]
            }
        }
    )
