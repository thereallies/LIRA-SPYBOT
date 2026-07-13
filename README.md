# Lira Spy Bot

Telegram-бот для отслеживания удалённых и отредактированных сообщений.

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository_url>
cd LIRA\ SPYBOT
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` из примера:
```bash
cp .env.example.txt .env
```

4. Заполните `.env` своими данными:
   - `API_ID` и `API_HASH` — получить на https://my.telegram.org
   - `PHONE` — номер телефона аккаунта
   - `SUPABASE_URL` и `SUPABASE_KEY` — данные из Supabase

5. Создайте базу данных в Supabase:
   - Выполните SQL из `database/schema.sql`

## Запуск

```bash
python main.py
```

## Команды бота

- `/start` — начало работы
- `/help` — справка
- `/add_chat` — добавить чат для отслеживания (в группе)
- `/remove_chat` — убрать чат из отслеживания
- `/list_chats` — список отслеживаемых чатов
- `/settings` — настройки уведомлений
- `/stats` — статистика
- `/privacy` — политика конфиденциальности

## Структура проекта

```
LIRA SPYBOT/
├── config.py              # Конфигурация
├── main.py               # Точка входа
├── requirements.txt      # Зависимости
├── database/
│   ├── __init__.py
│   ├── supabase_client.py # Клиент Supabase
│   └── schema.sql        # SQL миграции
├── handlers/
│   ├── __init__.py
│   ├── commands.py       # Обработчики команд
│   └── events.py         # Обработчики событий
├── services/
│   └── __init__.py
├── utils/
│   ├── __init__.py
│   └── helpers.py        # Вспомогательные функции
└── locales/
    ├── ru.json
    └── en.json
```
