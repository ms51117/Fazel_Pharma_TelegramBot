# app/patient/states.py

from aiogram.fsm.state import State, StatesGroup, default_state

class PatientRegistration(StatesGroup):
    """
    مجموعه وضعیت‌ها برای فرآیند ثبت‌نام بیمار.
    این وضعیت‌ها به ترتیب مراحل دریافت اطلاعات را مشخص می‌کنند.
    """
    waiting_for_full_name = State()      # منتظر دریافت نام و نام خانوادگی
    waiting_for_gender = State()         # منتظر دریافت جنسیت
    waiting_for_age = State()            # منتظر دریافت سن
    waiting_for_weight = State()         # منتظر دریافت وزن
    waiting_for_height = State()         # منتظر دریافت قد
    waiting_for_disease_description = State() # منتظر دریافت توضیحات بیماری
    waiting_for_special_conditions = State()


    waiting_for_photos = State()         # منتظر دریافت عکس‌ها
    confirm_photo_upload = State()
    waiting_for_edit_request = State()  # این را می‌توانیم حذف کنیم یا تغییر نام دهیم
    editing_invoice = State()



class PatientShippingInfo(StatesGroup):
    """
    وضعیت‌ها برای دریافت اطلاعات ارسال مرسوله.
    """
    waiting_for_national_id = State()
    waiting_for_phone_number = State()
    waiting_for_postal_code = State()
    waiting_for_address = State()

class PatientPaymentInfo(StatesGroup):
    """
    وضعیت‌ها برای دریافت اطلاعات پرداخت.
    """
    waiting_for_receipt_photo = State()
    waiting_for_amount = State()
    waiting_for_tracking_code = State()

class PatientConsultation(StatesGroup):
    """
    وضعیت مربوط به چت با مشاور
    """
    chatting = State()