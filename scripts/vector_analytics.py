import asyncio
import json
from datetime import datetime, timedelta

from src.config import get_settings

async def vector_search_analytics():
    """Generate analytics report for vector search performance"""
    
    settings = get_settings()
    
    if not settings.use_supabase:
        print("Supabase is required for analytics")
        return
    
    try:
        from supabase import create_client
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        
        print("📊 Vector Search Analytics Report")
        print("=" * 60)
        
        # Embedding coverage
        print("\n1. Embedding Coverage by Bot:")
        result = supabase.table('story_usage_with_vectors').select('*').execute()
        
        if result.data:
            coverage_by_bot = {}
            for row in result.data:
                bot_id = row['bot_id']
                if bot_id not in coverage_by_bot:
                    coverage_by_bot[bot_id] = {'total': 0, 'with_embedding': 0}
                
                coverage_by_bot[bot_id]['total'] += 1
                if row['has_embedding']:
                    coverage_by_bot[bot_id]['with_embedding'] += 1
            
            for bot_id, stats in coverage_by_bot.items():
                coverage = (stats['with_embedding'] / stats['total']) * 100
                print(f"   {bot_id}: {stats['with_embedding']}/{stats['total']} ({coverage:.1f}%)")
        
        # Recent embedding activity
        print("\n2. Recent Embedding Activity:")
        result = supabase.table('story_embeddings')\
            .select('bot_id, created_at')\
            .gte('created_at', (datetime.now() - timedelta(days=7)).isoformat())\
            .execute()
        
        if result.data:
            recent_by_bot = {}
            for row in result.data:
                bot_id = row['bot_id']
                recent_by_bot[bot_id] = recent_by_bot.get(bot_id, 0) + 1
            
            for bot_id, count in recent_by_bot.items():
                print(f"   {bot_id}: {count} embeddings created in last 7 days")
        else:
            print("   No recent embedding activity")
        
        # Storage usage
        print("\n3. Storage Usage:")
        result = supabase.rpc('get_embedding_storage_stats').execute()
        
        if result.data:
            for row in result.data:
                print(f"   Total embeddings: {row['total_embeddings']}")
                print(f"   Storage size: {row['storage_size_mb']:.1f} MB")
                print(f"   Average embedding size: {row['avg_embedding_size']} dimensions")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"Error generating analytics: {e}")

async def embedding_health_check():
    """Check health of embedding system"""
    
    settings = get_settings()
    
    try:
        from supabase import create_client
        supabase = create_client(settings.supabase_url, settings.supabase_key)
        
        print("🏥 Embedding System Health Check")
        print("=" * 50)
        
        # Check vector extension
        result = supabase.rpc('check_vector_extension').execute()
        vector_enabled = result.data[0]['extension_available'] if result.data else False
        
        print(f"✅ Vector Extension: {'Enabled' if vector_enabled else '❌ Disabled'}")
        
        # Check indexes
        result = supabase.rpc('check_vector_indexes').execute()
        if result.data:
            for index in result.data:
                print(f"✅ Index {index['indexname']}: {index['index_size']}")
        
        # Check for orphaned embeddings
        result = supabase.rpc('count_orphaned_embeddings').execute()
        orphaned_count = result.data[0]['orphaned_count'] if result.data else 0
        
        if orphaned_count > 0:
            print(f"⚠️  Orphaned embeddings: {orphaned_count}")
            print("   Run cleanup_orphaned_embeddings() to fix")
        else:
            print("✅ No orphaned embeddings")
        
        # Check embedding freshness
        result = supabase.rpc('check_stale_embeddings').execute()
        if result.data:
            stale_count = result.data[0]['stale_count']
            if stale_count > 0:
                print(f"⚠️  Stale embeddings: {stale_count}")
                print("   Some stories may need re-embedding")
            else:
                print("✅ All embeddings are fresh")
        
        print("=" * 50)
        
    except Exception as e:
        print(f"Health check failed: {e}")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Vector search analytics and monitoring')
    parser.add_argument('--analytics', action='store_true', help='Generate analytics report')
    parser.add_argument('--health', action='store_true', help='Run health check')
    
    args = parser.parse_args()
    
    if args.health:
        asyncio.run(embedding_health_check())
    else:
        asyncio.run(vector_search_analytics())