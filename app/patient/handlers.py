# app/patient/handlers.py

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

# وارد کردن کلاس‌های وضعیت و کیبوردها
from .states import PatientRegistration
from .keyboards import get_start_keyboard, get_gender_keyboard

patient_router = Router()
# این فیلتر تضمین می‌کند که تمام handlerهای این روتر فقط برای کاربران با نقش "Patient" اجرا شوند
# patient_router.message.filter(F.role == "Patient")
# patient_router.callback_query.filter(F.role == "Patient")


# --- مرحله ۱: خوشامدگویی و نمایش دکمه شروع ---
@patient_router.message(Command("start"))
async def patient_start(message: Message):
    """
    این handler با دستور /start اجرا می‌شود.
    پیام خوشامدگویی و دکمه شروع را نمایش می‌دهد.
    """
    welcome_text = (
        "به ربات داروخانه فاضل خوش آمدید!\n\n"
        "این ربات به شما کمک می‌کند تا به راحتی نیازهای دارویی خود را ثبت و پیگیری کنید.\n\n"
        "برای شروع، لطفاً روی دکمه زیر کلیک کنید تا اطلاعات اولیه شما را دریافت کنیم."
    )
    await message.answer(
        welcome_text,
        reply_markup=get_start_keyboard()
    )


# --- مرحله ۲: شروع فرآیند با کلیک روی دکمه ---
@patient_router.callback_query(F.data == "start_registration")
async def process_start_registration(callback: CallbackQuery, state: FSMContext):
    """
    این handler پس از کلیک روی دکمه "شروع فرآیند ثبت‌نام" اجرا می‌شود.
    """
    # تغییر وضعیت کاربر به "منتظر دریافت نام"
    await state.set_state(PatientRegistration.waiting_for_full_name)
    await callback.message.answer("لطفاً نام و نام خانوادگی خود را وارد کنید:")
    # برای جلوگیری از نمایش حالت لودینگ روی دکمه، به تلگرام پاسخ می‌دهیم
    await callback.answer()


# --- مرحله ۳: دریافت نام و درخواست جنسیت ---
@patient_router.message(PatientRegistration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    """
    نام کاربر را دریافت کرده و آن را در حافظه state ذخیره می‌کند.
    سپس درخواست جنسیت را ارسال می‌کند.
    """
    # ذخیره نام در حافظه موقت FSM
    await state.update_data(full_name=message.text)
    # تغییر وضعیت به مرحله بعد
    await state.set_state(PatientRegistration.waiting_for_gender)
    await message.answer(
        "جنسیت خود را انتخاب کنید:",
        reply_markup=get_gender_keyboard()
    )


# --- مرحله ۴: دریافت جنسیت و درخواست سن ---
# این handler فقط برای callback_query با داده‌های مشخص اجرا می‌شود.
@patient_router.callback_query(PatientRegistration.waiting_for_gender, F.data.in_({"gender_male", "gender_female"}))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    """
    جنسیت را دریافت، ذخیره و درخواست سن می‌کند.
    """
    # مقدار 'male' یا 'female' را از callback_data استخراج و ذخیره می‌کنیم
    gender_value = "male" if callback.data == "gender_male" else "female"
    await state.update_data(gender=gender_value)

    # تغییر وضعیت به مرحله بعد
    await state.set_state(PatientRegistration.waiting_for_age)
    await callback.message.answer("لطفاً سن خود را به عدد وارد کنید (مثال: 35):")
    await callback.answer()


# --- مرحله ۵: دریافت سن و درخواست وزن ---
@patient_router.message(PatientRegistration.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    """
    سن را دریافت، ذخیره و درخواست وزن می‌کند.
    """
    # اعتبارسنجی اولیه: مطمئن شویم ورودی عدد است
    if not message.text.isdigit():
        await message.answer("لطفاً سن را فقط به صورت عدد وارد کنید.")
        return  # از ادامه اجرای تابع جلوگیری می‌کنیم

    await state.update_data(age=int(message.text))
    await state.set_state(PatientRegistration.waiting_for_weight)
    await message.answer("لطفاً وزن خود را به کیلوگرم وارد کنید (مثال: 75.5):")


# --- مرحله ۶: دریافت وزن و درخواست قد ---
@patient_router.message(PatientRegistration.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    """
    وزن را دریافت، ذخیره و درخواست قد می‌کند.
    """
    try:
        weight = float(message.text)
    except ValueError:
        await message.answer("لطفاً وزن را به صورت یک عدد معتبر وارد کنید (مثال: 75 یا 75.5).")
        return

    await state.update_data(weight=weight)
    await state.set_state(PatientRegistration.waiting_for_height)
    await message.answer("لطفاً قد خود را به سانتی‌متر وارد کنید (مثال: 180):")


# --- مرحله ۷: دریافت قد و درخواست توضیحات بیماری ---
@patient_router.message(PatientRegistration.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    """
    قد را دریافت، ذخیره و درخواست توضیحات بیماری می‌کند.
    """
    if not message.text.isdigit():
        await message.answer("لطفاً قد را فقط به صورت عدد (سانتی‌متر) وارد کنید.")
        return

    await state.update_data(height=int(message.text))
    await state.set_state(PatientRegistration.waiting_for_disease_description)
    await message.answer(
        "عالی! اطلاعات اولیه شما ثبت شد.\n\n"
        "حالا لطفاً توضیحات کاملی در مورد بیماری، علائم و داروهای مورد نیاز خود را در یک پیام وارد کنید."
    )


# --- مرحله ۸ (نهایی): دریافت توضیحات بیماری و پایان فرآیند ---
@patient_router.message(PatientRegistration.waiting_for_disease_description)
async def process_disease_description(message: Message, state: FSMContext):
    """
    توضیحات بیماری را دریافت کرده و فرآیند را تکمیل می‌کند.
    """
    # ذخیره آخرین اطلاعات
    await state.update_data(disease_description=message.text)

    # تمام داده‌های جمع‌آوری شده را از state بخوان
    user_data = await state.get_data()

    # پاک کردن وضعیت کاربر تا از این چرخه خارج شود
    await state.clear()

    # در اینجا باید داده‌های user_data را به API بک‌اند ارسال کنید تا بیمار ثبت شود.
    # این بخش را در مرحله بعد پیاده‌سازی خواهیم کرد.
    # فعلاً فقط داده‌ها را به کاربر نمایش می‌دهیم تا از صحت عملکرد مطمئن شویم.

    response_text = (
        "✅ فرآیند ثبت‌نام شما با موفقیت به پایان رسید.\n\n"
        "اطلاعات ثبت شده:\n"
        f"<b>نام:</b> {user_data.get('full_name')}\n"
        f"<b>جنسیت:</b> {'مرد' if user_data.get('gender') == 'male' else 'زن'}\n"
        f"<b>سن:</b> {user_data.get('age')}\n"
        f"<b>وزن:</b> {user_data.get('weight')} کیلوگرم\n"
        f"<b>قد:</b> {user_data.get('height')} سانتی‌متر\n\n"
        "پرونده شما برای بررسی توسط کارشناسان ارسال شد. به زودی با شما تماس گرفته خواهد شد."
    )

    await message.answer(response_text, parse_mode='HTML')
