from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

def get_contact_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📱 Telefon raqamni ulash", request_contact=True))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def get_location_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📍 Lokatsiyani ulash", request_location=True))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def get_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🛍️ Buyurtma berish"))
    builder.add(KeyboardButton(text="📋 Mening buyurtmalarim"))
    builder.add(KeyboardButton(text="👤 Profilim"))
    builder.add(KeyboardButton(text="📞 Bog‘lanish"))
    if is_admin:
        builder.add(KeyboardButton(text="🔑 Admin Panel"))
    # Grid layout: 2 columns
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_products_keyboard(products: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.add(InlineKeyboardButton(
            text=f"{product['name']} — {int(product['price']):,} so'm".replace(",", " "),
            callback_data=f"select_product:{product['id']}"
        ))
    builder.adjust(1)
    return builder.as_markup()

def get_quantity_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i in range(1, 10):
        builder.add(InlineKeyboardButton(
            text=str(i),
            callback_data=f"qty:{product_id}:{i}"
        ))
    builder.adjust(3)
    # Add back button
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_products"))
    return builder.as_markup()

def get_cart_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Buyurtmani tasdiqlash", callback_data="confirm_order"))
    builder.add(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_order"))
    builder.adjust(1)
    return builder.as_markup()

def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📦 Buyurtmalar"))
    builder.add(KeyboardButton(text="👥 Mijozlar"))
    builder.add(KeyboardButton(text="🧀 Mahsulotlar va Narxlar"))
    builder.add(KeyboardButton(text="📊 Kunlik hisobotlar"))
    builder.add(KeyboardButton(text="🚪 Mijoz menyusiga qaytish"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_order_actions_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_order:confirm:{order_id}"))
    builder.add(InlineKeyboardButton(text="🚚 Yetkazildi", callback_data=f"admin_order:complete:{order_id}"))
    builder.add(InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"admin_order:cancel:{order_id}"))
    builder.adjust(2)
    return builder.as_markup()
