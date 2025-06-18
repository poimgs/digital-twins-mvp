import os
from dataclasses import dataclass

@dataclass
class Settings:
    """Application configuration settings"""
    # Required settings
    openai_api_key: str
    telegram_token: str
    bot_id: str
    
    # Optional database settings
    supabase_url: str
    supabase_key:str
    
    # Bot behavior defaults
    default_model: str = "gpt-4o-mini"
    default_max_tokens: int = 300
    default_temperature: float = 0.7

def get_settings() -> Settings:
    """Load settings from environment variables"""
    return Settings(
        openai_api_key=os.getenv('OPENAI_API_KEY', ''),
        telegram_token=os.getenv('TELEGRAM_TOKEN', ''),
        bot_id=os.getenv('BOT_ID', ''),
        supabase_url=os.getenv('SUPABASE_URL'),
        supabase_key=os.getenv('SUPABASE_KEY'),
        default_model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
        default_max_tokens=int(os.getenv('MAX_TOKENS', '300')),
        default_temperature=float(os.getenv('TEMPERATURE', '0.7')),
        local_storage_base=os.getenv('LOCAL_STORAGE_BASE', 'bot_data')
    )