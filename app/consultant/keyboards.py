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


def create_drugs_keyboard(drugs_list: list, cart_counts: dict = None) -> InlineKeyboardMarkup:
    """
    drugs_list: لیست دیکشنری‌های دارو که از API آمده.
    cart_counts: دیکشنری شامل تعداد انتخاب شده برای هر دارو {drug_id: quantity}
    """
    if cart_counts is None:
        cart_counts = {}

    builder = InlineKeyboardBuilder()

    for drug in drugs_list:
        d_id = drug['drugs_id']
        d_name = drug['drug_pname']

        # دریافت تعداد فعلی این دارو در سبد خرید (پیش‌فرض ۰)
        qty = cart_counts.get(d_id, 0)

        # متن دکمه اصلی (نام دارو + تعداد)
        # اگر تعداد ۰ باشد: "نام دارو"
        # اگر تعداد > ۰ باشد: "نام دارو (2)"
        if qty > 0:
            text = f"{d_name} ({qty})"
        else:
            text = d_name

        # ردیف دکمه‌ها برای این دارو
        # دکمه اول: نام دارو (که نقش افزودن +1 را دارد)
        builder.row(
            InlineKeyboardButton(text=text, callback_data=f"drug_add_{d_id}")
        )

        # دکمه دوم: دکمه منفی (فقط اگر تعداد بیشتر از ۰ باشد نمایش داده می‌شود)
        if qty > 0:
            builder.add(
                InlineKeyboardButton(text="➖", callback_data=f"drug_dec_{d_id}")
            )

    # تنظیم چیدمان:
    # اگر دکمه منفی اضافه شد، در آن ردیف ۲ دکمه داریم، اگر نه ۱ دکمه.
    # اما چون ما دستی از builder.row استفاده کردیم، نیازی به adjust پیچیده نیست.
    # فقط دکمه‌های کنترلی پایین را اضافه می‌کنیم.

    builder.row(
        InlineKeyboardButton(text="📂 بازگشت به دسته‌بندی‌ها", callback_data="back_to_categories")
    )

    # محاسبه مجموع اقلام برای دکمه مشاهده
    total_items = sum(cart_counts.values())
    if total_items > 0:
        builder.row(
            InlineKeyboardButton(text=f"👁‍🗨 مشاهده لیست تجویز ({total_items} قلم)", callback_data="review_prescription")
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