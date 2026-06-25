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

dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    logger.critical("BOT_TOKEN topilmadi!")
    import sys
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler_task = None

# ============================================================
# AUTH
# ============================================================
import hashlib

def get_auth_token():
    pwd = os.getenv("DASHBOARD_PASSWORD", "KiRishgA UrinmA")
    return hashlib.sha256(pwd.encode()).hexdigest()

def is_authorized(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return auth.split(" ")[1] == get_auth_token()

# ============================================================
# LIFECYCLE
# ============================================================

async def on_startup(bot: Bot):
    logger.info("Bot ishga tushmoqda...")
    try:
        await init_db_pool()
        await create_tables()
    except Exception as e:
        logger.critical(f"DB xatosi: {e}")
        raise e
    global scheduler_task
    scheduler_task = asyncio.create_task(scheduler_loop(bot))
    logger.info("Bot muvaffaqiyatli ishga tushdi.")

async def on_shutdown(bot: Bot):
    logger.info("Bot to'xtatilmoqda...")
    global scheduler_task
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    await close_db_pool()
    logger.info("Bot to'xtatildi.")

def register_routers(dp: Dispatcher):
    dp.include_router(registration.router)
    dp.include_router(admin.router)
    dp.include_router(menu.router)
    dp.include_router(order.router)

# ============================================================
# API HANDLERS
# ============================================================

async def handle_health(request):
    return web.Response(text="OK")

async def api_login(request):
    try:
        data = await request.json()
        pwd = data.get("password")
        if pwd == os.getenv("DASHBOARD_PASSWORD", "KiRishgA UrinmA"):
            logger.info("Panel kirish: muvaffaqiyatli")
            return web.json_response({"token": get_auth_token()})
        logger.warning("Panel kirish: noto'g'ri parol")
        return web.json_response({"error": "Parol noto'g'ri!"}, status=401)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

# --- STATS ---

async def api_get_stats(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        stats = await models.get_dashboard_stats()
        return web.json_response(stats)
    except Exception as e:
        logger.error(f"api_get_stats: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- ORDERS ---

async def api_get_orders(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        orders = await models.get_dashboard_orders()
        return web.json_response(orders)
    except Exception as e:
        logger.error(f"api_get_orders: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_order_status(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        order_id = int(request.match_info['id'])
        data = await request.json()
        new_status = data.get("status")

        from database import models
        db_order = await models.fetch_row(
            "SELECT o.id, u.telegram_id FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = $1;",
            order_id
        )
        if not db_order:
            return web.json_response({"error": "Buyurtma topilmadi!"}, status=404)

        await models.update_order_status(order_id, new_status)

        # Foydalanuvchini xabardor qil
        notify_map = {
            "confirmed": f"✅ #{order_id}-buyurtmangiz tasdiqlandi!\n⏰ Yetkazish: 06:30–07:30",
            "completed": f"🚚 #{order_id}-buyurtmangiz yetkazildi!\nYoqimli ishtaha!",
            "cancelled": f"❌ #{order_id}-buyurtmangiz bekor qilindi."
        }
        msg = notify_map.get(new_status)
        if msg:
            try:
                await bot.send_message(chat_id=db_order['telegram_id'], text=msg)
            except Exception as err:
                logger.warning(f"Xabar yuborishda xato {db_order['telegram_id']}: {err}")

        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_update_order_status: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_order_arrived(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        order_id = int(request.match_info['id'])
        from database import models
        db_order = await models.fetch_row(
            "SELECT o.id, u.telegram_id FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = $1;",
            order_id
        )
        if not db_order:
            return web.json_response({"error": "Buyurtma topilmadi!"}, status=404)
        await bot.send_message(
            chat_id=db_order['telegram_id'],
            text=f"🔔 *Kuryer yetib keldi!*\n\n#{order_id}-buyurtmangiz eshik oldida. Iltimos uchrashing.",
            parse_mode="Markdown"
        )
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_order_arrived: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- PRODUCTS ---

async def api_get_products(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        products = await models.get_all_products()
        for p in products:
            p['price'] = float(p['price'])
            if p.get('created_at'):
                p['created_at'] = p['created_at'].strftime("%Y-%m-%d %H:%M")
        return web.json_response(products)
    except Exception as e:
        logger.error(f"api_get_products: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_add_product(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from decimal import Decimal
        from database import models
        data = await request.json()
        name = data.get("name", "").strip()
        price = data.get("price")
        if not name or price is None:
            return web.json_response({"error": "Nom va narx kiritilishi shart!"}, status=400)
        product = await models.add_product(name, Decimal(str(price)))
        product['price'] = float(product['price'])
        if product.get('created_at'):
            product['created_at'] = product['created_at'].strftime("%Y-%m-%d %H:%M")
        logger.info(f"Yangi mahsulot qo'shildi: {name}")
        return web.json_response({"success": True, "product": product})
    except Exception as e:
        logger.error(f"api_add_product: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_product(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from decimal import Decimal
        from database.connection import execute_query
        from database import models
        product_id = int(request.match_info['id'])
        data = await request.json()
        name = data.get("name", "").strip()
        price = data.get("price")
        if not name or price is None:
            return web.json_response({"error": "Nom va narx kiritilishi shart!"}, status=400)
        await execute_query("UPDATE products SET name = $1 WHERE id = $2;", name, product_id)
        await models.update_product_price(product_id, Decimal(str(price)))
        logger.info(f"Mahsulot #{product_id} yangilandi: {name}, {price}")
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_update_product: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_toggle_product(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        product_id = int(request.match_info['id'])
        data = await request.json()
        is_active = bool(data.get("is_active", True))
        await models.set_product_active_status(product_id, is_active)
        logger.info(f"Mahsulot #{product_id} holati: {'faol' if is_active else 'nofaol'}")
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_toggle_product: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- CUSTOMERS ---

async def api_get_customers(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        users = await models.get_all_users()
        for u in users:
            if u.get('created_at'):
                u['created_at'] = u['created_at'].strftime("%Y-%m-%d %H:%M")
        return web.json_response(users)
    except Exception as e:
        logger.error(f"api_get_customers: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- BROADCAST ---

async def api_broadcast(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        data = await request.json()
        text = data.get("text", "").strip()
        if not text:
            return web.json_response({"error": "Xabar matni bo'sh!"}, status=400)

        users = await models.get_all_users()
        sent, failed = 0, 0
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user['telegram_id'],
                    text=text,
                    parse_mode="Markdown"
                )
                sent += 1
                await asyncio.sleep(0.05)  # Telegram rate limit
            except Exception as err:
                logger.warning(f"Broadcast xato {user['telegram_id']}: {err}")
                failed += 1

        logger.info(f"Broadcast: {sent} yuborildi, {failed} xato")
        return web.json_response({"success": True, "sent": sent, "failed": failed})
    except Exception as e:
        logger.error(f"api_broadcast: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- MINI APP ---

async def api_miniapp_order(request):
    """Mini App orqali buyurtma qabul qilish. Token tekshirilmaydi — Telegram initData ishlatiladi."""
    try:
        from decimal import Decimal
        from database import models
        data = await request.json()

        telegram_id = data.get("telegram_id")
        items = data.get("items", [])
        total_price = data.get("total_price", 0)
        delivery_date_str = data.get("delivery_date")
        delivery_time_start = data.get("delivery_time_start", "06:00")
        delivery_time_end = data.get("delivery_time_end", "07:00")
        new_lat = data.get("latitude")
        new_lon = data.get("longitude")

        if not telegram_id or not items:
            return web.json_response({"error": "Ma'lumotlar to'liq emas!"}, status=400)

        # Foydalanuvchi tekshiruvi
        user = await models.get_user_by_telegram_id(int(telegram_id))
        if not user:
            return web.json_response({"error": "Foydalanuvchi topilmadi! Avval botdan ro'yxatdan o'ting."}, status=404)

        # Agar yangi lokatsiya yuborilgan bo'lsa — yangilash
        if new_lat and new_lon:
            from database.connection import execute_query
            await execute_query(
                "UPDATE users SET latitude = $1, longitude = $2 WHERE telegram_id = $3;",
                float(new_lat), float(new_lon), int(telegram_id)
            )

        import datetime
        delivery_date = datetime.date.fromisoformat(delivery_date_str) if delivery_date_str else datetime.date.today()

        cart_items = [
            {
                'product_id': i['product_id'],
                'quantity': float(i['quantity']),
                'price': Decimal(str(i['price']))
            }
            for i in items
        ]

        order_id = await models.create_order(
            telegram_id=int(telegram_id),
            cart_items=cart_items,
            total_price=Decimal(str(total_price)),
            delivery_date=delivery_date,
            delivery_time_start=delivery_time_start,
            delivery_time_end=delivery_time_end
        )

        logger.info(f"MiniApp: Yangi buyurtma #{order_id} — tg:{telegram_id}")

        # Foydalanuvchiga tasdiqlash xabari
        time_label = {
            '06:00': '🌅 Ertalab 06:00–07:00',
            '12:00': '☀️ Kunduz 12:00–13:00',
            '18:00': '🌆 Kechqurun 18:00–19:00'
        }.get(delivery_time_start, f'{delivery_time_start}–{delivery_time_end}')

        items_text = '\n'.join([f"• {i['quantity']} dona — {i['product_id']}" for i in items])
        try:
            await bot.send_message(
                chat_id=int(telegram_id),
                text=(
                    f"✅ *Buyurtma #{order_id} qabul qilindi!*\n\n"
                    f"📅 Yetkazish: *{delivery_date.strftime('%d.%m.%Y')}*\n"
                    f"⏰ Vaqt: *{time_label}*\n"
                    f"💰 Jami: *{int(total_price):,} so'm*\n\n"
                    f"Buyurtmangiz tasdiqlangach xabar beramiz! 🚚"
                ),
                parse_mode="Markdown"
            )
        except Exception as notify_err:
            logger.warning(f"MiniApp: Xabar yuborishda xato {telegram_id}: {notify_err}")

        return web.json_response({"success": True, "order_id": order_id})

    except Exception as e:
        logger.error(f"api_miniapp_order: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_miniapp_get_orders(request):
    """Mini App uchun foydalanuvchining buyurtmalari."""
    try:
        from database import models
        telegram_id = int(request.match_info['telegram_id'])
        orders = await models.get_user_orders(telegram_id, limit=10)

        result = []
        for o in orders:
            order_dict = dict(o)
            if hasattr(order_dict.get('delivery_date'), 'strftime'):
                order_dict['delivery_date'] = order_dict['delivery_date'].strftime("%d.%m.%Y")
            if hasattr(order_dict.get('created_at'), 'strftime'):
                order_dict['created_at'] = order_dict['created_at'].strftime("%d.%m.%Y %H:%M")
            if order_dict.get('total_price'):
                order_dict['total_price'] = float(order_dict['total_price'])
            result.append(order_dict)

        return web.json_response(result)
    except Exception as e:
        logger.error(f"api_miniapp_get_orders: {e}")
        return web.json_response({"error": str(e)}, status=500)


# ============================================================
# WEB SERVER
# ============================================================

async def start_web_server():
    app = web.Application()

    # --- API Routes ---
    app.router.add_get('/health', handle_health)
    app.router.add_post('/api/login', api_login)

    # Stats
    app.router.add_get('/api/stats', api_get_stats)

    # Orders
    app.router.add_get('/api/orders', api_get_orders)
    app.router.add_post('/api/orders/{id}/status', api_update_order_status)
    app.router.add_post('/api/orders/{id}/arrived', api_order_arrived)

    # Products
    app.router.add_get('/api/products', api_get_products)
    app.router.add_post('/api/products', api_add_product)
    app.router.add_put('/api/products/{id}', api_update_product)
    app.router.add_post('/api/products/{id}/toggle', api_toggle_product)

    # Customers
    app.router.add_get('/api/customers', api_get_customers)

    # Broadcast
    app.router.add_post('/api/broadcast', api_broadcast)

    # Mini App
    app.router.add_post('/api/miniapp/order', api_miniapp_order)
    app.router.add_get('/api/miniapp/orders/{telegram_id}', api_miniapp_get_orders)

    # --- Static Pages ---
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

    async def index_handler(request):
        return web.FileResponse(os.path.join(static_path, 'index.html'))

    async def miniapp_handler(request):
        return web.FileResponse(os.path.join(static_path, 'miniapp.html'))

    async def sw_handler(request):
        return web.FileResponse(os.path.join(static_path, 'sw.js'))

    async def manifest_handler(request):
        return web.FileResponse(os.path.join(static_path, 'manifest.json'))

    app.router.add_get('/', handle_health)
    app.router.add_get('/chorvador-panel', index_handler)
    app.router.add_get('/chorvador-panel/login', index_handler)
    app.router.add_get('/miniapp', miniapp_handler)
    app.router.add_get('/sw.js', sw_handler)
    app.router.add_get('/manifest.json', manifest_handler)
    app.router.add_static('/static/', static_path, name='static')

    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server {port}-portda ishga tushdi.")

# ============================================================
# MAIN
# ============================================================

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    register_routers(dp)

    try:
        await start_web_server()
    except Exception as e:
        logger.error(f"Web server xatosi: {e}")

    logger.info("Bot polling boshlandi...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Bot xatosi: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
