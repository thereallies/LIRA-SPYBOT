-- Миграция: настройки медиа и сегментация

-- Добавляем настройку медиа в settings
ALTER TABLE settings ADD COLUMN IF NOT EXISTS notify_media BOOLEAN DEFAULT TRUE;

-- Таблица фильтров (сегментация) — от кого получать уведомления
CREATE TABLE IF NOT EXISTS user_filters (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id),
    filter_type VARCHAR(20) NOT NULL,  -- 'include' или 'exclude'
    target_type VARCHAR(20) NOT NULL,  -- 'chat' или 'user'
    target_id BIGINT NOT NULL,         -- chat_id или user_id
    target_name VARCHAR(255),          -- название для отображения
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, target_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_user_filters_user_id ON user_filters(user_id);

-- Таблица подключённых аккаунтов (для TDLib)
CREATE TABLE IF NOT EXISTS tdlib_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(telegram_id) UNIQUE,
    phone VARCHAR(20) NOT NULL,
    session_id VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);

ALTER TABLE tdlib_sessions DISABLE ROW LEVEL SECURITY;
