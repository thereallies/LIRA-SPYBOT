import asyncio
import logging
from datetime import datetime
from supabase import create_client, Client

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    async def _run(self, fn):
        return await asyncio.to_thread(fn)

    # === USERS ===

    async def get_user(self, telegram_id: int):
        try:
            def _fetch():
                return self.client.table('users')\
                    .select('*')\
                    .eq('telegram_id', telegram_id)\
                    .execute()
            result = await self._run(_fetch)
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    async def create_user(self, telegram_id: int, username: str = None,
                          first_name: str = None, role: str = 'user'):
        try:
            data = {
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name,
                'role': role,
                'status': 'active',
                'last_active': datetime.now().isoformat()
            }
            result = await self._run(
                lambda: self.client.table('users').upsert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return None

    async def update_user(self, telegram_id: int, data: dict):
        try:
            await self._run(
                lambda: self.client.table('users')
                    .update(data)
                    .eq('telegram_id', telegram_id)
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return False

    async def get_all_users(self):
        try:
            def _fetch():
                return self.client.table('users')\
                    .select('telegram_id, username, first_name, role, status')\
                    .execute()
            result = await self._run(_fetch)
            return result.data
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

    async def get_active_user_ids(self):
        try:
            def _fetch():
                return self.client.table('users')\
                    .select('telegram_id')\
                    .eq('status', 'active')\
                    .execute()
            result = await self._run(_fetch)
            return [u['telegram_id'] for u in result.data]
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []

    # === SESSIONS ===

    async def get_session(self, user_id: int):
        try:
            def _fetch():
                return self.client.table('sessions')\
                    .select('*')\
                    .eq('user_id', user_id)\
                    .execute()
            result = await self._run(_fetch)
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting session: {e}")
            return None

    async def save_session(self, user_id: int, phone: str, session_string: str):
        try:
            data = {
                'user_id': user_id,
                'phone': phone,
                'session_string': session_string,
                'status': 'active',
                'last_active': datetime.now().isoformat()
            }
            result = await self._run(
                lambda: self.client.table('sessions').upsert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error saving session: {e}")
            return None

    async def delete_session(self, user_id: int):
        try:
            await self._run(
                lambda: self.client.table('sessions')
                    .delete()
                    .eq('user_id', user_id)
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    async def get_all_active_sessions(self):
        try:
            def _fetch():
                return self.client.table('sessions')\
                    .select('*')\
                    .eq('status', 'active')\
                    .execute()
            result = await self._run(_fetch)
            return result.data
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return []

    # === AUTH FLOW ===

    async def set_auth_flow(self, user_id: int, phone: str = None,
                            phone_code_hash: str = None, step: str = 'idle'):
        try:
            # Удаляем старую запись, затем вставляем новую
            await self._run(
                lambda: self.client.table('auth_flow')
                    .delete()
                    .eq('user_id', user_id)
                    .execute()
            )
            data = {
                'user_id': user_id,
                'phone': phone,
                'phone_code_hash': phone_code_hash,
                'step': step,
                'created_at': datetime.now().isoformat()
            }
            result = await self._run(
                lambda: self.client.table('auth_flow').insert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error setting auth flow: {e}")
            return None

    async def get_auth_flow(self, user_id: int):
        try:
            def _fetch():
                return self.client.table('auth_flow')\
                    .select('*')\
                    .eq('user_id', user_id)\
                    .execute()
            result = await self._run(_fetch)
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting auth flow: {e}")
            return None

    async def clear_auth_flow(self, user_id: int):
        try:
            await self._run(
                lambda: self.client.table('auth_flow')
                    .delete()
                    .eq('user_id', user_id)
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error clearing auth flow: {e}")
            return False

    # === MESSAGES (unchanged) ===

    async def save_message(self, message):
        try:
            media_type = None
            media_file_id = None

            if message.photo:
                media_type = 'photo'
                media_file_id = str(message.photo.id)
            elif message.video:
                media_type = 'video'
                media_file_id = str(message.video.id)
            elif message.voice:
                media_type = 'voice'
                media_file_id = str(message.voice.id)
            elif message.document:
                media_type = 'document'
                media_file_id = str(message.document.id)
            elif message.video_note:
                media_type = 'video_note'
                media_file_id = str(message.video_note.id)

            sender = await message.get_sender() if message.sender_id else None
            from_username = sender.username if sender else None

            data = {
                'message_id': message.id,
                'chat_id': message.chat_id,
                'from_user_id': message.sender_id,
                'from_username': from_username,
                'text': message.text or '',
                'media_type': media_type,
                'media_file_id': media_file_id,
                'media_url': None,
                'sent_at': message.date.isoformat(),
                'edited_at': message.edit_date.isoformat() if message.edit_date else None
            }
            result = await self._run(
                lambda: self.client.table('messages').upsert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return None

    async def get_message(self, message_id: int, chat_id: int = None):
        """
        Get a message by ID and optional chat_id
        """
        try:
            query = self.client.table('messages').select('*').eq('message_id', message_id)
            if chat_id:
                query = query.eq('chat_id', chat_id)
            _fetch = query.execute()
            result = await self._run(_fetch)
            # Исправление: проверяем, что result.data — список, и он не пустой
            if isinstance(result.data, list) and result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error getting message: {e}")
            return None

    async def save_deleted_message(self, msg_data: dict):
        try:
            data = {
                'original_message_id': msg_data['id'],
                'chat_id': msg_data['chat_id'],
                'from_user_id': msg_data['from_user_id'],
                'from_username': msg_data['from_username'],
                'original_text': msg_data['text'],
                'media_type': msg_data['media_type'],
                'media_url': msg_data['media_url'],
                'sent_at': msg_data['sent_at'],
                'deleted_at': datetime.now().isoformat()
            }
            await self._run(
                lambda: self.client.table('deleted_messages').insert(data).execute()
            )
            await self._run(
                lambda: self.client.table('messages')
                    .update({'is_deleted': True})
                    .eq('id', msg_data['id'])
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error saving deleted message: {e}")
            return None

    async def save_edited_message(self, old_msg: dict, new_message):
        try:
            sender = await new_message.get_sender() if new_message.sender_id else None
            from_username = sender.username if sender else None

            data = {
                'original_message_id': old_msg['id'],
                'chat_id': new_message.chat_id,
                'from_user_id': new_message.sender_id,
                'from_username': from_username,
                'old_text': old_msg['text'],
                'new_text': new_message.text or '',
                'media_type': old_msg['media_type'],
                'media_url': old_msg['media_url'],
                'sent_at': old_msg['sent_at'],
                'edited_at': datetime.now().isoformat(),
                'edit_count': 1
            }
            result = await self._run(
                lambda: self.client.table('edited_messages').insert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error saving edited message: {e}")
            return None

    async def update_message(self, message):
        try:
            data = {
                'text': message.text or '',
                'edited_at': message.edit_date.isoformat() if message.edit_date else None
            }
            await self._run(
                lambda: self.client.table('messages')
                    .update(data)
                    .eq('message_id', message.id)
                    .eq('chat_id', message.chat_id)
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error updating message: {e}")
            return None

    # === SETTINGS ===

    async def get_user_settings(self, user_id: int):
        try:
            def _fetch():
                return self.client.table('settings')\
                    .select('*')\
                    .eq('user_id', user_id)\
                    .execute()
            result = await self._run(_fetch)
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting user settings: {e}")
            return None

    async def create_user_settings(self, user_id: int):
        try:
            data = {
                'user_id': user_id,
                'notify_deleted': True,
                'notify_edited': True,
                'notify_format': 'detailed',
                'save_media': True,
                'language': 'ru'
            }
            result = await self._run(
                lambda: self.client.table('settings').insert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error creating user settings: {e}")
            return None

    async def update_user_settings(self, user_id: int, settings: dict):
        try:
            await self._run(
                lambda: self.client.table('settings')
                    .update(settings)
                    .eq('user_id', user_id)
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error updating user settings: {e}")
            return False

    # === TRACKED CHATS ===

    async def add_tracked_chat(self, user_id: int, chat_id: int, chat_title: str, chat_type: str):
        try:
            data = {
                'chat_id': chat_id,
                'chat_title': chat_title,
                'chat_type': chat_type,
                'user_id': user_id,
                'is_active': True
            }
            result = await self._run(
                lambda: self.client.table('tracked_chats').insert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error adding tracked chat: {e}")
            return None

    async def get_tracked_chats(self, user_id: int):
        try:
            def _fetch():
                return self.client.table('tracked_chats')\
                    .select('*')\
                    .eq('user_id', user_id)\
                    .eq('is_active', True)\
                    .execute()
            result = await self._run(_fetch)
            return result.data
        except Exception as e:
            logger.error(f"Error getting tracked chats: {e}")
            return []

    async def remove_tracked_chat(self, user_id: int, chat_id: int):
        try:
            await self._run(
                lambda: self.client.table('tracked_chats')
                    .update({'is_active': False})
                    .eq('user_id', user_id)
                    .eq('chat_id', chat_id)
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error removing tracked chat: {e}")
            return False

    # === STATS ===

    async def get_user_message_count(self, user_id: int):
        try:
            def _fetch():
                return self.client.table('messages')\
                    .select('*', count='exact')\
                    .eq('from_user_id', user_id)\
                    .execute()
            result = await self._run(_fetch)
            return result.count or 0
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0

    async def get_deleted_count(self, user_id: int):
        try:
            def _fetch():
                return self.client.table('deleted_messages')\
                    .select('*', count='exact')\
                    .eq('from_user_id', user_id)\
                    .execute()
            result = await self._run(_fetch)
            return result.count or 0
        except Exception as e:
            logger.error(f"Error getting deleted count: {e}")
            return 0

    async def get_edited_count(self, user_id: int):
        try:
            def _fetch():
                return self.client.table('edited_messages')\
                    .select('*', count='exact')\
                    .eq('from_user_id', user_id)\
                    .execute()
            result = await self._run(_fetch)
            return result.count or 0
        except Exception as e:
            logger.error(f"Error getting edited count: {e}")
            return 0

    # === BOT API METHODS ===

    async def save_message_raw(self, data: dict):
        """Сохранение сообщения из Bot API"""
        try:
            result = await self._run(
                lambda: self.client.table('messages').upsert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error saving raw message: {e}")
            return None

    async def save_edited_message_raw(self, data: dict):
        """Сохранение отредактированного сообщения из Bot API"""
        try:
            result = await self._run(
                lambda: self.client.table('edited_messages').insert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error saving edited raw: {e}")
            return None

    async def save_deleted_message_raw(self, data: dict):
        """Сохранение удалённого сообщения из Bot API"""
        try:
            result = await self._run(
                lambda: self.client.table('deleted_messages').insert(data).execute()
            )
            return result.data
        except Exception as e:
            logger.error(f"Error saving deleted raw: {e}")
            return None

    async def update_message_text(self, message_id: int, chat_id: int, text: str):
        """Обновление текста сообщения"""
        try:
            await self._run(
                lambda: self.client.table('messages')
                    .update({'text': text})
                    .eq('message_id', message_id)
                    .eq('chat_id', chat_id)
                    .execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error updating message text: {e}")
            return False

    async def get_all_active_user_ids(self):
        """Получение ID всех активных пользователей"""
        try:
            def _fetch():
                return self.client.table('users')\
                    .select('telegram_id')\
                    .eq('status', 'active')\
                    .execute()
            result = await self._run(_fetch)
            return [u['telegram_id'] for u in result.data]
        except Exception as e:
            logger.error(f"Error getting active user IDs: {e}")
            return []
