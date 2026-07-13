"""
Auth Flow — manages Telethon authentication for users
"""
import os
import glob
import logging
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionPasswordNeededError,
    FloodWaitError
)

logger = logging.getLogger(__name__)


class AuthFlowManager:
    def __init__(self, db, api_id: int, api_hash: str):
        self.db = db
        self.api_id = api_id
        self.api_hash = api_hash
        self._clients = {}  # user_id -> TelegramClient
        self._phone_code_hashes = {}  # user_id -> hash

    def _cleanup_old_sessions(self, user_id: int):
        """Удаление старых файлов сессий"""
        pattern = f"_auth_{user_id}*"
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except Exception:
                pass

    async def send_code(self, user_id: int, phone: str):
        """Отправка кода подтверждения"""
        try:
            # Удаляем старый клиент если есть
            if user_id in self._clients:
                try:
                    await self._clients[user_id].disconnect()
                except Exception:
                    pass

            self._cleanup_old_sessions(user_id)

            session_name = f'_auth_{user_id}'
            self._clients[user_id] = TelegramClient(
                session_name, self.api_id, self.api_hash
            )
            await self._clients[user_id].connect()

            sent = await self._clients[user_id].send_code_request(phone)
            self._phone_code_hashes[user_id] = sent.phone_code_hash
            logger.info(f"Code sent to {phone} for user {user_id}")
            return True
        except FloodWaitError as e:
            logger.error(f"Flood wait for {phone}: {e.seconds}s")
            return {'error': f'flood_wait', 'seconds': e.seconds}
        except Exception as e:
            logger.error(f"Error sending code to {phone}: {e}")
            return None

    async def sign_in(self, user_id: int, phone: str, code: str):
        """Ввод кода подтверждения"""
        if user_id not in self._clients:
            logger.error(f"No client for user {user_id}")
            return None

        client = self._clients[user_id]
        phone_code_hash = self._phone_code_hashes.get(user_id)

        try:
            me = await client.sign_in(
                phone, code,
                phone_code_hash=phone_code_hash
            )
            logger.info(f"Signed in: {me.first_name} (user {user_id})")
            return me
        except SessionPasswordNeededError:
            logger.info(f"2FA required for user {user_id}")
            return 'need_password'
        except PhoneCodeInvalidError:
            logger.warning(f"Invalid code for user {user_id}")
            return 'invalid_code'
        except PhoneCodeExpiredError:
            logger.warning(f"Code expired for user {user_id}")
            return 'code_expired'
        except FloodWaitError as e:
            logger.error(f"Flood wait for user {user_id}: {e.seconds}s")
            return {'error': 'flood_wait', 'seconds': e.seconds}
        except Exception as e:
            logger.error(f"Error signing in user {user_id}: {e}")
            return None

    async def sign_in_password(self, user_id: int, password: str):
        """Ввод пароля 2FA"""
        if user_id not in self._clients:
            return None

        client = self._clients[user_id]

        try:
            me = await client.sign_in(password=password)
            logger.info(f"Signed in with 2FA: {me.first_name} (user {user_id})")
            return me
        except Exception as e:
            logger.error(f"Error with 2FA password for user {user_id}: {e}")
            return None

    async def get_session_string(self, user_id: int):
        """Получение строки сессии"""
        if user_id not in self._clients:
            return None

        client = self._clients[user_id]
        try:
            session_string = client.session.save()
            await client.disconnect()
            del self._clients[user_id]
            if user_id in self._phone_code_hashes:
                del self._phone_code_hashes[user_id]
            return session_string
        except Exception as e:
            logger.error(f"Error getting session string: {e}")
            return None

    async def cancel(self, user_id: int):
        """Отмена авторизации"""
        if user_id in self._clients:
            try:
                await self._clients[user_id].disconnect()
            except Exception:
                pass
            del self._clients[user_id]
        if user_id in self._phone_code_hashes:
            del self._phone_code_hashes[user_id]
        self._cleanup_old_sessions(user_id)
