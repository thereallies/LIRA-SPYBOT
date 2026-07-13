from telethon import events
from services.notifier import send_message, send_photo, send_document
from services.media_handler import is_disappearing, download_media
import logging
import traceback

logger = logging.getLogger(__name__)


def get_chat_id(event):
    """Получение chat_id с обработкой None для ЛС"""
    chat_id = event.chat_id
    if chat_id is None:
        chat_id = event.sender_id
    return chat_id


async def register_event_handlers(client, db):
    me = await client.get_me()
    my_id = me.id
    logger.info(f"Bot account: {me.first_name} (ID: {my_id})")

    @client.on(events.NewMessage)
    async def handle_new_message(event):
        try:
            message = event.message
            chat_id = get_chat_id(event)

            # Пропускаем свои сообщения в ЛС
            if message.sender_id == my_id and chat_id == my_id:
                return

            # Логируем все входящие для отладки
            media = getattr(message, 'media', None)
            media_ttl = getattr(media, 'ttl_seconds', None) if media else None
            msg_ttl = getattr(message, 'ttl_seconds', None)
            has_photo = bool(message.photo)
            has_video = bool(message.video)

            if has_photo or has_video or msg_ttl or media_ttl:
                logger.info(f"MSG id={message.id} chat={chat_id} sender={message.sender_id} "
                           f"photo={has_photo} video={has_video} "
                           f"msg_ttl={msg_ttl} media_ttl={media_ttl} text={message.text[:30] if message.text else ''}")

            # Скачиваем исчезающие фото/видео
            if is_disappearing(message):
                logger.info(f"DISAPPEARING DETECTED: msg_id={message.id} chat={chat_id} "
                           f"msg_ttl={msg_ttl} media_ttl={media_ttl}")
                # Сохраняем в БД тоже
                if chat_id:
                    await db.save_message(message)
                await handle_disappearing(message, client)
                return

            # Сохраняем обычное сообщение
            if chat_id:
                result = await db.save_message(message)
                if result:
                    logger.debug(f"Saved message {message.id} from chat {chat_id}")

        except Exception as e:
            logger.error(f"Error saving message: {traceback.format_exc()}")

    @client.on(events.MessageDeleted)
    async def handle_deleted_message(event):
        try:
            chat_id = event.chat_id
            logger.info(f"DELETED EVENT: chat_id={chat_id}, deleted_ids={event.deleted_ids}")

            for deleted_id in event.deleted_ids:
                # Если chat_id None — ищем сообщение в БД по message_id
                msg_data = await db.get_message(deleted_id, chat_id)
                if msg_data:
                    real_chat_id = msg_data.get('chat_id', chat_id)
                    await db.save_deleted_message(msg_data)
                    logger.info(f"Saved deleted message {deleted_id} from chat {real_chat_id}, sending notification...")
                    await notify_deleted(msg_data)
                else:
                    logger.info(f"Message {deleted_id} not in DB")
                    if chat_id:
                        await notify_deleted_simple(deleted_id, chat_id)
                    else:
                        send_message(
                            f"🗑 <b>Удалено сообщение</b>\n\n"
                            f"🆔 ID сообщения: {deleted_id}\n"
                            f"<i>Не найдено в БД (сообщение не было отслежено)</i>"
                        )

        except Exception as e:
            logger.error(f"Error handling deleted message: {traceback.format_exc()}")

    @client.on(events.MessageEdited)
    async def handle_edited_message(event):
        try:
            message = event.message
            chat_id = get_chat_id(event)

            # Пропускаем свои сообщения в ЛС
            if message.sender_id == my_id and chat_id == my_id:
                return

            if not chat_id:
                return

            logger.info(f"EDIT EVENT: message_id={message.id}, chat_id={chat_id}")

            old_msg = await db.get_message(message.id, chat_id)
            if old_msg:
                old_text = old_msg.get('text', '') or ''
                new_text = message.text or ''
                if old_text != new_text:
                    await db.save_edited_message(old_msg, message)
                    await db.update_message(message)
                    logger.info(f"Saved edit for message {message.id}, sending notification...")
                    await notify_edited(old_msg, message)
                else:
                    logger.info(f"Message {message.id} edited but text unchanged")
            else:
                logger.warning(f"Edited message {message.id} not found in DB")

        except Exception as e:
            logger.error(f"Error handling edited message: {traceback.format_exc()}")


async def handle_disappearing(message, client):
    """Обработка исчезающего сообщения"""
    try:
        sender = await message.get_sender()
        sender_name = sender.first_name if sender else 'Unknown'
        sender_id = message.sender_id or 0

        filepath = await download_media(message)

        caption = (
            f"🫥 <b>Исчезающее сообщение</b>\n\n"
            f"👤 <b>От:</b> {sender_name} (ID: {sender_id})\n"
            f"📎 Тип: {get_media_label(message)}\n"
            f"⏰ Время: {message.date}"
        )

        if filepath:
            if filepath.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                result = send_photo(filepath, caption)
            else:
                result = send_document(filepath, caption)
            logger.info(f"Disappearing media sent: {filepath}, result={result}")
        else:
            result = send_message(caption)
            logger.info(f"Disappearing text notification sent: {result}")

    except Exception as e:
        logger.error(f"Error handling disappearing: {traceback.format_exc()}")


def get_media_label(message) -> str:
    if message.photo:
        return 'Фото (исчезающее)'
    elif message.video:
        return 'Видео (исчезающее)'
    elif message.voice:
        return 'Голосовое (исчезающее)'
    elif message.video_note:
        return 'Видеокружок (исчезающий)'
    elif message.document:
        return 'Документ (исчезающий)'
    return 'Медиа (исчезающее)'


async def notify_deleted_simple(deleted_id, chat_id):
    try:
        notification = (
            f"🗑 <b>Удалено сообщение</b>\n\n"
            f"💬 Чат ID: {chat_id}\n"
            f"🆔 ID сообщения: {deleted_id}\n\n"
            f"<i>Не найдено в БД</i>"
        )
        result = send_message(notification)
        logger.info(f"Simple delete notification sent: {result}")
    except Exception as e:
        logger.error(f"Error sending simple deletion notification: {traceback.format_exc()}")


async def notify_deleted(msg_data):
    try:
        chat_title = msg_data.get('chat_id', 'Private')
        username = msg_data.get('from_username') or 'Неизвестный'
        text = msg_data.get('text', '')
        media = msg_data.get('media_type')

        notification = (
            f"🗑 <b>Удалено сообщение</b>\n\n"
            f"👤 <b>От:</b> {username}\n"
            f"💬 <b>Чат:</b> {chat_title}\n"
            f"⏰ <b>Время:</b> {msg_data.get('sent_at', 'Неизвестно')}\n"
        )

        if text:
            preview = text[:300] + "..." if len(text) > 300 else text
            notification += f"\n📝 <b>Текст:</b>\n{preview}\n"

        if media:
            notification += f"\n📎 <b>Медиа:</b> {media}\n"

        result = send_message(notification)
        logger.info(f"Delete notification sent: {result}")
    except Exception as e:
        logger.error(f"Error notifying deleted: {traceback.format_exc()}")


async def notify_edited(old_msg, new_message):
    try:
        sender = await new_message.get_sender()
        sender_name = sender.first_name if sender else 'Неизвестный'

        old_text = old_msg.get('text', '') or ''
        new_text = new_message.text or ''

        old_preview = old_text[:200] + "..." if len(old_text) > 200 else old_text
        new_preview = new_text[:200] + "..." if len(new_text) > 200 else new_text

        notification = (
            f"✏️ <b>Отредактировано сообщение</b>\n\n"
            f"👤 <b>От:</b> {sender_name}\n"
            f"💬 <b>Чат:</b> {old_msg.get('chat_id', 'Private')}\n"
            f"⏰ <b>Время:</b> {new_message.date}\n\n"
            f"❌ <b>Было:</b>\n{old_preview}\n\n"
            f"✅ <b>Стало:</b>\n{new_preview}\n"
        )

        result = send_message(notification)
        logger.info(f"Edit notification sent: {result}")
    except Exception as e:
        logger.error(f"Error notifying edited: {traceback.format_exc()}")
