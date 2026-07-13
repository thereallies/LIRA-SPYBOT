"""
Monitor Manager — manages Telethon sessions for each user
"""
import asyncio
import logging
from telethon import TelegramClient, events
from services.notifier import send_message, send_photo, send_document
from services.media_handler import is_disappearing, download_media

logger = logging.getLogger(__name__)


class MonitorManager:
    def __init__(self, db, api_id: int, api_hash: str):
        self.db = db
        self.api_id = api_id
        self.api_hash = api_hash
        self._clients = {}  # user_id -> TelegramClient
        self._tasks = {}    # user_id -> asyncio.Task

    def is_running(self, user_id: int) -> bool:
        return user_id in self._clients

    async def restore_all_sessions(self, db):
        """Восстановление всех активных сессий при запуске"""
        sessions = await db.get_all_active_sessions()
        for session in sessions:
            user_id = session['user_id']
            session_string = session.get('session_string')
            if session_string:
                logger.info(f"Restoring session for user {user_id}")
                await self.start_monitoring(user_id, session_string)

    async def start_monitoring(self, user_id: int, session_string: str):
        """Запуск мониторинга для пользователя"""
        if user_id in self._clients:
            await self.stop_monitoring(user_id)

        try:
            client = TelegramClient(
                f'_monitor_{user_id}', self.api_id, self.api_hash
            )
            await client.session.load_string(session_string)
            await client.connect()

            if not await client.is_user_authorized():
                logger.warning(f"Session for user {user_id} is not authorized")
                await client.disconnect()
                return False

            me = await client.get_me()
            logger.info(f"Monitor started for user {user_id}: {me.first_name}")

            self._clients[user_id] = client
            self._setup_handlers(user_id, client)

            # Запускаем в фоне
            task = asyncio.create_task(self._run_client(user_id, client))
            self._tasks[user_id] = task

            return True
        except Exception as e:
            logger.error(f"Error starting monitor for {user_id}: {e}")
            return False

    async def stop_monitoring(self, user_id: int):
        """Остановка мониторинга"""
        if user_id in self._tasks:
            self._tasks[user_id].cancel()
            del self._tasks[user_id]

        if user_id in self._clients:
            try:
                await self._clients[user_id].disconnect()
            except Exception:
                pass
            del self._clients[user_id]
            logger.info(f"Monitor stopped for user {user_id}")

    async def _run_client(self, user_id: int, client: TelegramClient):
        """Запуск клиента"""
        try:
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client error for user {user_id}: {e}")
        finally:
            if user_id in self._clients:
                del self._clients[user_id]
            if user_id in self._tasks:
                del self._tasks[user_id]

    def _setup_handlers(self, user_id: int, client: TelegramClient):
        """Настройка обработчиков для клиента"""
        db = self.db
        notify_user_id = user_id  # Кому слать уведомления

        @client.on(events.NewMessage)
        async def handle_new_message(event):
            try:
                message = event.message
                chat_id = event.chat_id or event.sender_id

                # Скачиваем исчезающие
                if is_disappearing(message):
                    logger.info(f"[{user_id}] Disappearing message in chat {chat_id}")
                    filepath = await download_media(message)
                    sender = await message.get_sender()
                    sender_name = sender.first_name if sender else 'Unknown'

                    caption = (
                        f"🫥 <b>Исчезающее сообщение</b>\n\n"
                        f"👤 <b>От:</b> {sender_name}\n"
                        f"📎 Тип: {get_media_label(message)}\n"
                        f"⏰ {message.date}"
                    )

                    if filepath:
                        if filepath.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                            send_photo(filepath, caption, chat_id=notify_user_id)
                        else:
                            send_document(filepath, caption, chat_id=notify_user_id)
                    else:
                        send_message(caption, chat_id=notify_user_id)
                    return

                # Сохраняем
                if chat_id:
                    await db.save_message(message)

            except Exception as e:
                logger.error(f"[{user_id}] Error in new_message: {e}")

        @client.on(events.MessageDeleted)
        async def handle_deleted(event):
            try:
                logger.info(f"[{user_id}] DELETED: chat={event.chat_id} ids={event.deleted_ids}")

                for deleted_id in event.deleted_ids:
                    msg_data = await db.get_message(deleted_id, event.chat_id)
                    if msg_data:
                        await db.save_deleted_message(msg_data)

                        text = msg_data.get('text', '')
                        username = msg_data.get('from_username') or 'Unknown'
                        preview = text[:200] + "..." if len(text) > 200 else text

                        notification = (
                            f"🗑 <b>Удалено сообщение</b>\n\n"
                            f"👤 <b>От:</b> {username}\n"
                            f"💬 Чат: {msg_data.get('chat_id', '?')}\n"
                            f"⏰ {msg_data.get('sent_at', '?')}\n\n"
                            f"📝 <b>Текст:</b>\n{preview}"
                        )
                        send_message(notification, chat_id=notify_user_id)
                    else:
                        send_message(
                            f"🗑 Удалено сообщение ID:{deleted_id} (не в БД)",
                            chat_id=notify_user_id
                        )

            except Exception as e:
                logger.error(f"[{user_id}] Error in deleted: {e}")

        @client.on(events.MessageEdited)
        async def handle_edited(event):
            try:
                message = event.message
                chat_id = event.chat_id or event.sender_id

                if not chat_id:
                    return

                old_msg = await db.get_message(message.id, chat_id)
                if old_msg and old_msg.get('text') != message.text:
                    await db.save_edited_message(old_msg, message)
                    await db.update_message(message)

                    sender = await message.get_sender()
                    sender_name = sender.first_name if sender else 'Unknown'
                    old_text = old_msg.get('text', '')[:200]
                    new_text = (message.text or '')[:200]

                    notification = (
                        f"✏️ <b>Отредактировано</b>\n\n"
                        f"👤 <b>От:</b> {sender_name}\n"
                        f"💬 Чат: {chat_id}\n"
                        f"⏰ {message.date}\n\n"
                        f"❌ <b>Было:</b> {old_text}\n"
                        f"✅ <b>Стало:</b> {new_text}"
                    )
                    send_message(notification, chat_id=notify_user_id)

            except Exception as e:
                logger.error(f"[{user_id}] Error in edited: {e}")


def get_media_label(message) -> str:
    if message.photo:
        return 'Фото'
    elif message.video:
        return 'Видео'
    elif message.voice:
        return 'Голосовое'
    elif message.video_note:
        return 'Видеокружок'
    elif message.document:
        return 'Документ'
    return 'Медиа'
