import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = './downloads'


def ensure_download_dir():
    """Создание папки для скачивания"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def is_disappearing(message) -> bool:
    """Проверка, является ли сообщение исчезающим (с таймером)"""
    if getattr(message, 'ttl_seconds', None) is not None:
        return True
    # Проверяем TTL на медиа (одноразовые фото/видео)
    media = getattr(message, 'media', None)
    if media and getattr(media, 'ttl_seconds', None) is not None:
        return True
    return False


def get_media_type(message) -> str:
    """Определение типа медиа"""
    if message.photo:
        return 'photo'
    elif message.video:
        return 'video'
    elif message.voice:
        return 'voice'
    elif message.document:
        return 'document'
    elif message.video_note:
        return 'video_note'
    return None


async def download_media(message) -> str:
    """Скачивание медиа из сообщения, возвращает путь к файлу"""
    ensure_download_dir()

    media_type = get_media_type(message)
    if not media_type:
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    sender_id = message.sender_id or 0

    ext_map = {
        'photo': 'jpg',
        'video': 'mp4',
        'voice': 'ogg',
        'document': None,
        'video_note': 'mp4'
    }

    if media_type == 'document' and message.document:
        mime = message.document.mime_type or ''
        if 'image' in mime:
            ext = 'jpg'
        elif 'video' in mime:
            ext = 'mp4'
        elif 'audio' in mime:
            ext = 'ogg'
        else:
            ext = message.document.attributes[0].file_name.split('.')[-1] if message.document.attributes else 'bin'
    else:
        ext = ext_map.get(media_type, 'bin')

    filename = f"{media_type}_{sender_id}_{timestamp}.{ext}"
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    try:
        await message.download_media(file=filepath)
        logger.info(f"Скачано: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        return None
