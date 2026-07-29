import os
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery
from aiogram.fsm.context import FSMContext

from database import models
from keyboards import keyboards
from states.admin_states import AdminStates
from states.profile_states import ProfileStates
from utils.logger import logger

router = Router(name="menu")

MINIAPP_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/") + "/miniapp"
ADMIN_PHONE = "+998900009615"

@router.message(F.text & F.text.contains("Buyurtma berish"))
async def cmd_open_miniapp(message: Message):
    try:
        user = await models.get_user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer("Siz ro'yxatdan o'tmagansiz. Iltimos /start bosing.")
            return

        loyalty_banner = ""
        try:
            loyalty = await models.get_user_loyalty_info(message.from_user.id)
            bar_str = loyalty.get('progress_bar', '⬜'*10)
            current = loyalty.get('current_step', 0)
            target  = loyalty.get('target', 10)
            rem     = loyalty.get('remaining', 10)

            if loyalty.get('is_gift_order'):
                loyalty_banner = f"🎁 **10-YUBILEY SOVG'ANGIZ SIZNI KUTMOQDA!**\n[ {bar_str} ] {target}/{target}\n\n"
            elif rem == 1:
                loyalty_banner = f"🔥 **JUDA YAQINSIZ!** Yana 1 ta buyurtma bersangiz SOVG'A olasiz!\n[ {bar_str} ] {current}/{target}\n\n"
            else:
                loyalty_banner = f"🎁 **Sovg'aga {rem} ta buyurtma qoldi!**\n[ {bar_str} ] {current}/{target}\n\n"
        except Exception as le:
            logger.error(f"Loyalty info error: {le}")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🍽️ Taom buyurtma berish", web_app=WebAppInfo(url=MINIAPP_URL))
        ]])

        await message.answer(
            f"🍽️ **Taomim — Mazali va tansiq taomlar siz uchun!** 🚀\n\n"
            f"{loyalty_banner}"
            f"O'zingizga yoqqan lazzatli taomlarni buyurtma qilish uchun pastdagi tugmani bosing 👇",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"cmd_open_miniapp error: {e}")
        # Xatolik yuz berganda ham minimal tugma bilan javob qaytarish
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🍽️ Taom buyurtma berish", web_app=WebAppInfo(url=MINIAPP_URL))
        ]])
        await message.answer(
            "🍽️ Buyurtma berish uchun pastdagi tugmani bosing:",
            reply_markup=keyboard
        )

@router.message(F.text == "👤 Profilim")
async def cmd_profile(message: Message):
    user = await models.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. /start bosing.")
        return
    reg_date = user['created_at'].strftime("%d.%m.%Y %H:%M")
    mfy_text = f"\n📍 *Mahalla:* {user['mfy_name']} MFY" if user.get('mfy_name') else ""

    loyalty = await models.get_user_loyalty_info(message.from_user.id)
    bar_str = loyalty.get('progress_bar', '⬜'*10)
    current = loyalty.get('current_step', 0)
    target  = loyalty.get('target', 10)
    rem     = loyalty.get('remaining', 10)
    gifts   = loyalty.get('gifts_earned', 0)

    await message.answer(
        f"👤 *Profil:*\n\n"
        f"📝 *Ism:* {user['full_name']}\n"
        f"📞 *Telefon:* {user['phone_number']}{mfy_text}\n"
        f"📅 *Ro'yxatdan o'tgan:* {reg_date}\n\n"
        f"🎁 *SOVG'A PROGRESSI (10-Yubiley):*\n"
        f"[ {bar_str} ] {current}/{target}\n"
        f"🏆 *Olingan sovg'alar:* {gifts} ta\n"
        f"✨ *Keyingi sovg'agacha:* {rem} ta buyurtma qoldi!",
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
    
    logger.info(f"FSM profile state: Location update received Lat={latitude}, Lon={longitude} for telegram ID {telegram_id}")
    
    try:
        from database.connection import execute_query
        await execute_query(
            "UPDATE users SET latitude = $1, longitude = $2 WHERE telegram_id = $3;",
            latitude, longitude, telegram_id
        )
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
