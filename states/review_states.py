from aiogram.fsm.state import State, StatesGroup

class ReviewStates(StatesGroup):
    waiting_for_comment = State()   # Yulduz bosilgandan keyin sharh so'raladi
