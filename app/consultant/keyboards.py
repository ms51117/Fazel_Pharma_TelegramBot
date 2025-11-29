# app/consultant/keyboards.py

from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
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


# def create_drugs_keyboard(drugs: list[dict], selected_drug_ids: set[int] = None):
#     """
#     Creates a dynamic keyboard for selecting drugs.
#     'selected_drug_ids' is a set of IDs of already selected drugs.
#     """
#     builder = InlineKeyboardBuilder()
#     if selected_drug_ids is None:
#         selected_drug_ids = set()
#
#     for drug in drugs:
#         drug_id = drug['drugs_id']
#         drug_name = drug['drug_pname']
#
#         if drug_id in selected_drug_ids:
#             text = f"✅ {drug_name}"
#         else:
#             text = drug_name
#
#         builder.row(
#             InlineKeyboardButton(
#                 text=text,
#                 callback_data=f"drug_select_{drug_id}"
#             )
#         )
#
#     # --- اصلاح اصلی اینجاست ---
#
#     # دکمه تایید نهایی و بازگشت را در یک ردیف قرار می‌دهیم
#     builder.row(
#         InlineKeyboardButton(
#             text="بازگشت",
#             callback_data="back_to_diseases"
#         ),
#         InlineKeyboardButton(
#             text="تایید و ادامه",
#             callback_data="confirm_drugs"
#         )
#     )
#     # --------------------------
#
#     return builder.as_markup()



def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    منوی اصلی مشاور را ایجاد می‌کند که نقطه شروع کار اوست.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="مشاهده درخواست‌های در انتظار بررسی",
        callback_data="consultant_panel"
    )
    return builder.as_markup()


def get_next_patient_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 بیمار بعدی", callback_data="next_patient")]
        ]
    )
    return keyboard



def get_consultant_chat_keyboard() -> ReplyKeyboardMarkup:
    """کیبورد مشاور در حالت گفت‌وگو با بیمار"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ شروع تجویز")],
            [KeyboardButton(text="👤 بیمار قبلی"), KeyboardButton(text="👤 بیمار بعدی")],
            [KeyboardButton(text="🏠 بازگشت به لیست تاریخ‌ها")]  # <--- دکمه جدید
        ],
        resize_keyboard=True
    )


# ---------------------------------------------------


def create_drugs_keyboard(drugs_list, selected_drugs_ids=None):
    """
    drugs_list: لیست تمام داروهای موجود در دسته فعلی
    selected_drugs_ids: مجموعه‌ای (Set) از آیدی داروهایی که تا الان انتخاب شده‌اند
    """
    if selected_drugs_ids is None:
        selected_drugs_ids = set()

    builder = InlineKeyboardBuilder()

    # 1. لیست داروها
    for drug in drugs_list:
        d_id = drug['drugs_id']
        d_name = drug['drug_pname']
        d_price_raw = drug.get('price', 0)

        # --- FIX START: تبدیل ایمن قیمت ---
        try:
            # تبدیل رشته علمی '2.50E+6' به فلوت و سپس اینتجر
            price_val = int(float(d_price_raw))
        except (ValueError, TypeError):
            price_val = 0
        # --- FIX END ---

        # اگر دارو انتخاب شده بود، تیک سبز، وگرنه مربع خالی
        is_selected = d_id in selected_drugs_ids
        icon = "✅" if is_selected else "⬜️"

        # نمایش قیمت با جداکننده هزارگان
        text = f"{icon} {d_name} ({price_val:,} R)"
        builder.button(text=text, callback_data=f"drug_select_{d_id}")

    builder.adjust(1)  # داروها زیر هم باشند

    # 2. دکمه‌های کنترلی
    builder.row(
        InlineKeyboardButton(text="📂 بازگشت به دسته‌بندی‌ها (افزودن داروی دیگر)", callback_data="back_to_categories")
    )

    if selected_drugs_ids:
        count = len(selected_drugs_ids)
        builder.row(
            InlineKeyboardButton(text=f"👁‍🗨 مشاهده لیست تجویز ({count} مورد)", callback_data="review_prescription")
        )

    return builder.as_markup()


def create_prescription_review_keyboard():
    """کیبورد مرحله پیش‌نمایش نهایی"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ ویرایش / افزودن دارو", callback_data="back_to_categories"),
        InlineKeyboardButton(text="✅ تایید و ارسال برای بیمار", callback_data="confirm_final_order")
    )
    return builder.as_markup()