# app/patient/handlers.py

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

# وارد کردن کلاس‌های وضعیت و کیبوردها
from .states import PatientRegistration
from .keyboards import get_start_keyboard, get_gender_keyboard, get_photo_confirmation_keyboard

patient_router = Router()

# --- شروع فرآیند FSM با کلیک روی دکمه ---
@patient_router.callback_query(F.data == "start_registration")
async def process_start_registration(callback: CallbackQuery, state: FSMContext):
    """
    این handler پس از کلیک روی دکمه "شروع فرآیند ثبت‌نام" اجرا می‌شود.
    """
    await state.set_state(PatientRegistration.waiting_for_full_name)
    await callback.message.answer("لطفاً نام و نام خانوادگی خود را وارد کنید:")
    await callback.answer()


# --- دریافت نام و درخواست جنسیت ---
@patient_router.message(PatientRegistration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(PatientRegistration.waiting_for_gender)
    await message.answer(
        "جنسیت خود را انتخاب کنید:",
        reply_markup=get_gender_keyboard()
    )


# --- دریافت جنسیت و درخواست سن ---
@patient_router.callback_query(PatientRegistration.waiting_for_gender, F.data.in_({"gender_male", "gender_female"}))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender_value = "male" if callback.data == "gender_male" else "female"
    await state.update_data(gender=gender_value)
    await state.set_state(PatientRegistration.waiting_for_age)
    await callback.message.answer("لطفاً سن خود را به عدد وارد کنید (مثال: 35):")
    await callback.answer()


# --- دریافت سن و درخواست وزن ---
@patient_router.message(PatientRegistration.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً سن را فقط به صورت عدد وارد کنید.")
        return
    await state.update_data(age=int(message.text))
    await state.set_state(PatientRegistration.waiting_for_weight)
    await message.answer("لطفاً وزن خود را به کیلوگرم وارد کنید (مثال: 75.5):")


# --- دریافت وزن و درخواست قد ---
@patient_router.message(PatientRegistration.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("لطفاً وزن را به صورت یک عدد معتبر وارد کنید (مثال: 75 یا 75.5).")
        return
    await state.update_data(weight=weight)
    await state.set_state(PatientRegistration.waiting_for_height)
    await message.answer("لطفاً قد خود را به سانتی‌متر وارد کنید (مثال: 180):")


# --- دریافت قد و درخواست توضیحات بیماری ---
@patient_router.message(PatientRegistration.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً قد را فقط به صورت عدد (سانتی‌متر) وارد کنید.")
        return
    await state.update_data(height=int(message.text))
    await state.set_state(PatientRegistration.waiting_for_disease_description)
    await message.answer(
        "اطلاعات اولیه شما ثبت شد.\n\n"
        "حالا لطفاً توضیحات کاملی در مورد بیماری، علائم و داروهای مورد نیاز خود را در یک پیام وارد کنید."
    )


# --- دریافت توضیحات بیماری و درخواست عکس ---
@patient_router.message(PatientRegistration.waiting_for_disease_description)
async def process_disease_description(message: Message, state: FSMContext):
    await state.update_data(disease_description=message.text, photos=[])
    await state.set_state(PatientRegistration.waiting_for_photos)
    await message.answer(
        "بسیار خب. حالا لطفاً عکس‌های مربوط به مشکل خود را ارسال کنید.\n"
        "(مثلاً عکس نسخه، عکس از ناحیه پوست و ...)\n\n"
        "پس از ارسال تمام عکس‌ها، روی دکمه 'پایان ثبت‌نام' کلیک کنید.",
        reply_markup=get_photo_confirmation_keyboard()
    )


# --- دریافت عکس‌ها ---
@patient_router.message(PatientRegistration.waiting_for_photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = message.photo[-1].file_id
    photo_list = data.get("photos", [])
    photo_list.append(photo_file_id)
    await state.update_data(photos=photo_list)
    await state.set_state(PatientRegistration.confirm_photo_upload)
    await message.answer(
        f"عکس شما دریافت شد. (تعداد عکس‌های ارسالی: {len(photo_list)})\n"
        "آیا عکس دیگری هم می‌خواهید ارسال کنید؟",
        reply_markup=get_photo_confirmation_keyboard()
    )


# --- کاربر می‌خواهد عکس دیگری ارسال کند ---
@patient_router.callback_query(PatientRegistration.confirm_photo_upload, F.data == "add_another_photo")
async def ask_for_another_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PatientRegistration.waiting_for_photos)
    await callback.message.edit_text("منتظر عکس بعدی شما هستم...")
    await callback.answer()

@patient_router.callback_query()


# --- کاربر فرآیند را تمام می‌کند (پایان ثبت‌نام) ---
@patient_router.callback_query(
    PatientRegistration.confirm_photo_upload,
    PatientRegistration.waiting_for_photos, # اگر کاربر هیچ عکسی نفرستد و مستقیم دکمه را بزند
    F.data == "finish_registration"
)
async def finish_registration(callback: CallbackQuery, state: FSMContext):
    print("تست----------------------------------------------------------------------")
    user_data = await state.get_data()
    await state.clear()
    photo_count = len(user_data.get("photos", []))
    photo_status = f"{photo_count} عکس" if photo_count > 0 else "هیچ عکسی ارسال نشد"
    response_text = (
        "✅ فرآیند ثبت‌نام شما با موفقیت به پایان رسید.\n\n"
        "<b>اطلاعات ثبت شده:</b>\n"
        f"<b>نام:</b> {user_data.get('full_name')}\n"
        f"<b>جنسیت:</b> {'مرد' if user_data.get('gender') == 'male' else 'زن'}\n"
        f"<b>سن:</b> {user_data.get('age')}\n"
        f"<b>وزن:</b> {user_data.get('weight')} کیلوگرم\n"
        f"<b>قد:</b> {user_data.get('height')} سانتی‌متر\n"
        f"<b>عکس‌های ارسالی:</b> {photo_status}\n\n"
        "پرونده شما برای بررسی توسط کارشناسان ارسال شد. به زودی با شما تماس گرفته خواهد شد."
    )
    await callback.message.edit_text(response_text, parse_mode='HTML')
    await callback.answer()


# --- مدیریت پیام‌های غیرمنتظره در حین FSM ---
@patient_router.message(F.text, PatientRegistration.waiting_for_photos)
@patient_router.message(F.text, PatientRegistration.confirm_photo_upload)
async def handle_unexpected_text_while_waiting_for_photo(message: Message):
    await message.answer(
        "در این مرحله لطفاً فقط عکس ارسال کنید یا روی دکمه‌های زیر پیام کلیک کنید.",
        reply_markup=get_photo_confirmation_keyboard()
    )


# --- هندلر پیش‌فرض برای تمام پیام‌های دیگر (شامل /start) ---
# این هندلر باید در آخر باشد
@patient_router.message(F.text)
async def patient_default_handler(message: Message, state: FSMContext):
    """
    این handler به هر پیام متنی که در وضعیت خاصی از FSM نباشد پاسخ می‌دهد.
    (شامل /start و هر متن دیگری)
    """
    current_state = await state.get_state()
    if current_state is not None:
        # اگر کاربر در میانه یک فرآیند دیگر است (مثلا منتظر سن) به او یادآوری می‌کنیم
        await message.answer("لطفاً اطلاعات خواسته شده را به درستی وارد کنید.")
        return

    welcome_text = (
        "بیمار گرامی، به ربات داروخانه فاضل خوش آمدید!\n\n"
        "برای ثبت پرونده و درخواست دارو، لطفاً از دکمه زیر برای شروع فرآیند استفاده کنید."
    )
    await message.answer(welcome_text, reply_markup=get_start_keyboard())
