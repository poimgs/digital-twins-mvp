from dataclasses import dataclass
from typing import List

@dataclass
class ChatMemory:
    """Per-chat memory to track context and prevent repetition"""
    chat_id: str
    bot_id: str  # Which bot this memory belongs to
    stories_shared: List[str]  # Story IDs already shared
    conversation_themes: List[str]  # Recurring topics in this chat
    user_interests: List[str]  # What the user seems interested in
    last_interaction: str
    message_count: int = 0
    relationship_stage: str = "new"  # new, warming_up, familiar
