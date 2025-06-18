import logging
import asyncio
from telegram.ext import Application
from telegram import Update

from src.core import DigitalTwinBot
from src.telegram import setup_handlers
from src.config import get_settings

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """Main function to run the digital twin bot"""
    
    # Load settings
    settings = get_settings()
    
    # Validate required settings
    if not settings.telegram_token:
        logger.error("TELEGRAM_TOKEN environment variable is required")
        return
        
    if not settings.bot_id:
        logger.error("BOT_ID environment variable is required")
        return
    
    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY environment variable is required")
        return
    
    # Create bot instance
    bot_instance = DigitalTwinBot(settings.bot_id)
    
    # Create Telegram application
    application = Application.builder().token(settings.telegram_token).build()
    
    # Setup handlers
    setup_handlers(application, bot_instance)
    
    # Initialize bot
    async def post_init(application):
        logger.info(f"🚀 Initializing Digital Twin Bot: {settings.bot_id}")
        success = await bot_instance.initialize()
        if not success:
            logger.error(f"❌ Failed to initialize bot {settings.bot_id}. Check configuration.")
            # Bot will still run but show initialization errors to users
        else:
            logger.info(f"✅ Bot {settings.bot_id} ready for conversations!")
    
    application.post_init = post_init
    
    # Run the bot
    logger.info(f"🤖 Starting Digital Twin Story-Sharing Bot: {settings.bot_id}")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())