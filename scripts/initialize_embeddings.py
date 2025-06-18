import os
import sys
import asyncio
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config import get_settings
from src.storage import StorageManager
from src.supabase_vector_matcher import SupabaseVectorStoryMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def initialize_embeddings_for_bot(bot_id: str):
    """Initialize embeddings for a specific bot"""
    settings = get_settings()
    storage = StorageManager(bot_id, settings)
    vector_matcher = SupabaseVectorStoryMatcher(bot_id, settings)
    
    try:
        # Load all stories for the bot
        stories = await storage.load_stories()
        
        if not stories:
            logger.info(f"No stories found for bot {bot_id}")
            return
        
        logger.info(f"Initializing embeddings for {len(stories)} stories for bot {bot_id}")
        
        # Initialize embeddings
        success = await vector_matcher.initialize_story_embeddings(stories)
        
        if success:
            logger.info(f"✅ Successfully initialized embeddings for bot {bot_id}")
        else:
            logger.error(f"❌ Failed to initialize embeddings for bot {bot_id}")
        
    except Exception as e:
        logger.error(f"Error initializing embeddings for bot {bot_id}: {e}")

async def initialize_all_bots():
    """Initialize embeddings for all active bots"""
    settings = get_settings()
    
    if not settings.use_supabase:
        logger.error("Supabase is required for vector embeddings")
        return
    
    try:
        from supabase import create_client
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        
        # Get all active bots
        result = supabase.table('bot_metadata').select('bot_id').eq('is_active', True).execute()
        
        if not result.data:
            logger.info("No active bots found")
            return
        
        bot_ids = [bot['bot_id'] for bot in result.data]
        logger.info(f"Found {len(bot_ids)} active bots: {', '.join(bot_ids)}")
        
        # Initialize embeddings for each bot
        for bot_id in bot_ids:
            await initialize_embeddings_for_bot(bot_id)
        
        logger.info("✅ Finished initializing embeddings for all bots")
        
    except Exception as e:
        logger.error(f"Error initializing embeddings for all bots: {e}")

async def check_embedding_status():
    """Check embedding status across all bots"""
    settings = get_settings()
    
    try:
        from supabase import create_client
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        
        # Query embedding status
        result = supabase.rpc('get_embedding_status').execute()
        
        if result.data:
            print("\n📊 Embedding Status Report:")
            print("-" * 60)
            for row in result.data:
                print(f"Bot: {row['bot_id']}")
                print(f"  Stories: {row['total_stories']}")
                print(f"  Embeddings: {row['stories_with_embeddings']}")
                print(f"  Missing: {row['missing_embeddings']}")
                print(f"  Coverage: {row['coverage_percentage']:.1f}%")
                print("-" * 60)
        else:
            print("No embedding data found")
        
    except Exception as e:
        logger.error(f"Error checking embedding status: {e}")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Initialize story embeddings')
    parser.add_argument('--bot-id', help='Initialize embeddings for specific bot')
    parser.add_argument('--all', action='store_true', help='Initialize embeddings for all bots')
    parser.add_argument('--status', action='store_true', help='Check embedding status')
    
    args = parser.parse_args()
    
    if args.status:
        asyncio.run(check_embedding_status())
    elif args.bot_id:
        asyncio.run(initialize_embeddings_for_bot(args.bot_id))
    elif args.all:
        asyncio.run(initialize_all_bots())
    else:
        parser.print_help()