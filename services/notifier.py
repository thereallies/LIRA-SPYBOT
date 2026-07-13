import os
import logging
import time
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_ID = os.getenv('ADMIN_ID', '')
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

MAX_RETRIES = 3
TIMEOUT = 20


def _send_with_retry(method, data=None, files=None):
    """Отправка с повторными попытками"""
    for attempt in range(MAX_RETRIES):
        try:
            if files:
                resp = requests.post(f"{API_BASE}/{method}", data=data, files=files, timeout=TIMEOUT)
            else:
                resp = requests.post(f"{API_BASE}/{method}", json=data, timeout=TIMEOUT)
            result = resp.json()
            if result.get('ok'):
                return result
            logger.warning(f"Telegram API error (attempt {attempt+1}): {result}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout (attempt {attempt+1}), retrying...")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"Send error (attempt {attempt+1}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return None


def send_message(text: str, chat_id: int = None, parse_mode: str = 'HTML'):
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан")
        return None
    target = chat_id or ADMIN_ID
    if not target:
        logger.error("ADMIN_ID не задан")
        return None
    return _send_with_retry('sendMessage', {
        'chat_id': int(target),
        'text': text,
        'parse_mode': parse_mode
    })


def send_photo(photo_path: str, caption: str = '', chat_id: int = None):
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан")
        return None
    target = chat_id or ADMIN_ID
    if not target:
        logger.error("ADMIN_ID не задан")
        return None
    try:
        with open(photo_path, 'rb') as f:
            return _send_with_retry('sendPhoto', {
                'chat_id': int(target),
                'caption': caption,
                'parse_mode': 'HTML'
            }, {'photo': f})
    except Exception as e:
        logger.error(f"Ошибка отправки фото: {e}")
        return None


def send_document(file_path: str, caption: str = '', chat_id: int = None):
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан")
        return None
    target = chat_id or ADMIN_ID
    if not target:
        logger.error("ADMIN_ID не задан")
        return None
    try:
        with open(file_path, 'rb') as f:
            return _send_with_retry('sendDocument', {
                'chat_id': int(target),
                'caption': caption,
                'parse_mode': 'HTML'
            }, {'document': f})
    except Exception as e:
        logger.error(f"Ошибка отправки документа: {e}")
        return None
