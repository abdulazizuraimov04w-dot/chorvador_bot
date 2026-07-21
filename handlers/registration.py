import os
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv

from states.registration_states import RegistrationStates
from database import models
from keyboards import keyboards
from utils.logger import logger

# Load admin IDs from .env
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)

try:
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
except Exception as e:
    logger.error(f"Error parsing ADMIN_IDS: {e}")
    ADMIN_IDS = []

router = Router(name="registration")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    
    # Check if user already exists
    user = await models.get_user_by_telegram_id(telegram_id)
    if user:
        is_admin = telegram_id in ADMIN_IDS or user.get("is_admin", False)
        # Update admin status in DB if needed
        if telegram_id in ADMIN_IDS and not user.get("is_admin", False):
            await models.update_user_admin_status(telegram_id, True)
            is_admin = True
            
        logger.info(f"User {telegram_id} ({user['full_name']}) started the bot. Already registered.")
        # Send main menu reply keyboard first so the customer has it permanently
        await message.answer(
            "Sut mahsulotlarini yetkazib berish xizmatiga xush kelibsiz. 🌅🥛",
            reply_markup=keyboards.get_main_menu_keyboard(is_admin=is_admin)
        )
        
        # Define inline keyboard with MiniApp WebAppInfo
        base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        miniapp_url = f"{base_url}/miniapp"
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛒 Buyurtma berish", web_app=WebAppInfo(url=miniapp_url))
        ]])
        
        # Then send greeting message with the inline button
        await message.answer(
            f"Assalomu alaykum, {user['full_name']}!\n"
            "Buyurtma berish uchun pastdagi tugmani bosing yoki menyudan foydalaning:",
            reply_markup=inline_keyboard
        )
        return

    logger.info(f"New user {telegram_id} started the bot. Initiating registration.")
    await message.answer(
        "Assalomu alaykum! Sut mahsulotlarini buyurtma qilish va yetkazib berish botiga xush kelibsiz.\n\n"
        "Xizmatdan foydalanish uchun ro'yxatdan o'tishingiz lozim.\n\n"
        "Iltimos, **ism va familiyangizni** kiriting (masalan: Alisher Usmonov):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RegistrationStates.waiting_for_name)

@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    full_name = message.text.strip() if message.text else ""
    if not full_name or len(full_name) < 3:
        await message.answer("Iltimos, ism va familiyangizni to'liq kiriting (kamida 3 ta harf):")
        return
        
    await state.update_data(full_name=full_name)
    logger.info(f"FSM registration state: Name set to '{full_name}' for telegram ID {message.from_user.id}")
    
    await message.answer(
        "Rahmat. Endi telefon raqamingizni jo'natish uchun quyidagi 'Telefon raqamni ulash' tugmasini bosing:",
        reply_markup=keyboards.get_contact_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_for_phone)

@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_contact(message: Message, state: FSMContext):
    phone_number = message.contact.phone_number
    # Standardize phone number: make sure it starts with + if missing, etc.
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number
        
    # Check if this phone number already exists in DB
    existing_user = await models.get_user_by_phone_number(phone_number)
    if existing_user:
        logger.warning(f"Registration conflict: Phone number {phone_number} already registered under Telegram ID {existing_user['telegram_id']}. Attempted by {message.from_user.id}")
        await message.answer(
            "Ushbu telefon raqami allaqachon boshqa foydalanuvchi tomonidan ro'yxatdan o'tkazilgan.\n"
            "Iltimos, boshqa telefon raqamdan foydalaning yoki qo'llab-quvvatlash xizmatiga murojaat qiling."
        )
        return
        
    await state.update_data(phone_number=phone_number)
    logger.info(f"FSM registration state: Phone set to '{phone_number}' for telegram ID {message.from_user.id}")
    
    await message.answer(
        "Rahmat. Oxirgi qadam: buyurtmalaringizni to'g'ri yetkazib berishimiz uchun joylashuvingizni (lokatsiyangizni) yuboring.\n"
        "Quyidagi 'Lokatsiyani ulash' tugmasini bosing:",
        reply_markup=keyboards.get_location_keyboard()
    )
    await state.set_state(RegistrationStates.waiting_for_location)

@router.message(RegistrationStates.waiting_for_phone)
async def process_phone_invalid(message: Message):
    await message.answer(
        "Iltimos, quyidagi 'Telefon raqamni ulash' tugmasini bosish orqali telefon raqamingizni ulashingiz shart:",
        reply_markup=keyboards.get_contact_keyboard()
    )

@router.message(RegistrationStates.waiting_for_location, F.location)
async def process_location(message: Message, state: FSMContext):
    latitude = message.location.latitude
    longitude = message.location.longitude
    telegram_id = message.from_user.id
    
    await state.update_data(latitude=latitude, longitude=longitude)
    logger.info(f"FSM registration state: Location set to Lat={latitude}, Lon={longitude} for telegram ID {telegram_id}")
    
    try:
        # Check if there are MFYs in DB
        mfy_list = await models.get_all_mfy()
        if not mfy_list:
            # If no MFYs configured, save user directly without MFY
            data = await state.get_data()
            full_name = data.get("full_name")
            phone_number = data.get("phone_number")
            is_admin = telegram_id in ADMIN_IDS
            
            logger.info(f"No MFYs found. Registering user {telegram_id} directly.")
            await models.create_user(
                telegram_id=telegram_id,
                full_name=full_name,
                phone_number=phone_number,
                latitude=latitude,
                longitude=longitude,
                branch_id=1,
                is_admin=is_admin,
                mfy_id=None
            )
            
            await message.answer(
                "Sut mahsulotlarini yetkazib berish xizmatiga xush kelibsiz. 🌅🥛",
                reply_markup=keyboards.get_main_menu_keyboard(is_admin=is_admin)
            )
            
            base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
            miniapp_url = f"{base_url}/miniapp"
            inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🛒 Buyurtma berish", web_app=WebAppInfo(url=miniapp_url))
            ]])
            
            await message.answer(
                f"Assalomu alaykum hurmatli {full_name}!\n"
                "Ro'yxatdan o'tish muvaffaqiyatli yakunlandi. Quyidagi tugmani bosish orqali buyurtma berishingiz mumkin:",
                reply_markup=inline_keyboard
            )
            await state.clear()
        else:
            # Transition to waiting_for_mfy
            await state.set_state(RegistrationStates.waiting_for_mfy)
            await message.answer(
                "Rahmat! Oxirgi bosqich: buyurtmalaringizni to'g'ri yetkazish va kuryerni aniqlash uchun quyidagi ro'yxatdan o'z **Mahallangizni (MFY)** tanlang:",
                reply_markup=keyboards.get_mfy_keyboard(mfy_list)
            )
    except Exception as e:
        logger.error(f"Failed to fetch MFY or register user {telegram_id}: {e}")
        await message.answer(
            "Tizimda xatolik yuz berdi. Iltimos, qayta urinib ko'ring yoki /start buyrug'ini bosing."
        )

@router.callback_query(RegistrationStates.waiting_for_mfy, F.data.startswith("select_mfy:"))
async def process_mfy_selection(callback_query: CallbackQuery, state: FSMContext):
    telegram_id = callback_query.from_user.id
    mfy_id = int(callback_query.data.split(":")[1])
    
    # Retrieve previous data
    data = await state.get_data()
    full_name = data.get("full_name")
    phone_number = data.get("phone_number")
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    
    is_admin = telegram_id in ADMIN_IDS
    
    logger.info(f"Completing registration for user {telegram_id}: Name={full_name}, MFY={mfy_id}")
    
    try:
        # Save to DB
        await models.create_user(
            telegram_id=telegram_id,
            full_name=full_name,
            phone_number=phone_number,
            latitude=latitude,
            longitude=longitude,
            branch_id=1, # Default main branch
            is_admin=is_admin,
            mfy_id=mfy_id
        )
        
        # Get MFY name for confirmation
        mfy_data = await models.get_mfy_by_id(mfy_id)
        mfy_name = mfy_data['name'] if mfy_data else ""
        
        # Acknowledge callback query
        await callback_query.answer("Ro'yxatdan o'tish yakunlandi!")
        
        # Delete or edit the message to remove inline buttons
        await callback_query.message.edit_text(
            f"Tanlangan mahalla: **{mfy_name}**",
            parse_mode="Markdown"
        )
        
        # Send main menu reply keyboard first so the customer has it permanently
        await callback_query.message.answer(
            "Sut mahsulotlarini yetkazib berish xizmatiga xush kelibsiz. 🌅🥛",
            reply_markup=keyboards.get_main_menu_keyboard(is_admin=is_admin)
        )
        
        # Define inline keyboard with MiniApp WebAppInfo
        base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        miniapp_url = f"{base_url}/miniapp"
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🛒 Buyurtma berish", web_app=WebAppInfo(url=miniapp_url))
        ]])
        
        # Then send greeting message with the inline button
        await callback_query.message.answer(
            f"Assalomu alaykum hurmatli {full_name}!\n"
            f"Mahalla: **{mfy_name}** MFY\n\n"
            "Ro'yxatdan o'tish muvaffaqiyatli yakunlandi. Quyidagi tugmani bosish orqali buyurtma berishingiz mumkin:",
            reply_markup=inline_keyboard,
            parse_mode="Markdown"
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Failed to register user {telegram_id} in database: {e}")
        await callback_query.answer("Tizim xatosi yuz berdi.", show_alert=True)
        await callback_query.message.answer(
            "Tizimda xatolik yuz berdi. Iltimos, /start orqali ro'yxatdan o'tishni boshidan boshlang."
        )

@router.message(RegistrationStates.waiting_for_location)
async def process_location_invalid(message: Message):
    await message.answer(
        "Iltimos, quyidagi 'Lokatsiyani ulash' tugmasini bosish orqali joylashuvingizni ulashingiz shart:",
        reply_markup=keyboards.get_location_keyboard()
    )
