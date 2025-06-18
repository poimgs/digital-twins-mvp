import logging
from datetime import datetime
from typing import Dict
import openai

from ..models import ChatMemory
from ..storage import StorageManager
from ..config import get_settings
from .personality import Personality
from .story_matcher import StoryMatcher

logger = logging.getLogger(__name__)

class DigitalTwinBot:
    """Main bot class orchestrating all components - fully data-driven"""
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.settings = get_settings()
        self.storage = StorageManager(bot_id, self.settings)
        self.metadata = None
        self.personality = None
        self.stories = []
        self.story_matcher = None
        self.chat_memories = {}
        self.is_initialized = False
        
        # Set OpenAI API key
        openai.api_key = self.settings.openai_api_key
    
    async def initialize(self) -> bool:
        """Initialize bot with metadata, personality, and stories from database"""
        try:
            # Load bot metadata from database
            self.metadata = await self.storage.load_bot_metadata()
            if not self.metadata:
                logger.error(f"No metadata found for bot {self.bot_id}")
                return False
            
            # Check if bot is active
            if not self.metadata.is_active:
                logger.warning(f"Bot {self.bot_id} is marked as inactive")
                return False
            
            # Initialize personality from metadata
            self.personality = Personality(self.metadata)
            
            # Load stories for this bot
            self.stories = await self.storage.load_stories()
            if not self.stories:
                logger.error(f"No stories found for bot {self.bot_id}, creating defaults")
                return False
            
            self.story_matcher = StoryMatcher(self.stories)
            self.is_initialized = True
            
            logger.info(f"✅ Bot initialized: {self.metadata.display_name} ({self.bot_id})")
            logger.info(f"   Stories: {len(self.stories)}")
            logger.info(f"   Version: {self.metadata.version}")
            logger.info(f"   Traits: {', '.join(self.metadata.core_traits[:3])}...")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot {self.bot_id}: {e}")
            return False
    
    async def reload_configuration(self) -> bool:
        """Reload bot configuration from database (for runtime updates)"""
        logger.info(f"🔄 Reloading configuration for bot {self.bot_id}")
        return await self.initialize()
    
    def get_welcome_message(self) -> str:
        """Get the bot's configured welcome message"""
        if not self.is_initialized or not self.metadata:
            return "Hi! I'm having trouble accessing my configuration right now. Please try again in a moment."
        return self.metadata.welcome_message
    
    async def get_chat_memory(self, chat_id: str) -> ChatMemory:
        """Get or create chat memory for a conversation"""
        memory_key = f"{self.bot_id}_{chat_id}"
        if memory_key not in self.chat_memories:
            self.chat_memories[memory_key] = await self.storage.load_chat_memory(chat_id)
        return self.chat_memories[memory_key]
    
    async def update_chat_memory(self, chat_id: str, user_message: str, bot_response: str):
        """Update chat memory with new interaction"""
        memory = await self.get_chat_memory(chat_id)
        memory.message_count += 1
        memory.last_interaction = datetime.now().isoformat()
        
        # Extract themes and interests from conversation
        combined_text = f"{user_message} {bot_response}".lower()
        
        # Simple keyword extraction for themes
        theme_keywords = ["family", "work", "travel", "learning", "food", "technology", "music", "sports"]
        for keyword in theme_keywords:
            if keyword in combined_text and keyword not in memory.conversation_themes:
                memory.conversation_themes.append(keyword)
        
        # Update relationship stage based on interaction count
        if memory.message_count > 20:
            memory.relationship_stage = "familiar"
        elif memory.message_count > 5:
            memory.relationship_stage = "warming_up"
        
        await self.storage.save_chat_memory(memory)
    
    async def generate_response(self, user_message: str, chat_id: str) -> str:
        """Generate contextual response with potential story integration"""
        
        if not self.is_initialized:
            return "I'm still getting my thoughts together. Please give me a moment to initialize properly."
        
        memory = await self.get_chat_memory(chat_id)
        
        # Find relevant stories based on bot's story sharing frequency
        max_stories = {
            "low": 1,
            "moderate": 2, 
            "high": 3
        }.get(self.metadata.story_sharing_frequency, 2)
        
        relevant_stories = self.story_matcher.find_relevant_stories(
            user_message, memory, max_stories=max_stories
        )
        
        # Build conversation context using bot's full context
        context_parts = [
            self.personality.full_context,
            f"Conversation stage: {memory.relationship_stage}",
            f"Previous themes discussed: {', '.join(memory.conversation_themes[-5:])}"
        ]
        
        if relevant_stories:
            context_parts.append("You have these relevant personal stories you could naturally weave in if appropriate:")
            for story in relevant_stories:
                context_parts.append(f"- {story.content}")
        
        # Add response length guidance
        length_guidance = {
            "short": "Keep your response concise, ideally 1-2 sentences.",
            "medium": "Provide a thoughtful response, typically 2-4 sentences.",
            "long": "Give a detailed, comprehensive response with rich context."
        }
        
        context_parts.extend([
            "",
            "Instructions:",
            "- Respond naturally to the user's message in your authentic voice",
            "- If a personal story feels relevant and natural, share it conversationally", 
            "- Don't force stories - only share if they genuinely relate",
            "- Ask follow-up questions to keep the conversation flowing",
            "- Be warm, genuine, and curious about the user's experiences",
            f"- {length_guidance.get(self.metadata.response_length_preference, length_guidance['medium'])}"
        ])
        
        system_message = "\n".join(context_parts)
        
        try:
            max_tokens = 300 if self.metadata.response_length_preference != "long" else 500
            
            response = await openai.ChatCompletion.acreate(
                model=self.settings.default_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens,
                temperature=self.settings.default_temperature
            )
            
            bot_response = response.choices[0].message.content
            
            # Check if any stories were used and update memory
            for story in relevant_stories:
                if any(phrase in bot_response.lower() for phrase in story.content.lower().split('.')[0:2]):
                    memory.stories_shared.append(story.id)
                    await self.storage.update_story_usage(story.id)
            
            # Update chat memory
            await self.update_chat_memory(chat_id, user_message, bot_response)
            
            return bot_response
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm having trouble organizing my thoughts right now. Could you try again?"