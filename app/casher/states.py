# app/casher/states.py

from aiogram.fsm.state import StatesGroup, State

class CasherReview(StatesGroup):
    """
    FSM states for the casher's payment review process.
    """
    choosing_date = State()         # مرحله انتخاب تاریخ
    choosing_payment = State()      # مرحله انتخاب پرداخت (بیمار) از لیست
    verifying_payment = State()     # مرحله مشاهده جزئیات و تایید/رد پرداخت
    entering_rejection_reason = State() # مرحله وارد کردن دلیل رد پرداخت
