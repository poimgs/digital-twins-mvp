from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class BotMetadata:
    """Complete bot configuration stored in database"""
    bot_id: str
    name: str
    display_name: str  # What users see in conversations
    description: str  # Brief description of the bot
    welcome_message: str  # Custom welcome message
    
    # Personality configuration
    core_traits: List[str]
    conversation_style: Dict[str, str]
    background_context: str
    
    # Bot behavior settings
    story_sharing_frequency: str = "moderate"  # low, moderate, high
    relationship_building_speed: str = "normal"  # slow, normal, fast
    response_length_preference: str = "medium"  # short, medium, long
    
    # Metadata
    version: str = "1.0"
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None