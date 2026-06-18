import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from database.connection import init_db_pool, close_db_pool
from database.models import create_tables
from handlers import registration, menu, order, admin
from utils.logger import logger
from utils.scheduler import scheduler_loop

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    logger.critical("BOT_TOKEN is missing or is set to placeholder in .env file! Please edit C:\\Users\\O'zimniki\\.gemini\\antigravity\\scratch\\dairy_delivery_bot\\.env and set a valid Telegram Bot Token.")
    print("\n[CRITICAL ERROR] Telegram Bot Tokeni topilmadi yoki .env faylda xato kiritilgan!")
    print("Iltimos, loyiha papkasidagi '.env' faylini ochib, BOT_TOKEN maydoniga o'z botingiz tokenini yozing.")
    print("Fayl yo'li: C:\\Users\\O'zimniki\\.gemini\\antigravity\\scratch\\dairy_delivery_bot\\.env\n")
    import sys
    sys.exit(1)

# Initialize Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Background task reference for scheduler
scheduler_task = None

async def on_startup(bot: Bot):
    """Actions to run on bot startup."""
    logger.info("Starting up Telegram Bot...")
    
    # 1. Initialize DB Connection Pool
    try:
        await init_db_pool()
        
        # 2. Check and Create Tables
        await create_tables()
    except Exception as e:
        logger.critical(f"Startup DB initialization failed: {e}")
        raise e
        
    # 3. Start automated report scheduler in background
    global scheduler_task
    scheduler_task = asyncio.create_task(scheduler_loop(bot))
    logger.info("Bot startup sequence completed successfully.")

async def on_shutdown(bot: Bot):
    """Actions to run on bot shutdown."""
    logger.info("Shutting down Telegram Bot...")
    
    # 1. Cancel background scheduler task
    global scheduler_task
    if scheduler_task:
        logger.info("Cancelling automated scheduler task...")
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info("Scheduler task cancelled successfully.")
            
    # 2. Close PostgreSQL connection pool
    await close_db_pool()
    logger.info("Bot shutdown sequence completed.")

def register_routers(dp: Dispatcher):
    """Registers all handler routers to the Dispatcher."""
    # Note: Order is important! 
    # Admin handlers should take priority on commands, or Registration handler should filter unregistered users
    dp.include_router(registration.router)
    dp.include_router(admin.router)
    dp.include_router(menu.router)
    dp.include_router(order.router)
    logger.info("All routers registered.")

async def main():
    # Register startup and shutdown lifecycle hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Register handlers
    register_routers(dp)
    
    # Start bot polling (skip accumulated updates on restart)
    logger.info("Starting bot polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Bot execution error: {e}")
    finally:
        # Guarantee bot session is closed cleanly
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
