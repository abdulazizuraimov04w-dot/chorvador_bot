import asyncio
import datetime
import os
from aiogram import Bot
from dotenv import load_dotenv

from database import models
from utils.logger import logger

# Load environment
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)

try:
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
except Exception as e:
    logger.error(f"Error parsing ADMIN_IDS in scheduler: {e}")
    ADMIN_IDS = []

# Config: report trigger hour and minute (e.g. 06:00 AM)
REPORT_HOUR = 6
REPORT_MINUTE = 0

async def send_production_report_to_admins(bot: Bot):
    """Generates the morning report for today's deliveries and sends it to all admins."""
    today = datetime.date.today()
    logger.info(f"Triggering automated morning report for date: {today}")
    
    # Get production requirements for today
    production = await models.get_production_report(today)
    
    date_str = today.strftime("%d.%m.%Y")
    
    text = (
        f"🏭 **AVTOMATIK KUNLIK HISOBOT ({date_str}):**\n\n"
        f"Bugun ertalab (**06:30 - 07:30**) yetkazilishi kerak bo'lgan jami mahsulotlar:\n\n"
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
        
    # Send to admin IDs configured in .env
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
            logger.info(f"Morning report successfully sent to admin {admin_id}")
        except Exception as e:
            logger.error(f"Failed to send morning report to admin {admin_id}: {e}")
            
    # Also search DB for other admin users and send to them
    try:
        db_users = await models.get_all_users()
        for u in db_users:
            if u.get("is_admin", False) and u['telegram_id'] not in ADMIN_IDS:
                try:
                    await bot.send_message(chat_id=u['telegram_id'], text=text, parse_mode="Markdown")
                    logger.info(f"Morning report sent to DB admin {u['telegram_id']}")
                except Exception as db_err:
                    logger.error(f"Failed to send morning report to DB admin {u['telegram_id']}: {db_err}")
    except Exception as db_fetch_err:
        logger.error(f"Failed to fetch DB admin users for report: {db_fetch_err}")

async def scheduler_loop(bot: Bot):
    """Background task running continuously to trigger daily reports."""
    logger.info("Automated scheduler background task started.")
    
    last_run_date = None
    
    while True:
        try:
            now = datetime.datetime.now()
            today = now.date()
            
            # Check if it's report time and report wasn't run today yet
            if now.hour == REPORT_HOUR and now.minute == REPORT_MINUTE:
                if last_run_date != today:
                    await send_production_report_to_admins(bot)
                    last_run_date = today
                    
            # Check every 30 seconds
            await asyncio.sleep(30)
            
        except asyncio.CancelledError:
            logger.info("Scheduler task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}")
            await asyncio.sleep(10) # wait before retrying on crash
