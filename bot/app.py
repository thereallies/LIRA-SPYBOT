"""
Lira Spy Bot — Bot API interface
Handles user interaction through @liraspy_bot
"""
import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.types import User
from database.supabase_client import SupabaseClient
from bot.auth_flow import AuthFlowManager
from monitor.manager import MonitorManager

logger = logging.getLogger(__name__)

ADMIN_IDS = [1658547011]  # Список администраторов


class LiraSpyBot:
    def __init__(self, bot_token: str, db: SupabaseClient,
                 api_id: int, api_hash: str):
        self.bot_token = bot_token
        self.db = db
        self.api_id = api_id
        self.api_hash = api_hash
        self.auth_manager = AuthFlowManager(db, api_id, api_hash)
        self.monitor_manager = MonitorManager(db, api_id, api_hash)
        self._client = None

    async def start(self):
        """Запуск бота"""
        from telethon import TelegramClient
        self._client = TelegramClient('bot_session', self.api_id, self.api_hash)
        await self._client.start(bot_token=self.bot_token)
        logger.info("Bot started")

        # Регистрация хендлеров
        self._register_handlers()

        # Восстановление сессий
        await self.monitor_manager.restore_all_sessions(self.db)

        logger.info("Bot is running...")
        await self._client.run_until_disconnected()

    def _register_handlers(self):
        from telethon import events

        @self._client.on(events.NewMessage(pattern='/start'))
        async def handle_start(event):
            await self._handle_start(event)

        @self._client.on(events.NewMessage(pattern='/help'))
        async def handle_help(event):
            await self._handle_help(event)

        @self._client.on(events.NewMessage(pattern='/login'))
        async def handle_login(event):
            await self._handle_login(event)

        @self._client.on(events.NewMessage(pattern='/logout'))
        async def handle_logout(event):
            await self._handle_logout(event)

        @self._client.on(events.NewMessage(pattern='/status'))
        async def handle_status(event):
            await self._handle_status(event)

        @self._client.on(events.NewMessage(pattern='/settings'))
        async def handle_settings(event):
            await self._handle_settings(event)

        @self._client.on(events.NewMessage(pattern='/toggle_deleted'))
        async def handle_toggle_deleted(event):
            await self._handle_toggle(event, 'notify_deleted')

        @self._client.on(events.NewMessage(pattern='/toggle_edited'))
        async def handle_toggle_edited(event):
            await self._handle_toggle(event, 'notify_edited')

        @self._client.on(events.NewMessage(pattern='/users'))
        async def handle_users(event):
            await self._handle_users(event)

        @self._client.on(events.NewMessage(pattern='/broadcast'))
        async def handle_broadcast(event):
            await self._handle_broadcast(event)

        @self._client.on(events.NewMessage(pattern='/ban'))
        async def handle_ban(event):
            await self._handle_ban(event)

        @self._client.on(events.NewMessage)
        async def handle_text(event):
            await self._handle_text(event)

    async def _handle_start(self, event):
        user = event.sender
        user_id = user.id

        # Создаём/обновляем пользователя
        existing = await self.db.get_user(user_id)
        if not existing:
            role = 'admin' if user_id in ADMIN_IDS else 'user'
            await self.db.create_user(user_id, user.username, user.first_name, role)
            await self.db.create_user_settings(user_id)

        text = (
            f"👋 Привет, {user.first_name}!\n\n"
            "Я <b>Lira Spy Bot</b> — бот для отслеживания удалённых и отредактированных сообщений.\n\n"
            "<b>Как начать:</b>\n"
            "1. Напиши /login\n"
            "2. Введи номер телефона своего Telegram\n"
            "3. Получи код и введи его сюда\n"
            "4. Готово! Бот начнёт отслеживать\n\n"
            "<b>Команды:</b>\n"
            "/login — Авторизовать аккаунт\n"
            "/logout — Отключить мониторинг\n"
            "/status — Статус мониторинга\n"
            "/settings — Настройки уведомлений\n"
            "/help — Справка"
        )
        await event.respond(text, parse_mode='html')

    async def _handle_help(self, event):
        text = (
            "📖 <b>Справка</b>\n\n"
            "<b>Основные команды:</b>\n"
            "/start — Начало работы\n"
            "/login — Авторизовать Telegram-аккаунт\n"
            "/logout — Отключить мониторинг\n"
            "/status — Текущий статус\n"
            "/settings — Настройки уведомлений\n\n"
            "<b>Как это работает:</b>\n"
            "1. Ты авторизуешь свой аккаунт через бота\n"
            "2. Бот начинает мониторить твои чаты\n"
            "3. При удалении/редактировании — присылает уведомление\n"
            "4. Исчезающие фото скачиваются автоматически\n\n"
            "<b>Безопасность:</b>\n"
            "• Твои данные хранятся в зашифрованном виде\n"
            "• Ты можешь отключить мониторинг в любой момент\n"
            "/logout"
        )
        await event.respond(text, parse_mode='html')

    async def _handle_login(self, event):
        user_id = event.sender_id

        # Проверяем, есть ли уже активная сессия
        session = await self.db.get_session(user_id)
        if session and session.get('status') == 'active':
            await event.respond(
                "✅ У тебя уже есть активная сессия!\n"
                "Используй /logout чтобы отключить текущую."
            )
            return

        # Начинаем flow авторизации
        await self.db.set_auth_flow(user_id, step='waiting_phone')
        await event.respond(
            "📱 Введи номер телефона своего Telegram-аккаунта:\n"
            "Формат: <code>+79991234567</code>",
            parse_mode='html'
        )

    async def _handle_logout(self, event):
        user_id = event.sender_id
        await self.monitor_manager.stop_monitoring(user_id)
        await self.db.delete_session(user_id)
        await self.db.clear_auth_flow(user_id)
        await event.respond("✅ Мониторинг отключён. Сессия удалена.")

    async def _handle_status(self, event):
        user_id = event.sender_id
        session = await self.db.get_session(user_id)
        user = await self.db.get_user(user_id)

        if not session or session.get('status') != 'active':
            await event.respond(
                "❌ Нет активной сессии.\n"
                "Используй /login чтобы начать мониторинг."
            )
            return

        phone = session.get('phone', 'Неизвестно')
        is_running = self.monitor_manager.is_running(user_id)

        status = "🟢 Работает" if is_running else "🔴 Остановлен"

        text = (
            f"📊 <b>Статус мониторинга</b>\n\n"
            f"📱 Телефон: <code>{phone}</code>\n"
            f"🔄 Статус: {status}\n"
            f"👤 Роль: {user.get('role', 'user') if user else 'user'}\n"
        )
        await event.respond(text, parse_mode='html')

    async def _handle_settings(self, event):
        user_id = event.sender_id
        settings = await self.db.get_user_settings(user_id)

        if not settings:
            await self.db.create_user_settings(user_id)
            settings = await self.db.get_user_settings(user_id)

        if not settings:
            await event.respond("❌ Ошибка загрузки настроек. Попробуй позже.")
            return

        nd = "✅" if settings.get('notify_deleted') else "❌"
        ne = "✅" if settings.get('notify_edited') else "❌"

        text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"{nd} Уведомления об удалении\n"
            f"{ne} Уведомления о редактировании\n\n"
            "Для изменения:\n"
            "/toggle_deleted — вкл/выкл удаления\n"
            "/toggle_edited — вкл/выкл редактирования"
        )
        await event.respond(text, parse_mode='html')

    async def _handle_toggle(self, event, field):
        user_id = event.sender_id
        settings = await self.db.get_user_settings(user_id)
        if not settings:
            await event.respond("❌ Сначала выполните /start")
            return

        new_val = not settings.get(field, True)
        await self.db.update_user_settings(user_id, {field: new_val})
        status = "включены" if new_val else "выключены"
        name = "удаления" if field == 'notify_deleted' else "редактирования"
        await event.respond(f"✅ Уведомления о {name} {status}.")

    async def _handle_users(self, event):
        user_id = event.sender_id
        user = await self.db.get_user(user_id)
        if not user or user.get('role') != 'admin':
            await event.respond("❌ Нет доступа.")
            return

        users = await self.db.get_all_users()
        text = "👥 <b>Пользователи:</b>\n\n"
        for u in users:
            status = "🟢" if u.get('status') == 'active' else "🔴"
            role = "👑" if u.get('role') == 'admin' else "👤"
            text += f"{status} {role} {u.get('first_name', 'N/A')} (@{u.get('username', 'N/A')}) ID: {u['telegram_id']}\n"

        await event.respond(text, parse_mode='html')

    async def _handle_broadcast(self, event):
        user_id = event.sender_id
        user = await self.db.get_user(user_id)
        if not user or user.get('role') != 'admin':
            await event.respond("❌ Нет доступа.")
            return

        text = event.message.text.replace('/broadcast ', '', 1)
        if text == '/broadcast':
            await event.respond("Использование: /broadcast <сообщение>")
            return

        users = await self.db.get_all_active_user_ids()
        sent = 0
        for uid in users:
            try:
                await self._client.send_message(uid, f"📢 <b>Объявление:</b>\n\n{text}", parse_mode='html')
                sent += 1
            except Exception:
                pass

        await event.respond(f"✅ Отправлено {sent} из {len(users)} пользователей.")

    async def _handle_ban(self, event):
        user_id = event.sender_id
        user = await self.db.get_user(user_id)
        if not user or user.get('role') != 'admin':
            await event.respond("❌ Нет доступа.")
            return

        parts = event.message.text.split()
        if len(parts) < 2:
            await event.respond("Использование: /ban <user_id>")
            return

        try:
            target_id = int(parts[1])
            await self.db.update_user(target_id, {'status': 'banned'})
            await self.monitor_manager.stop_monitoring(target_id)
            await self.db.delete_session(target_id)
            await event.respond(f"✅ Пользователь {target_id} заблокирован.")
        except ValueError:
            await event.respond("❌ Неверный ID.")

    async def _handle_text(self, event):
        """Обработка текстовых сообщений (для auth flow)"""
        # Игнорируем сообщения от самого бота
        try:
            me = await self._client.get_me()
            if event.sender_id == me.id:
                return
        except Exception:
            return

        user_id = event.sender_id
        auth = await self.db.get_auth_flow(user_id)

        if not auth or auth.get('step') == 'idle':
            return

        text = event.message.text.strip()

        if auth.get('step') == 'waiting_phone':
            # Проверяем формат телефона
            if not text.startswith('+') or not text[1:].isdigit() or len(text) < 10:
                await event.respond("❌ Неверный формат. Используй: +79991234567")
                return

            # Отправляем код
            await event.respond("⏳ Отправляю код...")
            result = await self.auth_manager.send_code(user_id, text)

            if result is True:
                await self.db.set_auth_flow(user_id, phone=text, step='waiting_code')
                await event.respond(
                    "📨 Код отправлен!\n"
                    "Введи 5-значный код из Telegram:"
                )
            elif isinstance(result, dict) and result.get('error') == 'flood_wait':
                seconds = result.get('seconds', 300)
                minutes = seconds // 60
                await event.respond(
                    f"⏳ Telegram просит подождать {minutes} мин. "
                    f"Повтори позже."
                )
                await self.db.clear_auth_flow(user_id)
            else:
                await event.respond("❌ Ошибка отправки кода. Попробуй позже.")

        elif auth.get('step') == 'waiting_code':
            phone = auth.get('phone')

            # Проверяем что введено 5-значный код
            if not text.isdigit() or len(text) != 5:
                await event.respond("❌ Код должен быть 5 цифр. Попробуй ещё:")
                return

            result = await self.auth_manager.sign_in(user_id, phone, text)

            if result == 'need_password':
                await self.db.set_auth_flow(user_id, phone=phone, step='waiting_password')
                await event.respond("🔑 Включена 2FA. Введи пароль:")

            elif result == 'invalid_code':
                await event.respond("❌ Неверный код. Попробуй ещё:")

            elif result == 'code_expired':
                await event.respond(
                    "⏰ Код истёк.\n"
                    "Напиши /login чтобы получить новый код."
                )
                await self.auth_manager.cancel(user_id)
                await self.db.clear_auth_flow(user_id)

            elif isinstance(result, dict) and result.get('error') == 'flood_wait':
                seconds = result.get('seconds', 300)
                minutes = seconds // 60
                await event.respond(
                    f"⏳ Telegram заблокировал на {minutes} мин. Подожди."
                )
                await self.auth_manager.cancel(user_id)
                await self.db.clear_auth_flow(user_id)

            elif result:
                # Успешная авторизация
                session_string = await self.auth_manager.get_session_string(user_id)
                if session_string:
                    await self.db.save_session(user_id, phone, session_string)
                    await self.db.clear_auth_flow(user_id)
                    await self.monitor_manager.start_monitoring(user_id, session_string)

                    await event.respond(
                        f"✅ Авторизация успешна!\n"
                        f"📱 Аккаунт: {phone}\n"
                        f"🔄 Мониторинг запущен!"
                    )
                else:
                    await event.respond("❌ Ошибка сохранения сессии.")

            else:
                await event.respond("❌ Ошибка авторизации. Попробуй /login заново.")
                await self.auth_manager.cancel(user_id)
                await self.db.clear_auth_flow(user_id)

        elif auth.get('step') == 'waiting_password':
            phone = auth.get('phone')

            result = await self.auth_manager.sign_in_password(user_id, text)

            if result:
                session_string = await self.auth_manager.get_session_string(user_id)
                if session_string:
                    await self.db.save_session(user_id, phone, session_string)
                    await self.db.clear_auth_flow(user_id)
                    await self.monitor_manager.start_monitoring(user_id, session_string)

                    await event.respond(
                        f"✅ Авторизация успешна!\n"
                        f"📱 Аккаунт: {phone}\n"
                        f"🔄 Мониторинг запущен!"
                    )
                else:
                    await event.respond("❌ Ошибка сохранения сессии.")

            elif isinstance(result, dict) and result.get('error') == 'flood_wait':
                seconds = result.get('seconds', 300)
                minutes = seconds // 60
                await event.respond(
                    f"⏳ Telegram заблокировал на {minutes} мин. Подожди."
                )
                await self.auth_manager.cancel(user_id)
                await self.db.clear_auth_flow(user_id)

            else:
                await event.respond(
                    "❌ Неверный пароль. Попробуй /login заново."
                )
                await self.auth_manager.cancel(user_id)
                await self.db.clear_auth_flow(user_id)
