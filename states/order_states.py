from aiogram.fsm.state import State, StatesGroup

class OrderStates(StatesGroup):
    selecting_product = State()      # User is viewing list of products
    waiting_for_quantity = State()   # User is inputting or selecting product quantity
    confirming_order = State()       # User is reviewing cart and confirming order
