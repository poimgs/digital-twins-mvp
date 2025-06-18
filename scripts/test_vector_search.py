import asyncio
import logging
from typing import List

from src.config import get_settings
from src.models import ChatMemory
from src.supabase_vector_matcher import SupabaseVectorStoryMatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_vector_search():
    """Test vector search with sample queries"""
    
    settings = get_settings()
    bot_id = "alex_v1"  # Change to your bot ID
    
    vector_matcher = SupabaseVectorStoryMatcher(bot_id, settings)
    
    # Create sample chat memory
    chat_memory = ChatMemory(
        chat_id="test_chat",
        bot_id=bot_id,
        stories_shared=[],
        conversation_themes=["work", "stress"],
        user_interests=["career", "technology"],
        last_interaction="2024-01-01T00:00:00",
        relationship_stage="warming_up"
    )
    
    # Test queries
    test_queries = [
        "I'm feeling really stressed about my job lately",
        "I had a funny thing happen at work today",
        "I'm thinking about traveling somewhere new",
        "Learning new skills is challenging but rewarding",
        "I made a big mistake in a presentation"
    ]
    
    print("\n🔍 Vector Search Test Results:")
    print("=" * 80)
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 50)
        
        try:
            matches = await vector_matcher.find_relevant_stories(
                query, chat_memory, max_stories=3
            )
            
            if matches:
                for i, match in enumerate(matches, 1):
                    print(f"{i}. {match.story.title}")
                    print(f"   Vector Similarity: {match.vector_similarity:.3f}")
                    print(f"   LLM Judge Score: {match.llm_judge_score:.3f}")
                    print(f"   Combined Score: {match.combined_score:.3f}")
                    print(f"   Reasoning: {match.reasoning}")
                    print()
            else:
                print("   No relevant stories found")
                
        except Exception as e:
            print(f"   Error: {e}")
    
    print("=" * 80)

async def benchmark_vector_search():
    """Benchmark vector search performance"""
    import time
    
    settings = get_settings()
    bot_id = "alex_v1"
    
    vector_matcher = SupabaseVectorStoryMatcher(bot_id, settings)
    
    chat_memory = ChatMemory(
        chat_id="benchmark_chat",
        bot_id=bot_id,
        stories_shared=[],
        conversation_themes=[],
        user_interests=[],
        last_interaction="2024-01-01T00:00:00"
    )
    
    query = "I'm having trouble with work-life balance"
    
    # Warm up
    await vector_matcher.find_relevant_stories(query, chat_memory, max_stories=3)
    
    # Benchmark
    times = []
    for i in range(10):
        start_time = time.time()
        await vector_matcher.find_relevant_stories(query, chat_memory, max_stories=3)
        end_time = time.time()
        times.append((end_time - start_time) * 1000)  # Convert to ms
    
    print(f"\n⏱️  Vector Search Performance (10 iterations):")
    print(f"Average: {sum(times) / len(times):.1f}ms")
    print(f"Min: {min(times):.1f}ms")
    print(f"Max: {max(times):.1f}ms")
    print(f"95th percentile: {sorted(times)[int(0.95 * len(times))]:.1f}ms")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test vector search functionality')
    parser.add_argument('--test', action='store_true', help='Run basic vector search test')
    parser.add_argument('--benchmark', action='store_true', help='Run performance benchmark')
    
    args = parser.parse_args()
    
    if args.benchmark:
        asyncio.run(benchmark_vector_search())
    else:
        asyncio.run(test_vector_search())