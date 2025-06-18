from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Story:
    """Represents a personal story with metadata for matching"""
    id: str
    bot_id: str  # Which bot this story belongs to
    title: str
    content: str
    themes: List[str]  # e.g., ["childhood", "family", "learning"]
    triggers: List[str]  # Keywords that might prompt this story
    emotional_tone: str  # "funny", "reflective", "inspiring", etc.
    context_hints: List[str]  # When this story fits well
    used_count: int = 0
    last_used: Optional[str] = None