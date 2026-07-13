from telethon import events
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantsAdmins
import logging

logger = logging.getLogger(__name__)


async def is_admin(client, chat_id, user_id):
    """Проверка, является ли пользователь администратором или создателем чата"""
    try:
        participant = await client(GetParticipantRequest(chat_id, user_id))
        p = participant.participant
        # creator или admin
        return getattr(p, 'admin', None) is not None or getattr(p, 'is_creator', False)
    except Exception:
        return False


async def register_commands(client, db):

    @client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        user = event.sender
        await db.save_user(user)
        await db.create_user_settings(user.id)

        welcome_text = (
            f"👋 <b>Привет, {user.first_name}!</b>\n\n"
            "Я <b>Lira Spy Bot</b> — бот для отслеживания удалённых и отредактированных сообщений.\n\n"
            "<b>Возможности:</b>\n"
            "✅ Сохраняю удалённые сообщения\n"
            "✅ Фиксирую редактирование\n"
            "✅ Сохраняю медиа (фото, видео, голосовые)\n"
            "✅ Мгновенные уведомления\n\n"
            "<b>Как использовать:</b>\n"
            "1. Добавьте меня в чат (если нужно отслеживать группу)\n"
            "2. Или просто напишите мне — я буду отслеживать ЛС\n"
            "3. Используйте /help для получения помощи\n\n"
            "🔒 Ваши данные надёжно защищены!"
        )
        await event.respond(welcome_text, parse_mode='html')

    @client.on(events.NewMessage(pattern='/help'))
    async def help_handler(event):
        help_text = (
            "📖 <b>Справка по боту</b>\n\n"
            "<b>Команды:</b>\n"
            "/start — Начать работу\n"
            "/help — Эта справка\n"
            "/add_chat — Добавить чат для отслеживания\n"
            "/remove_chat — Убрать чат из отслеживания\n"
            "/list_chats — Список отслеживаемых чатов\n"
            "/settings — Настройки уведомлений\n"
            "/stats — Статистика\n"
            "/privacy — Политика конфиденциальности\n\n"
            "<b>Как это работает:</b>\n"
            "• Я сохраняю все входящие сообщения в базу\n"
            "• Если сообщение удаляют — я отправлю вам его копию\n"
            "• Если сообщение редактируют — покажу старую и новую версию\n\n"
            "💡 <b>Совет:</b>\n"
            "Для отслеживания групповых чатов добавьте меня как участника!"
        )
        await event.respond(help_text, parse_mode='html')

    @client.on(events.NewMessage(pattern='/add_chat'))
    async def add_chat_handler(event):
        if not event.is_group and not event.is_channel:
            await event.respond("❌ Эта команда работает только в группах и каналах!")
            return

        chat = await event.get_chat()
        user_id = event.sender_id

        if not await is_admin(client, event.chat_id, user_id):
            await event.respond("❌ Только администраторы могут добавлять чаты!")
            return

        chat_type = 'supergroup' if event.is_group else 'channel'
        result = await db.add_tracked_chat(user_id, chat.id, chat.title, chat_type)

        if result:
            await event.respond(
                f"✅ Чат <b>{chat.title}</b> добавлен для отслеживания!",
                parse_mode='html'
            )
        else:
            await event.respond("❌ Ошибка при добавлении чата. Попробуйте позже.")

    @client.on(events.NewMessage(pattern='/remove_chat'))
    async def remove_chat_handler(event):
        if not event.is_group and not event.is_channel:
            await event.respond("❌ Эта команда работает только в группах и каналах!")
            return

        user_id = event.sender_id
        chat_id = event.chat_id
        result = await db.remove_tracked_chat(user_id, chat_id)

        if result:
            await event.respond("✅ Чат удалён из отслеживания.")
        else:
            await event.respond("❌ Чат не найден в отслеживаемых.")

    @client.on(events.NewMessage(pattern='/list_chats'))
    async def list_chats_handler(event):
        user_id = event.sender_id
        chats = await db.get_tracked_chats(user_id)

        if not chats:
            await event.respond(
                "📭 У вас пока нет отслеживаемых чатов.\n\n"
                "Используйте /add_chat в группе чтобы добавить её."
            )
            return

        text = "📋 <b>Ваши отслеживаемые чаты:</b>\n\n"
        for i, chat in enumerate(chats, 1):
            status = '✅ Активен' if chat['is_active'] else '❌ Неактивен'
            text += f"{i}. {chat['chat_title']}\n"
            text += f"   Тип: {chat['chat_type']}\n"
            text += f"   Статус: {status}\n\n"

        await event.respond(text, parse_mode='html')

    @client.on(events.NewMessage(pattern='/settings'))
    async def settings_handler(event):
        user_id = event.sender_id
        settings = await db.get_user_settings(user_id)

        if not settings:
            await db.create_user_settings(user_id)
            settings = await db.get_user_settings(user_id)

        nd = "✅" if settings.get('notify_deleted') else "❌"
        ne = "✅" if settings.get('notify_edited') else "❌"
        sm = "✅" if settings.get('save_media') else "❌"
        fmt = settings.get('notify_format', 'detailed')

        settings_text = (
            "⚙️ <b>Настройки уведомлений</b>\n\n"
            f"{nd} Удалённые сообщения\n"
            f"{ne} Отредактированные сообщения\n"
            f"{sm} Сохранять медиа\n"
            f"📝 Формат: {fmt}\n\n"
            "Для изменения используйте:\n"
            "/toggle_deleted — вкл/выкл уведомления об удалении\n"
            "/toggle_edited — вкл/выкл уведомления о редактировании\n"
            "/toggle_media — вкл/выкл сохранение медиа\n"
            "/toggle_format — переключить формат"
        )
        await event.respond(settings_text, parse_mode='html')

    @client.on(events.NewMessage(pattern='/toggle_deleted'))
    async def toggle_deleted_handler(event):
        user_id = event.sender_id
        settings = await db.get_user_settings(user_id)
        if not settings:
            await event.respond("❌ Сначала выполните /start")
            return
        new_val = not settings.get('notify_deleted', True)
        await db.update_user_settings(user_id, {'notify_deleted': new_val})
        status = "включены" if new_val else "выключены"
        await event.respond(f"✅ Уведомления об удалении {status}.")

    @client.on(events.NewMessage(pattern='/toggle_edited'))
    async def toggle_edited_handler(event):
        user_id = event.sender_id
        settings = await db.get_user_settings(user_id)
        if not settings:
            await event.respond("❌ Сначала выполните /start")
            return
        new_val = not settings.get('notify_edited', True)
        await db.update_user_settings(user_id, {'notify_edited': new_val})
        status = "включены" if new_val else "выключены"
        await event.respond(f"✅ Уведомления о редактировании {status}.")

    @client.on(events.NewMessage(pattern='/toggle_media'))
    async def toggle_media_handler(event):
        user_id = event.sender_id
        settings = await db.get_user_settings(user_id)
        if not settings:
            await event.respond("❌ Сначала выполните /start")
            return
        new_val = not settings.get('save_media', True)
        await db.update_user_settings(user_id, {'save_media': new_val})
        status = "включено" if new_val else "выключено"
        await event.respond(f"✅ Сохранение медиа {status}.")

    @client.on(events.NewMessage(pattern='/toggle_format'))
    async def toggle_format_handler(event):
        user_id = event.sender_id
        settings = await db.get_user_settings(user_id)
        if not settings:
            await event.respond("❌ Сначала выполните /start")
            return
        cur = settings.get('notify_format', 'detailed')
        new_fmt = 'short' if cur == 'detailed' else 'detailed'
        await db.update_user_settings(user_id, {'notify_format': new_fmt})
        await event.respond(f"✅ Формат уведомлений: {new_fmt}")

    @client.on(events.NewMessage(pattern='/stats'))
    async def stats_handler(event):
        user_id = event.sender_id
        total = await db.get_user_message_count(user_id)
        deleted = await db.get_deleted_count(user_id)
        edited = await db.get_edited_count(user_id)

        stats_text = (
            "📊 <b>Ваша статистика</b>\n\n"
            f"💬 Всего сообщений: {total}\n"
            f"🗑 Удалено: {deleted}\n"
            f"✏️ Отредактировано: {edited}\n\n"
            "Спасибо что используете бота!"
        )
        await event.respond(stats_text, parse_mode='html')

    @client.on(events.NewMessage(pattern='/privacy'))
    async def privacy_handler(event):
        privacy_text = (
            "🔒 <b>Политика конфиденциальности</b>\n\n"
            "<b>Какие данные мы собираем:</b>\n"
            "• Ваш Telegram ID\n"
            "• Имя пользователя\n"
            "• Сообщения из чатов которые вы отслеживаете\n"
            "• Метаданные сообщений (время, отправитель)\n\n"
            "<b>Как мы используем данные:</b>\n"
            "• Для сохранения удалённых/отредактированных сообщений\n"
            "• Для отправки уведомлений\n"
            "• Для улучшения работы бота\n\n"
            "<b>Хранение данных:</b>\n"
            "• Сообщения хранятся в зашифрованной базе Supabase\n"
            "• Вы можете запросить удаление ваших данных в любой момент\n\n"
            "<b>Безопасность:</b>\n"
            "• Мы не передаём данные третьим лицам\n"
            "• Используем защищённое соединение\n"
            "• Регулярные бэкапы\n\n"
            "Используя бота, вы соглашаетесь с этой политикой."
        )
        await event.respond(privacy_text, parse_mode='html')
