-- Отключение RLS для всех таблиц (для User API бота)
-- Выполни этот SQL в Supabase SQL Editor

ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE tracked_chats DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE deleted_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE edited_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE settings DISABLE ROW LEVEL SECURITY;

-- Удаляем существующие политики если есть
DROP POLICY IF EXISTS "Enable all for anon" ON users;
DROP POLICY IF EXISTS "Enable all for anon" ON tracked_chats;
DROP POLICY IF EXISTS "Enable all for anon" ON messages;
DROP POLICY IF EXISTS "Enable all for anon" ON deleted_messages;
DROP POLICY IF EXISTS "Enable all for anon" ON edited_messages;
DROP POLICY IF EXISTS "Enable all for anon" ON settings;
