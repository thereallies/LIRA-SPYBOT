-- Всё-в-одном: колонки + RLS
-- Выполни в Supabase SQL Editor

-- 1. Добавляем недостающие колонки в users
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';

-- 2. Отключаем RLS на ВСЕХ таблицах
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE tracked_chats DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE deleted_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE edited_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE settings DISABLE ROW LEVEL SECURITY;
ALTER TABLE sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE auth_flow DISABLE ROW LEVEL SECURITY;

-- 3. Создаём таблицы если их нет
CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) UNIQUE,
    phone VARCHAR(20) NOT NULL,
    session_string TEXT,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_flow (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) UNIQUE,
    phone VARCHAR(20),
    phone_code_hash VARCHAR(255),
    step VARCHAR(20) DEFAULT 'idle',
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- 4. Индексы
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_flow_user_id ON auth_flow(user_id);
