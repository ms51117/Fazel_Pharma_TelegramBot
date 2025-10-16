# app/roles/Admin/handlers.py

from aiogram import Router, types, F
from aiogram.filters import CommandStart

# 1. یک روتر جدید برای نقش casher ایجاد می‌کنیم
casher_router = Router()







# 2. یک هندلر برای دستور /start تعریف می‌کنیم
@casher_router.message(CommandStart())
async def handle_admin_start(message: types.Message):
    """
    این هندلر زمانی اجرا می‌شود که یک ادمین دستور /start را ارسال کند.
    """
    await message.answer(
        f"سلام صندوق دار {message.from_user.full_name}!\n"
        "شما به عنوان **صندوق دار** وارد شده‌اید.\n"
        "به پنل مدیریت ربات خوش آمدید."
    )

# 3. یک هندلر برای پیام‌های متنی دیگر
@casher_router.message(F.text)
async def handle_admin_other_messages(message: types.Message):
    """
    هندلری برای پاسخ به پیام‌های متنی که دستور خاصی نیستند.
    """
    await message.answer(
        "صندوق دار گرامی، پیام شما دریافت شد. لطفاً از دستورات پنل مدیریت استفاده کنید."
    )
