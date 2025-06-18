# Digital Twin Story-Sharing Bot System

## 🏗️ Modular Architecture

This system is now organized into clean, modular components:

```
digital_twin_bot/
├── src/                     # Core application code
│   ├── models/             # Data models (BotMetadata, Story, ChatMemory)
│   ├── core/               # Core business logic (Bot, Personality, StoryMatcher)
│   ├── storage/            # Database and file storage
│   ├── telegram/           # Telegram bot handlers
│   └── config/             # Configuration management
├── scripts/                # Management utilities
├── main.py                 # Application entry point
└── Docker files           # Deployment configuration
```

## 🚀 Quick Start

### 1. Clone and Setup
```bash
git clone <your-repo>
cd digital_twin_bot

# Copy environment template
cp .env.example .env
# Edit .env with your API keys
```

### 2. Create Your First Bot
```bash
# Create bot configuration
python scripts/bot_management.py create storyteller_v1 "Luna" \
  --description "A mystical storyteller who weaves tales of wonder" \
  --traits "mystical" "wise" "imaginative" \
  --story-freq high \
  --response-length long

# Import stories
python scripts/bot_management.py import storyteller_v1 luna_stories.json
```

### 3. Deploy
```bash
# Single bot
BOT_ID=storyteller_v1 TELEGRAM_TOKEN=$YOUR_TOKEN python main.py

# Multiple bots with Docker
docker-compose up -d
```

## 🔧 Development

### Project Structure Benefits

**Models** (`src/models/`): Clean data structures
- `BotMetadata`: Complete bot configuration
- `Story`: Story content and metadata  
- `ChatMemory`: Per-conversation state

**Core** (`src/core/`): Business logic separation
- `DigitalTwinBot`: Main orchestrator
- `Personality`: Personality management
- `StoryMatcher`: Intelligent story selection

**Storage** (`src/storage/`): Data persistence
- `StorageManager`: Unified database/file access
- Automatic Supabase/local file fallback

**Telegram** (`src/telegram/`): Clean handler separation
- All Telegram-specific code isolated
- Easy to add new commands
- Proper error handling

**Config** (`src/config/`): Centralized settings
- Environment variable management
- Type-safe configuration
- Default value handling

### Adding New Features

1. **New Commands**: Add to `src/telegram/handlers.py`
2. **New Models**: Create in `src/models/`
3. **New Storage**: Extend `StorageManager`
4. **New Core Logic**: Add to `src/core/`

### Testing

```bash
# Test bot management
python scripts/bot_management.py list

# Test single bot locally
BOT_ID=test_bot TELEGRAM_TOKEN=$TOKEN python main.py

# Health check
# Use /health command in Telegram
```

## 🎛️ Configuration

### Environment Variables
- `OPENAI_API_KEY`: Required OpenAI API key
- `TELEGRAM_TOKEN`: Required Telegram bot token
- `BOT_ID`: Required unique bot identifier
- `SUPABASE_URL`: Optional database URL (falls back to local files)
- `SUPABASE_KEY`: Optional database key
- `OPENAI_MODEL`: Optional model selection (default: gpt-4o-mini)
- `MAX_TOKENS`: Optional response length (default: 300)
- `TEMPERATURE`: Optional creativity setting (default: 0.7)

### Bot Behavior Configuration
All stored in database `bot_metadata` table:
- **Story Sharing**: `low`, `moderate`, `high`
- **Response Length**: `short`, `medium`, `long`
- **Personality Traits**: Customizable list
- **Welcome Message**: Custom per bot
- **Conversation Style**: Tone and approach

## 📊 Database Schema

### Core Tables
```sql
-- Complete bot configuration
bot_metadata (
    bot_id, display_name, description, welcome_message,
    core_traits[], conversation_style, background_context,
    story_sharing_frequency, response_length_preference,
    version, is_active, created_at, updated_at
)

-- Bot-specific stories
stories (
    id, bot_id, title, content, themes[], triggers[],
    emotional_tone, context_hints[], used_count, last_used
)

-- Per-bot, per-chat memory
chat_memories (
    chat_id, bot_id, stories_shared[], conversation_themes[],
    user_interests[], relationship_stage, message_count
)
```

## 🤖 Bot Commands

- `/start` - Welcome message (from database)
- `/info` - Bot personality and configuration
- `/stats` - Conversation statistics
- `/health` - System health status
- `/reload` - Reload configuration from database

## 🔄 Runtime Management

### Update Bot Configuration
```bash
# Change personality traits
python scripts/bot_management.py update alex_v1 \
  --description "A more philosophical storyteller"

# Adjust behavior
python scripts/bot_management.py update alex_v1 \
  --story-freq high \
  --response-length long

# Update welcome message
python scripts/bot_management.py update alex_v1 \
  --welcome "Greetings! I'm Alex, ready to share some amazing stories..."
```

### Live Reload
```bash
# In Telegram, send to your bot:
/reload

# Or programmatically:
# Bot will automatically reload configuration from database
```

## 🐳 Docker Deployment

### Single Bot
```bash
# Build and run one bot
docker build -t digital-twin-bot .
docker run -d \
  -e BOT_ID=alex_v1 \
  -e TELEGRAM_TOKEN=$ALEX_TOKEN \
  -e OPENAI_API_KEY=$OPENAI_KEY \
  -e SUPABASE_URL=$SUPABASE_URL \
  -e SUPABASE_KEY=$SUPABASE_KEY \
  digital-twin-bot
```

### Multiple Bots
```bash
# Deploy all configured bots
docker-compose up -d

# Scale specific bot
docker-compose up -d --scale bot-alex=2

# View logs
docker-compose logs -f bot-emma
```

## 🔍 Monitoring

### Health Checks
```bash
# Check all containers
docker-compose ps

# Individual bot health
# Send /health to bot in Telegram

# View bot logs
docker-compose logs bot-alex
```

### Database Monitoring
```sql
-- Bot usage statistics
SELECT 
  bot_id,
  display_name,
  is_active,
  version,
  COUNT(DISTINCT cm.chat_id) as active_chats,
  AVG(cm.message_count) as avg_messages_per_chat
FROM bot_metadata bm
LEFT JOIN chat_memories cm ON bm.bot_id = cm.bot_id
GROUP BY bot_id, display_name, is_active, version;

-- Story performance
SELECT 
  bot_id,
  COUNT(*) as total_stories,
  AVG(used_count) as avg_usage,
  MAX(used_count) as most_used_count
FROM stories 
GROUP BY bot_id;
```

## 🚀 Scaling

### Horizontal Scaling
- Deploy multiple instances of same bot with different tokens
- Load balance across different servers
- Use Supabase for shared state

### Performance Optimization
- Adjust `MAX_TOKENS` per bot based on needs
- Use different OpenAI models per bot type
- Implement caching for frequently accessed stories

### Adding New Bots
1. Create bot configuration with management script
2. Import custom stories
3. Get new Telegram token from @BotFather
4. Add to docker-compose.yml
5. Deploy

## ⚠️ Production Considerations

### Security
- Use environment variables for all secrets
- Implement rate limiting
- Add admin user restrictions for /reload command
- Use Supabase RLS policies

### Backup Strategy
```bash
# Export all bot data
python scripts/bot_management.py export alex_v1 --output ./backups/

# Supabase automatic backups enabled
# Local file backups in ./bot_data/
```

### Error Handling
- Graceful degradation when database unavailable
- Automatic retry logic in storage manager
- User-friendly error messages
- Comprehensive logging

This modular architecture provides clear separation of concerns, making the system easier to understand, test, and extend while maintaining the simplicity and effectiveness of the original design.