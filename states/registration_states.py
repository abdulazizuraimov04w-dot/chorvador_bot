from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_name = State()      # User enters full name
    waiting_for_phone = State()     # User shares contact phone number
    waiting_for_location = State()  # User shares current location
    waiting_for_mfy = State()       # User selects neighborhood (MFY)
