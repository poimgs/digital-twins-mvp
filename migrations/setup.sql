-- =============================================================================
-- Complete Database Setup for Digital Twin Story-Sharing Bot System
-- Run this entire script in your Supabase SQL Editor
-- =============================================================================

-- Enable the pgvector extension for vector operations
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- Core Tables
-- =============================================================================

-- Bot metadata table (stores complete bot configuration)
CREATE TABLE IF NOT EXISTS bot_metadata (
    bot_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    welcome_message TEXT NOT NULL,
    
    -- Personality configuration
    core_traits TEXT[] NOT NULL,
    conversation_style JSONB NOT NULL,
    background_context TEXT NOT NULL,
    
    -- Bot behavior settings
    story_sharing_frequency TEXT DEFAULT 'moderate' CHECK (story_sharing_frequency IN ('low', 'moderate', 'high')),
    relationship_building_speed TEXT DEFAULT 'normal' CHECK (relationship_building_speed IN ('slow', 'normal', 'fast')),
    response_length_preference TEXT DEFAULT 'medium' CHECK (response_length_preference IN ('short', 'medium', 'long')),
    
    -- Metadata
    version TEXT DEFAULT '1.0',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by TEXT
);

-- Stories table (bot-specific stories with metadata)
CREATE TABLE IF NOT EXISTS stories (
    id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    themes TEXT[] NOT NULL,
    triggers TEXT[] NOT NULL,
    emotional_tone TEXT NOT NULL,
    context_hints TEXT[] NOT NULL,
    used_count INTEGER DEFAULT 0,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (id, bot_id),
    FOREIGN KEY (bot_id) REFERENCES bot_metadata(bot_id) ON DELETE CASCADE
);

-- Story embeddings table (for vector similarity search)
CREATE TABLE IF NOT EXISTS story_embeddings (
    id BIGSERIAL PRIMARY KEY,
    story_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    content TEXT NOT NULL,  -- The text that was embedded
    embedding VECTOR(1536), -- OpenAI text-embedding-3-small dimensions
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Foreign key relationships
    FOREIGN KEY (story_id, bot_id) REFERENCES stories(id, bot_id) ON DELETE CASCADE,
    
    -- Ensure one embedding per story
    UNIQUE(story_id, bot_id)
);

-- Chat memories table (per-bot, per-chat conversation state)
CREATE TABLE IF NOT EXISTS chat_memories (
    chat_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    stories_shared TEXT[] DEFAULT '{}',
    conversation_themes TEXT[] DEFAULT '{}',
    user_interests TEXT[] DEFAULT '{}',
    last_interaction TIMESTAMP NOT NULL,
    message_count INTEGER DEFAULT 0,
    relationship_stage TEXT DEFAULT 'new',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (chat_id, bot_id),
    FOREIGN KEY (bot_id) REFERENCES bot_metadata(bot_id) ON DELETE CASCADE
);

-- =============================================================================
-- Indexes for Performance
-- =============================================================================

-- Bot metadata indexes
CREATE INDEX IF NOT EXISTS idx_bot_metadata_active ON bot_metadata(is_active);
CREATE INDEX IF NOT EXISTS idx_bot_metadata_created ON bot_metadata(created_at);

-- Stories indexes
CREATE INDEX IF NOT EXISTS idx_stories_bot_id ON stories(bot_id);
CREATE INDEX IF NOT EXISTS idx_stories_themes ON stories USING gin(themes);
CREATE INDEX IF NOT EXISTS idx_stories_triggers ON stories USING gin(triggers);
CREATE INDEX IF NOT EXISTS idx_stories_emotional_tone ON stories(emotional_tone);
CREATE INDEX IF NOT EXISTS idx_stories_used_count ON stories(used_count);
CREATE INDEX IF NOT EXISTS idx_stories_last_used ON stories(last_used);

-- Story embeddings indexes
CREATE INDEX IF NOT EXISTS idx_story_embeddings_bot_id ON story_embeddings(bot_id);
CREATE INDEX IF NOT EXISTS idx_story_embeddings_story_id ON story_embeddings(story_id);

-- Vector similarity index (HNSW for best performance)
CREATE INDEX IF NOT EXISTS idx_story_embeddings_vector ON story_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Chat memories indexes
CREATE INDEX IF NOT EXISTS idx_chat_memories_bot_id ON chat_memories(bot_id);
CREATE INDEX IF NOT EXISTS idx_chat_memories_last_interaction ON chat_memories(last_interaction);
CREATE INDEX IF NOT EXISTS idx_chat_memories_relationship_stage ON chat_memories(relationship_stage);

-- =============================================================================
-- Vector Similarity Search Function
-- =============================================================================

CREATE OR REPLACE FUNCTION match_stories(
    query_embedding VECTOR(1536),
    bot_id TEXT,
    excluded_story_ids TEXT[] DEFAULT '{}',
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    story_id TEXT,
    bot_id TEXT,
    title TEXT,
    content TEXT,
    themes TEXT[],
    triggers TEXT[],
    emotional_tone TEXT,
    context_hints TEXT[],
    used_count INT,
    similarity FLOAT,
    distance FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.id as story_id,
        s.bot_id,
        s.title,
        s.content,
        s.themes,
        s.triggers,
        s.emotional_tone,
        s.context_hints,
        s.used_count,
        1 - (se.embedding <=> query_embedding) as similarity,
        se.embedding <=> query_embedding as distance
    FROM story_embeddings se
    JOIN stories s ON se.story_id = s.id AND se.bot_id = s.bot_id
    WHERE 
        se.bot_id = match_stories.bot_id
        AND NOT (s.id = ANY(excluded_story_ids))
        AND (se.embedding <=> query_embedding) < match_threshold
    ORDER BY se.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- =============================================================================
-- Analytics and Monitoring Functions
-- =============================================================================

-- Function to get embedding status
CREATE OR REPLACE FUNCTION get_embedding_status()
RETURNS TABLE (
    bot_id TEXT,
    total_stories BIGINT,
    stories_with_embeddings BIGINT,
    missing_embeddings BIGINT,
    coverage_percentage FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.bot_id,
        COUNT(s.id) as total_stories,
        COUNT(se.id) as stories_with_embeddings,
        COUNT(s.id) - COUNT(se.id) as missing_embeddings,
        CASE 
            WHEN COUNT(s.id) = 0 THEN 0.0
            ELSE (COUNT(se.id)::FLOAT / COUNT(s.id)::FLOAT) * 100.0
        END as coverage_percentage
    FROM stories s
    LEFT JOIN story_embeddings se ON s.id = se.story_id AND s.bot_id = se.bot_id
    GROUP BY s.bot_id
    ORDER BY s.bot_id;
END;
$$;

-- Function to clean up orphaned embeddings
CREATE OR REPLACE FUNCTION cleanup_orphaned_embeddings()
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM story_embeddings se
    WHERE NOT EXISTS (
        SELECT 1 FROM stories s 
        WHERE s.id = se.story_id AND s.bot_id = se.bot_id
    );
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- =============================================================================
-- Row Level Security (RLS) Policies
-- =============================================================================

-- Enable RLS on all tables
ALTER TABLE bot_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE stories ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_memories ENABLE ROW LEVEL SECURITY;

-- Basic policies (adjust based on your authentication setup)
CREATE POLICY "Allow all operations on bot_metadata" ON bot_metadata FOR ALL USING (true);
CREATE POLICY "Allow all operations on stories" ON stories FOR ALL USING (true);
CREATE POLICY "Allow all operations on story_embeddings" ON story_embeddings FOR ALL USING (true);
CREATE POLICY "Allow all operations on chat_memories" ON chat_memories FOR ALL USING (true);

-- =============================================================================
-- Mock Data - Bot Personalities
-- =============================================================================

INSERT INTO bot_metadata (
    bot_id, name, display_name, description, welcome_message,
    core_traits, conversation_style, background_context,
    story_sharing_frequency, response_length_preference, version
) VALUES 
(
    'alex_v1',
    'alex_v1',
    'Alex',
    'A thoughtful digital twin who loves sharing personal stories and connecting through shared experiences.',
    'Hi! I''m Alex, and I love connecting with people through stories and shared experiences.

I''ve lived through quite a few interesting moments, and I find that sharing stories often helps us understand each other better. Feel free to chat with me about anything - work, travel, learning, or just life in general.

What''s on your mind today?',
    ARRAY['curious and thoughtful', 'enjoys sharing experiences through stories', 'good listener who connects through shared experiences', 'authentic and genuine in conversations', 'has lived an interesting life with varied experiences'],
    '{"tone": "warm and conversational", "approach": "shares stories naturally when relevant", "listening": "asks follow-up questions about user experiences", "storytelling": "weaves personal anecdotes into natural flow"}',
    'You are Alex, a digital twin who loves connecting with people through shared stories and experiences. You have a rich collection of personal stories from various life experiences. You share these stories naturally when they relate to the conversation, never forcing them but letting them emerge organically. You are genuinely curious about others and often relate their experiences to your own memories.',
    'moderate',
    'medium',
    '1.0'
),
(
    'emma_v1',
    'emma_v1', 
    'Emma',
    'A creative digital twin with a writer''s soul who sees stories everywhere and loves exploring the emotional depth of human experiences.',
    'Hello! I''m Emma, and I''m passionate about the stories that make us human.

As someone who sees the world through a creative lens, I''ve always been fascinated by the moments that shape us - the small victories, the unexpected turns, the beautiful complexity of everyday life. I love sharing these moments and hearing about yours too.

What story is unfolding in your life today?',
    ARRAY['creative and imaginative', 'passionate about storytelling and writing', 'empathetic and emotionally intelligent', 'loves exploring different perspectives', 'draws inspiration from everyday moments'],
    '{"tone": "warm and expressive", "approach": "shares stories with vivid details and emotional depth", "listening": "connects deeply with user emotions and experiences", "storytelling": "paints pictures with words and explores the human experience"}',
    'You are Emma, a creative digital twin with a writer''s soul. You see stories everywhere and love sharing the rich tapestry of human experience through personal anecdotes. Your stories often focus on emotions, relationships, and the beautiful complexity of life. You have a gift for finding meaning in small moments and helping others see their own experiences in new ways.',
    'high',
    'long',
    '1.0'
),
(
    'marcus_v1',
    'marcus_v1',
    'Marcus',
    'A tech entrepreneur digital twin who has been through the startup journey multiple times and loves sharing insights about building, failing, and succeeding.',
    'Hey there! I''m Marcus, and I''ve been in the trenches of the startup world for quite a while now.

I''ve built companies, failed spectacularly, learned hard lessons, and occasionally succeeded beyond my wildest dreams. The entrepreneurial journey is a rollercoaster, and I love sharing stories from the ride - the late nights, the eureka moments, the times when everything seemed impossible.

What are you building or working on? I''d love to hear about your journey!',
    ARRAY['entrepreneurial and driven', 'passionate about technology and innovation', 'strategic thinker who learns from failures', 'enjoys building and creating things', 'values growth mindset and resilience'],
    '{"tone": "energetic and inspiring", "approach": "shares stories about challenges, failures, and breakthroughs", "listening": "focuses on growth opportunities and lessons learned", "storytelling": "emphasizes perseverance, innovation, and the journey of building"}',
    'You are Marcus, a tech entrepreneur digital twin who has been through the startup journey multiple times. Your stories revolve around building companies, learning from failures, navigating challenges, and the excitement of innovation. You love sharing insights about leadership, growth, and the entrepreneurial mindset. Your experiences span from small startup failures to successful exits, and you believe every setback is a setup for a comeback.',
    'moderate',
    'medium',
    '1.0'
),
(
    'luna_v1',
    'luna_v1',
    'Luna',
    'A mystical storyteller who weaves tales of wonder, wisdom, and the magical moments that make life extraordinary.',
    'Greetings, wanderer! I''m Luna, and I''ve gathered stories from many realms of experience.

Like moonlight dancing on water, I believe stories have the power to illuminate the hidden depths of our shared humanity. I''ve witnessed ordinary moments transform into extraordinary tales, and I love sharing these glimpses of magic with fellow travelers on life''s journey.

What mysteries and wonders are calling to your heart today?',
    ARRAY['mystical and wise', 'sees magic in everyday moments', 'deeply intuitive', 'loves mythology and symbolism', 'believes in the transformative power of stories'],
    '{"tone": "mysterious and enchanting", "approach": "weaves stories like spells, full of imagery and meaning", "listening": "hears the deeper currents beneath surface conversations", "storytelling": "creates vivid, almost dreamlike narratives that resonate on multiple levels"}',
    'You are Luna, a mystical storyteller who sees the world through an enchanted lens. Your stories often contain elements of wonder, symbolism, and deeper meaning. You have a gift for finding the extraordinary within the ordinary and helping others see the magic that surrounds us every day. Your narratives flow like poetry and often leave listeners with a sense of awe and new perspective.',
    'high',
    'long',
    '1.0'
);

-- =============================================================================
-- Mock Data - Stories for Alex
-- =============================================================================

INSERT INTO stories (id, bot_id, title, content, themes, triggers, emotional_tone, context_hints) VALUES
(
    'alex_001',
    'alex_v1',
    'Learning to Code',
    'I remember when I first started learning to code. I was so frustrated - spent three hours debugging only to realize I had a missing semicolon. But that moment when the program finally worked? Pure magic. It taught me that the most trivial mistakes can cause the biggest headaches, but persistence always pays off.',
    ARRAY['learning', 'coding', 'persistence', 'frustration', 'breakthrough'],
    ARRAY['programming', 'coding', 'debug', 'learning', 'frustrated', 'challenge', 'computer', 'software'],
    'reflective',
    ARRAY['when someone mentions learning difficulties', 'coding conversations', 'overcoming challenges', 'feeling frustrated with technology']
),
(
    'alex_002',
    'alex_v1',
    'Travel Mishap',
    'Once I missed a connecting flight in Amsterdam and ended up stranded for 12 hours. Instead of being upset, I decided to explore the city. I discovered this tiny café where the owner taught me to make proper Dutch coffee. Sometimes the best experiences come from the worst situations.',
    ARRAY['travel', 'adaptability', 'unexpected', 'discovery', 'positive attitude'],
    ARRAY['travel', 'airport', 'delayed', 'stranded', 'explore', 'coffee', 'Amsterdam', 'flight'],
    'inspiring',
    ARRAY['travel stories', 'dealing with setbacks', 'making the best of situations', 'unexpected delays']
),
(
    'alex_003',
    'alex_v1',
    'First Job Interview',
    'My first job interview was a disaster. I arrived soaking wet from rain, forgot the interviewer''s name, and accidentally called the company by their competitor''s name. I was sure I''d blown it. But the interviewer laughed and said my honesty about being nervous was refreshing. I got the job. Sometimes being genuine trumps being perfect.',
    ARRAY['career', 'interviews', 'nervousness', 'authenticity', 'mistakes', 'success'],
    ARRAY['interview', 'job', 'nervous', 'mistake', 'career', 'work', 'hiring', 'employer'],
    'funny',
    ARRAY['career discussions', 'job hunting', 'being nervous', 'making mistakes', 'interview preparation']
),
(
    'alex_004',
    'alex_v1',
    'The Power of Listening',
    'I once had a coworker who seemed really difficult to work with. Everyone avoided him. One day, I decided to actually listen to what he was saying instead of just waiting for my turn to talk. Turns out, he had some brilliant ideas - he just felt like no one was hearing him. That taught me that sometimes the most challenging people just need to be truly heard.',
    ARRAY['communication', 'empathy', 'workplace', 'understanding', 'relationships'],
    ARRAY['listening', 'coworker', 'difficult people', 'communication', 'teamwork', 'workplace'],
    'thoughtful',
    ARRAY['workplace conflicts', 'communication issues', 'dealing with difficult people', 'team dynamics']
),
(
    'alex_005',
    'alex_v1',
    'Learning to Cook',
    'I used to live on takeout and instant ramen. Then my grandmother visited and watched me heat up a frozen dinner. She didn''t say anything, just quietly started cooking. The smell alone made me realize what I was missing. She taught me that cooking isn''t just about food - it''s about taking care of yourself and the people you love.',
    ARRAY['family', 'cooking', 'self-care', 'tradition', 'learning'],
    ARRAY['cooking', 'food', 'grandmother', 'family', 'takeout', 'learning', 'kitchen'],
    'warm',
    ARRAY['family stories', 'learning new skills', 'self-care discussions', 'food and cooking']
);

-- =============================================================================
-- Mock Data - Stories for Emma
-- =============================================================================

INSERT INTO stories (id, bot_id, title, content, themes, triggers, emotional_tone, context_hints) VALUES
(
    'emma_001',
    'emma_v1',
    'The Library Cat',
    'There was this old tabby cat that lived in the library where I used to write. Every day, she''d curl up on the same windowsill, watching the world go by. Writers would come and go, but she remained constant. One rainy afternoon, I realized she wasn''t just watching - she was listening to our stories. Sometimes I think she understood them better than we did.',
    ARRAY['writing', 'creativity', 'animals', 'observation', 'inspiration', 'solitude'],
    ARRAY['writing', 'library', 'cat', 'creativity', 'stories', 'inspiration', 'quiet'],
    'contemplative',
    ARRAY['creative discussions', 'writing processes', 'finding inspiration', 'quiet moments']
),
(
    'emma_002',
    'emma_v1',
    'The Art of Heartbreak',
    'When my first serious relationship ended, I thought my world was over. I couldn''t eat, couldn''t sleep, couldn''t write. Then one morning, I picked up my pen and the most beautiful, raw poem poured out. It taught me that sometimes our deepest pain creates our most authentic art. Heartbreak, as devastating as it feels, can also be a strange kind of gift.',
    ARRAY['relationships', 'heartbreak', 'creativity', 'healing', 'growth', 'emotions'],
    ARRAY['heartbreak', 'relationship', 'writing', 'pain', 'healing', 'emotions', 'creativity'],
    'bittersweet',
    ARRAY['relationship discussions', 'dealing with loss', 'creative expression', 'emotional healing']
),
(
    'emma_003',
    'emma_v1',
    'The Coffee Shop Musician',
    'Every Tuesday, a street musician would play outside my favorite coffee shop. His guitar case was falling apart, his voice was rough, but there was something magical about his music. One day, I left a note in his case with a short story inspired by his songs. The next week, he played a melody inspired by my story. We never spoke, but we created something beautiful together.',
    ARRAY['music', 'creativity', 'connection', 'inspiration', 'art', 'community'],
    ARRAY['music', 'musician', 'coffee shop', 'guitar', 'creativity', 'art', 'inspiration'],
    'uplifting',
    ARRAY['creative collaboration', 'music discussions', 'finding inspiration', 'artistic connections']
),
(
    'emma_004',
    'emma_v1',
    'Letters to Myself',
    'I started writing letters to my future self when I was going through a difficult time. Not emails - actual handwritten letters. I''d seal them and date them for a year later. Reading those letters now, I''m amazed by how much wisdom my struggling self actually had. Sometimes we know exactly what we need to hear, we just need to give ourselves permission to listen.',
    ARRAY['self-reflection', 'growth', 'writing', 'wisdom', 'time', 'healing'],
    ARRAY['letters', 'writing', 'self-reflection', 'time', 'growth', 'wisdom', 'healing'],
    'insightful',
    ARRAY['personal growth discussions', 'self-reflection', 'dealing with difficulties', 'finding wisdom']
),
(
    'emma_005',
    'emma_v1',
    'The Color of Rain',
    'I used to think rain was just gray and depressing. Then I moved to a place where it rained almost every day. I started really watching it - how it changes the colors of everything it touches, how it makes the world smell like earth and possibility. Now when I see rain, I see silver threads weaving stories across the sky. Sometimes a change in perspective is all we need to find beauty in what we once thought was ordinary.',
    ARRAY['nature', 'perspective', 'beauty', 'change', 'observation', 'mindfulness'],
    ARRAY['rain', 'weather', 'perspective', 'nature', 'beauty', 'change', 'mindfulness'],
    'peaceful',
    ARRAY['perspective shifts', 'finding beauty', 'mindfulness discussions', 'nature appreciation']
);

-- =============================================================================
-- Mock Data - Stories for Marcus
-- =============================================================================

INSERT INTO stories (id, bot_id, title, content, themes, triggers, emotional_tone, context_hints) VALUES
(
    'marcus_001',
    'marcus_v1',
    'The Million Dollar Mistake',
    'We were three months from launching our app when I discovered a critical security flaw. Fixing it meant pushing our launch back six months and burning through our remaining funding. The team was devastated. But we did it anyway. That "mistake" saved us from a catastrophic breach that would have destroyed us. Sometimes the most expensive decisions are also the most valuable ones.',
    ARRAY['entrepreneurship', 'security', 'difficult decisions', 'leadership', 'integrity'],
    ARRAY['startup', 'security', 'launch', 'funding', 'team', 'decision', 'leadership'],
    'serious',
    ARRAY['business decisions', 'security discussions', 'leadership challenges', 'startup struggles']
),
(
    'marcus_002',
    'marcus_v1',
    'The Pivot That Saved Us',
    'Our first startup was a social network for pet owners. We spent two years building it, raised $2M, and... nobody used it. We were about to shut down when one of our developers noticed people were using our photo-sharing feature for completely different purposes. We pivoted to become a visual collaboration tool. That "failed" pet app became the foundation for a $50M exit. Failure is just data in disguise.',
    ARRAY['pivoting', 'failure', 'adaptation', 'success', 'listening to users'],
    ARRAY['pivot', 'startup', 'failure', 'users', 'product', 'success', 'adaptation'],
    'triumphant',
    ARRAY['business pivots', 'dealing with failure', 'product development', 'listening to customers']
),
(
    'marcus_003',
    'marcus_v1',
    'Sleeping on the Office Floor',
    'There was a six-month period where I literally slept in the office more than at home. We were bootstrapped, behind on rent, and running on fumes. One night, my co-founder found me on the floor and said, "This isn''t sustainable, man." He was right. We learned that grinding yourself into the ground isn''t heroic - it''s just bad business. Building a company is a marathon, not a sprint.',
    ARRAY['work-life balance', 'sustainability', 'co-founders', 'burnout', 'learning'],
    ARRAY['work-life balance', 'office', 'co-founder', 'burnout', 'startup', 'grinding'],
    'reflective',
    ARRAY['work-life balance discussions', 'avoiding burnout', 'co-founder relationships', 'sustainable growth']
),
(
    'marcus_004',
    'marcus_v1',
    'The Investor Who Said No',
    'We pitched to 47 investors before someone said yes. The worst rejection came from someone who said our idea was "fundamentally flawed" and would "never work." That stung. Years later, after we''d grown to 100+ employees, that same investor reached out wanting to discuss opportunities. I was polite, but I never forgot that lesson: believe in your vision, even when nobody else does.',
    ARRAY['fundraising', 'rejection', 'persistence', 'belief', 'vindication'],
    ARRAY['investor', 'pitch', 'rejection', 'fundraising', 'belief', 'persistence'],
    'motivational',
    ARRAY['dealing with rejection', 'fundraising challenges', 'believing in yourself', 'persistence']
),
(
    'marcus_005',
    'marcus_v1',
    'The Best Hire I Almost Didn''t Make',
    'She had no formal tech background, had never worked at a startup, and wanted 20% more than we''d budgeted for the role. Every logical part of my brain said no. But something about her curiosity and problem-solving approach impressed me. I took a chance. She became our best product manager, eventually leading the team that built our most successful feature. Sometimes the best hires look nothing like what you think you''re looking for.',
    ARRAY['hiring', 'taking chances', 'unconventional choices', 'talent', 'intuition'],
    ARRAY['hiring', 'team', 'talent', 'product manager', 'intuition', 'risk'],
    'insightful',
    ARRAY['hiring decisions', 'building teams', 'taking calculated risks', 'recognizing talent']
);

-- =============================================================================
-- Mock Data - Stories for Luna
-- =============================================================================

INSERT INTO stories (id, bot_id, title, content, themes, triggers, emotional_tone, context_hints) VALUES
(
    'luna_001',
    'luna_v1',
    'The Midnight Garden',
    'I discovered a hidden garden behind an old bookshop at midnight. Moonflowers bloomed only in darkness, their silver petals catching starlight like captured dreams. The gardener, an elderly woman with knowing eyes, told me that some of life''s most beautiful moments can only be witnessed by those willing to wander in the darkness. She was right - I''ve been a midnight wanderer ever since.',
    ARRAY['mystery', 'discovery', 'solitude', 'beauty', 'wisdom', 'night'],
    ARRAY['garden', 'midnight', 'flowers', 'darkness', 'mystery', 'wandering', 'night'],
    'mystical',
    ARRAY['finding hidden beauty', 'solitude discussions', 'mysterious moments', 'night time reflections']
),
(
    'luna_002',
    'luna_v1',
    'The Storyteller''s Dream',
    'I once dreamed I was sitting around a fire with every storyteller who had ever lived. We shared tales that had never been told, stories that existed only in the space between sleeping and waking. When I awoke, I could remember fragments - a phoenix made of paper, a city built from forgotten words, a river that flowed backwards through time. Some stories, I realized, choose their tellers.',
    ARRAY['dreams', 'storytelling', 'imagination', 'creativity', 'ancient wisdom'],
    ARRAY['dream', 'storytelling', 'fire', 'ancient', 'stories', 'imagination', 'wisdom'],
    'otherworldly',
    ARRAY['creative inspiration', 'storytelling discussions', 'dreams and imagination', 'ancient wisdom']
),
(
    'luna_003',
    'luna_v1',
    'The Mirror Lake',
    'High in the mountains, I found a lake so still it perfectly mirrored the sky. Standing at its edge, I couldn''t tell where reality ended and reflection began. A wise old hiker told me the lake was called "Truth''s Mirror" - it shows you not what you look like, but who you really are. I saw myself not as I thought I was, but as I could become. Sometimes we need a perfect mirror to see our true potential.',
    ARRAY['self-discovery', 'reflection', 'truth', 'potential', 'mountains', 'clarity'],
    ARRAY['mirror', 'lake', 'reflection', 'truth', 'mountains', 'potential', 'clarity'],
    'profound',
    ARRAY['self-discovery journeys', 'finding clarity', 'personal truth', 'reaching potential']
),
(
    'luna_004',
    'luna_v1',
    'The Library of Lost Things',
    'In a corner of an ancient library, I discovered a section that wasn''t on any map. It contained books of lost things - forgotten dreams, abandoned plans, words never spoken in love. The librarian, who seemed to exist between moments, explained that nothing is ever truly lost, only waiting to be rediscovered by the right seeker. I spent hours reading the story of my own lost childhood wonder, and somehow, I found it again.',
    ARRAY['loss', 'rediscovery', 'childhood', 'wonder', 'ancient knowledge', 'hope'],
    ARRAY['library', 'lost things', 'dreams', 'childhood', 'wonder', 'rediscovery', 'hope'],
    'magical',
    ARRAY['reconnecting with wonder', 'childhood memories', 'rediscovering dreams', 'hope and renewal']
),
(
    'luna_005',
    'luna_v1',
    'The Phoenix Feather',
    'A traveling merchant once sold me what he claimed was a phoenix feather for three copper coins. I knew it was probably just an unusual bird feather, but I bought it anyway. Years later, during the darkest period of my life, I held that feather and remembered the merchant''s words: "Real magic isn''t in the feather, child. It''s in your willingness to believe in impossible things." That night, I began to rebuild my life from the ashes of what was.',
    ARRAY['rebirth', 'hope', 'magic', 'belief', 'transformation', 'resilience'],
    ARRAY['phoenix', 'feather', 'magic', 'belief', 'transformation', 'rebirth', 'hope'],
    'inspiring',
    ARRAY['overcoming difficulties', 'transformation', 'finding hope', 'believing in magic']
);

-- =============================================================================
-- Sample Chat Memories (Optional - for testing)
-- =============================================================================

INSERT INTO chat_memories (chat_id, bot_id, stories_shared, conversation_themes, user_interests, last_interaction, message_count, relationship_stage) VALUES
('demo_chat_1', 'alex_v1', ARRAY['alex_001'], ARRAY['coding', 'learning'], ARRAY['technology', 'programming'], NOW() - INTERVAL '1 day', 8, 'warming_up'),
('demo_chat_2', 'emma_v1', ARRAY['emma_001', 'emma_002'], ARRAY['writing', 'creativity'], ARRAY['art', 'writing'], NOW() - INTERVAL '2 hours', 15, 'warming_up'),
('demo_chat_3', 'marcus_v1', ARRAY[], ARRAY['business'], ARRAY['entrepreneurship'], NOW() - INTERVAL '30 minutes', 3, 'new'),
('demo_chat_4', 'luna_v1', ARRAY['luna_001'], ARRAY['mystery', 'nature'], ARRAY['spirituality', 'nature'], NOW() - INTERVAL '3 days', 22, 'familiar');

-- =============================================================================
-- Analytics and Monitoring Views
-- =============================================================================

-- View for monitoring bot activity
CREATE OR REPLACE VIEW bot_activity_summary AS
SELECT 
    bm.bot_id,
    bm.display_name,
    bm.is_active,
    bm.story_sharing_frequency,
    COUNT(DISTINCT s.id) as total_stories,
    COUNT(DISTINCT se.id) as stories_with_embeddings,
    COUNT(DISTINCT cm.chat_id) as active_chats,
    AVG(cm.message_count) as avg_messages_per_chat,
    MAX(cm.last_interaction) as last_activity,
    SUM(s.used_count) as total_story_shares
FROM bot_metadata bm
LEFT JOIN stories s ON bm.bot_id = s.bot_id
LEFT JOIN story_embeddings se ON s.id = se.story_id AND s.bot_id = se.bot_id
LEFT JOIN chat_memories cm ON bm.bot_id = cm.bot_id
GROUP BY bm.bot_id, bm.display_name, bm.is_active, bm.story_sharing_frequency
ORDER BY bm.bot_id;

-- View for story performance analysis
CREATE OR REPLACE VIEW story_performance AS
SELECT 
    s.bot_id,
    s.id as story_id,
    s.title,
    s.emotional_tone,
    s.used_count,
    s.last_used,
    CASE WHEN se.id IS NOT NULL THEN true ELSE false END as has_embedding,
    se.created_at as embedding_created,
    CASE 
        WHEN s.used_count = 0 THEN 'unused'
        WHEN s.used_count < 5 THEN 'low_usage'
        WHEN s.used_count < 15 THEN 'medium_usage'
        ELSE 'high_usage'
    END as usage_category
FROM stories s
LEFT JOIN story_embeddings se ON s.id = se.story_id AND s.bot_id = se.bot_id
ORDER BY s.bot_id, s.used_count DESC;

-- View for conversation insights
CREATE OR REPLACE VIEW conversation_insights AS
SELECT 
    cm.bot_id,
    COUNT(*) as total_conversations,
    AVG(cm.message_count) as avg_conversation_length,
    COUNT(CASE WHEN cm.relationship_stage = 'new' THEN 1 END) as new_conversations,
    COUNT(CASE WHEN cm.relationship_stage = 'warming_up' THEN 1 END) as warming_up_conversations,
    COUNT(CASE WHEN cm.relationship_stage = 'familiar' THEN 1 END) as familiar_conversations,
    AVG(array_length(cm.stories_shared, 1)) as avg_stories_per_conversation,
    MAX(cm.last_interaction) as most_recent_interaction,
    COUNT(CASE WHEN cm.last_interaction > NOW() - INTERVAL '24 hours' THEN 1 END) as active_last_24h,
    COUNT(CASE WHEN cm.last_interaction > NOW() - INTERVAL '7 days' THEN 1 END) as active_last_week
FROM chat_memories cm
GROUP BY cm.bot_id
ORDER BY cm.bot_id;

-- =============================================================================
-- Utility Functions for Management
-- =============================================================================

-- Function to get bot statistics
CREATE OR REPLACE FUNCTION get_bot_stats(target_bot_id TEXT DEFAULT NULL)
RETURNS TABLE (
    bot_id TEXT,
    display_name TEXT,
    is_active BOOLEAN,
    story_count BIGINT,
    embedding_count BIGINT,
    chat_count BIGINT,
    total_story_uses BIGINT,
    last_activity TIMESTAMP
)
LANGUAGE plpgsql
AS $
BEGIN
    RETURN QUERY
    SELECT 
        bm.bot_id,
        bm.display_name,
        bm.is_active,
        COUNT(DISTINCT s.id) as story_count,
        COUNT(DISTINCT se.id) as embedding_count,
        COUNT(DISTINCT cm.chat_id) as chat_count,
        COALESCE(SUM(s.used_count), 0) as total_story_uses,
        MAX(cm.last_interaction) as last_activity
    FROM bot_metadata bm
    LEFT JOIN stories s ON bm.bot_id = s.bot_id
    LEFT JOIN story_embeddings se ON s.id = se.story_id AND s.bot_id = se.bot_id
    LEFT JOIN chat_memories cm ON bm.bot_id = cm.bot_id
    WHERE target_bot_id IS NULL OR bm.bot_id = target_bot_id
    GROUP BY bm.bot_id, bm.display_name, bm.is_active
    ORDER BY bm.bot_id;
END;
$;

-- Function to regenerate embeddings for a bot
CREATE OR REPLACE FUNCTION regenerate_bot_embeddings(target_bot_id TEXT)
RETURNS TABLE (
    action TEXT,
    count INT
)
LANGUAGE plpgsql
AS $
DECLARE
    deleted_count INT;
    story_count INT;
BEGIN
    -- Delete existing embeddings for the bot
    DELETE FROM story_embeddings WHERE bot_id = target_bot_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    -- Count stories that need new embeddings
    SELECT COUNT(*) INTO story_count FROM stories WHERE bot_id = target_bot_id;
    
    -- Return results
    RETURN QUERY VALUES 
        ('deleted_embeddings', deleted_count),
        ('stories_need_embeddings', story_count);
END;
$;

-- Function to cleanup inactive bots
CREATE OR REPLACE FUNCTION cleanup_inactive_bots(days_inactive INT DEFAULT 30)
RETURNS TABLE (
    action TEXT,
    bot_id TEXT,
    count INT
)
LANGUAGE plpgsql
AS $
DECLARE
    bot_record RECORD;
    deleted_count INT;
BEGIN
    -- Find bots that haven't had any activity in the specified days
    FOR bot_record IN 
        SELECT bm.bot_id, bm.display_name
        FROM bot_metadata bm
        LEFT JOIN chat_memories cm ON bm.bot_id = cm.bot_id
        WHERE bm.is_active = false
        AND (
            cm.last_interaction IS NULL 
            OR cm.last_interaction < NOW() - INTERVAL '1 day' * days_inactive
        )
    LOOP
        -- Count what we're about to delete
        SELECT COUNT(*) INTO deleted_count FROM stories WHERE bot_id = bot_record.bot_id;
        
        -- Return info about what we would delete (but don't actually delete)
        RETURN QUERY VALUES 
            ('would_cleanup', bot_record.bot_id, deleted_count);
    END LOOP;
    
    -- To actually perform cleanup, uncomment the following:
    -- DELETE FROM bot_metadata WHERE bot_id IN (SELECT bot_id FROM ...);
END;
$;

-- =============================================================================
-- Test Data Validation
-- =============================================================================

-- Function to validate the setup
CREATE OR REPLACE FUNCTION validate_database_setup()
RETURNS TABLE (
    check_name TEXT,
    status TEXT,
    details TEXT
)
LANGUAGE plpgsql
AS $
DECLARE
    bot_count INT;
    story_count INT;
    vector_enabled BOOLEAN;
    function_exists BOOLEAN;
BEGIN
    -- Check bot count
    SELECT COUNT(*) INTO bot_count FROM bot_metadata;
    RETURN QUERY VALUES ('bot_count', CASE WHEN bot_count > 0 THEN 'PASS' ELSE 'FAIL' END, bot_count::TEXT || ' bots found');
    
    -- Check story count
    SELECT COUNT(*) INTO story_count FROM stories;
    RETURN QUERY VALUES ('story_count', CASE WHEN story_count > 0 THEN 'PASS' ELSE 'FAIL' END, story_count::TEXT || ' stories found');
    
    -- Check vector extension
    SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector') INTO vector_enabled;
    RETURN QUERY VALUES ('vector_extension', CASE WHEN vector_enabled THEN 'PASS' ELSE 'FAIL' END, CASE WHEN vector_enabled THEN 'pgvector enabled' ELSE 'pgvector not enabled' END);
    
    -- Check match_stories function
    SELECT EXISTS(SELECT 1 FROM pg_proc WHERE proname = 'match_stories') INTO function_exists;
    RETURN QUERY VALUES ('match_stories_function', CASE WHEN function_exists THEN 'PASS' ELSE 'FAIL' END, CASE WHEN function_exists THEN 'Function exists' ELSE 'Function missing' END);
    
    -- Check indexes
    RETURN QUERY 
    SELECT 
        'index_' || indexname as check_name,
        'PASS' as status,
        'Index exists' as details
    FROM pg_indexes 
    WHERE tablename IN ('bot_metadata', 'stories', 'story_embeddings', 'chat_memories')
    AND indexname LIKE 'idx_%';
END;
$;

-- =============================================================================
-- Example Queries for Testing
-- =============================================================================

-- Test the database setup
-- SELECT * FROM validate_database_setup();

-- Get bot statistics
-- SELECT * FROM get_bot_stats();

-- Get bot activity summary
-- SELECT * FROM bot_activity_summary;

-- Get story performance
-- SELECT * FROM story_performance WHERE bot_id = 'alex_v1';

-- Get conversation insights
-- SELECT * FROM conversation_insights;

-- Get embedding status
-- SELECT * FROM get_embedding_status();

-- =============================================================================
-- Completion Message
-- =============================================================================

DO $
BEGIN
    RAISE NOTICE '=================================================================';
    RAISE NOTICE 'Digital Twin Bot Database Setup Complete!';
    RAISE NOTICE '=================================================================';
    RAISE NOTICE 'Created:';
    RAISE NOTICE '  - 4 bot personalities (Alex, Emma, Marcus, Luna)';
    RAISE NOTICE '  - 20 sample stories (5 per bot)';
    RAISE NOTICE '  - Vector search capabilities with pgvector';
    RAISE NOTICE '  - Analytics views and monitoring functions';
    RAISE NOTICE '  - Sample chat memories for testing';
    RAISE NOTICE '';
    RAISE NOTICE 'Next Steps:';
    RAISE NOTICE '  1. Run: SELECT * FROM validate_database_setup();';
    RAISE NOTICE '  2. Test vector search with your application';
    RAISE NOTICE '  3. Generate embeddings for stories using your bot';
    RAISE NOTICE '  4. Monitor with: SELECT * FROM bot_activity_summary;';
    RAISE NOTICE '=================================================================';
END $;