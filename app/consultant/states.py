# app/consultant/states.py

from aiogram.fsm.state import State, StatesGroup

class ConsultantFlow(StatesGroup):
    # حالت‌های اصلی جریان کاری
    choosing_date = State()
    choosing_patient = State()
    viewing_patient_details = State()
    choosing_disease_type = State()
    choosing_drugs = State()
    sending_final_message = State()

    # حالت‌های فرعی (برای ذخیره اطلاعات)
    # با استفاده از FSM Storage، می‌توانیم اطلاعات انتخاب شده را در هر مرحله ذخیره کنیم.
