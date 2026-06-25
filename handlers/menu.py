import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext

from database import models
from keyboards import keyboards
from states.admin_states import AdminStates
from utils.logger import logger

router = Router(name="menu")

# Mini App URL — Render URL + /miniapp
MINIAPP_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/") + "/miniapp"

@router.message(F.text == "🛒 Buyurtma berish")
async def cmd_open_miniapp(message: Message):
    telegram_id = message.from_user.id
    user = await models.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. Iltimos, /start buyrug'ini bosing.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🛒 Buyurtma berish",
            web_app=WebAppInfo(url=MINIAPP_URL)
        )
    ]])
    await message.answer(
        "🥛 *Sut mahsulotlari katalogi*\n\n"
        "Quyidagi tugmani bosib buyurtma bering:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.message(F.text == "📋 Mening buyurtmalarim")
async def cmd_my_orders(message: Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} requested their order history.")

    user = await models.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. Iltimos, /start buyrug'ini bosing.")
        return

    orders = await models.get_user_orders(telegram_id, limit=5)
    if not orders:
        await message.answer("Sizda hali buyurtmalar mavjud emas.")
        return

    text = "📋 *Oxirgi buyurtmalaringiz:*\n\n"
    for order in orders:
        status_emoji = {
            "pending":   "⏳ Kutilmoqda",
            "confirmed": "✅ Tasdiqlangan",
            "completed": "🚚 Yetkazilgan",
            "cancelled": "❌ Bekor qilingan"
        }.get(order['status'], order['status'])

        delivery_date_str = order['delivery_date'].strftime("%d.%m.%Y")
        text += f"*Buyurtma #{order['order_id']}* ({status_emoji})\n"
        text += f"📅 {delivery_date_str} | ⏰ {order['delivery_time_start']}–{order['delivery_time_end']}\n"
        text += "📦 Mahsulotlar:\n"
        for item in order['items']:
            qty_unit = "dona" if item['product_name'] == "Malako" else "kg"
            text += f"  • {item['product_name']}: {item['quantity']} {qty_unit} × {int(item['price']):,} so'm\n"
        text += f"💵 *Jami: {int(order['total_price']):,} so'm*\n"
        text += "—————————————\n\n"

    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "👤 Profilim")
async def cmd_profile(message: Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} requested profile info.")

    user = await models.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. Iltimos, /start buyrug'ini bosing.")
        return

    reg_date = user['created_at'].strftime("%d.%m.%Y %H:%M")
    text = (
        "👤 *Profil ma'lumotlaringiz:*\n\n"
        f"📝 *Ism:* {user['full_name']}\n"
        f"📞 *Telefon:* {user['phone_number']}\n"
        f"📅 *Ro'yxatdan o'tgan:* {reg_date}\n"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "📞 Bog'lanish")
async def cmd_contact(message: Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} requested support contacts.")

    text = (
        "📞 *Bog'lanish*\n\n"
        "☎️ *Telefon:* +998 90 123 45 67\n"
        "✉️ *Telegram:* @sut_yetkazib_berish_admin\n"
        "🕒 *Ish vaqti:* Har kuni 08:00–20:00\n"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "🔑 Admin Panel")
async def cmd_admin_panel(message: Message, state: FSMContext):
    telegram_id = message.from_user.id

    user = await models.get_user_by_telegram_id(telegram_id)
    if not user or not user.get("is_admin", False):
        return

    logger.info(f"Admin {telegram_id} accessed the Admin Panel.")
    await state.set_state(AdminStates.main_menu)
    await message.answer(
        "🔑 *Admin Panelga xush kelibsiz!*\n\nKerakli bo'limni tanlang:",
        reply_markup=keyboards.get_admin_menu_keyboard(),
        parse_mode="Markdown"
    )
