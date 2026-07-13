import os
import logging
import asyncio
from supabase import create_client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

class SupabaseClient:
    def __init__(self, url: str = None, key: str = None):
        self.supabase_url = url or os.getenv('SUPABASE_URL')
        self.supabase_key = key or os.getenv('SUPABASE_KEY')
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be provided")
        self.client = create_client(self.supabase_url, self.supabase_key)

    async def _run(self, coro):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, coro.execute)

    # ---------- Messages ----------
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
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            return None

    async def save_message_raw(self, data: dict):
        """Сохранение сырого сообщения (для main.py)"""
        try:
            result = await self._run(self.client.table('messages').insert(data))
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error saving raw message: {e}")
            return None

    async def update_message_text(self, message_id: int, chat_id: int, new_text: str):
        """Обновление текста сообщения (при редактировании)"""
        try:
            result = await self._run(
                self.client.table('messages')
                .update({'text': new_text})
                .eq('message_id', message_id)
                .eq('chat_id', chat_id)
            )
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error updating message text: {e}")
            return None

    async def save_edited_message_raw(self, data: dict):
        """Сохранение записи о редактировании"""
        try:
            result = await self._run(self.client.table('edited_messages').insert(data))
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error saving edited message: {e}")
            return None

    async def save_deleted_message_raw(self, data: dict):
        """Сохранение записи об удалении"""
        try:
            result = await self._run(self.client.table('deleted_messages').insert(data))
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error saving deleted message: {e}")
            return None

    # ---------- Users ----------
    async def get_user(self, user_id: int):
        try:
            result = await self._run(self.client.table('users').select('*').eq('id', user_id))
            if isinstance(result.data, list) and result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    async def add_user(self, user_data: dict):
        try:
            result = await self._run(self.client.table('users').insert(user_data))
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return None

    # Исправленная сигнатура для main.py
    async def create_user(self, user_id: int, username: str, first_name: str, role: str = 'user'):
        user_data = {
            'id': user_id,
            'telegram_id': user_id,          # обязательное поле
            'username': username,
            'first_name': first_name,
            'role': role,
            'status': 'active'
        }
        return await self.add_user(user_data)

    async def update_user(self, user_id: int, update_data: dict):
        try:
            result = await self._run(self.client.table('users').update(update_data).eq('id', user_id))
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return None

    async def get_all_users(self):
        """Получение всех пользователей"""
        try:
            result = await self._run(self.client.table('users').select('*'))
            return result.data if isinstance(result.data, list) else []
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    async def get_all_active_user_ids(self):
        """Получение ID всех активных пользователей"""
        try:
            result = await self._run(self.client.table('users').select('id').eq('status', 'active'))
            if isinstance(result.data, list):
                return [u['id'] for u in result.data]
            return []
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []

    # ---------- Sessions ----------
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
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error adding session: {e}")
            return None

    async def update_session(self, user_id: int, update_data: dict):
        try:
            result = await self._run(self.client.table('sessions').update(update_data).eq('user_id', user_id))
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error updating session: {e}")
            return None

    # ---------- User Settings ----------
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
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error adding user settings: {e}")
            return None

    async def update_user_settings(self, user_id: int, update_data: dict):
        try:
            result = await self._run(self.client.table('user_settings').update(update_data).eq('user_id', user_id))
            return result.data[0] if isinstance(result.data, list) and result.data else None
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            return None