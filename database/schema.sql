-- Lira Spy Bot — Multi-User Schema

-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user',  -- 'admin', 'user'
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'banned', 'pending'
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

-- Сессии Telethon (одна на пользователя)
CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) UNIQUE,
    phone VARCHAR(20) NOT NULL,
    session_string TEXT,
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'expired', 'banned'
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

-- Отслеживаемые чаты
CREATE TABLE IF NOT EXISTS tracked_chats (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    chat_title VARCHAR(255),
    chat_type VARCHAR(50),
    user_id BIGINT REFERENCES users(telegram_id),
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(chat_id, user_id)
);

-- Кэш сообщений
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL,
    chat_id BIGINT NOT NULL,
    from_user_id BIGINT,
    from_username VARCHAR(255),
    text TEXT,
    media_type VARCHAR(50),
    media_file_id TEXT,
    media_url TEXT,
    sent_at TIMESTAMP NOT NULL,
    edited_at TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(message_id, chat_id)
);

-- Удалённые сообщения
CREATE TABLE IF NOT EXISTS deleted_messages (
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
CREATE TABLE IF NOT EXISTS edited_messages (
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
CREATE TABLE IF NOT EXISTS settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) UNIQUE,
    notify_deleted BOOLEAN DEFAULT TRUE,
    notify_edited BOOLEAN DEFAULT TRUE,
    notify_format VARCHAR(50) DEFAULT 'detailed',
    save_media BOOLEAN DEFAULT TRUE,
    language VARCHAR(10) DEFAULT 'ru',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Состояние авторизации (для временного хранения кода)
CREATE TABLE IF NOT EXISTS auth_flow (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) UNIQUE,
    phone VARCHAR(20),
    phone_code_hash VARCHAR(255),
    step VARCHAR(20) DEFAULT 'idle',  -- 'idle', 'waiting_phone', 'waiting_code', 'waiting_password'
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_from_user_id ON messages(from_user_id);
CREATE INDEX IF NOT EXISTS idx_messages_sent_at ON messages(sent_at);
CREATE INDEX IF NOT EXISTS idx_deleted_messages_chat_id ON deleted_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_edited_messages_chat_id ON edited_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_tracked_chats_user_id ON tracked_chats(user_id);
CREATE INDEX IF NOT EXISTS idx_settings_user_id ON settings(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_flow_user_id ON auth_flow(user_id);
