from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import models
from keyboards import keyboards
from states.order_states import OrderStates
from utils.logger import logger

router = Router(name="order")

@router.message(F.text == "🛍️ Buyurtma berish")
async def start_order(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    logger.info(f"User {telegram_id} initiated an order.")
    
    # Check registration
    user = await models.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.answer("Buyurtma berish uchun avval ro'yxatdan o'tishingiz kerak. Iltimos, /start buyrug'ini bosing.")
        return
        
    products = await models.get_active_products()
    if not products:
        await message.answer("Hozirda sotuvda mahsulotlar mavjud emas. Iltimos, keyinroq urinib ko'ring.")
        return
        
    await state.clear()
    # Initialize empty cart in state
    await state.update_data(cart=[])
    
    keyboard = keyboards.get_products_keyboard(products)
    await message.answer(
        "🧀 **Sotuvdagi sut mahsulotlarimiz:**\n\n"
        "Sotib olmoqchi bo'lgan mahsulotni tanlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.selecting_product)

@router.callback_query(F.data == "back_to_products", OrderStates.waiting_for_quantity)
async def back_to_products(callback: CallbackQuery, state: FSMContext):
    products = await models.get_active_products()
    if not products:
        await callback.message.edit_text("Hozirda sotuvda mahsulotlar mavjud emas.")
        return
        
    keyboard = keyboards.get_products_keyboard(products)
    await callback.message.edit_text(
        "🧀 **Sotuvdagi sut mahsulotlarimiz:**\n\n"
        "Sotib olmoqchi bo'lgan mahsulotni tanlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.selecting_product)
    await callback.answer()

@router.callback_query(F.data.startswith("select_product:"))
async def process_product_selection(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    user = await models.get_user_by_telegram_id(telegram_id)
    if not user:
        await callback.answer("Buyurtma berish uchun avval ro'yxatdan o'tishingiz kerak. Iltimos, /start buyrug'ini bosing.", show_alert=True)
        return
        
    product_id = int(callback.data.split(":")[1])
    product = await models.get_product_by_id(product_id)
    
    if not product or not product['is_active']:
        await callback.answer("Kechirasiz, bu mahsulot hozirda sotuvda yo'q.", show_alert=True)
        return
        
    # Ensure cart is initialized in FSM context
    state_data = await state.get_data()
    if "cart" not in state_data:
        await state.update_data(cart=[])
        
    await state.update_data(current_product_id=product_id, current_product_name=product['name'], current_product_price=float(product['price']))
    
    qty_unit = "dona" if product['name'] == "Malako" else "kg"
    
    await callback.message.edit_text(
        f"🥛 **{product['name']}**\n"
        f"💵 Narxi: {int(product['price']):,} so'm / {qty_unit}\n\n"
        f"Qancha miqdorda buyurtma qilmoqchisiz? Quyidagi tugmalardan birini tanlang yoki o'zingiz xohlagan miqdorni kiriting (masalan: 1.5 yoki 3):".replace(",", " "),
        reply_markup=keyboards.get_quantity_keyboard(product_id)
    )
    await state.set_state(OrderStates.waiting_for_quantity)
    await callback.answer()

@router.callback_query(F.data.startswith("qty:"), OrderStates.waiting_for_quantity)
async def process_quantity_callback(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    product_id = int(data_parts[1])
    quantity = float(data_parts[2])
    
    await add_to_cart_and_show(callback.message, state, product_id, quantity)
    await callback.answer()

@router.message(OrderStates.waiting_for_quantity)
async def process_quantity_text(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        quantity = float(text)
        if quantity <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("Iltimos, musbat son kiriting (masalan: 2 yoki 1.5):")
        return
        
    state_data = await state.get_data()
    product_id = state_data.get("current_product_id")
    
    await add_to_cart_and_show(message, state, product_id, quantity)

async def add_to_cart_and_show(message: Message, state: FSMContext, product_id: int, quantity: float):
    state_data = await state.get_data()
    cart = state_data.get("cart", [])
    product_name = state_data.get("current_product_name")
    product_price = state_data.get("current_product_price")
    
    # Update quantity if product already in cart, else add new
    existing_item = next((item for item in cart if item['product_id'] == product_id), None)
    if existing_item:
        existing_item['quantity'] = round(existing_item['quantity'] + quantity, 2)
    else:
        cart.append({
            'product_id': product_id,
            'name': product_name,
            'quantity': quantity,
            'price': product_price
        })
        
    await state.update_data(cart=cart)
    logger.info(f"Cart updated for user {message.chat.id}. Cart: {cart}")
    
    # Show cart status
    await show_cart(message, state)

async def show_cart(message: Message, state: FSMContext):
    state_data = await state.get_data()
    cart = state_data.get("cart", [])
    
    if not cart:
        await message.answer("Savatingiz bo'sh. Iltimos, buyurtma berishni qaytadan boshlang.")
        await state.clear()
        return
        
    text = "🛒 **Savatingiz tarkibi:**\n\n"
    total_price = Decimal("0.00")
    
    for item in cart:
        qty_unit = "dona" if item['name'] == "Malako" else "kg"
        item_total = Decimal(str(item['quantity'])) * Decimal(str(item['price']))
        total_price += item_total
        text += f"**{item['name']}**: {item['quantity']} {qty_unit} x {int(item['price']):,} so'm = {int(item_total):,} so'm\n"
        
    text += f"\n💵 **Jami summa:** {int(total_price):,} so'm\n\n".replace(",", " ")
    text += "Yana mahsulot qo'shmoqchimisiz yoki buyurtmani tasdiqlaysizmi?"
    
    # Create action keyboard
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🧀 Yana qo'shish", callback_data="add_more_products"))
    builder.add(InlineKeyboardButton(text="✅ Buyurtmani tasdiqlash", callback_data="confirm_order"))
    builder.add(InlineKeyboardButton(text="❌ Savatni tozalash", callback_data="clear_cart"))
    builder.adjust(2, 1)
    
    # Send a new message instead of editing if it was a text input, to avoid errors
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await state.set_state(OrderStates.confirming_order)

@router.callback_query(F.data == "add_more_products", OrderStates.confirming_order)
async def add_more_products(callback: CallbackQuery, state: FSMContext):
    products = await models.get_active_products()
    if not products:
        await callback.message.edit_text("Hozirda sotuvda mahsulotlar mavjud emas.")
        return
        
    keyboard = keyboards.get_products_keyboard(products)
    await callback.message.edit_text(
        "🧀 **Sotuvdagi sut mahsulotlarimiz:**\n\n"
        "Sotib olmoqchi bo'lgan qo'shimcha mahsulotni tanlang:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(OrderStates.selecting_product)
    await callback.answer()

@router.callback_query(F.data == "clear_cart", OrderStates.confirming_order)
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    logger.info(f"User {telegram_id} cleared their cart.")
    await state.clear()
    await callback.message.edit_text("Savatingiz tozalandi. Buyurtma bekor qilindi.")
    await callback.message.answer(
        "Asosiy menyu:",
        reply_markup=keyboards.get_main_menu_keyboard(is_admin=False) # Will auto-check admin on button click
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_order", OrderStates.confirming_order)
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    state_data = await state.get_data()
    cart = state_data.get("cart", [])
    
    if not cart:
        await callback.answer("Savatingiz bo'sh!", show_alert=True)
        return
        
    # Calculate total price
    total_price = Decimal("0.00")
    db_items = []
    for item in cart:
        total_price += Decimal(str(item['quantity'])) * Decimal(str(item['price']))
        db_items.append({
            'product_id': item['product_id'],
            'quantity': item['quantity'],
            'price': Decimal(str(item['price']))
        })
        
    try:
        # Save to DB
        order_id = await models.create_order(
            telegram_id=telegram_id,
            cart_items=db_items,
            total_price=total_price
        )
        
        logger.info(f"Order #{order_id} successfully created for user {telegram_id}. Total: {total_price}")
        
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

        # Success message
        await callback.message.edit_text(
            f"✅ Buyurtmangiz qabul qilindi.\n\n"
            f"Yetkazib berish vaqti:\n"
            f"⏰ 06:30 - 07:30\n\n"
            f"Buyurtma raqami: #{order_id}"
        )
        
        # Clear FSM
        await state.clear()
        
        # Check admin for main menu keyboard
        user = await models.get_user_by_telegram_id(telegram_id)
        is_admin = user.get("is_admin", False) if user else False
        
        await callback.message.answer(
            "Xizmatimizdan foydalanganingiz uchun rahmat!",
            reply_markup=keyboards.get_main_menu_keyboard(is_admin=is_admin)
        )
        
        # Send notification to admins
        import os
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
        try:
            admin_ids = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
        except Exception:
            admin_ids = []
            
        # Also select all admin users from DB
        try:
            db_users = await models.get_all_users()
            for u in db_users:
                if u.get("is_admin", False) and u['telegram_id'] not in admin_ids:
                    admin_ids.append(u['telegram_id'])
        except Exception as db_err:
            logger.error(f"Failed to fetch db admins for order notification: {db_err}")
            
        # Format products list for notification
        items_text = ""
        for item in cart:
            qty_unit = "dona" if item['name'] == "Malako" else "kg"
            items_text += f"  - {item['name']}: {item['quantity']} {qty_unit}\n"
            
        courier_info = f"**Kuryer:** {courier_name}\n" if courier_name else ""
        mfy_info = f"**Mahalla (MFY):** {mfy_name} MFY\n" if mfy_name else ""

        admin_text = (
            f"🔔 **YANGI BUYURTMA KELIB TUSHDI!**\n\n"
            f"**Buyurtma raqami:** #{order_id}\n"
            f"**Mijoz:** {user['full_name']}\n"
            f"**Telefon:** {user['phone_number']}\n"
            f"{mfy_info}"
            f"{courier_info}"
            f"**Yetkazish vaqti:** 06:30 - 07:30 (Ertaga)\n\n"
            f"**Mahsulotlar:**\n{items_text}\n"
            f"💵 **Jami summa:** {int(total_price):,} so'm\n\n".replace(",", " ") +
            f"*Batafsil ma'lumot va boshqarish uchun Web Panelga kiring!*"
        )
        
        for admin_id in admin_ids:
            try:
                await callback.bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="Markdown")
                logger.info(f"New order notification sent to admin {admin_id}")
            except Exception as notify_err:
                logger.error(f"Failed to send order notification to admin {admin_id}: {notify_err}")
        
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
                    f"**Yetkazish vaqti:** 06:30 - 07:30 (Ertaga)\n\n"
                    f"**Mahsulotlar:**\n{items_text}\n"
                    f"💵 **Jami:** {int(total_price):,} so'm\n"
                    f"{loc_link}"
                ).replace(",", " ")
                
                await callback.bot.send_message(chat_id=courier_tg_id, text=courier_text, parse_mode="Markdown")
                logger.info(f"New order notification sent to courier {courier_tg_id}")
            except Exception as notify_err:
                logger.error(f"Failed to send order notification to courier {courier_tg_id}: {notify_err}")
        
    except Exception as e:
        logger.error(f"Failed to confirm order for user {telegram_id}: {e}")
        await callback.message.edit_text(
            "Buyurtmani tasdiqlashda xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
        )
    
    await callback.answer()
