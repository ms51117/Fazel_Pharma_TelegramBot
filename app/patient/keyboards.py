# app/patient/keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from typing import List, Dict, Any

# این نام را تغییر می‌دهیم تا واضح‌تر باشد
def get_start_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # این callback_data را هم تغییر می‌دهیم تا با منطق جدید همخوانی داشته باشد
    builder.add(InlineKeyboardButton(text="✍️ تکمیل/ویرایش پروفایل", callback_data="start_profile_completion"))
    return builder.as_markup()

# این کیبورد عالی است و تغییری نیاز ندارد
def get_gender_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="مرد", callback_data="gender_male"),
        InlineKeyboardButton(text="زن", callback_data="gender_female")
    )
    return builder.as_markup()

# این کیبورد هم عالی است
def get_photo_confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✔️ بله، عکس دیگری دارم", callback_data="add_another_photo"),
        InlineKeyboardButton(text="✅ خیر، کافی است (پایان)", callback_data="finish_registration")
    )
    return builder.as_markup()

# ===== کیبورد جدید و مهم: منوی اصلی =====
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    منوی اصلی را برای کاربری که پروفایلش کامل است نمایش می‌دهد.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 درخواست مشاوره جدید", callback_data="new_consultation_request")
    builder.button(text="📦 پیگیری سفارش‌ها", callback_data="track_orders")
    builder.button(text="👤 مشاهده پروفایل من", callback_data="view_profile")
    builder.adjust(1)
    return builder.as_markup()

# ===== کیبورد جدید: برای تایید فاکتور =====

def get_invoice_action_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """
    کیبوردی برای تایید یا درخواست ویرایش فاکتور توسط بیمار.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تأیید و رفتن به پرداخت", callback_data=f"invoice_approve_{order_id}"),
        InlineKeyboardButton(text="✏️ درخواست ویرایش", callback_data=f"invoice_edit_{order_id}")
    )
    return builder.as_markup()



def get_interactive_invoice_keyboard(items: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    یک کیبورد تعاملی برای ویرایش فاکتور ایجاد می‌کند.
    هر آیتم یک دیکشنری است که باید حاوی 'drug_id', 'drug_name', 'qty', 'price', و یک کلید 'selected' باشد.
    """
    builder = InlineKeyboardBuilder()

    total_price = 0
    for item in items:
        # اگر آیتم انتخاب شده باشد، تیک سبز، در غیر این صورت یک نماد دیگر
        status_icon = "✅" if item.get("selected", True) else "☑️"
        drug_name = item.get("drug_name", "نامشخص")
        qty = item.get("qty", 0)
        price = item.get("price", 0)

        # محاسبه قیمت کل فقط برای آیتم‌های انتخاب شده
        if item.get("selected", True):
            total_price += qty * price

        button_text = f"{status_icon} {drug_name} | {qty} عدد | {price:,} تومان"

        # callback_data شامل یک پیشوند و شناسه دارو است
        builder.button(
            text=button_text,
            callback_data=f"toggle_item:{item['drug_id']}"
        )

    # دکمه‌ها را به صورت تک ستونی مرتب می‌کنیم
    builder.adjust(1)

    # اضافه کردن دکمه‌های کنترلی
    # <<<--- شروع بخش اصلاح شده --->>>
    # به جای builder.button از InlineKeyboardButton استفاده می‌کنیم
    builder.row(
        InlineKeyboardButton(text="🔄 بازنشانی", callback_data="reset_invoice_edit"),
        InlineKeyboardButton(text="✅ تایید ویرایش", callback_data="confirm_invoice_edit")
    )

    # برای دکمه قیمت کل هم همینطور
    builder.row(
        InlineKeyboardButton(text=f"💰 قیمت کل: {total_price:,.0f} تومان", callback_data="do_nothing")
    )
    # <<<--- پایان بخش اصلاح شده --->>>

    return builder.as_markup()
def get_shipping_info_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    کیبوردی برای تایید یا درخواست اصلاح اطلاعات ارسال.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید و ادامه", callback_data="confirm_shipping_info")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ اصلاح اطلاعات", callback_data="edit_shipping_info")
    )
    return builder.as_markup()