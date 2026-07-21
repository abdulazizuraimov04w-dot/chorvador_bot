import asyncio
import datetime
import os
from aiogram import Bot
from aiogram.types import URLInputFile, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

from database import models
from utils.logger import logger

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)

try:
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
except Exception as e:
    logger.error(f"Error parsing ADMIN_IDS in scheduler: {e}")
    ADMIN_IDS = []


async def send_breakfast_reminder_to_customers(bot: Bot):
    """
    Mijozlarga ertalabki eslatma yuboradi.
    Mahsulotlar ro'yxati o'rniga 'Buyurtma berish' MiniApp tugmasi ko'rsatiladi.
    """
    logger.info("Triggering automated breakfast order reminder for customers.")

    # Bazadan matn va rasmni olish
    text = await models.get_setting(
        'reminder_text',
        "☀️ Xayrli tong!\n\nBugun nonushtaga sut mahsulotlari buyurtma qiling 🥛"
    )
    photo_url = await models.get_setting('reminder_photo', '')

    # MiniApp URL
    base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    miniapp_url = f"{base_url}/miniapp"

    # "Buyurtma berish" tugmasi — WebApp ochadi
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📲 Buyurtma berish",
            web_app=WebAppInfo(url=miniapp_url)
        )
    ]])

    try:
        users = await models.get_all_users()
    except Exception as e:
        logger.error(f"Failed to fetch users for breakfast reminder: {e}")
        return

    sent_count = 0
    fail_count = 0

    for u in users:
        if not u.get("is_admin", False):
            try:
                if photo_url:
                    await bot.send_photo(
                        chat_id=u['telegram_id'],
                        photo=URLInputFile(photo_url),
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await bot.send_message(
                        chat_id=u['telegram_id'],
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                sent_count += 1
                await asyncio.sleep(0.05)   # Telegram rate limit
            except Exception as send_err:
                fail_count += 1
                logger.error(f"Failed to send breakfast reminder to {u['telegram_id']}: {send_err}")

    logger.info(f"Breakfast reminder complete. Sent: {sent_count}, Failed: {fail_count}.")


async def send_production_report_to_admins(bot: Bot):
    """Bugungi yetkazish hisobotini adminlarga yuboradi."""
    today = datetime.date.today()
    logger.info(f"Triggering automated morning report for date: {today}")

    production = await models.get_production_report(today)
    date_str = today.strftime("%d.%m.%Y")

    text = (
        f"🏭 **AVTOMATIK KUNLIK HISOBOT ({date_str}):**\n\n"
        f"Bugun yetkazilishi kerak bo'lgan jami mahsulotlar:\n\n"
    )

    if not production:
        text += "⚠️ Bugun yetkazilishi kerak bo'lgan tasdiqlangan buyurtmalar mavjud emas."
    else:
        for p in production:
            qty_unit = "dona" if p['product_name'] == "Malako" else "kg"
            qty = p['total_quantity']
            formatted_qty = f"{qty:g}"
            text += f"🥛 **{p['product_name']}:** {formatted_qty} {qty_unit}\n"
        text += "\nKuningiz xayrli va barakali o'tsin!"

    # .env dagi adminlarga yuborish
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
            logger.info(f"Morning report sent to admin {admin_id}")
        except Exception as e:
            logger.error(f"Failed to send morning report to admin {admin_id}: {e}")

    # DB dagi adminlarga yuborish
    try:
        db_users = await models.get_all_users()
        for u in db_users:
            if u.get("is_admin", False) and u['telegram_id'] not in ADMIN_IDS:
                try:
                    await bot.send_message(chat_id=u['telegram_id'], text=text, parse_mode="Markdown")
                except Exception as db_err:
                    logger.error(f"Failed to send report to DB admin {u['telegram_id']}: {db_err}")
    except Exception as db_fetch_err:
        logger.error(f"Failed to fetch DB admin users for report: {db_fetch_err}")

async def send_scheduled_notification(bot: Bot, notif: dict):
    """Mijozlarga rejalashtirilgan eslatmani (rasm/video bilan) yuboradi."""
    logger.info(f"Triggering scheduled notification: {notif['title']} (ID: {notif['id']})")
    
    text = notif['text']
    media_url = notif.get('media_url', '')
    media_type = notif.get('media_type', '')
    
    base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    miniapp_url = f"{base_url}/miniapp"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📲 Buyurtma berish",
            web_app=WebAppInfo(url=miniapp_url)
        )
    ]])
    
    try:
        users = await models.get_all_users()
    except Exception as e:
        logger.error(f"Failed to fetch users for scheduled notification {notif['id']}: {e}")
        return
        
    sent_count = 0
    fail_count = 0
    
    for u in users:
        if not u.get("is_admin", False):
            try:
                if media_url and media_type == 'photo':
                    await bot.send_photo(
                        chat_id=u['telegram_id'],
                        photo=URLInputFile(media_url),
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                elif media_url and media_type == 'video':
                    await bot.send_video(
                        chat_id=u['telegram_id'],
                        video=URLInputFile(media_url),
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await bot.send_message(
                        chat_id=u['telegram_id'],
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                sent_count += 1
                await asyncio.sleep(0.05)   # Telegram rate limit
            except Exception as send_err:
                fail_count += 1
                logger.error(f"Failed to send scheduled notification {notif['id']} to {u['telegram_id']}: {send_err}")
                
    logger.info(f"Scheduled notification {notif['id']} complete. Sent: {sent_count}, Failed: {fail_count}.")

async def scheduler_loop(bot: Bot):
    """Har kuni belgilangan vaqtda (bazadan o'qib) hisobot va eslatma yuboradi."""
    logger.info("Automated scheduler background task started.")
 
    last_run_date = None
    last_customer_run_date = None
 
    while True:
        try:
            now = datetime.datetime.now()
            today = now.date()
 
            # Bazadan joriy vaqtlarni o'qish (har safar — admin o'zgartirgan bo'lishi mumkin)
            try:
                report_hour   = int(await models.get_setting('report_hour',   '6'))
                report_minute = int(await models.get_setting('report_minute', '0'))
                reminder_hour   = int(await models.get_setting('reminder_hour',   '6'))
                reminder_minute = int(await models.get_setting('reminder_minute', '0'))
            except Exception as set_err:
                logger.error(f"Settings o'qishda xato, defaultga o'tildi: {set_err}")
                report_hour, report_minute     = 6, 0
                reminder_hour, reminder_minute = 6, 0
 
            # Admin hisoboti
            if now.hour == report_hour and now.minute == report_minute:
                if last_run_date != today:
                    await send_production_report_to_admins(bot)
                    last_run_date = today
 
            # Mijoz eslatmasi
            if now.hour == reminder_hour and now.minute == reminder_minute:
                if last_customer_run_date != today:
                    await send_breakfast_reminder_to_customers(bot)
                    last_customer_run_date = today
 
            # Dinamik scheduled notifications
            try:
                active_notifs = await models.get_all_scheduled_notifications()
                for notif in active_notifs:
                    if notif['is_active'] and now.hour == notif['send_hour'] and now.minute == notif['send_minute']:
                        if notif['last_sent_date'] != today:
                            await send_scheduled_notification(bot, notif)
                            await models.update_notification_last_sent(notif['id'], today)
            except Exception as dyn_err:
                logger.error(f"Error checking dynamic scheduled notifications: {dyn_err}")
 
            await asyncio.sleep(30)
 
        except asyncio.CancelledError:
            logger.info("Scheduler task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}")
            await asyncio.sleep(10)
