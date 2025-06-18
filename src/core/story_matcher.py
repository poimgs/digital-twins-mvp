import logging
from typing import List
import tiktoken

from ..models import Story, ChatMemory

logger = logging.getLogger(__name__)

class StoryMatcher:
    """Intelligent story selection based on conversation context"""
    
    def __init__(self, stories: List[Story]):
        self.stories = stories
        self.tokenizer = tiktoken.get_encoding("o200k_base")
    
    def find_relevant_stories(self, 
                            conversation_context: str, 
                            chat_memory: ChatMemory,
                            max_stories: int = 3) -> List[Story]:
        """Find stories that match the current conversation context"""
        
        # Filter out already shared stories
        available_stories = [
            story for story in self.stories 
            if story.id not in chat_memory.stories_shared
        ]
        
        if not available_stories:
            return []
        
        # Score stories based on relevance
        story_scores = []
        context_lower = conversation_context.lower()
        
        for story in available_stories:
            score = 0
            
            # Check theme matches
            for theme in story.themes:
                if theme.lower() in context_lower:
                    score += 3
            
            # Check trigger words
            for trigger in story.triggers:
                if trigger.lower() in context_lower:
                    score += 2
            
            # Check context hints
            for hint in story.context_hints:
                if hint.lower() in context_lower:
                    score += 1
            
            # Boost less-used stories
            if story.used_count == 0:
                score += 1
            elif story.used_count < 3:
                score += 0.5
            
            # Consider user interests
            for interest in chat_memory.user_interests:
                if interest.lower() in [t.lower() for t in story.themes]:
                    score += 1
            
            if score > 0:
                story_scores.append((story, score))
        
        # Sort by score and return top matches
        story_scores.sort(key=lambda x: x[1], reverse=True)
        return [story for story, _ in story_scores[:max_stories]]