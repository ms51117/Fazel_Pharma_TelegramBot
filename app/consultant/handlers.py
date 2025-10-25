# app/consultant/handlers.py

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputFile, InputMediaPhoto
from aiogram.types import Message, CallbackQuery, FSInputFile # <--- این را اضافه کنید
from aiogram.fsm.context import FSMContext


from app.core.API_Client import APIClient
from .states import ConsultantFlow
from .keyboards import create_dates_keyboard, create_patients_keyboard
from .keyboards import (
    create_dates_keyboard,
    create_patients_keyboard,
    get_start_prescription_keyboard, # <--- جدید
    create_disease_types_keyboard,   # <--- جدید
    create_drugs_keyboard            # <--- جدید
)

consultant_router = Router()
logger = logging.getLogger(__name__)


# --- مرحله ۱: شروع کار مشاور با دستور /start ---
@consultant_router.message(Command("start"))
async def consultant_start(message: Message, state: FSMContext, api_client: APIClient):
    await state.clear()  # شروع تمیز

    await message.answer("در حال دریافت لیست تاریخ‌های نیازمند بررسی...")

    unassigned_dates = await api_client.get_unassigned_dates()

    if not unassigned_dates:
        await message.answer("در حال حاضر هیچ بیماری در صف انتظار برای بررسی وجود ندارد. ✅")
        return

    keyboard = create_dates_keyboard(unassigned_dates)
    await message.answer(
        "📅 لطفاً تاریخی که می‌خواهید بیماران آن را بررسی کنید، انتخاب نمایید:",
        reply_markup=keyboard
    )
    await state.set_state(ConsultantFlow.choosing_date)


# --- مرحله ۲: دریافت تاریخ و نمایش بیماران آن روز ---
@consultant_router.callback_query(ConsultantFlow.choosing_date, F.data.startswith("consultant_date_"))
async def process_date_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    date = callback.data.split("_")[-1]
    await state.update_data(selected_date=date)

    await callback.message.edit_text(f"⏳ در حال دریافت لیست بیماران برای تاریخ {date}...")

    patients = await api_client.get_patients_by_date(date)

    if not patients:
        await callback.message.edit_text(f"خطا: بیماری برای تاریخ {date} یافت نشد. لطفاً دوباره تلاش کنید.")
        # می‌توانیم به مرحله قبل برگردیم یا فرآیند را تمام کنیم
        await state.clear()
        return

    keyboard = create_patients_keyboard(patients)
    await callback.message.edit_text(
        f"👥 لیست بیماران ثبت‌نام شده در تاریخ {date}:\nلطفاً بیمار مورد نظر را برای مشاهده جزئیات انتخاب کنید.",
        reply_markup=keyboard
    )
    await state.set_state(ConsultantFlow.choosing_patient)
    await callback.answer()


# --- مرحله ۳: دریافت بیمار و نمایش اطلاعات کامل او ---
@consultant_router.callback_query(ConsultantFlow.choosing_patient, F.data.startswith("consultant_patient_"))
async def process_patient_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    patient_id = int(callback.data.split("_")[-1])
    await state.update_data(selected_patient_id=patient_id)

    await callback.message.edit_text(f"🔍 در حال دریافت اطلاعات کامل بیمار با شناسه {patient_id}...")

    patient_details = await api_client.get_patient_details_by_id(patient_id)

    if not patient_details:
        await callback.message.edit_text("خطا: اطلاعات این بیمار یافت نشد!")
        await state.clear()
        return

    # ذخیره اطلاعات کلیدی برای مراحل بعدی
    await state.update_data(patient_telegram_id=patient_details.get("user", {}).get("telegram_id"))

    # آماده‌سازی متن نمایش اطلاعات
    info_text = (
        f"📄 **اطلاعات بیمار:** `{patient_details.get('full_name')}`\n\n"
        f"▪️ **شناسه تلگرام:** `{patient_details.get('user', {}).get('telegram_id')}`\n"
        f"▪️ **جنسیت:** {'مرد' if patient_details.get('gender') == 'male' else 'زن'}\n"
        f"▪️ **سن:** {patient_details.get('age')} سال\n"
        f"▪️ **وزن:** {patient_details.get('weight')} کیلوگرم\n"
        f"▪️ **قد:** {patient_details.get('height')} سانتی‌متر\n\n"
        f"📝 **شرح مشکل بیمار:**\n"
        f"{patient_details.get('disease_description')}"
    )

    await callback.message.edit_text(info_text, parse_mode="Markdown")

    # ارسال عکس‌ها
    photo_paths = patient_details.get("photo_paths", [])
    if photo_paths:
        try:
            # --- اصلاح اصلی اینجاست ---
            # تبدیل لیست مسیرهای فایل به لیست آبجکت‌های FSInputFile
            media_group = [InputMediaPhoto(media=FSInputFile(path)) for path in photo_paths]



            await callback.message.answer_media_group(media=media_group)

        except Exception as e:
            # لاگ خطا را بهبود می‌بخشیم
            logger.error(f"Failed to send media group for patient {patient_id}. Error: {e}")
    else:
        # اگر عکسی وجود نداشت، فقط متن را بفرست
        await callback.message.answer("این بیمار عکسی ارسال نکرده است.")

    await callback.message.answer(
        "برای ادامه، روی دکمه زیر کلیک کنید:",
        reply_markup=get_start_prescription_keyboard()
    )

    await state.set_state(ConsultantFlow.viewing_patient_details)
    await callback.answer()


@consultant_router.callback_query(ConsultantFlow.viewing_patient_details, F.data == "start_prescription")
async def process_start_prescription(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    await callback.message.edit_text("در حال دریافت لیست انواع بیماری‌ها...")

    disease_types = await api_client.get_all_disease_types()
    if not disease_types:
        await callback.message.edit_text("خطا: هیچ نوع بیماری در سیستم تعریف نشده است.")
        await state.clear()
        return

    keyboard = create_disease_types_keyboard(disease_types)
    await callback.message.edit_text(
        "لطفاً دسته بندی بیماری را مشخص کنید:",
        reply_markup=keyboard
    )

    # در FSM Storage یک مجموعه خالی برای داروهای انتخابی ایجاد می‌کنیم
    await state.update_data(selected_drugs=set())
    await state.set_state(ConsultantFlow.choosing_disease_type)
    await callback.answer()


# --- مرحله ۵: انتخاب نوع بیماری و نمایش داروها ---
@consultant_router.callback_query(ConsultantFlow.choosing_disease_type, F.data.startswith("disease_type_"))
async def process_disease_type_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    disease_type_id = int(callback.data.split("_")[2])
    await state.update_data(selected_disease_type_id=disease_type_id)

    await callback.message.edit_text(f"در حال دریافت لیست داروها برای دسته بندی انتخابی...")

    drugs = await api_client.get_drugs_by_disease_type(disease_type_id)
    if not drugs:
        await callback.message.edit_text("هیچ دارویی برای این دسته بندی یافت نشد.")
        # می‌توانیم به کاربر اجازه دهیم دسته دیگری را انتخاب کند
        # فعلا فرآیند را متوقف می‌کنیم
        await state.clear()
        return

    # ذخیره لیست کامل داروها برای این دسته در state
    # این کار باعث می‌شود برای هر بار تیک زدن، دوباره از API دارو نگیریم
    await state.update_data(available_drugs=drugs)

    keyboard = create_drugs_keyboard(drugs)  # در ابتدا هیچ دارویی انتخاب نشده
    await callback.message.edit_text(
        "لطفاً دارو(های) مورد نظر را انتخاب کنید.\n"
        "با هر کلیک، دارو به لیست شما اضافه یا از آن حذف می‌شود.",
        reply_markup=keyboard
    )

    await state.set_state(ConsultantFlow.choosing_drugs)
    await callback.answer()


# --- مرحله ۶: انتخاب/حذف یک دارو (منطق تیک زدن) ---
@consultant_router.callback_query(ConsultantFlow.choosing_drugs, F.data.startswith("drug_select_"))
async def process_drug_selection(callback: CallbackQuery, state: FSMContext):
    drug_id = int(callback.data.split("_")[2])

    data = await state.get_data()
    selected_drugs: set[int] = data.get("selected_drugs", set())
    available_drugs: list[dict] = data.get("available_drugs", [])

    # اگر دارو در لیست بود، حذفش کن. اگر نبود، اضافه‌اش کن.
    if drug_id in selected_drugs:
        selected_drugs.remove(drug_id)
    else:
        selected_drugs.add(drug_id)

    await state.update_data(selected_drugs=selected_drugs)

    # کیبورد را با لیست به‌روز شده داروها دوباره بساز و ویرایش کن
    new_keyboard = create_drugs_keyboard(available_drugs, selected_drugs)

    try:
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    except Exception as e:
        logger.warning(f"Could not edit keyboard, probably unchanged. {e}")

    await callback.answer()


# --- مرحله ۷: کلیک روی "ثبت نهایی داروها" ---
# این هندلر در گام بعدی که ثبت سفارش است، پیاده‌سازی خواهد شد.
# فعلا فقط اطلاعات را نمایش می‌دهیم تا از صحت عملکرد مطمئن شویم.
@consultant_router.callback_query(ConsultantFlow.choosing_drugs, F.data == "confirm_drugs")
async def process_confirm_drugs(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_drugs_ids = data.get("selected_drugs", set())

    if not selected_drugs_ids:
        await callback.answer("هیچ دارویی انتخاب نشده است!", show_alert=True)
        return

    # برای نمایش نام داروها، از لیست ذخیره شده استفاده می‌کنیم
    available_drugs = data.get("available_drugs", [])
    selected_drug_names = [
        drug['drug_pname'] for drug in available_drugs if drug['drugs_id'] in selected_drugs_ids
    ]

    await callback.message.edit_text(
        "داروهای زیر برای بیمار انتخاب شدند:\n\n"
        "🔹 " + "\n🔹 ".join(selected_drug_names) +
        "\n\nدر مرحله بعد، این سفارش ثبت خواهد شد و شما یک پیام نهایی برای بیمار ارسال خواهید کرد."
    )

    # اینجا وضعیت را به sending_final_message تغییر می‌دهیم
    await state.set_state(ConsultantFlow.sending_final_message)
    await callback.answer()
