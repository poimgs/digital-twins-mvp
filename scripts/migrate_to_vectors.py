import asyncio
import logging
from typing import List

from src.config import get_settings
from src.models import Story

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_existing_installation():
    """Migrate existing bot installation to use vector search"""
    
    settings = get_settings()
    
    if not settings.use_supabase:
        logger.error("Supabase is required for vector migration")
        return
    
    try:
        from supabase import create_client
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        
        logger.info("🔄 Starting migration to vector search...")
        
        # Step 1: Check if vector extension is enabled
        logger.info("1. Checking vector extension...")
        try:
            result = supabase.rpc('check_vector_extension').execute()
            if not result.data or not result.data[0].get('extension_available'):
                logger.error("❌ Vector extension not enabled. Run: CREATE EXTENSION vector;")
                return
            logger.info("✅ Vector extension is enabled")
        except Exception:
            logger.error("❌ Could not check vector extension. Please enable it manually.")
            return
        
        # Step 2: Create vector tables if they don't exist
        logger.info("2. Creating vector tables...")
        # The tables should be created via the SQL schema script
        logger.info("✅ Ensure story_embeddings table exists via SQL schema")
        
        # Step 3: Get all active bots
        logger.info("3. Finding active bots...")
        result = supabase.table('bot_metadata').select('bot_id').eq('is_active', True).execute()
        
        if not result.data:
            logger.warning("No active bots found")
            return
        
        bot_ids = [bot['bot_id'] for bot in result.data]
        logger.info(f"Found {len(bot_ids)} active bots: {', '.join(bot_ids)}")
        
        # Step 4: Initialize embeddings for each bot
        logger.info("4. Initializing embeddings...")
        for bot_id in bot_ids:
            try:
                await initialize_embeddings_for_bot(bot_id)
                logger.info(f"✅ Initialized embeddings for {bot_id}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize embeddings for {bot_id}: {e}")
        
        # Step 5: Verify migration
        logger.info("5. Verifying migration...")
        await verify_migration(supabase, bot_ids)
        
        logger.info("🎉 Migration completed successfully!")
        logger.info("Next steps:")
        logger.info("1. Update your bot deployment to use SupabaseEnhancedStoryMatcher")
        logger.info("2. Set USE_VECTOR_MATCHING=true in environment")
        logger.info("3. Monitor performance with vector_analytics.py")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")

async def verify_migration(supabase, bot_ids: List[str]):
    """Verify that migration was successful"""
    
    for bot_id in bot_ids:
        # Check story count vs embedding count
        stories_result = supabase.table('stories').select('id').eq('bot_id', bot_id).execute()
        embeddings_result = supabase.table('story_embeddings').select('story_id').eq('bot_id', bot_id).execute()
        
        story_count = len(stories_result.data) if stories_result.data else 0
        embedding_count = len(embeddings_result.data) if embeddings_result.data else 0
        
        if story_count == embedding_count:
            logger.info(f"✅ {bot_id}: {embedding_count}/{story_count} stories have embeddings")
        else:
            logger.warning(f"⚠️  {bot_id}: {embedding_count}/{story_count} stories have embeddings")

if __name__ == '__main__':
    asyncio.run(migrate_existing_installation())