# bot.py

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.casher.handlers import casher_router
from app.consultant.handlers import consultant_router
from app.core.setting import settings
from app.core.API_Client import APIClient
from app.filters.role_filter import RoleFilter

# ایمپورت کردن روترهای جدید از فایل‌هایشان
from app.admin.handlers import admin_router
from app.patient.handlers import patient_router

# لیست تمام نقش‌های تعریف شده در سیستم شما
# این لیست برای ثبت یک هندلر "fallback" استفاده می‌شود
ALL_ROLES = ["Admin", "Consultant", "Casher", "Patient"]


async def main() -> None:
    # ۱. ساخت کلاینت API
    # این کلاینت به عنوان یک وابستگی به Dispatcher تزریق می‌شود تا در فیلترها در دسترس باشد
    api_client = APIClient(base_url=settings.API_BASE_URL)

    # ۲. ساخت Bot و Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    # پاس دادن نمونه api_client به dispatcher در زمان ساخت
    # حالا در تمام فیلترها و میدل‌ورها به متغیر 'api_client' دسترسی داریم
    dp = Dispatcher(api_client=api_client)

    # ۳. ثبت روترها با فیلتر نقش
    # این روتر فقط برای کاربرانی با نقش "Admin" فعال می‌شود
    admin_router.message.filter(RoleFilter(allowed_roles=["Admin"]))
    dp.include_router(admin_router)


    # این روتر فقط برای کاربرانی با نقش "Patient" فعال می‌شود
    patient_router.message.filter(RoleFilter(allowed_roles=["Patient"]))
    patient_router.callback_query.filter(RoleFilter(allowed_roles=["Patient"]))
    dp.include_router(patient_router)


    # در آینده می‌توانید به همین ترتیب روترهای دیگر را اضافه کنید
    consultant_router.message.filter(RoleFilter(allowed_roles=["Consultant"]))
    patient_router.callback_query.filter(RoleFilter(allowed_roles=["Consultant"]))
    dp.include_router(consultant_router)


    casher_router.message.filter(RoleFilter(allowed_roles=["Casher"]))
    patient_router.callback_query.filter(RoleFilter(allowed_roles=["Casher"]))
    dp.include_router(casher_router)

    # ۴. اجرای ربات
    try:
        # بررسی سلامت API قبل از شروع
        await api_client.login_check()  # بیایید یک نام بهتر برای این تابع بگذاریم
        logging.info("API Health check passed. Starting bot...")

        await dp.start_polling(bot)
    finally:
        await api_client.close()
        await bot.session.close()
        logging.info("Bot stopped and sessions closed.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.warning("Bot stopped by user.")
