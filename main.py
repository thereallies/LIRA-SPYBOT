"""
Lira Spy Bot — Bot API + TDLib
С сегментацией, настройками медиа и сохранением исчезающих фото
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
ADMIN_IDS = [CREATOR_ID]
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

# Фильтры в памяти
_filters_cache = {}
_filters_cache_time = {}


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


def is_admin(user_id):
    return user_id in ADMIN_IDS


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
        settings = data[0] if data else {'notify_deleted': True, 'notify_edited': True, 'notify_media': True}
    except Exception:
        settings = {'notify_deleted': True, 'notify_edited': True, 'notify_media': True}
    _settings_cache[user_id] = settings
    _settings_cache_time[user_id] = now
    return settings


def invalidate_settings_cache(user_id):
    _settings_cache.pop(user_id, None)
    _settings_cache_time.pop(user_id, None)


def get_user_filters(user_id):
    """Получение фильтров пользователя (с кэшем)"""
    now = time.time()
    if user_id in _filters_cache:
        if now - _filters_cache_time.get(user_id, 0) < CACHE_TTL:
            return _filters_cache[user_id]
    try:
        resp = requests.get(f"{SUPABASE_URL}/rest/v1/user_filters", params={
            'select': '*', 'user_id': f'eq.{user_id}'
        }, headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=5)
        filters = resp.json()
    except Exception:
        filters = []
    _filters_cache[user_id] = filters
    _filters_cache_time[user_id] = now
    return filters


def should_notify(user_id, chat_id, sender_id):
    """Проверяет нужно ли отправлять уведомление по фильтрам"""
    filters = get_user_filters(user_id)
    if not filters:
        return True  # Нет фильтров — уведомляем всегда

    include = [f for f in filters if f['filter_type'] == 'include']
    exclude = [f for f in filters if f['filter_type'] == 'exclude']

    # Если есть include-фильтры — уведомляем ТОЛЬКО для включённых
    if include:
        for f in include:
            if f['target_type'] == 'chat' and f['target_id'] == chat_id:
                return True
            if f['target_type'] == 'user' and f['target_id'] == sender_id:
                return True
        return False

    # Если есть exclude-фильтры — НЕ уведомляем для исключённых
    for f in exclude:
        if f['target_type'] == 'chat' and f['target_id'] == chat_id:
            return False
        if f['target_type'] == 'user' and f['target_id'] == sender_id:
            return False

    return True


# ============================================================
# TDLib ИНТЕГРАЦИЯ
# ============================================================

class TDLibClient:
    """Клиент для скачивания медиа через TDLib"""

    def __init__(self):
        self.process = None
        self.connected = False

    def start(self):
        """Запуск TDLib клиента"""
        try:
            # Проверяем наличие TDLib
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
        """Отправка запроса в TDLib"""
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
        """Скачивание файла через TDLib"""
        request = {
            '@type': 'downloadFile',
            'file_id': file_id,
            'priority': 1
        }
        result = self.send_request(request)
        return result

    def stop(self):
        """Остановка TDLib"""
        if self.process:
            self.process.terminate()
            self.connected = False


tdlib = TDLibClient()


# ============================================================
# MEDIA HANDLING
# ============================================================

def download_telegram_file(file_id):
    """Скачать файл через Bot API"""
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


def send_media_to_admin(msg, chat_id):
    """Переслать медиа админу"""
    sender = msg.get('from', {})
    sender_name = sender.get('first_name', 'Unknown')
    sender_id = sender.get('id', 0)
    caption = f"📎 <b>Медиа</b>\n👤 {sender_name} | 💬 Чат: {chat_id}"

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
                for admin_id in ADMIN_IDS:
                    api('sendPhoto', {'chat_id': admin_id, 'caption': caption, 'parse_mode': 'HTML'},
                        files={'photo': f})
            elif msg.get('video'):
                for admin_id in ADMIN_IDS:
                    api('sendVideo', {'chat_id': admin_id, 'caption': caption, 'parse_mode': 'HTML'},
                        files={'video': f})
            elif msg.get('voice'):
                for admin_id in ADMIN_IDS:
                    api('sendVoice', {'chat_id': admin_id, 'caption': caption, 'parse_mode': 'HTML'},
                        files={'voice': f})
            elif msg.get('video_note'):
                for admin_id in ADMIN_IDS:
                    api('sendVideoNote', {'chat_id': admin_id}, files={'video_note': f})
            else:
                for admin_id in ADMIN_IDS:
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
        buttons.append([{'text': '👑 Админ', 'callback_data': 'admin'}])
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
        [{'text': '📸 Медиа', 'callback_data': 'how_media'}],
        [{'text': '🎯 Фильтры', 'callback_data': 'how_filters'}],
        [{'text': '◀️ Назад', 'callback_data': 'main'}],
    ]}


def admin_kb():
    return {'inline_keyboard': [
        [{'text': '👥 Пользователи', 'callback_data': 'adm_users'}],
        [{'text': '📊 Статистика', 'callback_data': 'adm_stats'}],
        [{'text': '📋 Удаления', 'callback_data': 'adm_deleted'}],
        [{'text': '📋 Редактирования', 'callback_data': 'adm_edited'}],
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
        role = 'admin' if user_id in ADMIN_IDS else 'user'
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

    # Медиа из бизнес-сообщений
    if is_business and media_type:
        s = get_cached_settings(CREATOR_ID)
        if s.get('notify_media') and should_notify(CREATOR_ID, chat_id, user_id):
            send_media_to_admin(msg, chat_id)

    if not is_business:
        if text == '/start':
            await cmd_start(chat_id, msg.get('from'))
        elif text == '/help':
            send(chat_id, "📖 Используй /start для главного меню")
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
                if target not in ADMIN_IDS:
                    await db.update_user(target, {'status': 'banned'})
                    send(chat_id, f"✅ Заблокирован <code>{target}</code>")
            except (ValueError, IndexError):
                send(chat_id, "❌ /ban <code>ID</code>")


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

    # === ГЛАВНОЕ МЕНЮ ===
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

    # === НАСТРОЙКИ ===
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
        # notify_media пока не в БД — просто переключаем в кэше
        s = get_cached_settings(user_id)
        new_val = not s.get('notify_media', True)
        s['notify_media'] = new_val
        _settings_cache[user_id] = s
        send(chat_id, "⚙️ <b>Настройки</b>", reply_markup=settings_kb(user_id))

    # === ФИЛЬТРЫ ===
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

    # === ИНСТРУКЦИИ ===
    elif data == 'how_connect':
        send(chat_id,
            "🔌 <b>Как подключить</b>\n\n"
            "1. Настройки → Аккаунт → Автоматизация чатов\n"
            "2. Введи <b>@liraspy_bot</b>\n"
            "3. Добавить")

    elif data == 'how_media':
        send(chat_id,
            "📸 <b>Медиа</b>\n\n"
            "Бот скачивает и пересылает:\n"
            "• Фото и видео\n"
            "• Голосовые\n"
            "• Документы\n"
            "• Видеокружки\n\n"
            "Включить/выключить: ⚙️ Настройки → Медиа")

    elif data == 'how_filters':
        send(chat_id,
            "🎯 <b>Фильтры</b>\n\n"
            "Позволяют выбрать от кого получать уведомления.\n\n"
            "<b>Типы фильтров:</b>\n"
            "➕ Include — уведомлять ТОЛЬКО от этих чатов/юзеров\n"
            "➖ Exclude — НЕ уведомлять от этих чатов/юзеров\n\n"
            "Пример: добавьте exclude для чата с мамой, чтобы не спамить.")

    elif data == 'referral':
        send(chat_id,
            "👥 <b>Реферальная программа</b>\n\n"
            "Приглашай друзей!\n"
            "Ссылка: @liraspy_bot\n\n"
            "Скоро будут бонусы!")

    # === АДМИНКА ===
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
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/messages", params={
                'select': 'id', 'count': 'exact'
            }, headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}, timeout=5)
            total_msgs = resp.headers.get('content-range', '*/0').split('/')[1]
        except Exception:
            total_msgs = '?'
        send(chat_id,
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Пользователей: {len(users)} (активных: {active})\n"
            f"💬 Сообщений: {total_msgs}")

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


# ============================================================
# BOT COMMANDS
# ============================================================

async def cmd_start(chat_id, user=None):
    name = user.get('first_name', '') if user else ''
    text = (
        f"👋 <b>Добро пожаловать, {name}!</b>\n\n"
        "Отслеживание удалённых и отредактированных сообщений.\n\n"
        "<b>Возможности:</b>\n"
        "• 🗑 Удалённые сообщения\n"
        "• ✏️ Отредактированные сообщения\n"
        "• 📸 Медиа (фото, видео, голосовые)\n"
        "• 🎯 Фильтры — выбирай от кого получать\n\n"
        "Подключите бота:\n"
        "1. Настройки → Аккаунт → Автоматизация чатов\n"
        "2. Введите <b>@liraspy_bot</b>\n"
        "3. Добавить"
    )
    send(chat_id, text, reply_markup=main_menu(is_admin(user.get('id') if user else 0)))


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
    me = api('getMe')
    if me and me.get('ok'):
        logger.info(f"Bot: @{me['result'].get('username')}")

    # Запускаем TDLib если доступен
    if tdlib.start():
        logger.info("TDLib started for media downloads")

    api('setMyCommands', {
        'commands': [
            {'command': 'start', 'description': 'Главное меню'},
            {'command': 'settings', 'description': 'Настройки'},
            {'command': 'filters', 'description': 'Фильтры'},
            {'command': 'myid', 'description': 'Мой ID'},
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
                    await handle_edited_message(u['edited_business_message'], True)
                elif 'deleted_business_messages' in u:
                    await handle_deleted_messages(u['deleted_business_messages'])
            except Exception as e:
                logger.error(f"Error: {e}")
        await asyncio.sleep(0.05)


async def handle_edited_message(msg, is_business=False):
    chat_id = msg['chat']['id']
    message_id = msg['message_id']
    new_text = msg.get('text', '')
    user_id = msg.get('from', {}).get('id')

    if user_id == CREATOR_ID:
        return

    s = get_cached_settings(CREATOR_ID)
    if not s.get('notify_edited'):
        return

    if not should_notify(CREATOR_ID, chat_id, user_id):
        return

    old_msg = await db.get_message(message_id, chat_id)
    if old_msg and old_msg.get('text') != new_text:
        await db.save_edited_message_raw({
            'original_message_id': old_msg.get('id'),
            'chat_id': chat_id,
            'from_user_id': user_id,
            'from_username': msg.get('from', {}).get('username'),
            'old_text': old_msg.get('text', ''),
            'new_text': new_text,
            'sent_at': old_msg.get('sent_at'),
        })
        await db.update_message_text(message_id, chat_id, new_text)

        sender = msg.get('from', {}).get('first_name', 'Unknown')
        old_p = (old_msg.get('text', '') or '')[:150]
        new_p = (new_text or '')[:150]

        for admin_id in ADMIN_IDS:
            send(admin_id,
                f"✏️ <b>Редактирование</b>\n\n"
                f"👤 {sender} | 💬 Чат: {chat_id}\n\n"
                f"❌ <code>{old_p}</code>\n"
                f"✅ <code>{new_p}</code>")


async def handle_deleted_messages(update):
    chat_id = update.get('chat', {}).get('id')
    message_ids = update.get('message_ids', [])

    s = get_cached_settings(CREATOR_ID)
    if not s.get('notify_deleted'):
        return

    for msg_id in message_ids:
        msg_data = await db.get_message(msg_id, chat_id)
        if not msg_data:
            continue

        from_user_id = msg_data.get('from_user_id')
        if from_user_id == CREATOR_ID:
            continue

        if not should_notify(CREATOR_ID, chat_id, from_user_id):
            continue

        await db.save_deleted_message_raw({
            'original_message_id': msg_data.get('id'),
            'chat_id': chat_id,
            'from_user_id': from_user_id,
            'from_username': msg_data.get('from_username'),
            'original_text': msg_data.get('text'),
            'media_type': msg_data.get('media_type'),
            'sent_at': msg_data.get('sent_at'),
        })

        text = (msg_data.get('text', '') or '')[:200]
        username = msg_data.get('from_username') or 'Unknown'
        for admin_id in ADMIN_IDS:
            send(admin_id,
                f"🗑 <b>Удалено</b>\n\n"
                f"👤 {username} | 💬 Чат: {chat_id}\n"
                f"📝 {text}")


if __name__ == '__main__':
    asyncio.run(main())
