# app/roles/Patient/handlers.py

from aiogram import Router, types, F
from aiogram.filters import CommandStart

# 1. یک روتر جدید برای نقش Patient ایجاد می‌کنیم
patient_router = Router()

# 2. یک هندلر برای دستور /start تعریف می‌کنیم
@patient_router.message(CommandStart())
async def handle_patient_start(message: types.Message):
    """
    این هندلر زمانی اجرا می‌شود که یک بیمار دستور /start را ارسال کند.
    """
    # در آینده می‌توانیم از keyboards.py کیبوردها را اضافه کنیم
    await message.answer(
        f"سلام {message.from_user.full_name}!\n"
        "شما به عنوان **بیمار/کاربر** شناسایی شدید.\n"
        "به ربات داروخانه دکتر فاضل خوش آمدید. برای شروع مشاوره روی دکمه زیر کلیک کنید."
    )

# 3. یک هندلر برای پیام‌های متنی دیگر
@patient_router.message(F.text)
async def handle_patient_other_messages(message: types.Message):
    """
    هندلری برای پاسخ به پیام‌های متنی که دستور خاصی نیستند.
    """
    await message.answer(
        "پیام شما دریافت شد. لطفاً از دستورات و دکمه‌های موجود استفاده کنید."
    )
