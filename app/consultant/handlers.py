# app/consultant/handlers.py

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputFile

from app.core.API_Client import APIClient
from .states import ConsultantFlow
from .keyboards import create_dates_keyboard, create_patients_keyboard

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
        await callback.message.answer("🖼️ **تصاویر ارسالی بیمار:**")
        for photo_path in photo_paths:
            try:
                # چون مسیر مطلق را ذخیره کردیم، می‌توانیم مستقیما فایل را بخوانیم
                photo = InputFile(photo_path)
                await callback.message.answer_photo(photo)
            except Exception as e:
                await callback.message.answer(f"⚠️ خطا در بارگذاری عکس: `{photo_path}`")
                logger.error(f"Failed to send photo {photo_path} to consultant. Error: {e}")
    else:
        await callback.message.answer("این بیمار عکسی ارسال نکرده است.")

    # ... ادامه جریان کاری در مراحل بعد (انتخاب بیماری و دارو) ...
    # اینجا باید به مرحله بعدی برویم
    await state.set_state(ConsultantFlow.viewing_patient_details)  # یک وضعیت میانی
    await callback.answer()
    # در اینجا باید دکمه‌ای برای "شروع تجویز" نمایش دهیم که کاربر را به مرحله بعد ببرد.
    # این کار را در پاسخ بعدی انجام خواهیم داد تا مراحل خیلی طولانی نشوند.
