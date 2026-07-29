"""
Review handler — mahsulotlarni baholash va sharh yozish.
Buyurtma "yakunlandi" bo'lganda bot yulduz tugmalarini yuboradi.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import models
from states.review_states import ReviewStates
from utils.logger import logger

router = Router(name="review")

STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}


def rating_keyboard(order_id: int, product_id: int) -> InlineKeyboardMarkup:
    """1–5 yulduzli inline tugmalar."""
    buttons = [
        InlineKeyboardButton(
            text=f"{i}⭐",
            callback_data=f"rate:{order_id}:{product_id}:{i}"
        )
        for i in range(1, 6)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def skip_keyboard(order_id: int, product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="O'tkazib yuborish ➡️",
            callback_data=f"skip_review:{order_id}:{product_id}"
        )
    ]])


async def send_review_request(bot, telegram_id: int, order_id: int):
    """Buyurtmadagi har bir mahsulot uchun baholash so'rovi."""
    try:
        order_products = await models.get_order_products_for_review(order_id)
        if not order_products:
            return
        for prod in order_products:
            await bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"🍽️ *{prod['name']}*ni qanday baholagen bo'lardingiz?\n"
                    f"_(Buyurtma #{order_id})_"
                ),
                parse_mode="Markdown",
                reply_markup=rating_keyboard(order_id, prod['product_id'])
            )
    except Exception as e:
        logger.error(f"send_review_request error: {e}")


# ── Yulduz tugmasi bosilganda ─────────────────────────────────
@router.callback_query(F.data.startswith("rate:"))
async def handle_rating(callback: CallbackQuery, state: FSMContext):
    _, order_id, product_id, rating = callback.data.split(":")
    order_id, product_id, rating = int(order_id), int(product_id), int(rating)

    telegram_id = callback.from_user.id
    user_id = await models.get_user_id_by_telegram_id(telegram_id)
    if not user_id:
        await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
        return

    # Reytingni vaqtincha FSM ga saqlaymiz (sharh kutamiz)
    await state.set_state(ReviewStates.waiting_for_comment)
    await state.update_data(
        review_order_id=order_id,
        review_product_id=product_id,
        review_rating=rating,
        review_user_id=user_id
    )

    stars_str = STARS.get(rating, "⭐")
    await callback.message.edit_text(
        f"*{stars_str}* — {rating} yulduz!\n\n"
        f"💬 Ixtiyoriy: sharh yozing yoki o'tkazib yuboring 👇",
        parse_mode="Markdown",
        reply_markup=skip_keyboard(order_id, product_id)
    )
    await callback.answer()


# ── Sharh matni kiritilganda ──────────────────────────────────
@router.message(ReviewStates.waiting_for_comment)
async def handle_review_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id    = data.get("review_order_id")
    product_id  = data.get("review_product_id")
    rating      = data.get("review_rating")
    user_id     = data.get("review_user_id")

    comment = message.text.strip() if message.text else None

    try:
        await models.add_review(product_id, user_id, order_id, rating, comment)
        stars_str = STARS.get(rating, "⭐")
        await message.answer(
            f"✅ Rahmat! *{stars_str}* bahoyingiz saqlandi!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"handle_review_comment: {e}")
        await message.answer("Xatolik yuz berdi. Keyinroq urinib ko'ring.")

    await state.clear()


# ── "O'tkazib yuborish" bosilganda ───────────────────────────
@router.callback_query(F.data.startswith("skip_review:"))
async def handle_skip_review(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_id   = data.get("review_order_id")
    product_id = data.get("review_product_id")
    rating     = data.get("review_rating")
    user_id    = data.get("review_user_id")

    if order_id and product_id and rating and user_id:
        try:
            # Sharh yo'q, faqat reyting saqlanadi
            await models.add_review(product_id, user_id, order_id, rating, None)
        except Exception as e:
            logger.error(f"handle_skip_review save: {e}")

    await callback.message.edit_text("✅ Bahoyingiz saqlandi! Rahmat.")
    await state.clear()
    await callback.answer()
