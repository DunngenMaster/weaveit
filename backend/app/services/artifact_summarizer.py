"""
Sprint 17.9: Artifact Summarizer

Converts extracted pages into clean ArtifactSummary Weaviate objects.
Raw HTML stored in Redis (24h TTL), only clean summaries in Weaviate.

For job_posting:
- title, company, location, skills
- 5-7 bullet summary
- Reference to raw HTML in Redis
"""

import json
import re
from typing import Dict, Any, List
from datetime import datetime, timezone
from app.services.redis_client import redis_client
from app.services.weaviate_client import weaviate_client


class ArtifactSummarizer:
    """
    Process browser extraction results into clean Weaviate artifacts.
    
    Sprint 17.9 Rules:
    - Raw HTML/text stored in Redis with 24h TTL
    - Only clean, structured summaries in Weaviate
    - 5-7 bullet points for quick scanning
    - Skills extracted from description
    """
    
    def __init__(self):
        self.redis_client = redis_client.client
        self.weaviate_client = weaviate_client.client
    
    def process_job_posting(
        self,
        user_id: str,
        extraction_data: Dict[str, Any],
        extraction_method: str = "dom"
    ) -> bool:
        """
        Process job posting extraction into ArtifactSummary.
        
        Args:
            user_id: User identifier
            extraction_data: Raw extraction data (title, company, description, etc.)
            extraction_method: How it was extracted (dom/heuristics/screenshot)
            
        Returns:
            True if stored successfully
        """
        try:
            title = extraction_data.get('title', '')
            company = extraction_data.get('company', '')
            location = extraction_data.get('location', '')
            description = extraction_data.get('description', '')
            url = extraction_data.get('url', '')
            
            if not title or not description:
                print(f"[ARTIFACT] Skipping incomplete extraction (no title/desc)")
                return False
            
            # Store raw HTML in Redis (24h TTL)
            raw_html_key = f"raw_extract:{user_id}:{int(datetime.now().timestamp())}"
            raw_data = {
                'title': title,
                'company': company,
                'location': location,
                'description': description,
                'url': url,
                'extracted_at': extraction_data.get('extracted_at', 0)
            }
            self.redis_client.setex(raw_html_key, 24 * 60 * 60, json.dumps(raw_data))
            
            # Extract skills from description
            skills = self._extract_skills(description)
            
            # Generate 5-7 bullet summary
            summary_bullets = self._generate_summary_bullets(description, title, company)
            
            # Store in Weaviate as ArtifactSummary
            collection = self.weaviate_client.collections.get("ArtifactSummary")
            
            collection.data.insert({
                'user_id': user_id,
                'kind': 'job_posting',
                'title': title,
                'company': company,
                'location': location,
                'skills': skills,
                'summary_bullets': summary_bullets,
                'source_url': url,
                'raw_html_key': raw_html_key,
                'extraction_method': extraction_method,
                'created_at': datetime.now(timezone.utc)
            })
            
            print(f"[ARTIFACT] Stored job_posting: {title[:40]}... ({len(skills)} skills, {len(summary_bullets)} bullets)")
            return True
            
        except Exception as e:
            print(f"[ARTIFACT] Error processing job posting: {e}")
            return False
    
    def _extract_skills(self, description: str) -> List[str]:
        """
        Extract technical skills from job description.
        
        Args:
            description: Job description text
            
        Returns:
            List of skills (max 20)
        """
        # Common technical skills patterns
        skill_patterns = [
            r'\b(Python|Java|JavaScript|TypeScript|Go|Rust|C\+\+|Ruby|PHP|Swift|Kotlin)\b',
            r'\b(React|Vue|Angular|Node\.js|Express|Django|Flask|FastAPI|Spring)\b',
            r'\b(AWS|Azure|GCP|Docker|Kubernetes|Terraform|Jenkins|CI/CD)\b',
            r'\b(PostgreSQL|MySQL|MongoDB|Redis|Elasticsearch|DynamoDB)\b',
            r'\b(Git|GitHub|GitLab|Jira|Agile|Scrum|REST|GraphQL|gRPC)\b',
            r'\b(Machine Learning|ML|AI|TensorFlow|PyTorch|scikit-learn|NLP)\b',
            r'\b(Linux|Unix|Bash|Shell|API|Microservices|Serverless)\b',
        ]
        
        skills = set()
        for pattern in skill_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            skills.update([m.strip() for m in matches])
        
        # Limit to 20 skills
        return sorted(list(skills))[:20]
    
    def _generate_summary_bullets(
        self,
        description: str,
        title: str,
        company: str
    ) -> List[str]:
        """
        Generate 5-7 bullet point summary of job posting.
        
        This is a simple heuristic version. In production, use LLM summarization.
        
        Args:
            description: Full job description
            title: Job title
            company: Company name
            
        Returns:
            List of 5-7 bullet points
        """
        bullets = []
        
        # Bullet 1: Role overview
        if title and company:
            bullets.append(f"{title} position at {company}")
        
        # Extract requirements section
        req_match = re.search(
            r'(?:Requirements?|Qualifications?|Skills?|Must[- ]have)[:\s]+(.{100,500})',
            description,
            re.IGNORECASE | re.DOTALL
        )
        if req_match:
            req_text = req_match.group(1).strip()
            # Split into sentences
            sentences = re.split(r'[.!?]\s+', req_text)
            for sent in sentences[:3]:  # First 3 requirements
                if len(sent) > 20:
                    bullets.append(sent.strip()[:120])  # Truncate long sentences
        
        # Extract responsibilities section
        resp_match = re.search(
            r'(?:Responsibilities?|Duties?|You will)[:\s]+(.{100,500})',
            description,
            re.IGNORECASE | re.DOTALL
        )
        if resp_match:
            resp_text = resp_match.group(1).strip()
            sentences = re.split(r'[.!?]\s+', resp_text)
            for sent in sentences[:2]:  # First 2 responsibilities
                if len(sent) > 20:
                    bullets.append(sent.strip()[:120])
        
        # If we don't have enough bullets, extract any sentence with key verbs
        if len(bullets) < 5:
            key_verbs = ['build', 'develop', 'design', 'lead', 'manage', 'work', 'collaborate']
            for verb in key_verbs:
                pattern = rf'([A-Z][^.!?]*{verb}[^.!?]{{20,100}}[.!?])'
                matches = re.findall(pattern, description, re.IGNORECASE)
                if matches:
                    bullets.append(matches[0].strip()[:120])
                    if len(bullets) >= 7:
                        break
        
        # Ensure 5-7 bullets
        return bullets[:7] if len(bullets) >= 5 else bullets + ["Details in full description"]
    
    def get_artifact_summary(
        self,
        user_id: str,
        url: str
    ) -> Dict[str, Any]:
        """
        Retrieve stored artifact summary by URL.
        
        Args:
            user_id: User identifier
            url: Source URL
            
        Returns:
            Artifact data or empty dict
        """
        try:
            collection = self.weaviate_client.collections.get("ArtifactSummary")
            
            # Query by user_id and source_url
            import weaviate.classes as wvc
            filters = (
                wvc.query.Filter.by_property("user_id").equal(user_id) &
                wvc.query.Filter.by_property("source_url").equal(url)
            )
            
            result = collection.query.fetch_objects(filters=filters, limit=1)
            
            if result.objects:
                props = result.objects[0].properties
                return {
                    'kind': props.get('kind', ''),
                    'title': props.get('title', ''),
                    'company': props.get('company', ''),
                    'location': props.get('location', ''),
                    'skills': props.get('skills', []),
                    'summary_bullets': props.get('summary_bullets', []),
                    'source_url': props.get('source_url', ''),
                    'raw_html_key': props.get('raw_html_key', ''),
                    'extraction_method': props.get('extraction_method', ''),
                    'created_at': props.get('created_at', None)
                }
            
            return {}
            
        except Exception as e:
            print(f"[ARTIFACT] Error retrieving summary: {e}")
            return {}


# Global instance
artifact_summarizer = ArtifactSummarizer()
