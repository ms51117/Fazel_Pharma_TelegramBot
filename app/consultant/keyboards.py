# app/consultant/keyboards.py

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def create_dates_keyboard(dates: list[str]) -> InlineKeyboardMarkup:
    """Creates a keyboard with buttons for each date."""
    builder = InlineKeyboardBuilder()
    for date in dates:
        # Callback_data را با یک پیشوند مشخص می‌کنیم تا بعدا راحت‌تر فیلتر کنیم
        builder.button(text=date, callback_data=f"consultant_date_{date}")
    builder.adjust(2)  # نمایش دکمه‌ها در دو ستون
    return builder.as_markup()


def create_patients_keyboard(patients: list[dict]) -> InlineKeyboardMarkup:
    """Creates a keyboard with buttons for each patient."""
    builder = InlineKeyboardBuilder()
    for patient in patients:
        # در callback_data، آیدی دیتابیس بیمار را ارسال می‌کنیم
        patient_id = patient.get("patient_id")
        patient_name = patient.get("full_name", "Unknown Patient")
        telegram_id = patient.get("user", {}).get("telegram_id", "N/A")

        button_text = f"{patient_name} ({telegram_id})"
        builder.button(text=button_text, callback_data=f"consultant_patient_{patient_id}")
    builder.adjust(1)  # هر بیمار در یک سطر
    return builder.as_markup()
