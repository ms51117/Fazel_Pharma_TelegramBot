# app/roles/Admin/handlers.py

from aiogram import Router, types, F
from aiogram.filters import CommandStart

# 1. یک روتر جدید برای نقش Admin ایجاد می‌کنیم
admin_router = Router()

# 2. یک هندلر برای دستور /start تعریف می‌کنیم
@admin_router.message(CommandStart())
async def handle_admin_start(message: types.Message):
    """
    این هندلر زمانی اجرا می‌شود که یک ادمین دستور /start را ارسال کند.
    """
    await message.answer(
        f"سلام ادمین {message.from_user.full_name}!\n"
        "شما به عنوان **مدیر سیستم** وارد شده‌اید.\n"
        "به پنل مدیریت ربات خوش آمدید."
    )

# 3. یک هندلر برای پیام‌های متنی دیگر
@admin_router.message(F.text)
async def handle_admin_other_messages(message: types.Message):
    """
    هندلری برای پاسخ به پیام‌های متنی که دستور خاصی نیستند.
    """
    await message.answer(
        "ادمین گرامی، پیام شما دریافت شد. لطفاً از دستورات پنل مدیریت استفاده کنید."
    )
