# app/patient/handlers.py

import os
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

# وارد کردن کلاس‌های لازم
from .states import PatientRegistration
from .keyboards import get_start_keyboard, get_gender_keyboard, get_photo_confirmation_keyboard
from app.core.API_Client import APIClient
from app.filters.role_filter import RoleFilter

patient_router = Router()
logger = logging.getLogger(__name__)



# ... (تمام handler های دیگر از process_start_registration تا ask_for_another_photo بدون تغییر باقی می‌مانند) ...

# --- شروع فرآیند FSM با کلیک روی دکمه ---
@patient_router.callback_query(F.data == "start_registration")
async def process_start_registration(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PatientRegistration.waiting_for_full_name)
    await callback.message.answer("لطفاً نام و نام خانوادگی خود را وارد کنید:")
    await callback.answer()


# --- دریافت نام و درخواست جنسیت ---
@patient_router.message(PatientRegistration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(PatientRegistration.waiting_for_gender)
    await message.answer("جنسیت خود را انتخاب کنید:", reply_markup=get_gender_keyboard())


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
        "اطلاعات اولیه شما ثبت شد.\n\nحالا لطفاً توضیحات کاملی در مورد بیماری، علائم و داروهای مورد نیاز خود را در یک پیام وارد کنید.")


# --- دریافت توضیحات بیماری و درخواست عکس ---
@patient_router.message(PatientRegistration.waiting_for_disease_description)
async def process_disease_description(message: Message, state: FSMContext):
    await state.update_data(disease_description=message.text, photos=[])
    await state.set_state(PatientRegistration.waiting_for_photos)
    await message.answer(
        "بسیار خب. حالا لطفاً عکس‌های مربوط به مشکل خود را ارسال کنید.\nپس از ارسال تمام عکس‌ها، روی دکمه 'پایان ثبت‌نام' کلیک کنید.",
        reply_markup=get_photo_confirmation_keyboard())


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
        f"عکس شما دریافت شد. (تعداد عکس‌های ارسالی: {len(photo_list)})\nآیا عکس دیگری هم می‌خواهید ارسال کنید؟",
        reply_markup=get_photo_confirmation_keyboard())


# --- کاربر می‌خواهد عکس دیگری ارسال کند ---
@patient_router.callback_query(PatientRegistration.confirm_photo_upload, F.data == "add_another_photo")
async def ask_for_another_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PatientRegistration.waiting_for_photos)
    await callback.message.edit_text("منتظر عکس بعدی شما هستم...")
    await callback.answer()


# vvvvvv بازنویسی کامل و نهایی این هندلر vvvvvv
# --- کاربر فرآیند را تمام می‌کند (پایان ثبت‌نام) ---
@patient_router.callback_query(
    PatientRegistration.confirm_photo_upload,
    F.data == "finish_registration"
)
async def finish_registration(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        api_client: APIClient
):
    await callback.message.edit_text("⏳ در حال پردازش و ذخیره اطلاعات شما... لطفاً کمی صبر کنید.")

    user_data = await state.get_data()
    telegram_id = callback.from_user.id
    full_name = user_data.get("full_name", "کاربر") # <-- CHANGE: گرفتن نام برای پیام خوش‌آمدگویی


    saved_photo_paths = []

    # بخش دانلود و ذخیره عکس‌ها
    photo_file_ids = user_data.get("photos", [])
    if photo_file_ids:
        user_storage_path = os.path.join("patient_files", str(telegram_id))
        os.makedirs(user_storage_path, exist_ok=True)

        for i, file_id in enumerate(photo_file_ids):
            try:
                file_info = await bot.get_file(file_id)
                file_path_on_telegram = file_info.file_path

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_extension = os.path.splitext(file_path_on_telegram)[1] or ".jpg"
                filename = f"{telegram_id}_{timestamp}_{i + 1}{file_extension}"

                destination_path = os.path.join(user_storage_path, filename)

                await bot.download_file(file_path_on_telegram, destination=destination_path)

                absolute_path = os.path.abspath(destination_path)
                saved_photo_paths.append(absolute_path)

            except Exception as e:
                logging.error(f"Could not download file {file_id} for user {telegram_id}. Error: {e}")

    # بخش آماده‌سازی و ارسال داده‌ها به API
    # نام فیلدها باید دقیقاً با PatientCreate schema در بک‌اند مطابقت داشته باشد
    final_data_to_send = {
        "user_telegram_id": telegram_id,
        "full_name": user_data.get("full_name"),
        "sex": user_data.get("gender"),
        "age": user_data.get("age"),
        "weight": user_data.get("weight"),
        "height": user_data.get("height"),
        "telegram_id": str(telegram_id),
        "specific_diseases": user_data.get("disease_description"),
        "photo_paths": saved_photo_paths
    }

    new_patient_id = await api_client.create_patient_profile(final_data_to_send)


    await state.clear()

    if new_patient_id:
        # ثبت پروفایل موفقیت‌آمیز بود
        logging.info(f"Patient profile created with ID: {new_patient_id}. Now creating initial message.")

        # محتوای پیام اولیه‌ای که در دیتابیس ذخیره می‌شود
        initial_message_content = (
            f"پرونده جدید برای بیمار «{full_name}» با موفقیت ثبت شد. "
            "این یک پیام خودکار برای نشانه‌گذاری شروع تعامل است."
        )

        # فراخوانی تابع create_message برای ثبت این رویداد
        message_creation_result = await api_client.create_message(
            patient_id=new_patient_id,
            message_content=initial_message_content,
            messages_sender=True  # ارسال از طرف بیمار/سیستم
            # user_id و attachments به طور پیش‌فرض None هستند
        )
        if message_creation_result:
            logging.info(f"Initial system message created successfully for patient_id: {new_patient_id}")
        else:
            logging.warning(
                f"Patient profile was created ({new_patient_id}), but failed to create the initial system message.")



        # آماده‌سازی پیام برای نمایش به کاربر در تلگرام
        response_text = (
            f"✅ {full_name} عزیز، فرآیند ثبت‌نام شما با موفقیت به پایان رسید.\n\n"
            "پرونده شما در سیستم ذخیره شد و یک تیکت پشتیبانی برای شما ایجاد گردید.\n\n"
            f"<b>تعداد عکس‌های ذخیره شده:</b> {len(saved_photo_paths)}\n\n"
            "کارشناسان ما به زودی پرونده شما را بررسی کرده و از طریق همین ربات به شما پاسخ خواهند داد."
        )
    else:
        # ثبت پروفایل با خطا مواجه شد
        logging.error(f"Failed to create patient profile for telegram_id: {telegram_id}. API returned None.")
        response_text = (
            "❌ متاسفانه در هنگام ذخیره اطلاعات شما در سرور مشکلی پیش آمد.\n\n"
            "ممکن است شما قبلاً یک پرونده با این شماره تلگرام ثبت کرده باشید. "
            "در غیر این صورت، لطفاً چند دقیقه دیگر دوباره امتحان کنید یا با پشتیبانی تماس بگیرید."
        )

        # <-- CHANGE 4: ارسال پیام نهایی به کاربر
    await callback.message.edit_text(response_text, parse_mode='HTML')
    await callback.answer()


# ^^^^^^ پایان بخش بازنویسی شده ^^^^^^


# --- مدیریت پیام‌های غیرمنتظره در حین FSM ---
@patient_router.message(F.text, PatientRegistration.waiting_for_photos)
@patient_router.message(F.text, PatientRegistration.confirm_photo_upload)
async def handle_unexpected_text_while_waiting_for_photo(message: Message):
    await message.answer(
        "در این مرحله لطفاً فقط عکس ارسال کنید یا روی دکمه‌های زیر پیام کلیک کنید.",
        reply_markup=get_photo_confirmation_keyboard()
    )


# --- هندلر پیش‌فرض برای تمام پیام‌های دیگر (شامل /start) ---
@patient_router.message(F.text)
async def patient_default_handler(message: Message, state: FSMContext):

    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("لطفاً اطلاعات خواسته شده را به درستی وارد کنید.")
        return

    welcome_text = (
        "بیمار گرامی، به ربات داروخانه فاضل خوش آمدید!\n\n"
        "برای ثبت پرونده و درخواست دارو، لطفاً از دکمه زیر برای شروع فرآیند استفاده کنید."
    )
    await message.answer(welcome_text, reply_markup=get_start_keyboard())
