from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_for_new_location = State()  # User shares new location
    waiting_for_new_mfy = State()       # User selects new neighborhood (MFY)
