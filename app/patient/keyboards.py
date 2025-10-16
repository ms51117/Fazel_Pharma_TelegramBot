# app/patient/keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_start_keyboard() -> InlineKeyboardMarkup:
    """
    یک کیبورد با دکمه "شروع فرآیند ثبت‌نام" ایجاد می‌کند.
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🚀 شروع فرآیند ثبت‌نام", callback_data="start_registration"))
    return builder.as_markup()

def get_gender_keyboard() -> InlineKeyboardMarkup:
    """
    یک کیبورد برای انتخاب جنسیت (مرد/زن) ایجاد می‌کند.
    """
    builder = InlineKeyboardBuilder()
    # callback_data را با مقادیر enum مدل Patient هماهنگ می‌کنیم
    builder.row(
        InlineKeyboardButton(text="مرد", callback_data="gender_male"),
        InlineKeyboardButton(text="زن", callback_data="gender_female")
    )
    return builder.as_markup()
