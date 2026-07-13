import os
import logging
import asyncio
from supabase import create_client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

class SupabaseClient:
    def __init__(self, url: str = None, key: str = None):
        # Если параметры переданы — используем их, иначе берём из .env
        self.supabase_url = url or os.getenv('SUPABASE_URL')
        self.supabase_key = key or os.getenv('SUPABASE_KEY')
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be provided either as arguments or in .env")
        self.client = create_client(self.supabase_url, self.supabase_key)

    async def _run(self, coro):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, coro.execute)

    async def get_message(self, message_id: int, chat_id: int = None):
        try:
            query = self.client.table('messages').select('*').eq('message_id', message_id)
            if chat_id:
                query = query.eq('chat_id', chat_id)
            result = await self._run(query)
            if isinstance(result.data, list) and result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting message: {e}")
            return None

    async def add_message(self, message_data: dict):
        try:
            result = await self._run(self.client.table('messages').insert(message_data))
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            return None

    async def get_user(self, user_id: int):
        try:
            result = await self._run(self.client.table('users').select('*').eq('user_id', user_id))
            if isinstance(result.data, list) and result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    async def add_user(self, user_data: dict):
        try:
            result = await self._run(self.client.table('users').insert(user_data))
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return None

    async def update_user(self, user_id: int, update_data: dict):
        try:
            result = await self._run(self.client.table('users').update(update_data).eq('user_id', user_id))
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return None

    async def get_session(self, user_id: int):
        try:
            result = await self._run(self.client.table('sessions').select('*').eq('user_id', user_id))
            if isinstance(result.data, list) and result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None

    async def add_session(self, session_data: dict):
        try:
            result = await self._run(self.client.table('sessions').insert(session_data))
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            return None

    async def update_session(self, user_id: int, update_data: dict):
        try:
            result = await self._run(self.client.table('sessions').update(update_data).eq('user_id', user_id))
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error updating session: {e}")
            return None

    async def get_user_settings(self, user_id: int):
        try:
            result = await self._run(self.client.table('user_settings').select('*').eq('user_id', user_id))
            if isinstance(result.data, list) and result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting user settings: {e}")
            return None

    async def add_user_settings(self, settings_data: dict):
        try:
            result = await self._run(self.client.table('user_settings').insert(settings_data))
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error adding user settings: {e}")
            return None

    async def update_user_settings(self, user_id: int, update_data: dict):
        try:
            result = await self._run(self.client.table('user_settings').update(update_data).eq('user_id', user_id))
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            return None