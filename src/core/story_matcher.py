import logging
import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json
import openai
from datetime import datetime

from ..models import Story, ChatMemory
from ..config import get_settings

logger = logging.getLogger(__name__)

@dataclass
class StoryMatch:
    """Story match with vector similarity and LLM reasoning"""
    story: Story
    vector_similarity: float  # 0.0 to 1.0 from pgvector
    llm_judge_score: float   # 0.0 to 1.0 from GPT judgment
    reasoning: str           # Why this story was selected
    context_factors: List[str]  # Contextual factors
    distance: float          # Raw vector distance from pgvector
    
    @property
    def combined_score(self) -> float:
        """Weighted combination optimized for Supabase vectors"""
        return (
            0.5 * self.vector_similarity +   # pgvector is very good
            0.4 * self.llm_judge_score +     # LLM adds contextual reasoning
            0.1 * (1.0 - min(self.distance, 1.0))  # Distance as tiebreaker
        )

class StoryMatcher:
    """Story matcher using Supabase pgvector for semantic search"""
    
    def __init__(self, bot_id: str, settings):
        self.bot_id = bot_id
        self.settings = settings
        
        # Initialize Supabase client
        from supabase import create_client, Client
        self.supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
        
        # Embedding model for query embeddings
        self.embedding_model_name = getattr(settings, 'embedding_model', 'text-embedding-3-small')
        
        # LLM judge cache
        self.judge_cache = {}
        
        # Initialize embedding functions
        self._embedding_cache = {}
    
    async def initialize_story_embeddings(self, stories: List[Story]) -> bool:
        """Initialize or update story embeddings in Supabase"""
        try:
            logger.info(f"Initializing embeddings for {len(stories)} stories in Supabase...")
            
            # Get existing embeddings to avoid re-computing
            existing_embeddings = await self._get_existing_embeddings()
            existing_story_ids = {emb['story_id'] for emb in existing_embeddings}
            
            # Find stories that need embeddings
            stories_to_embed = [
                story for story in stories 
                if story.id not in existing_story_ids
            ]
            
            if not stories_to_embed:
                logger.info("All stories already have embeddings")
                return True
            
            # Generate embeddings for new stories
            embeddings_batch = []
            for story in stories_to_embed:
                embedding_text = self._prepare_story_text(story)
                embedding = await self._generate_embedding(embedding_text)
                
                embedding_record = {
                    'story_id': story.id,
                    'bot_id': story.bot_id,
                    'content': embedding_text,
                    'embedding': embedding,
                    'created_at': datetime.now().isoformat()
                }
                embeddings_batch.append(embedding_record)
            
            # Batch insert embeddings
            if embeddings_batch:
                result = self.supabase.table('story_embeddings').insert(embeddings_batch).execute()
                logger.info(f"✅ Added {len(embeddings_batch)} story embeddings to Supabase")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize story embeddings: {e}")
            return False
    
    async def should_share_story(self, 
                               conversation_context: str,
                               chat_memory: ChatMemory) -> Dict:
        """
        Determine if a story should be shared and get the best match
        
        Returns:
        {
            "should_share": bool,
            "confidence": float,
            "story_match": StoryMatch or None,
            "reasoning": str
        }
        """
        try:
            # Generate embedding for conversation context
            enhanced_context = self._build_enhanced_context(conversation_context, chat_memory)
            query_embedding = await self._generate_embedding(enhanced_context)
            
            # Get best story match
            matches = await self._vector_similarity_search(
                query_embedding, 
                chat_memory.stories_shared,
                max_candidates=3,  # Get top 3 for LLM judge
                threshold=0.6  # Lower threshold for should_share decision
            )
            
            if not matches:
                return {
                    "should_share": False,
                    "confidence": 0.0,
                    "story_match": None,
                    "reasoning": "No stories found above similarity threshold"
                }
            
            # Use LLM to judge if story sharing is appropriate
            best_match = await self._evaluate_story_sharing_appropriateness(
                conversation_context, matches[0], chat_memory
            )
            
            # Decision logic based on multiple factors
            should_share = self._make_sharing_decision(best_match, chat_memory)
            
            return {
                "should_share": should_share["should_share"],
                "confidence": should_share["confidence"],
                "story_match": best_match if should_share["should_share"] else None,
                "reasoning": should_share["reasoning"]
            }
            
        except Exception as e:
            logger.error(f"Error in story sharing decision: {e}")
            return {
                "should_share": False,
                "confidence": 0.0,
                "story_match": None,
                "reasoning": f"Error in story evaluation: {str(e)}"
            }
    
    async def find_relevant_stories(self, 
                                  conversation_context: str,
                                  chat_memory: ChatMemory,
                                  max_stories: int = 3) -> List[StoryMatch]:
        """Find and rank relevant stories using vector search + LLM judge"""
        
        try:
            # Generate embedding for conversation context
            enhanced_context = self._build_enhanced_context(conversation_context, chat_memory)
            query_embedding = await self._generate_embedding(enhanced_context)
            
            # Vector similarity search in Supabase
            vector_candidates = await self._vector_similarity_search(
                query_embedding, 
                chat_memory.stories_shared,
                max_candidates=max_stories * 2,
                threshold=0.7
            )
            
            if not vector_candidates:
                logger.info("No vector candidates found above threshold")
                return []
            
            # LLM judge for contextual ranking
            final_matches = await self._llm_judge_ranking(
                conversation_context, vector_candidates, chat_memory
            )
            
            # Apply final selection criteria
            selected_matches = self._apply_selection_criteria(
                final_matches, chat_memory, max_stories
            )
            
            logger.info(f"Selected {len(selected_matches)} stories using Supabase vectors")
            return selected_matches
            
        except Exception as e:
            logger.error(f"Error in vector story matching: {e}")
            return []
    
    async def _vector_similarity_search(self, 
                                      query_embedding: List[float],
                                      excluded_story_ids: List[str],
                                      max_candidates: int,
                                      threshold: float) -> List[Dict]:
        """Perform vector similarity search using Supabase pgvector"""
        try:
            result = self.supabase.rpc(
                'match_stories',
                {
                    'query_embedding': query_embedding,
                    'bot_id': self.bot_id,
                    'excluded_story_ids': excluded_story_ids,
                    'match_threshold': 1.0 - threshold,  # Convert similarity to distance
                    'match_count': max_candidates
                }
            ).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Vector similarity search failed: {e}")
            return []
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using OpenAI's embedding API"""
        
        # Check cache first
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        try:
            response = await openai.Embedding.acreate(
                model=self.embedding_model_name,
                input=text
            )
            
            embedding = response['data'][0]['embedding']
            
            # Cache the result
            self._embedding_cache[text] = embedding
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise
    
    def _prepare_story_text(self, story: Story) -> str:
        """Prepare story text for embedding generation"""
        return f"{story.title}. {story.content}. Themes: {', '.join(story.themes)}. Emotional tone: {story.emotional_tone}. Context: {', '.join(story.context_hints)}"
    
    def _build_enhanced_context(self, context: str, chat_memory: ChatMemory) -> str:
        """Build enhanced context for better vector matching"""
        context_parts = [context]
        
        # Add conversation history
        if chat_memory.conversation_themes:
            context_parts.append(f"Conversation themes: {', '.join(chat_memory.conversation_themes[-5:])}")
        
        # Add user interests
        if chat_memory.user_interests:
            context_parts.append(f"User interests: {', '.join(chat_memory.user_interests)}")
        
        # Add relationship stage for better context
        context_parts.append(f"Relationship stage: {chat_memory.relationship_stage}")
        
        return ". ".join(context_parts)
    
    async def _get_existing_embeddings(self) -> List[Dict]:
        """Get existing story embeddings from Supabase"""
        try:
            result = self.supabase.table('story_embeddings')\
                .select('story_id, bot_id')\
                .eq('bot_id', self.bot_id)\
                .execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Failed to get existing embeddings: {e}")
            return []
    
    async def _evaluate_story_sharing_appropriateness(self,
                                                    context: str,
                                                    candidate: Dict,
                                                    chat_memory: ChatMemory) -> StoryMatch:
        """Use LLM to evaluate if story sharing is appropriate in this context"""
        
        try:
            prompt = f"""
            CONVERSATION CONTEXT: {context}
            RELATIONSHIP STAGE: {chat_memory.relationship_stage}
            MESSAGE COUNT: {chat_memory.message_count}
            
            CANDIDATE STORY:
            Title: {candidate['title']}
            Content: {candidate['content']}
            Themes: {', '.join(candidate['themes'])}
            Emotional tone: {candidate['emotional_tone']}
            Vector similarity: {candidate['similarity']:.3f}
            
            TASK: Evaluate if sharing this story is appropriate right now.
            Consider: conversation flow, emotional appropriateness, relationship stage, story relevance.
            
            Respond in JSON format:
            {{
                "appropriateness_score": 0.85,
                "reasoning": "Perfect emotional match for user's situation...",
                "factors": ["emotional_resonance", "timing", "relevance"],
                "should_share_now": true
            }}
            """
            
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert at determining when personal story sharing is appropriate in conversations."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            # Parse response
            llm_response = response.choices[0].message.content
            start_idx = llm_response.find('{')
            end_idx = llm_response.rfind('}') + 1
            json_str = llm_response[start_idx:end_idx]
            
            judgment = json.loads(json_str)
            
            # Create StoryMatch object
            story = Story(
                id=candidate['story_id'],
                bot_id=candidate['bot_id'],
                title=candidate['title'],
                content=candidate['content'],
                themes=candidate['themes'],
                triggers=candidate['triggers'],
                emotional_tone=candidate['emotional_tone'],
                context_hints=candidate['context_hints'],
                used_count=candidate['used_count']
            )
            
            return StoryMatch(
                story=story,
                vector_similarity=candidate['similarity'],
                llm_judge_score=judgment.get('appropriateness_score', 0.0),
                reasoning=judgment.get('reasoning', 'No reasoning provided'),
                context_factors=judgment.get('factors', []),
                distance=candidate['distance']
            )
            
        except Exception as e:
            logger.error(f"Error evaluating story appropriateness: {e}")
            # Fallback to basic match
            story = Story(
                id=candidate['story_id'],
                bot_id=candidate['bot_id'],
                title=candidate['title'],
                content=candidate['content'],
                themes=candidate['themes'],
                triggers=candidate['triggers'],
                emotional_tone=candidate['emotional_tone'],
                context_hints=candidate['context_hints'],
                used_count=candidate['used_count']
            )
            
            return StoryMatch(
                story=story,
                vector_similarity=candidate['similarity'],
                llm_judge_score=candidate['similarity'],
                reasoning="Fallback to vector similarity",
                context_factors=["vector_similarity"],
                distance=candidate['distance']
            )
    
    def _make_sharing_decision(self, story_match: StoryMatch, chat_memory: ChatMemory) -> Dict:
        """Make final decision on whether to share a story"""
        
        # Base decision on combined score
        base_confidence = story_match.combined_score
        
        # Adjust based on conversation stage
        stage_multipliers = {
            "new": 0.7,          # Be more conservative with new users
            "warming_up": 1.0,   # Normal sharing
            "familiar": 1.2      # More liberal sharing with familiar users
        }
        
        stage_multiplier = stage_multipliers.get(chat_memory.relationship_stage, 1.0)
        adjusted_confidence = base_confidence * stage_multiplier
        
        # Adjust based on recent story sharing
        if len(chat_memory.stories_shared) >= 3:
            # Reduce likelihood if we've shared many stories recently
            adjusted_confidence *= 0.8
        
        # Decision threshold
        threshold = 0.6  # Adjustable based on bot personality
        should_share = adjusted_confidence >= threshold
        
        # Build reasoning
        if should_share:
            reasoning = f"Story sharing appropriate: {story_match.reasoning}. Confidence: {adjusted_confidence:.3f}"
        else:
            reasoning = f"Story sharing not recommended: confidence {adjusted_confidence:.3f} below threshold {threshold}"
        
        return {
            "should_share": should_share,
            "confidence": adjusted_confidence,
            "reasoning": reasoning
        }
    
    async def _llm_judge_ranking(self, 
                               context: str,
                               vector_candidates: List[Dict],
                               chat_memory: ChatMemory) -> List[StoryMatch]:
        """Use LLM to judge and rank vector candidates"""
        
        if not vector_candidates:
            return []
        
        # Create cache key
        candidate_ids = [c['story_id'] for c in vector_candidates]
        cache_key = f"{hash(context)}_{hash(str(candidate_ids))}"
        
        if cache_key in self.judge_cache:
            return self.judge_cache[cache_key]
        
        try:
            # Build judgment prompt
            prompt = self._build_llm_judgment_prompt(context, vector_candidates, chat_memory)
            
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are an expert at matching personal stories to conversation contexts. Provide relevance scores from 0.0 to 1.0 with clear reasoning."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            # Parse LLM response
            judged_stories = self._parse_llm_response(response.choices[0].message.content, vector_candidates)
            
            # Cache results
            self.judge_cache[cache_key] = judged_stories
            
            return judged_stories
            
        except Exception as e:
            logger.error(f"LLM judge ranking failed: {e}")
            # Fallback to vector scores only
            return self._create_fallback_matches(vector_candidates)
    
    def _build_llm_judgment_prompt(self, 
                                  context: str,
                                  candidates: List[Dict],
                                  chat_memory: ChatMemory) -> str:
        """Build prompt for LLM judgment"""
        
        prompt_parts = [
            f"CONVERSATION CONTEXT: {context}",
            f"RELATIONSHIP STAGE: {chat_memory.relationship_stage}",
            f"RECENT THEMES: {', '.join(chat_memory.conversation_themes[-5:]) if chat_memory.conversation_themes else 'None'}",
            "",
            "CANDIDATE STORIES (already pre-filtered by vector similarity):",
            ""
        ]
        
        for i, candidate in enumerate(candidates):
            prompt_parts.extend([
                f"STORY {i+1}:",
                f"Title: {candidate['title']}",
                f"Content: {candidate['content']}",
                f"Themes: {', '.join(candidate['themes'])}",
                f"Emotional tone: {candidate['emotional_tone']}",
                f"Vector similarity: {candidate['similarity']:.3f}",
                ""
            ])
        
        prompt_parts.extend([
            "TASK: Rate each story's contextual relevance (0.0-1.0) and provide reasoning.",
            "Consider: emotional appropriateness, conversation flow, user relationship stage.",
            "",
            "Respond in JSON format:",
            '{"evaluations": [{"story_index": 1, "score": 0.85, "reasoning": "Perfect emotional match...", "factors": ["emotional_resonance", "theme_alignment"]}]}'
        ])
        
        return "\n".join(prompt_parts)
    
    def _parse_llm_response(self, llm_response: str, candidates: List[Dict]) -> List[StoryMatch]:
        """Parse LLM response into StoryMatch objects"""
        
        try:
            # Extract JSON from response
            start_idx = llm_response.find('{')
            end_idx = llm_response.rfind('}') + 1
            json_str = llm_response[start_idx:end_idx]
            
            judgment_data = json.loads(json_str)
            
            matches = []
            for evaluation in judgment_data.get("evaluations", []):
                story_idx = evaluation.get("story_index", 1) - 1
                
                if 0 <= story_idx < len(candidates):
                    candidate = candidates[story_idx]
                    
                    # Reconstruct Story object from candidate data
                    story = Story(
                        id=candidate['story_id'],
                        bot_id=candidate['bot_id'],
                        title=candidate['title'],
                        content=candidate['content'],
                        themes=candidate['themes'],
                        triggers=candidate['triggers'],
                        emotional_tone=candidate['emotional_tone'],
                        context_hints=candidate['context_hints'],
                        used_count=candidate['used_count']
                    )
                    
                    match = StoryMatch(
                        story=story,
                        vector_similarity=candidate['similarity'],
                        llm_judge_score=evaluation.get("score", 0.0),
                        reasoning=evaluation.get("reasoning", "No reasoning provided"),
                        context_factors=evaluation.get("factors", []),
                        distance=candidate['distance']
                    )
                    
                    matches.append(match)
            
            return matches
            
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return self._create_fallback_matches(candidates)
    
    def _create_fallback_matches(self, candidates: List[Dict]) -> List[StoryMatch]:
        """Create fallback matches using only vector similarity"""
        
        matches = []
        for candidate in candidates:
            story = Story(
                id=candidate['story_id'],
                bot_id=candidate['bot_id'],
                title=candidate['title'],
                content=candidate['content'],
                themes=candidate['themes'],
                triggers=candidate['triggers'],
                emotional_tone=candidate['emotional_tone'],
                context_hints=candidate['context_hints'],
                used_count=candidate['used_count']
            )
            
            match = StoryMatch(
                story=story,
                vector_similarity=candidate['similarity'],
                llm_judge_score=candidate['similarity'],  # Use vector score as fallback
                reasoning="Vector similarity only (LLM judge unavailable)",
                context_factors=["vector_similarity"],
                distance=candidate['distance']
            )
            
            matches.append(match)
        
        return matches
    
    def _apply_selection_criteria(self,
                                matches: List[StoryMatch],
                                chat_memory: ChatMemory,
                                max_stories: int) -> List[StoryMatch]:
        """Apply final selection criteria"""
        
        # Boost stories that align with user interests
        for match in matches:
            interest_boost = 0.0
            for interest in chat_memory.user_interests:
                if interest.lower() in [theme.lower() for theme in match.story.themes]:
                    interest_boost += 0.1
            
            match.llm_judge_score = min(1.0, match.llm_judge_score + interest_boost)
        
        # Boost less-used stories for variety
        for match in matches:
            if match.story.used_count == 0:
                match.vector_similarity += 0.1
            elif match.story.used_count < 3:
                match.vector_similarity += 0.05
        
        # Sort by combined score and return top matches
        matches.sort(key=lambda x: x.combined_score, reverse=True)
        return matches[:max_stories]