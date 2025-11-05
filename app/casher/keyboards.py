# app/casher/keyboards.py

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """منوی اصلی صندوق داروسازی فاضل."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎯 شروع", callback_data="start_box")

    builder.adjust(1)
    return builder.as_markup()


def create_payment_dates_keyboard(dates: list[str]) -> InlineKeyboardMarkup:
    """برای تاریخ‌هایی که پرداخت در انتظار دارند، کیبورد می‌سازد."""
    builder = InlineKeyboardBuilder()
    for date in dates:
        builder.button(text=date, callback_data=f"casher_date_{date}")
    builder.adjust(2)
    return builder.as_markup()


def create_pending_payments_keyboard(payments: list[dict]) -> InlineKeyboardMarkup:
    """
    یک کیبورد برای انتخاب پرداخت‌های در انتظار از لیست دریافتی ایجاد می‌کند.
    """
    builder = InlineKeyboardBuilder()
    for payment in payments:
        patient_name = payment.get("full_name", "نامشخص")
        amount = payment.get("payment_value", 0)  # مقدار ممکن است رشته باشد
        payment_id = payment.get("payment_list_id")

        # ==================== اصلاحیه اصلی اینجاست ====================
        try:
            # ابتدا به عدد صحیح تبدیل کرده، سپس با کاما فرمت‌بندی می‌کنیم
            formatted_amount = f"{int(float(amount)):,} ریال"
        except (ValueError, TypeError):
            # اگر تبدیل ناموفق بود (مثلا مقدار None یا رشته غیرعددی بود)
            formatted_amount = "مبلغ نامشخص"

        button_text = f"{patient_name} - مبلغ: {formatted_amount}"
        # =============================================================

        builder.button(text=button_text, callback_data=f"casher_payment_{payment_id}")

    builder.adjust(1)
    # اضافه کردن دکمه بازگشت به منوی تاریخ‌ها
    builder.row(InlineKeyboardButton(text="⬅️ بازگشت به تاریخ‌ها", callback_data="casher_back_to_dates"))
    return builder.as_markup()


def create_payment_verification_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    """کیبورد تایید یا رد پرداخت را ایجاد می‌کند."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ رد کردن", callback_data=f"reject_payment_{payment_id}"),
        InlineKeyboardButton(text="✅ تأیید پرداخت", callback_data=f"approve_payment_{payment_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 بازگشت به لیست بیماران", callback_data="casher_back_to_list"))
    return builder.as_markup()

def create_rejection_back_keyboard() -> InlineKeyboardMarkup:
    """کیبوردی برای لغو فرآیند وارد کردن دلیل رد."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 لغو و بازگشت", callback_data="cancel_rejection")
    return builder.as_markup()

def create_after_action_keyboard(selected_date: str) -> InlineKeyboardMarkup:
    """
    کیبوردی که پس از تایید یا رد یک پرداخت نمایش داده می‌شود.
    """
    builder = InlineKeyboardBuilder()
    # این دکمه کاربر را به لیست بیماران همان روز برمی‌گرداند
    builder.button(text=" نفر بعدی", callback_data=f"casher_date_{selected_date}")
    builder.button(text="بازگشت به تاریخ‌ها", callback_data="casher_back_to_dates")
    builder.adjust(1)
    return builder.as_markup()
