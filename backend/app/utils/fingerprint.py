import hashlib
import re


def compute_fingerprint(text: str) -> str:
    """
    Compute a fingerprint for USER_MESSAGE text to identify duplicates.
    
    Algorithm:
    1. Lowercase the text
    2. Strip leading/trailing whitespace
    3. Replace all consecutive whitespace with single space
    4. Remove punctuation characters: .,!?;:"'()[]{}<>
    5. Truncate to first 600 chars
    6. Compute SHA256 hash
    
    Args:
        text: The message text to fingerprint
        
    Returns:
        SHA256 hex digest (64 character string)
    """
    
    # Step 1: Lowercase
    normalized = text.lower()
    
    # Step 2: Strip whitespace
    normalized = normalized.strip()
    
    # Step 3: Replace consecutive whitespace with single space
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Step 4: Remove punctuation
    punctuation = r'[.,!?;:"\'()\[\]{}<>]'
    normalized = re.sub(punctuation, '', normalized)
    
    # Step 5: Truncate to 600 chars
    normalized = normalized[:600]
    
    # Step 6: Compute SHA256
    fingerprint = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    
    return fingerprint
