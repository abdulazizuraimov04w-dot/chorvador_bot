import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiohttp import web

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

import hashlib

def get_auth_token():
    pwd = os.getenv("DASHBOARD_PASSWORD", "KiRishgA UrinmA")
    return hashlib.sha256(pwd.encode()).hexdigest()

def is_authorized(request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False
    token = auth_header.split(" ")[1]
    return token == get_auth_token()

async def handle_health(request):
    """Simple health check endpoint for Render."""
    return web.Response(text="Bot is running!")

async def api_login(request):
    try:
        data = await request.json()
        password = data.get("password")
        expected_pwd = os.getenv("DASHBOARD_PASSWORD", "KiRishgA UrinmA")
        if password == expected_pwd:
            logger.info("Web Dashboard login successful.")
            return web.json_response({"token": get_auth_token()})
        else:
            logger.warning("Web Dashboard login failed: incorrect password.")
            return web.json_response({"error": "Parol noto'g'ri!"}, status=401)
    except Exception as e:
        logger.error(f"Error in api_login: {e}")
        return web.json_response({"error": "Xato so'rov"}, status=400)

async def api_get_stats(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat berilmagan!"}, status=401)
    
    try:
        from database import models
        stats = await models.get_dashboard_stats()
        return web.json_response(stats)
    except Exception as e:
        logger.error(f"Error in api_get_stats: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_get_orders(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat berilmagan!"}, status=401)
        
    try:
        from database import models
        orders = await models.get_dashboard_orders()
        return web.json_response(orders)
    except Exception as e:
        logger.error(f"Error in api_get_orders: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_order_status(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat berilmagan!"}, status=401)
        
    try:
        order_id = int(request.match_info['id'])
        data = await request.json()
        new_status = data.get("status")
        
        from database import models
        # Fetch user telegram_id first to notify
        db_order = await models.fetch_row(
            "SELECT o.id, u.telegram_id FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = $1;",
            order_id
        )
        if not db_order:
            return web.json_response({"error": "Buyurtma topilmadi!"}, status=404)
            
        await models.update_order_status(order_id, new_status)
        logger.info(f"API: Order #{order_id} status updated to {new_status}")
        
        # Notify user
        user_tg_id = db_order['telegram_id']
        status_text_uz = {
            "confirmed": "Tasdiqlandi ✅",
            "completed": "Yetkazildi 🚚",
            "cancelled": "Bekor qilindi ❌"
        }.get(new_status)
        
        notification_text = ""
        if new_status == "confirmed":
            notification_text = (
                f"✅ Sizning #{order_id}-sonli buyurtmangiz tasdiqlandi!\n\n"
                f"⏰ Yetkazib berish vaqti: 06:30 - 07:30\n"
                f"Sog'lom va barra mahsulotlar tez orada sizga yetkaziladi."
            )
        elif new_status == "completed":
            notification_text = (
                f"🚚 Sizning #{order_id}-sonli buyurtmangiz muvaffaqiyatli yetkazildi!\n\n"
                f"Yoqimli ishtaha!"
            )
        elif new_status == "cancelled":
            notification_text = f"❌ Sizning #{order_id}-sonli buyurtmangiz bekor qilindi."
            
        if notification_text:
            try:
                await bot.send_message(chat_id=user_tg_id, text=notification_text)
                logger.info(f"API: Notification sent to user {user_tg_id} about Order #{order_id}")
            except Exception as notify_err:
                logger.warning(f"API: Could not notify user {user_tg_id}: {notify_err}")
                
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"Error in api_update_order_status: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_order_arrived(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat berilmagan!"}, status=401)
        
    try:
        order_id = int(request.match_info['id'])
        from database import models
        db_order = await models.fetch_row(
            "SELECT o.id, u.telegram_id FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = $1;",
            order_id
        )
        if not db_order:
            return web.json_response({"error": "Buyurtma topilmadi!"}, status=404)
            
        user_tg_id = db_order['telegram_id']
        notification_text = (
            f"🔔 **Kuryerimiz yetib keldi!**\n\n"
            f"Sizning #{order_id}-sonli buyurtmangiz yetkazish nuqtasida. Iltimos, kuryer bilan uchrashing."
        )
        
        try:
            await bot.send_message(chat_id=user_tg_id, text=notification_text, parse_mode="Markdown")
            logger.info(f"API: Courier arrived notification sent to user {user_tg_id} for Order #{order_id}")
            return web.json_response({"success": True})
        except Exception as notify_err:
            logger.error(f"API: Failed to notify user {user_tg_id} about courier arrival: {notify_err}")
            return web.json_response({"error": "Telegram orqali foydalanuvchiga xabar yuborishda xatolik yuz berdi"}, status=500)
            
    except Exception as e:
        logger.error(f"Error in api_order_arrived: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def start_web_server():
    """Starts a web server to satisfy Render's health checks and host the admin dashboard."""
    app = web.Application()
    
    # API Routes
    app.router.add_get('/health', handle_health)
    app.router.add_post('/api/login', api_login)
    app.router.add_get('/api/stats', api_get_stats)
    app.router.add_get('/api/orders', api_get_orders)
    app.router.add_post('/api/orders/{id}/status', api_update_order_status)
    app.router.add_post('/api/orders/{id}/arrived', api_order_arrived)
    
    # Static pages & files
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    
    # Custom routes for PWA service worker and manifest to run in root scope
    async def sw_handler(request):
        return web.FileResponse(os.path.join(static_path, 'sw.js'))
        
    async def manifest_handler(request):
        return web.FileResponse(os.path.join(static_path, 'manifest.json'))
        
    async def index_handler(request):
        return web.FileResponse(os.path.join(static_path, 'index.html'))
        
    async def login_handler(request):
        return web.FileResponse(os.path.join(static_path, 'login.html'))
        
    app.router.add_get('/', handle_health) # Root serves health check (security by obscurity)
    app.router.add_get('/chorvador-panel', index_handler)
    app.router.add_get('/chorvador-panel/login', login_handler)
    app.router.add_get('/sw.js', sw_handler)
    app.router.add_get('/manifest.json', manifest_handler)
    
    # Route for other static files (CSS, JS, Icons)
    app.router.add_static('/static/', static_path, name='static')
    
    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server started on port {port} for Render health checks and Web Panel.")

async def main():
    # Register startup and shutdown lifecycle hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Register handlers
    register_routers(dp)
    
    # Start web server for Render health checks
    try:
        await start_web_server()
    except Exception as e:
        logger.error(f"Failed to start web server: {e}")
    
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
