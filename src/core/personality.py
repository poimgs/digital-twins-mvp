import logging
from typing import Dict

from ..models import BotMetadata

logger = logging.getLogger(__name__)

class Personality:
    """Core personality system loaded from database configuration"""
    
    def __init__(self, bot_metadata: BotMetadata):
        self.bot_id = bot_metadata.bot_id
        self.name = bot_metadata.name
        self.display_name = bot_metadata.display_name
        self.description = bot_metadata.description
        self.welcome_message = bot_metadata.welcome_message
        self.core_traits = bot_metadata.core_traits
        self.conversation_style = bot_metadata.conversation_style
        self.background_context = bot_metadata.background_context
        
        # Behavior settings
        self.story_sharing_frequency = bot_metadata.story_sharing_frequency
        self.relationship_building_speed = bot_metadata.relationship_building_speed
        self.response_length_preference = bot_metadata.response_length_preference
        
        # Build dynamic context based on metadata
        self._build_dynamic_context()
    
    def _build_dynamic_context(self):
        """Build comprehensive context from metadata"""
        frequency_instructions = {
            "low": "Share stories sparingly, only when they're very relevant",
            "moderate": "Share stories naturally when they relate to the conversation",
            "high": "Look for opportunities to weave in relevant stories frequently"
        }
        
        length_instructions = {
            "short": "Keep responses concise and to the point",
            "medium": "Provide thoughtful, well-developed responses", 
            "long": "Give detailed, comprehensive responses with rich context"
        }
        
        self.full_context = f"""
        You are {self.display_name}, a digital twin with the following personality:
        
        Core traits: {', '.join(self.core_traits)}
        
        Conversation approach: {self.conversation_style.get('approach', 'engaging and authentic')}
        Tone: {self.conversation_style.get('tone', 'warm and genuine')}
        
        Background: {self.background_context}
        
        Story sharing guidance: {frequency_instructions.get(self.story_sharing_frequency, frequency_instructions['moderate'])}
        Response style: {length_instructions.get(self.response_length_preference, length_instructions['medium'])}
        
        Always maintain your authentic personality while being genuinely curious about the user's experiences.
        """