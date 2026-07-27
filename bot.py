import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiohttp import web

from database.connection import init_db_pool, close_db_pool
from database.models import create_tables
from database import models
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

DASHBOARD_PASSWORD = "ozimniki2604"

def get_auth_token():
    return hashlib.sha256(DASHBOARD_PASSWORD.encode()).hexdigest()

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
        if pwd == DASHBOARD_PASSWORD:
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
        import datetime
        from database import models
        date_str = request.rel_url.query.get('date', None)
        date_filter = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
        orders = await models.get_dashboard_orders(date_filter=date_filter)
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
            "confirmed": f"✅ #{order_id}-buyurtmangiz tasdiqlandi!",
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





# --- CATEGORY API ENDPOINTS ---

async def api_get_categories(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        categories = await models.get_all_categories()
        for c in categories:
            if c.get('created_at'):
                c['created_at'] = c['created_at'].strftime("%Y-%m-%d %H:%M:%S")
        return web.json_response(categories)
    except Exception as e:
        logger.error(f"api_get_categories: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_create_category(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        icon = data.get("icon", "🛍️").strip()
        sort_order = int(data.get("sort_order", 0))
        if not name:
            return web.json_response({"error": "Kategoriya nomi kiritilishi shart!"}, status=400)
        cat_id = await models.create_category(name, icon, sort_order)
        return web.json_response({"success": True, "id": cat_id})
    except Exception as e:
        logger.error(f"api_create_category: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_category(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        cat_id = int(request.match_info['id'])
        data = await request.json()
        name = data.get("name", "").strip()
        icon = data.get("icon", "🛍️").strip()
        sort_order = int(data.get("sort_order", 0))
        if not name:
            return web.json_response({"error": "Kategoriya nomi kiritilishi shart!"}, status=400)
        await models.update_category(cat_id, name, icon, sort_order)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_update_category: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_delete_category(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        cat_id = int(request.match_info['id'])
        await models.delete_category(cat_id)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_delete_category: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- PRODUCT API ENDPOINTS ---

async def api_add_product(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from decimal import Decimal
        data = await request.json()
        name = data.get("name", "").strip()
        price = data.get("price")
        image_url = data.get("image_url")
        category_id = data.get("category_id")
        if not name or price is None:
            return web.json_response({"error": "Nom va narx kiritilishi shart!"}, status=400)
        cat_id = int(category_id) if category_id else None
        product = await models.add_product(name, Decimal(str(price)), image_url, cat_id)
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
        product_id = int(request.match_info['id'])
        data = await request.json()
        name = data.get("name", "").strip()
        price = data.get("price")
        image_url = data.get("image_url")
        category_id = data.get("category_id")
        if not name or price is None:
            return web.json_response({"error": "Nom va narx kiritilishi shart!"}, status=400)
        cat_id = int(category_id) if category_id else None
        await models.update_product(product_id, name, Decimal(str(price)), image_url, cat_id)
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
    """Barcha mijozlar analitik ma'lumotlar bilan (segment, buyurtmalar, summa va boshqalar)."""
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        customers = await models.get_customers_analytics()
        return web.json_response(customers)
    except Exception as e:
        logger.error(f"api_get_customers: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_get_customer_detail(request):
    """Alohida mijoz profili + buyurtmalar tarixi."""
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        user_id = int(request.match_info['id'])
        detail = await models.get_customer_detail(user_id)
        if not detail:
            return web.json_response({"error": "Mijoz topilmadi!"}, status=404)
        return web.json_response(detail)
    except Exception as e:
        logger.error(f"api_get_customer_detail: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_get_user_loyalty(request):
    """Mijozning loyalty progressini va minimal summani qaytarish (Public endpoint for Mini App)."""
    try:
        from database import models
        tg_id = request.query.get('telegram_id')
        user_id = int(tg_id) if (tg_id and tg_id.isdigit()) else 0
        loyalty = await models.get_user_loyalty_info(user_id)
        return web.json_response(loyalty)
    except Exception as e:
        logger.error(f"api_get_user_loyalty: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_get_loyalty_settings(request):
    """Admin panel uchun loyalty va min_amount sozlamalari."""
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        min_amount = await models.get_min_order_amount()
        target = await models.get_loyalty_target()
        return web.json_response({
            "min_order_amount": min_amount,
            "loyalty_target": target
        })
    except Exception as e:
        logger.error(f"api_get_loyalty_settings: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_loyalty_settings(request):
    """Admin paneldan minimal summa va loyalty marrasini yangilash."""
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        data = await request.json()
        min_amount = float(data.get("min_order_amount", 70000))
        target     = int(data.get("loyalty_target", 10))
        await models.execute_query(
            "INSERT INTO settings (key, value) VALUES ('min_order_amount', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
            str(int(min_amount))
        )
        await models.execute_query(
            "INSERT INTO settings (key, value) VALUES ('loyalty_target', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
            str(target)
        )
        logger.info(f"Loyalty settings updated: min={min_amount}, target={target}")
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_update_loyalty_settings: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- FILE UPLOAD (rasm/video - Permanent Cloud Storage) ---

async def upload_image_to_cloud(file_bytes: bytes, filename: str) -> str:
    """Rasmlarni doimiy saqlash uchun bulutli Cloud CDN xostingiga yuklaydi (Git push bo'lganda ham o'chib ketmasligi uchun)"""
    import base64
    import aiohttp
    
    # 1-Urinish: FreeImage.host API
    try:
        encoded = base64.b64encode(file_bytes).decode('utf-8')
        payload = {'key': '6d207e02198a847aa98d0a2a901485a5', 'action': 'upload', 'source': encoded}
        async with aiohttp.ClientSession() as session:
            async with session.post('https://freeimage.host/api/1/upload', data=payload, timeout=12) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    cdn_url = res_json.get('image', {}).get('url')
                    if cdn_url:
                        logger.info(f"Rasm FreeImage.host CDN ga muvaffaqiyatli yuklandi: {cdn_url}")
                        return cdn_url
    except Exception as err1:
        logger.warning(f"FreeImage upload warning: {err1}")

    # 2-Urinish: Catbox.moe API (Zaxira)
    try:
        data = aiohttp.FormData()
        data.add_field('reqtype', 'fileupload')
        data.add_field('fileToUpload', file_bytes, filename=filename or 'product.jpg', content_type='image/jpeg')
        async with aiohttp.ClientSession() as session:
            async with session.post('https://catbox.moe/user/api.php', data=data, timeout=12) as resp:
                if resp.status == 200:
                    cdn_url = (await resp.text()).strip()
                    if cdn_url.startswith("http"):
                        logger.info(f"Rasm Catbox.moe CDN ga muvaffaqiyatli yuklandi: {cdn_url}")
                        return cdn_url
    except Exception as err2:
        logger.warning(f"Catbox upload warning: {err2}")

    return None

async def api_upload_file(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        import uuid
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != 'file':
            return web.json_response({"error": "Fayl topilmadi!"}, status=400)

        filename = field.filename or 'file'
        ext = os.path.splitext(filename)[1].lower()
        allowed_ext = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.avi']
        if ext not in allowed_ext:
            return web.json_response({"error": "Fayl turi qo'llab-quvvatlanmaydi!"}, status=400)

        file_bytes = bytearray()
        size = 0
        max_size = 20 * 1024 * 1024  # 20 MB
        
        while True:
            chunk = await field.read_chunk(1024 * 64)
            if not chunk:
                break
            size += len(chunk)
            if size > max_size:
                return web.json_response({"error": "Fayl hajmi 20MB dan oshmasligi kerak!"}, status=400)
            file_bytes.extend(chunk)

        file_url = None
        media_type = 'video' if ext in ['.mp4', '.mov', '.avi'] else 'photo'

        # Agar rasm bo'lsa, avval Bulutli Cloud storage ga yuklaymiz (Git push-da yo'qolmasligi uchun)
        if media_type == 'photo':
            cloud_url = await upload_image_to_cloud(bytes(file_bytes), filename)
            if cloud_url:
                file_url = cloud_url

        # Agar bulutga yuklanmay qolsa yoki video bo'lsa, mahalliy xotiraga saqlaymiz (zaxira)
        if not file_url:
            uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
            os.makedirs(uploads_dir, exist_ok=True)
            unique_name = f"{uuid.uuid4().hex}{ext}"
            filepath = os.path.join(uploads_dir, unique_name)
            with open(filepath, 'wb') as f:
                f.write(file_bytes)
            base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
            file_url = f"{base_url}/static/uploads/{unique_name}"

        logger.info(f"File uploaded successfully: {file_url} ({size} bytes)")
        return web.json_response({"success": True, "url": file_url, "media_type": media_type})
    except Exception as e:
        logger.error(f"api_upload_file: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- SETTINGS (scheduler vaqti va xabar matni) ---

async def api_get_settings(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        settings = await models.get_all_settings()
        return web.json_response(settings)
    except Exception as e:
        logger.error(f"api_get_settings: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_save_settings(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        data = await request.json()
        allowed_keys = ['reminder_hour', 'reminder_minute', 'reminder_text', 'reminder_photo', 'report_hour', 'report_minute']
        for key in allowed_keys:
            if key in data:
                await models.set_setting(key, str(data[key]))
        logger.info(f"Settings updated: {list(data.keys())}")
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_save_settings: {e}")
        return web.json_response({"error": str(e)}, status=500)

# --- BROADCAST ---

async def api_broadcast(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        from aiogram.types import URLInputFile
        data = await request.json()
        text = data.get("text", "").strip()
        media_url = data.get("media_url", "").strip()
        media_type = data.get("media_type", "")  # 'photo' yoki 'video'
        mfy_id = data.get("mfy_id")

        target_mfy_id = None
        if mfy_id is not None and str(mfy_id).strip() != "":
            try:
                target_mfy_id = int(mfy_id)
            except ValueError:
                target_mfy_id = None

        if not text and not media_url:
            return web.json_response({"error": "Xabar matni yoki media bo'sh!"}, status=400)

        users = await models.get_all_users()
        sent, failed = 0, 0
        for user in users:
            # Filter by MFY if requested
            if target_mfy_id is not None and user.get("mfy_id") != target_mfy_id:
                continue
            try:
                if media_url and media_type == 'photo':
                    await bot.send_photo(
                        chat_id=user['telegram_id'],
                        photo=URLInputFile(media_url),
                        caption=text or None,
                        parse_mode="Markdown"
                    )
                elif media_url and media_type == 'video':
                    await bot.send_video(
                        chat_id=user['telegram_id'],
                        video=URLInputFile(media_url),
                        caption=text or None,
                        parse_mode="Markdown"
                    )
                else:
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

async def api_get_undelivered_orders(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        from database import models
        orders = await models.get_undelivered_orders()
        return web.json_response(orders)
    except Exception as e:
        logger.error(f"api_get_undelivered_orders: {e}")
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
        tz_uz = datetime.timezone(datetime.timedelta(hours=5))
        now_uz = datetime.datetime.now(tz_uz)
        today_uz = now_uz.date()

        delivery_date = datetime.date.fromisoformat(delivery_date_str) if delivery_date_str else today_uz

        min_amount = await models.get_min_order_amount()
        if float(total_price) < min_amount:
            return web.json_response({
                "error": f"Minimal buyurtma summasi — {int(min_amount):,} so'm. Hozirgi savatingiz: {int(total_price):,} so'm.".replace(",", " ")
            }, status=400)

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

        # Get the assigned courier for this order
        courier_tg_id = None
        courier_name = None
        mfy_name = None
        try:
            order_row = await models.fetch_row("""
                SELECT o.id, c.telegram_id as courier_tg_id, c.name as courier_name, m.name as mfy_name
                FROM orders o
                JOIN users u ON o.user_id = u.id
                LEFT JOIN mfy m ON u.mfy_id = m.id
                LEFT JOIN couriers c ON o.courier_id = c.id
                WHERE o.id = $1;
            """, order_id)
            if order_row:
                courier_tg_id = order_row['courier_tg_id']
                courier_name = order_row['courier_name']
                mfy_name = order_row['mfy_name']
        except Exception as err:
            logger.error(f"Failed to fetch courier for order notification: {err}")

        # Adminlarga xabar yuborish
        try:
            admin_ids_env = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
            db_users = await models.get_all_users()
            for u in db_users:
                if u.get("is_admin", False) and u['telegram_id'] not in admin_ids_env:
                    admin_ids_env.append(u['telegram_id'])

            items_text = ""
            for i in items:
                prod = next((p for p in await models.get_all_products() if p['id'] == i['product_id']), None)
                name = prod['name'] if prod else f"Mahsulot #{i['product_id']}"
                items_text += f"  - {name}: {i['quantity']} dona\n"

            courier_info = f"**Kuryer:** {courier_name}\n" if courier_name else ""
            mfy_info = f"**Mahalla (MFY):** {mfy_name} MFY\n" if mfy_name else ""

            admin_text = (
                f"🔔 *YANGI BUYURTMA (Mini App)*\n\n"
                f"*Buyurtma:* #{order_id}\n"
                f"*Mijoz:* {user['full_name']}\n"
                f"*Telefon:* {user['phone_number']}\n"
                f"{mfy_info}"
                f"{courier_info}"
                f"*Yetkazish:* {delivery_date} | {delivery_time_start}–{delivery_time_end}\n\n"
                f"*Mahsulotlar:*\n{items_text}"
                f"💵 *Jami:* {int(total_price):,} so'm\n\n"
                f"_Web Panelda ko'rish mumkin!_"
            ).replace(",", " ")

            for admin_id in admin_ids_env:
                try:
                    await bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="Markdown")
                    logger.info(f"MiniApp order notification sent to admin {admin_id}")
                except Exception as ae:
                    logger.warning(f"MiniApp: admin {admin_id} ga xabar yuborib bo'lmadi: {ae}")
        except Exception as admin_err:
            logger.error(f"MiniApp admin notification error: {admin_err}")

        # Send notification to courier
        if courier_tg_id:
            try:
                loc_link = ""
                if user.get("latitude") and user.get("longitude"):
                    loc_link = f"\n📍 [Mijoz joylashuvi (Lokatsiya)](https://maps.google.com/?q={user['latitude']},{user['longitude']})"
                
                courier_text = (
                    f"🚚 **YANGI BUYURTMA (Kuryer uchun)**\n\n"
                    f"**Hudud (MFY):** {mfy_name} MFY\n"
                    f"**Buyurtma:** #{order_id}\n"
                    f"**Mijoz:** {user['full_name']}\n"
                    f"**Telefon:** {user['phone_number']}\n"
                    f"**Yetkazish:** {delivery_date} | {delivery_time_start}–{delivery_time_end}\n\n"
                    f"**Mahsulotlar:**\n{items_text}\n"
                    f"💵 **Jami:** {int(total_price):,} so'm\n"
                    f"{loc_link}"
                ).replace(",", " ")
                
                await bot.send_message(chat_id=courier_tg_id, text=courier_text, parse_mode="Markdown")
                logger.info(f"MiniApp order notification sent to courier {courier_tg_id}")
            except Exception as notify_err:
                logger.error(f"Failed to send order notification to courier {courier_tg_id}: {notify_err}")

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
# LOGISTICS & SCHEDULED NOTIFICATIONS API ENDPOINTS
# ============================================================

async def api_get_couriers(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        couriers = await models.get_all_couriers()
        for c in couriers:
            if c.get('created_at'):
                c['created_at'] = c['created_at'].strftime("%Y-%m-%d %H:%M:%S")
        return web.json_response(couriers)
    except Exception as e:
        logger.error(f"api_get_couriers: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_create_courier(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        phone_number = data.get("phone_number", "").strip()
        telegram_id = data.get("telegram_id")
        
        if not name or not phone_number:
            return web.json_response({"error": "Ism va telefon raqam bo'sh bo'lmasligi kerak!"}, status=400)
            
        tg_id = int(telegram_id) if telegram_id else None
        courier_id = await models.create_courier(name, phone_number, tg_id)
        return web.json_response({"success": True, "id": courier_id})
    except Exception as e:
        logger.error(f"api_create_courier: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_courier(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        courier_id = int(request.match_info['id'])
        data = await request.json()
        name = data.get("name", "").strip()
        phone_number = data.get("phone_number", "").strip()
        telegram_id = data.get("telegram_id")
        is_active = data.get("is_active", True)
        
        if not name or not phone_number:
            return web.json_response({"error": "Ism va telefon raqam bo'sh bo'lmasligi kerak!"}, status=400)
            
        tg_id = int(telegram_id) if telegram_id else None
        await models.update_courier(courier_id, name, phone_number, tg_id, is_active)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_update_courier: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_delete_courier(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        courier_id = int(request.match_info['id'])
        await models.delete_courier(courier_id)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_delete_courier: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_get_mfy(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        mfy = await models.get_all_mfy()
        return web.json_response(mfy)
    except Exception as e:
        logger.error(f"api_get_mfy: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_create_mfy(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        data = await request.json()
        name = data.get("name", "").strip()
        courier_id = data.get("courier_id")
        
        if not name:
            return web.json_response({"error": "Mahalla nomi bo'sh bo'lmasligi kerak!"}, status=400)
            
        c_id = int(courier_id) if courier_id else None
        mfy_id = await models.create_mfy(name, c_id)
        return web.json_response({"success": True, "id": mfy_id})
    except Exception as e:
        logger.error(f"api_create_mfy: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_mfy(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        mfy_id = int(request.match_info['id'])
        data = await request.json()
        name = data.get("name", "").strip()
        courier_id = data.get("courier_id")
        
        if not name:
            return web.json_response({"error": "Mahalla nomi bo'sh bo'lmasligi kerak!"}, status=400)
            
        c_id = int(courier_id) if courier_id else None
        await models.update_mfy(mfy_id, name, c_id)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_update_mfy: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_delete_mfy(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        mfy_id = int(request.match_info['id'])
        await models.delete_mfy(mfy_id)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_delete_mfy: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def api_get_scheduled_notifications(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        notifs = await models.get_all_scheduled_notifications()
        for n in notifs:
            if n.get('last_sent_date'):
                n['last_sent_date'] = n['last_sent_date'].strftime("%Y-%m-%d")
            if n.get('created_at'):
                n['created_at'] = n['created_at'].strftime("%Y-%m-%d %H:%M:%S")
        return web.json_response(notifs)
    except Exception as e:
        logger.error(f"api_get_scheduled_notifications: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_create_scheduled_notification(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        data = await request.json()
        title = data.get("title", "").strip()
        text = data.get("text", "").strip()
        media_url = data.get("media_url", "").strip()
        media_type = data.get("media_type")
        send_hour = int(data.get("send_hour", 6))
        send_minute = int(data.get("send_minute", 0))
        
        if not title or not text:
            return web.json_response({"error": "Sarlavha va matn bo'sh bo'lmasligi kerak!"}, status=400)
            
        notif_id = await models.create_scheduled_notification(
            title, text, media_url or None, media_type or None, send_hour, send_minute
        )
        return web.json_response({"success": True, "id": notif_id})
    except Exception as e:
        logger.error(f"api_create_scheduled_notification: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_update_scheduled_notification(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        notif_id = int(request.match_info['id'])
        data = await request.json()
        title = data.get("title", "").strip()
        text = data.get("text", "").strip()
        media_url = data.get("media_url", "").strip()
        media_type = data.get("media_type")
        send_hour = int(data.get("send_hour", 6))
        send_minute = int(data.get("send_minute", 0))
        is_active = data.get("is_active", True)
        
        if not title or not text:
            return web.json_response({"error": "Sarlavha va matn bo'sh bo'lmasligi kerak!"}, status=400)
            
        await models.update_scheduled_notification(
            notif_id, title, text, media_url or None, media_type or None, send_hour, send_minute, is_active
        )
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_update_scheduled_notification: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_delete_scheduled_notification(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        notif_id = int(request.match_info['id'])
        await models.delete_scheduled_notification(notif_id)
        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_delete_scheduled_notification: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def api_assign_order_courier(request):
    if not is_authorized(request):
        return web.json_response({"error": "Ruxsat yo'q!"}, status=401)
    try:
        order_id = int(request.match_info['id'])
        data = await request.json()
        courier_id = data.get("courier_id")
        
        c_id = int(courier_id) if courier_id else None
        await models.update_order_courier(order_id, c_id)
        
        # Send a notification to the courier if assigned
        if c_id:
            order_row = await models.fetch_row("""
                SELECT o.id, o.total_price, o.delivery_date, o.delivery_time_start, o.delivery_time_end,
                       c.telegram_id as courier_tg_id, c.name as courier_name, m.name as mfy_name,
                       u.full_name as user_name, u.phone_number as user_phone, u.latitude, u.longitude,
                       array_to_json(array_agg(json_build_object(
                           'product_name', p.name,
                           'quantity', oi.quantity
                       ))) as items
                FROM orders o
                JOIN users u ON o.user_id = u.id
                LEFT JOIN mfy m ON u.mfy_id = m.id
                LEFT JOIN couriers c ON o.courier_id = c.id
                LEFT JOIN order_items oi ON o.id = oi.order_id
                LEFT JOIN products p ON oi.product_id = p.id
                WHERE o.id = $1
                GROUP BY o.id, u.id, m.name, c.name, c.telegram_id;
            """, order_id)
            
            if order_row and order_row['courier_tg_id']:
                import json
                items_list = json.loads(order_row['items']) if isinstance(order_row['items'], str) else order_row['items']
                items_text = ""
                for it in items_list:
                    items_text += f"  - {it['product_name']}: {it['quantity']} dona\n"
                    
                loc_link = ""
                if order_row['latitude'] and order_row['longitude']:
                    loc_link = f"\n📍 [Mijoz joylashuvi (Lokatsiya)](https://maps.google.com/?q={order_row['latitude']},{order_row['longitude']})"
                
                courier_text = (
                    f"🚚 **BUYURTMA BIRIKTIRILDI (Kuryer uchun)**\n\n"
                    f"**Hudud (MFY):** {order_row['mfy_name']} MFY\n"
                    f"**Buyurtma:** #{order_id}\n"
                    f"**Mijoz:** {order_row['user_name']}\n"
                    f"**Telefon:** {order_row['user_phone']}\n"
                    f"**Yetkazish:** {order_row['delivery_date']} | {order_row['delivery_time_start']}–{order_row['delivery_time_end']}\n\n"
                    f"**Mahsulotlar:**\n{items_text}\n"
                    f"💵 **Jami:** {int(order_row['total_price']):,} so'm\n"
                    f"{loc_link}"
                ).replace(",", " ")
                
                try:
                    await bot.send_message(chat_id=order_row['courier_tg_id'], text=courier_text, parse_mode="Markdown")
                except Exception as notify_err:
                    logger.error(f"Failed to notify courier on manual assign: {notify_err}")

        return web.json_response({"success": True})
    except Exception as e:
        logger.error(f"api_assign_order_courier: {e}")
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

    # Categories
    app.router.add_get('/api/categories', api_get_categories)
    app.router.add_post('/api/categories', api_create_category)
    app.router.add_put('/api/categories/{id}', api_update_category)
    app.router.add_delete('/api/categories/{id}', api_delete_category)

    # Products
    app.router.add_get('/api/products', api_get_products)
    app.router.add_post('/api/products', api_add_product)
    app.router.add_put('/api/products/{id}', api_update_product)
    app.router.add_post('/api/products/{id}/toggle', api_toggle_product)

    # Customers
    app.router.add_get('/api/customers', api_get_customers)
    app.router.add_get('/api/customers/{id}', api_get_customer_detail)

    # Broadcast
    app.router.add_post('/api/broadcast', api_broadcast)

    # Settings (scheduler vaqti, xabar matni)
    app.router.add_get('/api/settings', api_get_settings)
    app.router.add_post('/api/settings', api_save_settings)

    # File upload (rasm/video)
    app.router.add_post('/api/upload', api_upload_file)

    # Yetkazilmagan buyurtmalar
    app.router.add_get('/api/orders/undelivered', api_get_undelivered_orders)

    # Mini App
    app.router.add_post('/api/miniapp/order', api_miniapp_order)
    app.router.add_get('/api/miniapp/orders/{telegram_id}', api_miniapp_get_orders)

    # Couriers
    app.router.add_get('/api/couriers', api_get_couriers)
    app.router.add_post('/api/couriers', api_create_courier)
    app.router.add_put('/api/couriers/{id}', api_update_courier)
    app.router.add_delete('/api/couriers/{id}', api_delete_courier)

    # MFY
    app.router.add_get('/api/mfy', api_get_mfy)
    app.router.add_post('/api/mfy', api_create_mfy)
    app.router.add_put('/api/mfy/{id}', api_update_mfy)
    app.router.add_delete('/api/mfy/{id}', api_delete_mfy)

    # Scheduled Notifications
    app.router.add_get('/api/scheduled-notifications', api_get_scheduled_notifications)
    app.router.add_post('/api/scheduled-notifications', api_create_scheduled_notification)
    app.router.add_put('/api/scheduled-notifications/{id}', api_update_scheduled_notification)
    app.router.add_delete('/api/scheduled-notifications/{id}', api_delete_scheduled_notification)

    # Assign courier to order
    app.router.add_post('/api/orders/{id}/assign-courier', api_assign_order_courier)

    # Loyalty & Min amount
    app.router.add_get('/api/loyalty', api_get_user_loyalty)
    app.router.add_get('/api/settings/loyalty', api_get_loyalty_settings)
    app.router.add_post('/api/settings/loyalty', api_update_loyalty_settings)

    # --- Static Pages ---
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

    async def index_handler(request):
        return web.FileResponse(os.path.join(static_path, 'index.html'))

    async def miniapp_handler(request):
        base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        token = get_auth_token()
        miniapp_path = os.path.join(static_path, 'miniapp.html')
        with open(miniapp_path, 'r', encoding='utf-8') as f:
            html = f.read()
        html = html.replace('%%BASE_URL%%', base_url)
        html = html.replace('%%API_TOKEN%%', token)
        return web.Response(text=html, content_type='text/html')

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
        from database import models
        await init_db_pool()
        await models.create_tables()
        await start_web_server()
        try:
            await bot.set_my_description(
                "🍊 Mandarin Supermarket botiga xush kelibsiz!\n\n"
                "Bu bot orqali siz sarxil meva-chevalar, ichimliklar, oziq-ovqat va ro'zg'or mahsulotlariga uyingizdan turib qulay buyurtma berishingiz mumkin. Kuryerlarimiz mahsulotlarni tez va sifatli yetkazib beradi.\n"
                "Buyurtma berish uchun botni ishga tushiring!"
            )
            await bot.set_my_short_description(
                "🍊 Mandarin Supermarket - oziq-ovqat va ro'zg'or mahsulotlarini uyingizga yetkazib berish boti"
            )
            logger.info("Bot ta'rifi (description) muvaffaqiyatli yangilandi.")
        except Exception as desc_err:
            logger.warning(f"Bot ta'rifini yangilashda xatolik (token noto'g'ri bo'lishi mumkin): {desc_err}")
    except Exception as e:
        logger.error(f"Web server xatosi: {e}")

    logger.info("Bot polling boshlandi...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Bot xatosi: {e}")
        logger.info("Web serverni ochiq qoldirish uchun kutish rejimiga o'tilmoqda...")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
