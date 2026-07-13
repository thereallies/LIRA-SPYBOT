import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Telegram
_api_id_raw = os.getenv('API_ID')
_api_hash_raw = os.getenv('API_HASH')
_phone = os.getenv('PHONE')
_session_name = os.getenv('SESSION_NAME', 'dialog_spy')

# Supabase
_supabase_url = os.getenv('SUPABASE_URL')
_supabase_key = os.getenv('SUPABASE_KEY')

# Bot
_bot_token = os.getenv('BOT_TOKEN')
_admin_id_raw = os.getenv('ADMIN_ID')

# Settings
DOWNLOAD_PATH = './downloads'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


def validate_config():
    """Проверка обязательных переменных окружения"""
    required = {
        'API_ID': _api_id_raw,
        'API_HASH': _api_hash_raw,
        'PHONE': _phone,
        'SUPABASE_URL': _supabase_url,
        'SUPABASE_KEY': _supabase_key,
    }
    missing = [name for name, val in required.items() if not val]
    if missing:
        print(f"ОШИБКА: Не заданы переменные окружения: {', '.join(missing)}")
        print("Скопируйте .env.example.txt в .env и заполните значения.")
        sys.exit(1)


# Выполняем валидацию при импорте
validate_config()

# Преобразуем типы после проверки
API_ID = int(_api_id_raw)
API_HASH = _api_hash_raw
PHONE = _phone
SESSION_NAME = _session_name
SUPABASE_URL = _supabase_url
SUPABASE_KEY = _supabase_key
BOT_TOKEN = _bot_token
ADMIN_ID = int(_admin_id_raw) if _admin_id_raw else 0
