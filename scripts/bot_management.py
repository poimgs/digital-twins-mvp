import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from typing import Dict, List
from dataclasses import asdict

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models import BotMetadata, Story
from src.storage import StorageManager
from src.config import get_settings

class BotManager:
    """Utility class for managing multiple bot personalities and their data"""
    
    def __init__(self):
        self.settings = get_settings()
        self.storage_managers = {}
    
    def get_storage_manager(self, bot_id: str) -> StorageManager:
        """Get or create storage manager for a bot"""
        if bot_id not in self.storage_managers:
            self.storage_managers[bot_id] = StorageManager(bot_id, self.settings)
        return self.storage_managers[bot_id]
    
    async def create_bot_metadata(self, 
                                bot_id: str,
                                display_name: str,
                                description: str,
                                welcome_message: str,
                                core_traits: List[str],
                                conversation_style: Dict[str, str],
                                background_context: str,
                                story_sharing_frequency: str = "moderate",
                                response_length_preference: str = "medium",
                                version: str = "1.0") -> BotMetadata:
        """Create and save complete bot metadata"""
        
        metadata = BotMetadata(
            bot_id=bot_id,
            name=bot_id,
            display_name=display_name,
            description=description,
            welcome_message=welcome_message,
            core_traits=core_traits,
            conversation_style=conversation_style,
            background_context=background_context,
            story_sharing_frequency=story_sharing_frequency,
            response_length_preference=response_length_preference,
            version=version
        )
        
        storage = self.get_storage_manager(bot_id)
        await storage.save_bot_metadata(metadata)
        
        print(f"✅ Created bot metadata: {display_name} (ID: {bot_id})")
        print(f"   Story sharing: {story_sharing_frequency}")
        print(f"   Response style: {response_length_preference}")
        print(f"   Version: {version}")
        return metadata
    
    async def update_bot_metadata(self, bot_id: str, **updates):
        """Update specific fields of bot metadata"""
        storage = self.get_storage_manager(bot_id)
        metadata = await storage.load_bot_metadata()
        
        if not metadata:
            print(f"❌ Bot {bot_id} not found")
            return
        
        # Update specified fields
        for key, value in updates.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
                print(f"   Updated {key}: {value}")
            else:
                print(f"   ⚠️  Unknown field: {key}")
        
        await storage.save_bot_metadata(metadata)
        print(f"✅ Updated bot metadata for {bot_id}")
    
    async def list_bots(self, show_inactive: bool = False):
        """List all bot metadata"""
        # List from Supabase
        from supabase import create_client
        supabase = create_client(self.settings.supabase_url, self.settings.supabase_key)
        try:
            query = supabase.table('bot_metadata').select('*')
            if not show_inactive:
                query = query.eq('is_active', True)
            response = query.execute()
            bots = [BotMetadata(**bot) for bot in response.data]
        except Exception as e:
            print(f"❌ Failed to fetch from Supabase: {e}")
            bots = []
        
        if not bots:
            print("📭 No bots found")
            return
        
        print(f"🤖 Found {len(bots)} bots:")
        print("-" * 80)
        for bot in bots:
            status = "🟢 Active" if bot.is_active else "🔴 Inactive"
            print(f"ID: {bot.bot_id} | {status}")
            print(f"Name: {bot.display_name}")
            print(f"Description: {bot.description[:100]}{'...' if len(bot.description) > 100 else ''}")
            print(f"Version: {bot.version} | Story sharing: {bot.story_sharing_frequency} | Response: {bot.response_length_preference}")
            print(f"Created: {bot.created_at}")
            print("-" * 80)
    
    async def import_stories_for_bot(self, bot_id: str, stories_file: str):
        """Import stories from a JSON file for a specific bot"""
        stories_path = Path(stories_file)
        if not stories_path.exists():
            print(f"❌ Stories file not found: {stories_file}")
            return
        
        with open(stories_path, 'r') as f:
            stories_data = json.load(f)
        
        stories = []
        for story_data in stories_data:
            # Ensure bot_id is set correctly
            story_data['bot_id'] = bot_id
            stories.append(Story(**story_data))
        
        storage = self.get_storage_manager(bot_id)
        await storage.save_stories(stories)
        
        print(f"✅ Imported {len(stories)} stories for bot {bot_id}")
    
    async def export_bot_data(self, bot_id: str, output_dir: str):
        """Export all data for a specific bot"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        storage = self.get_storage_manager(bot_id)
        
        # Export metadata
        metadata = await storage.load_bot_metadata()
        if metadata:
            metadata_file = output_path / f"{bot_id}_metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(asdict(metadata), f, indent=2)
            print(f"✅ Exported metadata to {metadata_file}")
        
        # Export stories
        stories = await storage.load_stories()
        if stories:
            stories_file = output_path / f"{bot_id}_stories.json"
            stories_data = [asdict(story) for story in stories]
            with open(stories_file, 'w') as f:
                json.dump(stories_data, f, indent=2)
            print(f"✅ Exported {len(stories)} stories to {stories_file}")
        
        print(f"📦 Bot data exported to {output_path}")

async def main():
    parser = argparse.ArgumentParser(description='Digital Twin Bot Management Utility')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create bot command
    create_parser = subparsers.add_parser('create', help='Create a new bot with complete metadata')
    create_parser.add_argument('bot_id', help='Unique bot identifier (e.g., emma_v1)')
    create_parser.add_argument('display_name', help='Bot display name (e.g., Emma)')
    create_parser.add_argument('--description', required=True, help='Bot description')
    create_parser.add_argument('--welcome', help='Custom welcome message')
    create_parser.add_argument('--traits', nargs='+', required=True, help='Core personality traits')
    create_parser.add_argument('--tone', default='warm and conversational', help='Conversation tone')
    create_parser.add_argument('--approach', default='shares stories naturally', help='Story sharing approach')
    create_parser.add_argument('--context', help='Custom background context (optional)')
    create_parser.add_argument('--story-freq', choices=['low', 'moderate', 'high'], default='moderate', help='Story sharing frequency')
    create_parser.add_argument('--response-length', choices=['short', 'medium', 'long'], default='medium', help='Response length preference')
    create_parser.add_argument('--version', default='1.0', help='Bot version')
    
    # Update bot command
    update_parser = subparsers.add_parser('update', help='Update bot metadata')
    update_parser.add_argument('bot_id', help='Bot identifier to update')
    update_parser.add_argument('--display-name', help='Update display name')
    update_parser.add_argument('--description', help='Update description')
    update_parser.add_argument('--welcome', help='Update welcome message')
    update_parser.add_argument('--story-freq', choices=['low', 'moderate', 'high'], help='Update story frequency')
    update_parser.add_argument('--response-length', choices=['short', 'medium', 'long'], help='Update response length')
    update_parser.add_argument('--version', help='Update version')
    
    # List bots command
    list_parser = subparsers.add_parser('list', help='List all bot metadata')
    list_parser.add_argument('--show-inactive', action='store_true', help='Include inactive bots')
    
    # Import stories command
    import_parser = subparsers.add_parser('import', help='Import stories for a bot')
    import_parser.add_argument('bot_id', help='Bot identifier')
    import_parser.add_argument('stories_file', help='JSON file containing stories')
    
    # Export bot command
    export_parser = subparsers.add_parser('export', help='Export bot data')
    export_parser.add_argument('bot_id', help='Bot identifier to export')
    export_parser.add_argument('--output', default='./exports', help='Output directory')
    
    args = parser.parse_args()
    manager = BotManager()
    
    if args.command == 'create':
        conversation_style = {
            "tone": args.tone,
            "approach": args.approach,
            "listening": "asks thoughtful follow-up questions",
            "storytelling": "shares relevant personal experiences"
        }
        
        welcome_message = args.welcome or f"""Hi! I'm {args.display_name}, and I love connecting with people through stories and shared experiences.

{args.description}

What's on your mind today?"""
        
        background_context = args.context or f"""You are {args.display_name}, a digital twin who connects with people through personal stories and shared experiences. You have a unique personality defined by being {', '.join(args.traits)}. Share your stories naturally when they relate to conversations, always being genuine and curious about others' experiences."""
        
        await manager.create_bot_metadata(
            args.bot_id, args.display_name, args.description, welcome_message,
            args.traits, conversation_style, background_context.strip(),
            args.story_freq, args.response_length, args.version
        )
    
    elif args.command == 'update':
        updates = {}
        if args.display_name: updates['display_name'] = args.display_name
        if args.description: updates['description'] = args.description
        if args.welcome: updates['welcome_message'] = args.welcome
        if args.story_freq: updates['story_sharing_frequency'] = args.story_freq
        if args.response_length: updates['response_length_preference'] = args.response_length
        if args.version: updates['version'] = args.version
        
        if updates:
            await manager.update_bot_metadata(args.bot_id, **updates)
        else:
            print("No updates specified")
    
    elif args.command == 'list':
        await manager.list_bots(args.show_inactive)
    
    elif args.command == 'import':
        await manager.import_stories_for_bot(args.bot_id, args.stories_file)
    
    elif args.command == 'export':
        await manager.export_bot_data(args.bot_id, args.output)
    
    else:
        parser.print_help()

if __name__ == '__main__':
    asyncio.run(main())