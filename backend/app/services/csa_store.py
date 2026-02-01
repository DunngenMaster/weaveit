"""
Story 18.3: CSA Store - Materialize CSA as files

Stores CSA as:
- JSON file (machine-readable)
- Markdown file (human-readable)
- Redis metadata pointer

Storage options:
- Local disk (single server, hackathon)
- Redis bytes (distributed, small CSAs)
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from app.schemas.csa import ConversationSnapshotArtifact
from app.services.redis_client import redis_client


class CSAStore:
    """Stores and retrieves Conversation Snapshot Artifacts."""
    
    def __init__(self, storage_dir: str = "csa_files"):
        """
        Initialize CSA store.
        
        Args:
            storage_dir: Directory to store CSA files (default: csa_files/)
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.redis = redis_client
    
    def save_csa(
        self,
        csa: ConversationSnapshotArtifact,
        save_markdown: bool = True
    ) -> Dict[str, str]:
        """
        Save CSA to disk and Redis metadata.
        
        Args:
            csa: ConversationSnapshotArtifact to save
            save_markdown: Whether to also save markdown view
            
        Returns:
            Dict with file paths and metadata
        """
        # Generate filenames
        json_filename = f"csa_{csa.user_id}_{csa.created_ts_ms}.json"
        md_filename = f"csa_{csa.user_id}_{csa.created_ts_ms}.md"
        
        json_path = self.storage_dir / json_filename
        md_path = self.storage_dir / md_filename
        
        # 1. Save JSON file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(csa.model_dump(), f, indent=2, ensure_ascii=False)
        
        # 2. Save markdown view (optional)
        md_path_str = None
        if save_markdown:
            markdown = self._csa_to_markdown(csa)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown)
            md_path_str = str(md_path)
        
        # 3. Store in Redis as bytes (for distributed access, TTL 7 days)
        csa_bytes_key = f"csa_file:{csa.csa_id}"
        csa_json_bytes = json.dumps(csa.model_dump()).encode('utf-8')
        self.redis.client.setex(csa_bytes_key, 7 * 24 * 60 * 60, csa_json_bytes)
        
        # 4. Store metadata pointer in Redis
        metadata = {
            "csa_id": csa.csa_id,
            "filename": json_filename,
            "created_ts_ms": csa.created_ts_ms,
            "title": csa.title,
            "source_provider": csa.source_provider,
            "source_session_id": csa.source_session_id
        }
        
        latest_key = f"csa_latest:{csa.user_id}"
        self.redis.client.setex(latest_key, 7 * 24 * 60 * 60, json.dumps(metadata))
        
        print(f"[CSA_STORE] Saved CSA {csa.csa_id} for user {csa.user_id}")
        
        return {
            "csa_id": csa.csa_id,
            "json_path": str(json_path),
            "md_path": md_path_str,
            "redis_key": csa_bytes_key,
            "metadata": metadata
        }
    
    def get_csa_by_id(self, csa_id: str) -> Optional[ConversationSnapshotArtifact]:
        """
        Retrieve CSA by ID from Redis or disk.
        
        Args:
            csa_id: CSA identifier
            
        Returns:
            ConversationSnapshotArtifact or None if not found
        """
        # Try Redis first (fastest)
        csa_bytes_key = f"csa_file:{csa_id}"
        csa_bytes = self.redis.client.get(csa_bytes_key)
        
        if csa_bytes:
            csa_data = json.loads(csa_bytes)
            return ConversationSnapshotArtifact(**csa_data)
        
        # Fallback to disk search (slower)
        for json_file in self.storage_dir.glob(f"csa_*_{csa_id}*.json"):
            with open(json_file, 'r', encoding='utf-8') as f:
                csa_data = json.load(f)
                if csa_data.get('csa_id') == csa_id:
                    return ConversationSnapshotArtifact(**csa_data)
        
        return None
    
    def get_latest_csa_metadata(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for user's latest CSA.
        
        Args:
            user_id: User identifier
            
        Returns:
            Metadata dict or None if no CSA exists
        """
        latest_key = f"csa_latest:{user_id}"
        metadata_json = self.redis.client.get(latest_key)
        
        if metadata_json:
            return json.loads(metadata_json)
        
        return None
    
    def get_csa_file_bytes(self, csa_id: str) -> Optional[bytes]:
        """
        Get raw CSA file bytes for download/attachment.
        
        Args:
            csa_id: CSA identifier
            
        Returns:
            JSON bytes or None
        """
        csa_bytes_key = f"csa_file:{csa_id}"
        return self.redis.client.get(csa_bytes_key)
    
    def _csa_to_markdown(self, csa: ConversationSnapshotArtifact) -> str:
        """Convert CSA to markdown format for human readability."""
        md = f"""# {csa.title}

**CSA ID:** `{csa.csa_id}`  
**User:** `{csa.user_id}`  
**Created:** {csa.created_ts_ms} (Unix ms)  
**Source:** {csa.source_provider} (Session: {csa.source_session_id})  
**Schema Version:** {csa.schema_version}

---

## User Intent

{csa.user_intent}

---

## What We Did

"""
        for item in csa.what_we_did:
            md += f"- {item}\n"
        
        md += "\n---\n\n## What Worked\n\n"
        for item in csa.what_worked:
            md += f"✅ {item}\n"
        
        md += "\n---\n\n## What Failed\n\n"
        for item in csa.what_failed:
            md += f"❌ {item}\n"
        
        md += "\n---\n\n## Constraints\n\n"
        for item in csa.constraints:
            md += f"- {item}\n"
        
        md += "\n---\n\n## Preferences\n\n"
        for item in csa.preferences:
            md += f"- {item}\n"
        
        md += "\n---\n\n## Key Entities\n\n```json\n"
        md += json.dumps(csa.key_entities, indent=2)
        md += "\n```\n"
        
        md += "\n---\n\n## Artifacts\n\n"
        for artifact in csa.artifacts:
            md += f"### {artifact.get('name', 'Unnamed')}\n"
            md += f"- **Type:** {artifact.get('type', 'unknown')}\n"
            md += f"- **Description:** {artifact.get('description', 'N/A')}\n"
            md += f"- **Quality Score:** {artifact.get('quality_score', 0.0):.2f}\n\n"
        
        md += "\n---\n\n## Next Steps\n\n"
        for item in csa.next_steps:
            md += f"1. {item}\n"
        
        md += "\n---\n\n## Instructions for Next Model\n\n"
        for item in csa.instructions_for_next_model:
            md += f"📌 {item}\n"
        
        return md


# Singleton instance
csa_store = CSAStore()
