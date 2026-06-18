from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    main_menu = State()                   # Admin in admin main menu
    viewing_orders = State()              # Admin is browsing orders
    selecting_product_for_price = State()  # Admin is selecting product to edit price
    entering_new_price = State()          # Admin is typing new price for a product
    entering_date_for_report = State()    # Admin is typing a date for sales report
