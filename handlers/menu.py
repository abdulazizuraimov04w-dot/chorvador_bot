from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database import models
from keyboards import keyboards
from states.admin_states import AdminStates
from utils.logger import logger

router = Router(name="menu")

@router.message(F.text == "📋 Mening buyurtmalarim")
async def cmd_my_orders(message: Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} requested their order history.")
    
    # Check registration
    user = await models.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.answer("Siz ro'yxatdan o'tmagansiz. Iltimos, /start buyrug'ini bosing.")
        return
        
    orders = await models.get_user_orders(telegram_id, limit=5)
    if not orders:
        await message.answer("Sizda hali buyurtmalar mavjud emas. Buyurtma berish tugmasini bosib buyurtma qilishingiz mumkin.")
        return
        
    text = "📋 **Oxirgi buyurtmalaringiz:**\n\n"
    for idx, order in enumerate(orders, 1):
        status_emoji = {
            "pending": "⏳ Kutilmoqda",
            "confirmed": "✅ Tasdiqlangan",
            "completed": "🚚 Yetkazilgan",
            "cancelled": "❌ Bekor qilingan"
        }.get(order['status'], order['status'])
        
        # Format date
        delivery_date_str = order['delivery_date'].strftime("%d.%m.%Y")
        
        text += f"**Buyurtma #{order['order_id']}** ({status_emoji})\n"
        text += f"📅 Yetkazish kuni: {delivery_date_str}\n"
        text += f"⏰ Vaqti: {order['delivery_time_start']} - {order['delivery_time_end']}\n"
        text += "📦 Mahsulotlar:\n"
        
        for item in order['items']:
            qty_unit = "dona" if item['product_name'] == "Malako" else "kg"
            text += f"  - {item['product_name']}: {item['quantity']} {qty_unit} x {int(item['price']):,} so'm\n"
            
        text += f"💵 **Jami summasi:** {int(order['total_price']):,} so'm\n\n".replace(",", " ")
        text += "---------------------------------\n\n"
        
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
        "👤 **Profil ma'lumotlaringiz:**\n\n"
        f"💳 **Telegram ID:** `{user['telegram_id']}`\n"
        f"📝 **Ism, Familiya:** {user['full_name']}\n"
        f"📞 **Telefon raqam:** {user['phone_number']}\n"
        f"📅 **Ro'yxatdan o'tgan sana:** {reg_date}\n\n"
        "Agar ma'lumotlaringiz xato bo'lsa yoki o'zgartirmoqchi bo'lsangiz, qo'llab-quvvatlash xizmati bilan bog'laning."
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "📞 Bog‘lanish")
async def cmd_contact(message: Message):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} requested support contacts.")
    
    text = (
        "📞 **Bog'lanish va qo'llab-quvvatlash**\n\n"
        "Murojaat va takliflar bo'yicha biz bilan bog'lanishingiz mumkin:\n\n"
        "☎️ **Telefon raqam:** +998 90 123 45 67\n"
        "✉️ **Telegram profil:** @sut_yetkazib_berish_admin\n"
        "🕒 **Ish tartibi:** Har kuni 08:00 - 20:00\n\n"
        "Savollaringiz bo'lsa, yozib qoldiring. Tez orada javob beramiz!"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "🔑 Admin Panel")
async def cmd_admin_panel(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    
    user = await models.get_user_by_telegram_id(telegram_id)
    if not user or not user.get("is_admin", False):
        # Silence or access denied
        return
        
    logger.info(f"Admin {telegram_id} accessed the Admin Panel.")
    await state.set_state(AdminStates.main_menu)
    await message.answer(
        "🔑 **Admin Panelga xush kelibsiz!**\n\n"
        "Kerakli boshqaruv bo'limini tanlang:",
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
