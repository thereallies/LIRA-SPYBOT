# ЗАДАЧА: Создать Telegram бота для отслеживания удалённых и отредактированных сообщений (аналог @DialogSpyBot)

## ТРЕБОВАНИЯ:

### 1. СТЕК ТЕХНОЛОГИЙ:
- **Язык**: Python 3.11+
- **Библиотека**: Telethon (MTProto User API)
- **База данных**: Supabase (PostgreSQL)
- **Хостинг**: совместимость with bothost
- **Асинхронность**: asyncio

### 2. ФУНКЦИОНАЛ:

#### Основные возможности:
✅ **Отслеживание удалённых сообщений** — сохранять текст, медиа, автора, время
✅ **Отслеживание отредактированных сообщений** — хранить старую и новую версию
✅ **Фиксация медиа** — фото, видео, голосовые, документы, кружочки
✅ **Мониторинг активности** — когда пользователь был онлайн (если возможно)
✅ **Уведомления** — мгновенные уведомления о изменениях
✅ **Поддержка групп и личных чатов**

#### Команды бота:
/start — начало работы, инструкция
/help — помощь
/add_chat — добавить чат для отслеживания
/remove_chat — убрать чат из отслеживания
/list_chats — список отслеживаемых чатов
/settings — настройки уведомлений
/stats — статистика
/privacy — политика конфиденциальности

### 3. СТРУКТУРА БАЗЫ ДАННЫХ (Supabase):

Создай SQL миграции для следующих таблиц:

```sql
-- Пользователи бота
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    phone VARCHAR(20),
    is_premium BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

-- Отслеживаемые чаты
CREATE TABLE tracked_chats (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    chat_title VARCHAR(255),
    chat_type VARCHAR(50), -- 'private', 'group', 'supergroup', 'channel'
    user_id BIGINT REFERENCES users(telegram_id),
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(chat_id, user_id)
);

-- Кэш сообщений
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL,
    chat_id BIGINT NOT NULL,
    from_user_id BIGINT,
    from_username VARCHAR(255),
    text TEXT,
    media_type VARCHAR(50), -- 'photo', 'video', 'voice', 'document', 'video_note'
    media_file_id TEXT,
    media_url TEXT,
    sent_at TIMESTAMP NOT NULL,
    edited_at TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(message_id, chat_id)
);

-- Удалённые сообщения
CREATE TABLE deleted_messages (
    id BIGSERIAL PRIMARY KEY,
    original_message_id BIGINT REFERENCES messages(id),
    chat_id BIGINT NOT NULL,
    from_user_id BIGINT,
    from_username VARCHAR(255),
    original_text TEXT,
    media_type VARCHAR(50),
    media_url TEXT,
    sent_at TIMESTAMP,
    deleted_at TIMESTAMP DEFAULT NOW(),
    deleted_by BIGINT
);

-- Отредактированные сообщения
CREATE TABLE edited_messages (
    id BIGSERIAL PRIMARY KEY,
    original_message_id BIGINT REFERENCES messages(id),
    chat_id BIGINT NOT NULL,
    from_user_id BIGINT,
    from_username VARCHAR(255),
    old_text TEXT,
    new_text TEXT,
    media_type VARCHAR(50),
    media_url TEXT,
    sent_at TIMESTAMP,
    edited_at TIMESTAMP DEFAULT NOW(),
    edit_count INTEGER DEFAULT 1
);

-- Настройки пользователя
CREATE TABLE settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) UNIQUE,
    notify_deleted BOOLEAN DEFAULT TRUE,
    notify_edited BOOLEAN DEFAULT TRUE,
    notify_format VARCHAR(50) DEFAULT 'detailed', -- 'short', 'detailed'
    save_media BOOLEAN DEFAULT TRUE,
    language VARCHAR(10) DEFAULT 'ru',
    created_at TIMESTAMP DEFAULT NOW()
);