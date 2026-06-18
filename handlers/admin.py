import os
import datetime
from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from database import models
from keyboards import keyboards
from states.admin_states import AdminStates
from utils.logger import logger

# Load admin IDs
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)

try:
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
except Exception as e:
    logger.error(f"Error parsing ADMIN_IDS in admin handler: {e}")
    ADMIN_IDS = []

router = Router(name="admin")

# Custom check to ensure only admins access these handlers
async def is_admin_check(event) -> bool:
    telegram_id = event.from_user.id
    if telegram_id in ADMIN_IDS:
        return True
    user = await models.get_user_by_telegram_id(telegram_id)
    return user is not None and user.get("is_admin", False)

# Protect all handlers in this router from non-admins
router.message.filter(is_admin_check)
router.callback_query.filter(is_admin_check)

@router.message(F.text == "🚪 Mijoz menyusiga qaytish", AdminStates.main_menu)
async def cmd_exit_admin(message: Message, state: FSMContext):
    await state.clear()
    logger.info(f"Admin {message.from_user.id} exited Admin Panel.")
    await message.answer(
        "Mijoz menyusiga qaytdingiz.",
        reply_markup=keyboards.get_main_menu_keyboard(is_admin=True)
    )

# --- VIEW CUSTOMERS ---

@router.message(F.text == "👥 Mijozlar", AdminStates.main_menu)
async def admin_view_customers(message: Message):
    if not await is_admin_check(message):
        return
        
    logger.info(f"Admin {message.from_user.id} requested customer list.")
    users = await models.get_all_users()
    
    if not users:
        await message.answer("Tizimda hali mijozlar ro'yxatdan o'tmagan.")
        return
        
    text = f"👥 **Jami ro'yxatdan o'tgan mijozlar: {len(users)} ta**\n\n"
    for idx, u in enumerate(users, 1):
        reg_date = u['created_at'].strftime("%d.%m.%Y")
        text += f"{idx}. **{u['full_name']}**\n"
        text += f"   📞 Tel: {u['phone_number']}\n"
        text += f"   📅 Sana: {reg_date} | ID: `{u['telegram_id']}`\n\n"
        
        # Avoid exceeding message length limit
        if len(text) > 3500:
            await message.answer(text, parse_mode="Markdown")
            text = ""
            
    if text:
        await message.answer(text, parse_mode="Markdown")

# --- VIEW & MANAGE ORDERS ---

@router.message(F.text == "📦 Buyurtmalar", AdminStates.main_menu)
async def admin_view_orders(message: Message):
    if not await is_admin_check(message):
        return
        
    logger.info(f"Admin {message.from_user.id} requested orders list.")
    orders = await models.get_all_orders(limit=15)
    
    if not orders:
        await message.answer("Tizimda hali buyurtmalar mavjud emas.")
        return
        
    await message.answer("📦 **Oxirgi 15 ta buyurtmalar ro'yxati:**\n(Holatni o'zgartirish uchun ostidagi tugmalardan foydalaning)")
    
    for order in orders:
        status_emoji = {
            "pending": "⏳ Kutilmoqda",
            "confirmed": "✅ Tasdiqlangan",
            "completed": "🚚 Yetkazildi",
            "cancelled": "❌ Bekor qilingan"
        }.get(order['status'], order['status'])
        
        delivery_date_str = order['delivery_date'].strftime("%d.%m.%Y")
        created_at_str = order['created_at'].strftime("%H:%M | %d.%m.%Y")
        
        text = (
            f"📋 **Buyurtma #{order['order_id']}** ({status_emoji})\n"
            f"👤 Mijoz: **{order['full_name']}**\n"
            f"📞 Telefon: {order['phone_number']}\n"
            f"🕒 Yaratilgan vaqt: {created_at_str}\n"
            f"📅 Yetkazish kuni: {delivery_date_str}\n"
            f"⏰ Vaqti: {order['delivery_time_start']} - {order['delivery_time_end']}\n"
            f"📍 Lokatsiya: https://maps.google.com/?q={order['latitude']},{order['longitude']}\n"
            f"📦 Mahsulotlar:\n"
        )
        
        for item in order['items']:
            qty_unit = "dona" if item['product_name'] == "Malako" else "kg"
            text += f"  - {item['product_name']}: {item['quantity']} {qty_unit} x {int(item['price']):,} so'm\n"
            
        text += f"💵 **Jami summasi:** {int(order['total_price']):,} so'm\n".replace(",", " ")
        
        await message.answer(
            text, 
            reply_markup=keyboards.get_order_actions_keyboard(order['order_id']),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("admin_order:"))
async def process_admin_order_action(callback: CallbackQuery):
    if not await is_admin_check(callback):
        await callback.answer("Ruxsat berilmagan!", show_alert=True)
        return
        
    parts = callback.data.split(":")
    action = parts[1]
    order_id = int(parts[2])
    
    status_map = {
        "confirm": "confirmed",
        "complete": "completed",
        "cancel": "cancelled"
    }
    
    new_status = status_map.get(action)
    if not new_status:
        await callback.answer("Noma'lum amal", show_alert=True)
        return
        
    try:
        # Get order current details to find user and notify them
        # We need to run a select to find the customer's telegram_id
        db_order = await models.fetch_row(
            """
            SELECT o.id, u.telegram_id, o.status, u.full_name
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.id = $1;
            """,
            order_id
        )
        
        if not db_order:
            await callback.answer("Buyurtma topilmadi!", show_alert=True)
            return
            
        # Update database
        await models.update_order_status(order_id, new_status)
        logger.info(f"Admin {callback.from_user.id} updated Order #{order_id} status to '{new_status}'")
        
        # Notify user
        user_tg_id = db_order['telegram_id']
        status_notification_text = ""
        if new_status == "confirmed":
            status_notification_text = (
                f"✅ Sizning #{order_id}-sonli buyurtmangiz tasdiqlandi!\n\n"
                f"⏰ Yetkazib berish vaqti: 06:30 - 07:30\n"
                f"Sog'lom va barra mahsulotlar tez orada sizga yetkaziladi."
            )
        elif new_status == "completed":
            status_notification_text = (
                f"🚚 Sizning #{order_id}-sonli buyurtmangiz muvaffaqiyatli yetkazildi!\n\n"
                f"Xizmatimizdan foydalanganingiz uchun rahmat. Yoqimli ishtaha!"
            )
        elif new_status == "cancelled":
            status_notification_text = (
                f"❌ Sizning #{order_id}-sonli buyurtmangiz bekor qilindi.\n\n"
                f"Savollaringiz bo'lsa, qo'llab-quvvatlash xizmatimizga murojaat qiling."
            )
            
        try:
            await callback.bot.send_message(chat_id=user_tg_id, text=status_notification_text)
            logger.info(f"Notification sent to user {user_tg_id} about Order #{order_id} status change.")
        except Exception as notify_err:
            logger.warning(f"Could not notify user {user_tg_id}: {notify_err}")
            
        status_text_uz = {
            "confirmed": "Tasdiqlandi ✅",
            "completed": "Yetkazildi 🚚",
            "cancelled": "Bekor qilindi ❌"
        }.get(new_status)
        
        # Edit current message representation or just show alert
        await callback.answer(f"Buyurtma #{order_id} holati o'zgartirildi: {status_text_uz}")
        
        # Update the message text to show status changed
        current_text = callback.message.text
        # Append status info at the top or bottom
        updated_text = current_text + f"\n🔄 **Holat o'zgardi:** {status_text_uz} (admin tomonidan)"
        await callback.message.edit_text(updated_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error handling admin order status change: {e}")
        await callback.answer("Amal bajarilmadi. Xatolik yuz berdi.", show_alert=True)

# --- PRODUCTS & PRICES ---

@router.message(F.text == "🧀 Mahsulotlar va Narxlar", AdminStates.main_menu)
async def admin_view_products(message: Message):
    if not await is_admin_check(message):
        return
        
    logger.info(f"Admin {message.from_user.id} requested products and prices list.")
    products = await models.get_all_products()
    
    await message.answer("🧀 **Mahsulotlar va ularning joriy narxlari:**")
    
    for p in products:
        status_str = "Sotuvda Bor ✅" if p['is_active'] else "Nofaol / Yo'q ❌"
        qty_unit = "dona" if p['name'] == "Malako" else "kg"
        text = (
            f"🥛 **{p['name']}**\n"
            f"💵 Narxi: {int(p['price']):,} so'm / {qty_unit}\n"
            f"⚙️ Holati: {status_str}".replace(",", " ")
        )
        
        # Dynamic inline keyboard for product actions
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✏️ Narxni o'zgartirish", callback_data=f"admin_prod:price:{p['id']}"))
        
        status_btn_text = "❌ Nofaol qilish" if p['is_active'] else "✅ Faol qilish"
        builder.add(InlineKeyboardButton(text=status_btn_text, callback_data=f"admin_prod:toggle:{p['id']}:{1 if p['is_active'] else 0}"))
        builder.adjust(1, 1)
        
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("admin_prod:toggle"))
async def process_product_status_toggle(callback: CallbackQuery):
    if not await is_admin_check(callback):
        return
        
    parts = callback.data.split(":")
    product_id = int(parts[2])
    is_currently_active = int(parts[3]) == 1
    
    new_status = not is_currently_active
    await models.set_product_active_status(product_id, new_status)
    
    logger.info(f"Admin {callback.from_user.id} toggled product {product_id} active state to {new_status}")
    await callback.answer(f"Mahsulot holati yangilandi!")
    
    # Update the message text
    product = await models.get_product_by_id(product_id)
    status_str = "Sotuvda Bor ✅" if product['is_active'] else "Nofaol / Yo'q ❌"
    qty_unit = "dona" if product['name'] == "Malako" else "kg"
    
    text = (
        f"🥛 **{product['name']}**\n"
        f"💵 Narxi: {int(product['price']):,} so'm / {qty_unit}\n"
        f"⚙️ Holati: {status_str}".replace(",", " ")
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✏️ Narxni o'zgartirish", callback_data=f"admin_prod:price:{product['id']}"))
    status_btn_text = "❌ Nofaol qilish" if product['is_active'] else "✅ Faol qilish"
    builder.add(InlineKeyboardButton(text=status_btn_text, callback_data=f"admin_prod:toggle:{product['id']}:{1 if product['is_active'] else 0}"))
    builder.adjust(1, 1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("admin_prod:price"))
async def process_product_price_edit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_check(callback):
        return
        
    parts = callback.data.split(":")
    product_id = int(parts[2])
    
    product = await models.get_product_by_id(product_id)
    if not product:
        await callback.answer("Mahsulot topilmadi!")
        return
        
    await state.update_data(edit_product_id=product_id, edit_product_name=product['name'])
    await state.set_state(AdminStates.entering_new_price)
    
    qty_unit = "dona" if product['name'] == "Malako" else "kg"
    await callback.message.answer(
        f"✏️ **{product['name']}** uchun yangi narxni kiriting (so'mda, faqat son kiritilsin):\n"
        f"Hozirgi narxi: {int(product['price']):,} so'm / {qty_unit}".replace(",", " ")
    )
    await callback.answer()

@router.message(AdminStates.entering_new_price)
async def process_new_price_input(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        new_price = Decimal(text)
        if new_price <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("Iltimos, noto'g'ri qiymat! Narxni musbat son shaklida kiriting (masalan: 7500):")
        return
        
    state_data = await state.get_data()
    product_id = state_data.get("edit_product_id")
    product_name = state_data.get("edit_product_name")
    
    try:
        await models.update_product_price(product_id, new_price)
        logger.info(f"Admin {message.from_user.id} updated price of product {product_name} (ID: {product_id}) to {new_price}")
        await message.answer(
            f"✅ **{product_name}** narxi muvaffaqiyatli o'zgartirildi!\n"
            f"Yangi narx: {int(new_price):,} so'm".replace(",", " "),
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        await state.set_state(AdminStates.main_menu)
    except Exception as e:
        logger.error(f"Failed to update product price: {e}")
        await message.answer("Narxni o'zgartirishda xatolik yuz berdi. Iltimos qayta urinib ko'ring.")
        await state.set_state(AdminStates.main_menu)

# --- DAILY REPORTS ---

@router.message(F.text == "📊 Kunlik hisobotlar", AdminStates.main_menu)
async def admin_view_reports_menu(message: Message):
    if not await is_admin_check(message):
        return
        
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📅 Bugungi hisobot", callback_data="admin_rep:today"))
    builder.add(InlineKeyboardButton(text="📅 Ertangi hisobot", callback_data="admin_rep:tomorrow"))
    builder.add(InlineKeyboardButton(text="✏️ Boshqa sana hisoboti", callback_data="admin_rep:custom"))
    builder.adjust(1)
    
    await message.answer(
        "📊 **Hisobot olish kunini tanlang:**",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data.startswith("admin_rep:"))
async def process_report_selection(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    
    target_date = None
    if action == "today":
        target_date = datetime.date.today()
    elif action == "tomorrow":
        target_date = datetime.date.today() + datetime.timedelta(days=1)
    elif action == "custom":
        await callback.message.answer(
            "Iltimos, hisobot sanasini yozing (Format: YYYY-MM-DD, masalan: 2026-06-19):"
        )
        await state.set_state(AdminStates.entering_date_for_report)
        await callback.answer()
        return
        
    await generate_and_send_report(callback.message, target_date)
    await callback.answer()

@router.message(AdminStates.entering_date_for_report)
async def process_custom_report_date(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        # Parse date
        target_date = datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await message.answer("Sana formati noto'g'ri! Iltimos, YYYY-MM-DD formatida kiriting (masalan: 2026-06-19):")
        return
        
    await generate_and_send_report(message, target_date)
    await state.set_state(AdminStates.main_menu)

async def generate_and_send_report(message: Message, target_date: datetime.date):
    logger.info(f"Generating report for date: {target_date}")
    
    # 1. Get Production Report
    production = await models.get_production_report(target_date)
    
    # 2. Get Sales/Revenue Report
    sales = await models.get_daily_sales_report(target_date)
    
    date_str = target_date.strftime("%d.%m.%Y")
    
    text = f"📊 **KUNLIK HISOBOT ({date_str}):**\n\n"
    text += f"💵 **Umumiy tushum:** {int(sales['revenue']):,} so'm\n".replace(",", " ")
    text += f"📦 **Jami buyurtmalar soni:** {sales['order_count']} ta\n\n"
    
    text += "🏭 **Ishlab chiqarish uchun tayyorlanadigan mahsulotlar (Barcha tasdiqlangan buyurtmalar):**\n"
    if not production:
        text += "  - Ushbu kunda yetkazib beriladigan buyurtmalar mavjud emas.\n"
    else:
        for p in production:
            qty_unit = "dona" if p['product_name'] == "Malako" else "kg"
            # Format quantity with up to 2 decimals
            qty = p['total_quantity']
            formatted_qty = f"{qty:g}"  # Strips trailing zeros after decimal
            text += f"  🥛 **{p['product_name']}:** {formatted_qty} {qty_unit}\n"
            
    text += "\n📦 **Mahsulotlar bo'yicha savdo tahlili:**\n"
    if not sales['items']:
        text += "  - Savdo ma'lumotlari yo'q.\n"
    else:
        for item in sales['items']:
            qty_unit = "dona" if item['product_name'] == "Malako" else "kg"
            qty = item['total_quantity']
            formatted_qty = f"{qty:g}"
            text += f"  - **{item['product_name']}:** {formatted_qty} {qty_unit} | Jami: {int(item['total_revenue']):,} so'm\n".replace(",", " ")
            
    await message.answer(text, parse_mode="Markdown")
