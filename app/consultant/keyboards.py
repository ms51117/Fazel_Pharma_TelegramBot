# app/consultant/keyboards.py

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


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
        patient_name = patient.get("full_name", "Unknown Patient")
        telegram_id = patient.get("telegram_id", "N/A")

        button_text = f"{patient_name} ({telegram_id})"
        builder.button(text=button_text, callback_data=f"consultant_patient_{telegram_id}")
    builder.adjust(1)  # هر بیمار در یک سطر
    return builder.as_markup()


def get_start_prescription_keyboard() -> InlineKeyboardMarkup:
    """Creates a keyboard with a 'Start Prescription' button."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ شروع تجویز", callback_data="start_prescription")
    return builder.as_markup()


def create_disease_types_keyboard(disease_types: list[dict]) -> InlineKeyboardMarkup:
    """Creates a keyboard for selecting a disease type."""
    builder = InlineKeyboardBuilder()
    for dtype in disease_types:
        # VVVVVV  تغییرات اصلی اینجا اعمال شده است  VVVVVV
        # از 'diseases_name' برای متن دکمه استفاده می‌کنیم
        button_text = dtype.get('diseases_name', 'Unnamed Disease')
        # از 'diseases_type_id' برای callback_data استفاده می‌کنیم
        disease_id = dtype.get('diseases_type_id')

        if disease_id is not None:
            builder.button(text=button_text, callback_data=f"disease_type_{disease_id}")
    builder.adjust(2)
    return builder.as_markup()


def create_drugs_keyboard(drugs: list[dict], selected_drug_ids: set[int] = None):
    """
    Creates a dynamic keyboard for selecting drugs.
    'selected_drug_ids' is a set of IDs of already selected drugs.
    """
    builder = InlineKeyboardBuilder()
    if selected_drug_ids is None:
        selected_drug_ids = set()

    for drug in drugs:
        drug_id = drug['drugs_id']
        drug_name = drug['drug_pname']

        if drug_id in selected_drug_ids:
            text = f"✅ {drug_name}"
        else:
            text = drug_name

        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"drug_select_{drug_id}"
            )
        )

    # --- اصلاح اصلی اینجاست ---

    # دکمه تایید نهایی و بازگشت را در یک ردیف قرار می‌دهیم
    builder.row(
        InlineKeyboardButton(
            text="بازگشت",
            callback_data="back_to_diseases"
        ),
        InlineKeyboardButton(
            text="تایید و ادامه",
            callback_data="confirm_drugs"
        )
    )
    # --------------------------

    return builder.as_markup()