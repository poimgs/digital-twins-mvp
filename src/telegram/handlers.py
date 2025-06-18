import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from ..core import DigitalTwinBot

logger = logging.getLogger(__name__)

class TelegramHandlers:
    """Telegram bot handlers for the digital twin"""
    
    def __init__(self, bot_instance: DigitalTwinBot):
        self.bot = bot_instance
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with database-driven welcome message"""
        if not self.bot.is_initialized:
            await update.message.reply_text(
                "I'm still getting set up. Please give me a moment and try again."
            )
            return
        
        welcome_message = self.bot.get_welcome_message()
        await update.message.reply_text(welcome_message)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        if not self.bot.is_initialized:
            await update.message.reply_text(
                "I'm still initializing my personality. Please give me a moment..."
            )
            return
            
        user_message = update.message.text
        chat_id = str(update.effective_chat.id)
        
        try:
            # Generate response using the bot
            response = await self.bot.generate_response(user_message, chat_id)
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(
                "Sorry, I got a bit distracted there. What were you saying?"
            )

def setup_handlers(application, bot_instance: DigitalTwinBot):
    """Setup all Telegram handlers for the bot"""
    handlers = TelegramHandlers(bot_instance)
    
    # Add command handlers
    application.add_handler(CommandHandler("start", handlers.start_command))
    
    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    
    logger.info("Telegram handlers configured")
    return handlers