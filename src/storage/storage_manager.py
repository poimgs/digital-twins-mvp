import logging
from datetime import datetime
from typing import List, Optional
from dataclasses import asdict

from ..models import BotMetadata, Story, ChatMemory
from ..config import Settings

logger = logging.getLogger(__name__)

class StorageManager:
    """Storage manager handling Supabase"""
    
    def __init__(self, bot_id: str, settings: Settings):
        self.bot_id = bot_id
        self.settings = settings
        
        from supabase import create_client, Client
        self.supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
    
    async def load_bot_metadata(self) -> Optional[BotMetadata]:
        """Load complete bot metadata from database"""
        try:
            response = self.supabase.table('bot_metadata').select('*').eq('bot_id', self.bot_id).execute()
            if response.data:
                return BotMetadata(**response.data[0])
        except Exception as e:
            logger.error(f"Failed to load bot metadata from Supabase: {e}")
    
    async def save_bot_metadata(self, metadata: BotMetadata):
        """Save bot metadata to database"""
        metadata.updated_at = datetime.now().isoformat()
        if not metadata.created_at:
            metadata.created_at = metadata.updated_at
            
        try:
            data = asdict(metadata)
            self.supabase.table('bot_metadata').upsert(data).execute()
            logger.info(f"Saved bot metadata for {metadata.bot_id} to Supabase")
            return
        except Exception as e:
            logger.error(f"Failed to save bot metadata to Supabase: {e}")
    
    async def load_stories(self) -> List[Story]:
        """Load stories for this bot from storage"""
        try:
            response = self.supabase.table('stories').select('*').eq('bot_id', self.bot_id).execute()
            return [Story(**story) for story in response.data]
        except Exception as e:
            logger.error(f"Failed to load stories from Supabase: {e}")
    
    async def save_stories(self, stories: List[Story]):
        """Save stories for this bot"""
        try:
            stories_data = [asdict(story) for story in stories]
            # Delete existing stories for this bot and insert new ones
            self.supabase.table('stories').delete().eq('bot_id', self.bot_id).execute()
            if stories_data:
                self.supabase.table('stories').insert(stories_data).execute()
            return
        except Exception as e:
            logger.error(f"Failed to save stories to Supabase: {e}")
    
    async def save_chat_memory(self, memory: ChatMemory):
        """Save chat memory to storage"""
        try:
            data = asdict(memory)
            self.supabase.table('chat_memories').upsert(data).execute()
            return
        except Exception as e:
            logger.error(f"Failed to save to Supabase: {e}")
    
    async def load_chat_memory(self, chat_id: str) -> ChatMemory:
        """Load chat memory from storage"""
        try:
            response = self.supabase.table('chat_memories').select('*').eq('bot_id', self.bot_id).eq('chat_id', chat_id).execute()
            if response.data:
                return ChatMemory(**response.data[0])
        except Exception as e:
            logger.error(f"Failed to load from Supabase: {e}")
        
        # Create new memory
        return ChatMemory(
            chat_id=chat_id,
            bot_id=self.bot_id,
            stories_shared=[],
            conversation_themes=[],
            user_interests=[],
            last_interaction=datetime.now().isoformat()
        )
    
    async def update_story_usage(self, story_id: str):
        """Update story usage statistics"""
        try:
            self.supabase.table('stories').update({
                'used_count': 'used_count + 1',
                'last_used': datetime.now().isoformat()
            }).eq('id', story_id).eq('bot_id', self.bot_id).execute()
        except Exception as e:
            logger.error(f"Failed to update story usage: {e}")