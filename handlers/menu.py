import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext

from database import models
from keyboards import keyboards
from states.admin_states import AdminStates
from states.profile_states import ProfileStates
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

# Location Update Handlers
@router.message(F.text == "📍 Joylashuvni yangilash")
async def cmd_update_location(message: Message, state: FSMContext):
    user = await models.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. /start bosing.")
        return
    await state.set_state(ProfileStates.waiting_for_new_location)
    await message.answer(
        "📍 **Joylashuvni yangilash**\n\n"
        "Buyurtmalaringizni to'g'ri yetkazib berishimiz uchun yangi manzilingizni ulashishingiz kerak.\n"
        "Iltimos, quyidagi '📍 Yangi lokatsiyani ulash' tugmasini bosing:",
        reply_markup=keyboards.get_update_location_keyboard(),
        parse_mode="Markdown"
    )

@router.message(ProfileStates.waiting_for_new_location, F.location)
async def process_new_location(message: Message, state: FSMContext):
    latitude = message.location.latitude
    longitude = message.location.longitude
    telegram_id = message.from_user.id
    
    try:
        from database.connection import execute_query
        await execute_query(
            "UPDATE users SET latitude = $1, longitude = $2 WHERE telegram_id = $3;",
            latitude, longitude, telegram_id
        )
        logger.info(f"User {telegram_id} updated their location: Lat={latitude}, Lon={longitude}")
        
        user = await models.get_user_by_telegram_id(telegram_id)
        is_admin = user.get("is_admin", False) if user else False
        
        await message.answer(
            "📍 **Joylashuv muvaffaqiyatli yangilandi!**\n\n"
            "Endi buyurtmalaringiz ushbu yangi manzilga yetkazib beriladi.",
            reply_markup=keyboards.get_main_menu_keyboard(is_admin=is_admin),
            parse_mode="Markdown"
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Failed to update location for user {telegram_id}: {e}")
        await message.answer(
            "Tizimda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
        )

@router.message(ProfileStates.waiting_for_new_location)
async def process_new_location_invalid(message: Message):
    await message.answer(
        "Iltimos, yangi uyingiz koordinatasini yuborish uchun pastdagi '📍 Yangi lokatsiyani ulash' tugmasini bosing:",
        reply_markup=keyboards.get_update_location_keyboard()
    )
