import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext

from database import models
from keyboards import keyboards
from states.admin_states import AdminStates
from utils.logger import logger

router = Router(name="menu")

MINIAPP_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/") + "/miniapp"
ADMIN_PHONE = "+998900009615"

@router.message(F.text == "🛒 Buyurtma berish")
async def cmd_open_miniapp(message: Message):
    user = await models.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. /start bosing.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛒 Buyurtma berish", web_app=WebAppInfo(url=MINIAPP_URL))
    ]])
    await message.answer("🥛 *Sut mahsulotlari katalogi*\n\nQuyidagi tugmani bosib buyurtma bering:",
        reply_markup=keyboard, parse_mode="Markdown")

@router.message(F.text == "👤 Profilim")
async def cmd_profile(message: Message):
    user = await models.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. /start bosing.")
        return
    reg_date = user['created_at'].strftime("%d.%m.%Y %H:%M")
    await message.answer(
        f"👤 *Profil:*\n\n"
        f"📝 *Ism:* {user['full_name']}\n"
        f"📞 *Telefon:* {user['phone_number']}\n"
        f"📅 *Ro'yxatdan o'tgan:* {reg_date}",
        parse_mode="Markdown")

@router.message(F.text == "📞 Bog'lanish")
async def cmd_contact(message: Message):
    await message.answer(
        f"📞 *Bog'lanish*\n\n"
        f"☎️ *Telefon:* {ADMIN_PHONE}\n"
        f"🕒 *Ish vaqti:* Har kuni 08:00–20:00\n\n"
        f"Savollaringiz bo'lsa yozib qoldiring!",
        parse_mode="Markdown")

@router.message(F.text == "🔑 Admin Panel")
async def cmd_admin_panel(message: Message, state: FSMContext):
    user = await models.get_user_by_telegram_id(message.from_user.id)
    if not user or not user.get("is_admin", False):
        return
    await state.set_state(AdminStates.main_menu)
    await message.answer("🔑 *Admin Panel*\n\nBo'limni tanlang:",
        reply_markup=keyboards.get_admin_menu_keyboard(), parse_mode="Markdown")
