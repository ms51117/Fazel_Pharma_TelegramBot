# handler_test.py (بازنویسی کامل)

import os
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.state import default_state  # ### <-- ایمپورت جدید
from aiogram.filters import CommandStart, StateFilter # ### <-- ایمپورت جدید
from aiogram.filters import StateFilter
from aiogram.types import FSInputFile, Message
from aiogram.fsm.context import FSMContext

# ایمپورت‌های پروژه شما
from app.patient.states import PatientRegistration, PatientShippingInfo, PatientPaymentInfo, PatientConsultation
from app.patient.keyboards import (
    get_gender_keyboard,
    get_photo_confirmation_keyboard,
    get_interactive_invoice_keyboard,
    get_shipping_info_confirmation_keyboard, get_invoice_action_keyboard, get_consultation_keyboard
)
from app.core.API_Client import APIClient
from app.core.enums import PatientStatus, OrderStatusEnum

# ساخت روتر
patient_router = Router(name="patient")
logger = logging.getLogger(__name__)

async def save_telegram_file(
    bot: Bot,
    file_id: str,
    telegram_id: int,
    purpose: str = "file"
) -> Optional[str]:
    """
    یک فایل (عکس/ویس) را از تلگرام دانلود و ذخیره می‌کند.
    """
    try:
        user_storage_path = os.path.join("patient_files", str(telegram_id))
        os.makedirs(user_storage_path, exist_ok=True)

        file_info = await bot.get_file(file_id)
        file_path_on_telegram = file_info.file_path

        # تعیین پسوند فایل
        ext = os.path.splitext(file_path_on_telegram)[1]
        if not ext:
            ext = ".jpg" if purpose.startswith("photo") else ".ogg"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{telegram_id}_{timestamp}_{purpose}{ext}"
        destination_path = os.path.join(user_storage_path, filename)

        await bot.download_file(file_path_on_telegram, destination=destination_path)

        absolute_path = os.path.abspath(destination_path)
        logger.info(f"File saved for user {telegram_id} at: {absolute_path}")
        return absolute_path

    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {e}")
        return None

async def save_telegram_photo(
    bot: Bot,
    file_id: str,
    telegram_id: int,
    purpose: str = "photo"
) -> Optional[str]:
    """
    یک فایل را از تلگرام دانلود و در مسیر استاندارد پروژه ذخیره می‌کند.

    Args:
        bot (Bot): نمونه Bot برای دانلود فایل.
        file_id (str): شناسه فایل در تلگرام.
        telegram_id (int): شناسه تلگرام کاربر برای ساخت پوشه.
        purpose (str): هدفی برای نام‌گذاری فایل (مثلا 'illness', 'receipt').

    Returns:
        Optional[str]: مسیر مطلق فایل ذخیره شده یا None در صورت خطا.
    """
    try:
        user_storage_path = os.path.join("patient_files", str(telegram_id))
        os.makedirs(user_storage_path, exist_ok=True)

        file_info = await bot.get_file(file_id)
        file_path_on_telegram = file_info.file_path

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = os.path.splitext(file_path_on_telegram)[1] or ".jpg"
        filename = f"{telegram_id}_{timestamp}_{purpose}{file_extension}"

        destination_path = os.path.join(user_storage_path, filename)

        await bot.download_file(file_path_on_telegram, destination=destination_path)

        absolute_path = os.path.abspath(destination_path)
        logger.info(f"File saved for user {telegram_id} at: {absolute_path}")
        return absolute_path

    except Exception as e:
        logger.error(f"Could not download file {file_id} for user {telegram_id}. Purpose: {purpose}. Error: {e}")
        return None



# =============================================================================
# 1. نقطه ورود اصلی و مدیریت وضعیت (Main State-Driven Handler)
# =============================================================================

@patient_router.message(CommandStart())
@patient_router.message(StateFilter(default_state),F.text)
async def main_patient_handler(message: Message, state: FSMContext, api_client: APIClient, bot: Bot):
    """
    این هندلر نقطه ورود اصلی برای تمام پیام‌های بیمار است.
    ۱. وضعیت فعلی FSM را بررسی می‌کند. اگر در حال انجام فرآیندی باشد، اجازه نمی‌دهد خارج شود.
    ۲. پروفایل بیمار را از API دریافت می‌کند.
    ۳. بر اساس فیلد `status` بیمار، او را به تابع مناسب هدایت می‌کند.
    """
    # اگر کاربر در میانه یک فرآیند FSM (مثل ثبت‌نام) است، به او اجازه خروج ندهید
    # current_fsm_state = await state.get_state()
    # if current_fsm_state is not None:
    #     await message.answer("لطفاً ابتدا فرآیند فعلی را تکمیل کنید.")
    #     return

    telegram_id = message.from_user.id

    # دریافت پروفایل بیمار از بک‌اند
    patient_profile = await api_client.get_patient_details_by_telegram_id(str(telegram_id))

    # --- شاخه‌بندی بر اساس وضعیت بیمار (PatientStatus) ---

    # وضعیت ۱: بیمار جدید یا پروفایل ناقص
    if not patient_profile or patient_profile.get("patient_status") == PatientStatus.AWAITING_PROFILE_COMPLETION.value:
        return await handle_new_or_incomplete_profile(message, state)

    # وضعیت ۲: بیمار منتظر مشاوره است
    if patient_profile.get("patient_status") == PatientStatus.AWAITING_CONSULTATION.value:
        patient_id = patient_profile.get("patient_id")
        return await handle_awaiting_consultation(message,state,api_client,patient_id,bot)

    # وضعیت ۳: پیش‌فاکتور برای بیمار صادر شده و منتظر تایید اوست
    if patient_profile.get("patient_status") == PatientStatus.AWAITING_INVOICE_APPROVAL.value:
        patient_id = patient_profile.get("patient_id")
        return await handle_awaiting_invoice_approval(message, state, api_client, patient_id)

    # وضعیت ۴: بیمار فاکتور را تایید کرده و منتظر پرداخت است
    if patient_profile.get("patient_status") == PatientStatus.AWAITING_PAYMENT.value:
        patient_id = patient_profile.get("patient_id")
        return await handle_awaiting_payment(message, state, api_client, patient_id, bot)

    # وضعیت ۵: پروفایل کامل شده (پرداخت انجام شده و...)
    if patient_profile.get("patient_status") == PatientStatus.PROFILE_COMPLETED.value:
        return await handle_profile_completed(message,state, api_client)

    if patient_profile.get("patient_status") == PatientStatus.PAYMENT_COMPLETED.value:
        return await handle_payment_completed(message,state, api_client)

    # وضعیت پیش‌فرض برای سایر حالت‌ها
    await message.answer("شما در وضعیت نامشخصی قرار دارید. لطفاً با پشتیبانی تماس بگیرید.")


# =============================================================================
# 2. توابع کمکی برای مدیریت هر وضعیت (Sub-Handlers)
# =============================================================================

async def handle_new_or_incomplete_profile(message: Message, state: FSMContext):
    """اگر بیمار جدید است یا پروفایلش ناقص است، فرآیند ثبت‌نام را شروع می‌کند."""
    await state.set_state(PatientRegistration.waiting_for_full_name)
    await message.answer("سلام وقت بخیر: \n"
                         "حجم پیامها بیسار بالاست و ممکنه چند روز زمان ببره تا نوبت مشاوره شما برسه , پیشاپیش ممنون از صبوریتون \n"
                         "\n"
                         "اگر مشهد هستید و امکان مراجعه حضوری دارین عصر ها بین ساعت 17 تا 22 میتونید به داروخانه مراجعه کنید\n"
                         "\n"
                         "اگر میخاین از مشاوره انلاین ما استفاده کنید , لطفا سوالاتی که در ادامه ازتون پرسیده میشه با دقت جواب بدین تا بتونیم بهتر راهنماییتون کنیم ")
    await message.answer(
        "برای شروع، لطفاً نام و نام خانوادگی خود را وارد کنید:",
        reply_markup=ReplyKeyboardRemove()
    )



async def handle_awaiting_consultation(message: Message, state: FSMContext, api_client: APIClient, patient_id: int,
                                       bot: Bot):
    """ورود به محیط چت با مشاور و نمایش تاریخچه کامل"""

    # ذخیره patient_id برای استفاده در پیام‌های بعدی
    await state.update_data(chat_patient_id=patient_id)

    # دریافت تاریخچه پیام‌ها
    history = await api_client.read_messages_history_by_patient_id(patient_id)

    if history:
        await message.answer("📜 **تاریخچه گفتگو:**")

        for msg in history:
            # تشخیص فرستنده
            is_sender_me = msg.get('messages_sender', True)
            sender_title = "👤 شما" if is_sender_me else "👨‍⚕️ مشاور"

            text_content = msg.get('messages')

            # دریافت لیست فایل‌های پیوست
            raw_attachments = msg.get('attachment_path')
            attachments = []

            # نرمال‌سازی لیست پیوست‌ها (ممکن است استرینگ باشد یا لیست)
            if isinstance(raw_attachments, list):
                attachments = raw_attachments
            elif isinstance(raw_attachments, str) and raw_attachments:
                # گاهی اوقات دیتابیس مسیر را به صورت استرینگ برمی‌گرداند
                import ast
                try:
                    # تلاش برای تبدیل رشته لیست‌مانند به لیست واقعی
                    attachments = ast.literal_eval(raw_attachments)
                    if not isinstance(attachments, list):
                        attachments = [raw_attachments]
                except:
                    attachments = [raw_attachments]

            # --- مرحله ۱: نمایش متن پیام ---
            if text_content:
                await message.answer(f"**{sender_title}:**\n{text_content}", parse_mode="Markdown")
            elif not attachments:
                # اگر نه متن بود نه فایل
                await message.answer(f"**{sender_title}:**\n[پیام خالی]", parse_mode="Markdown")

            # --- مرحله ۲: نمایش و ارسال فایل‌ها ---
            if attachments:
                for file_path in attachments:
                    # پاکسازی مسیر (گاهی اوقات کاراکترهای اضافی دارد)
                    file_path = str(file_path).strip()

                    if not os.path.exists(file_path):
                        await message.answer(f"⚠️ **{sender_title}:** [فایل یافت نشد]\n")
                        continue

                    try:
                        # آماده‌سازی فایل برای ارسال از روی دیسک
                        file_to_send = FSInputFile(file_path)
                        file_ext = os.path.splitext(file_path)[1].lower()

                        if file_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            await bot.send_photo(
                                chat_id=message.chat.id,
                                photo=file_to_send,
                                caption=f"📷 تصویر ارسالی {sender_title}"
                            )
                        elif file_ext in ['.ogg', '.mp3', '.wav', '.m4a']:
                            await bot.send_voice(
                                chat_id=message.chat.id,
                                voice=file_to_send,
                                caption=f"🎙 ویس ارسالی {sender_title}"
                            )
                        else:
                            # سایر فایل‌ها به صورت داکیومنت
                            await bot.send_document(
                                chat_id=message.chat.id,
                                document=file_to_send,
                                caption=f"📎 فایل ارسالی {sender_title}"
                            )
                    except Exception as e:
                        logging.error(f"Error sending history file {file_path}: {e}")
                        await message.answer(f"❌ خطا در نمایش فایل: {os.path.basename(file_path)}")

    # نمایش پیام راهنما در انتها
    info_text = (
        "✅ پرونده شما در صف بررسی مشاوران قرار دارد.\n\n"
        "💬 **گفتگو با مشاور**\n"
        "شما می‌توانید در اینجا برای مشاور پیام بگذارید (متن، عکس یا ویس).\n"
        "پاسخ‌های مشاور نیز همینجا نمایش داده می‌شود.\n\n"
        "پس از پایان مشاوره، پیش‌فاکتور برای شما ارسال می‌گردد."
    )
    await message.answer(info_text, reply_markup=get_consultation_keyboard())

    # تنظیم وضعیت روی حالت چت
    await state.set_state(PatientConsultation.chatting)

async def handle_awaiting_invoice_approval(message: Message, state: FSMContext, api_client: APIClient, patient_id: int):
    """
    اگر بیمار منتظر تایید فاکتور است، آخرین فاکتور 'Created' را به او نمایش می‌دهد.
    """
    # آخرین سفارش ایجاد شده برای بیمار را پیدا کن
    orders = await api_client.get_orders_by_status(patient_id, OrderStatusEnum.CREATED.value)


    if not orders:
        await message.answer("خطا: پیش‌فاکتوری برای تایید شما یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")
        return

    # فرض می‌کنیم آخرین سفارش، سفارش مدنظر ماست
    order_to_approve = orders[-1]

    # فراخوانی تابع نمایش فاکتور تعاملی
    await display_interactive_invoice(message, state, order_to_approve)

async def handle_profile_completed(message: Message, state: FSMContext,api_client: APIClient):
    """اگر پروفایل بیمار کامل است، به او منوی اصلی را نمایش می‌دهد."""
    # در آینده می‌توانید اینجا کیبورد منوی اصلی را نمایش دهید
    # شروع فرآیند دریافت اطلاعات ارسال
    await state.set_state(PatientShippingInfo.waiting_for_national_id)
    await message.answer("لطفاً کد ملی خود را وارد کنید:")

    await process_national_id(message, state)


async def handle_awaiting_payment(message: Message, state: FSMContext, api_client: APIClient, patient_id: int, bot:Bot):
    """
    اگر بیمار منتظر پرداخت است، اطلاعات پرداخت را به او نمایش می‌دهد.
    """
    orders = await api_client.get_orders_by_status(patient_id, OrderStatusEnum.CREATED.value)
    if not orders:
        await message.answer("خطا: سفارشی در انتظار پرداخت یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")
        return

    order_id = orders[-1]['order_id']  # گرفتن شناسه آخرین سفارش در انتظار پرداخت
    await state.update_data(paying_order_id=order_id, patient_id=patient_id)

    payment_info_text = (
        "سفارش شما تایید شد. لطفاً هزینه را به یکی از حساب‌های زیر واریز کرده و سپس اطلاعات پرداخت را ثبت کنید.\n\n"
        "<b>شماره کارت:</b>\n<code>1234-5678-9012-3456</code>\n(به نام ...)\n\n"
        "<b>شماره شبا:</b>\n<code>IR123456789012345678901234</code>\n\n"
        "پس از واریز، لطفاً عکس واضح از رسید پرداخت را ارسال کنید."
    )
    await state.set_state(PatientPaymentInfo.waiting_for_receipt_photo)
    await message.answer(payment_info_text)
    await process_receipt_photo(message, state, bot)

async def handle_payment_completed(message: Message, state: FSMContext, api_client: APIClient):
    await message.answer("درخاست شما در سامانه ثبت شد و در انتظاره تایید پرداخت است , پس از تایید پرداخت سفارش شما برای ارسال اماده میشود")



# =============================================================================
# 3. هندلرهای فرآیند ثبت‌نام (FSM: PatientRegistration)
# این بخش مشابه کد قبلی شماست و فقط کمی مرتب شده است.
# =============================================================================

# --- دریافت نام و درخواست جنسیت ---
@patient_router.message(PatientRegistration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await state.set_state(PatientRegistration.waiting_for_gender)
    await message.answer("جنسیت خود را انتخاب کنید:", reply_markup=get_gender_keyboard())


# --- دریافت جنسیت و درخواست سن ---
@patient_router.callback_query(PatientRegistration.waiting_for_gender, F.data.in_({"gender_male", "gender_female"}))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender_value = "male" if callback.data == "gender_male" else "female"
    await state.update_data(gender=gender_value)
    try:
        await callback.message.edit_text(
            f"✅ جنسیت انتخاب شد: **{gender_value}**",
            reply_markup=None,
            parse_mode="Markdown"
        )
    except Exception as e:
        # اگر ویرایش پیام به هر دلیلی (مثلا قدیمی بودن پیام) ممکن نبود، خطا لاگ شود
        # و از ادامه کار جلوگیری نشود.
        print(f"Could not edit gender message: {e}")
    await state.set_state(PatientRegistration.waiting_for_age)
    await callback.message.answer("لطفاً سن خود را به عدد وارد کنید (مثال: 35):")
    await callback.answer()


# --- دریافت سن و درخواست وزن ---
@patient_router.message(PatientRegistration.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً سن را فقط به صورت عدد وارد کنید.")
        return
    await state.update_data(age=int(message.text))
    await state.set_state(PatientRegistration.waiting_for_weight)
    await message.answer("لطفاً وزن خود را به کیلوگرم وارد کنید (مثال: 75.5):")


# --- دریافت وزن و درخواست قد ---
@patient_router.message(PatientRegistration.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("لطفاً وزن را به صورت یک عدد معتبر وارد کنید (مثال: 75 یا 75.5).")
        return
    await state.update_data(weight=weight)
    await state.set_state(PatientRegistration.waiting_for_height)
    await message.answer("لطفاً قد خود را به سانتی‌متر وارد کنید (مثال: 180):")


# --- دریافت قد و درخواست توضیحات بیماری ---
@patient_router.message(PatientRegistration.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("لطفاً قد را فقط به صورت عدد (سانتی‌متر) وارد کنید.")
        return
    await state.update_data(height=int(message.text))
    await state.set_state(PatientRegistration.waiting_for_disease_description)
    await message.answer(
        "اطلاعات اولیه شما ثبت شد.\n\nحالا لطفاً توضیحات کاملی در مورد بیماری، علائم و داروهای مورد نیاز خود را در یک پیام وارد کنید.")





# --- دریافت توضیحات بیماری و درخواست عکس ---
@patient_router.message(PatientRegistration.waiting_for_disease_description)
async def process_disease_description(message: Message, state: FSMContext):
    await state.update_data(disease_description=message.text, photos=[])
    await state.set_state(PatientRegistration.waiting_for_special_conditions)
    await message.answer(
        "اگر دارای شرایط خاصی مثل بیماری‌های زمینه‌ای (مثلاً تیروئید)، "
        "بارداری، شیردهی یا مصرف داروی خاص هستید، حتماً بنویسید.\n"
        "در غیر این صورت بنویسید 'ندارم'."
    )

@patient_router.message(PatientRegistration.waiting_for_special_conditions)
async def process_special_conditions(message: Message, state: FSMContext):
    """دریافت شرایط خاص بیمار مثل بیماری زمینه‌ای، بارداری یا داروی خاص."""
    await state.update_data(special_conditions=message.text)
    await state.set_state(PatientRegistration.waiting_for_photos)
    await message.answer(
        "حالا لطفاً عکس‌های مربوط به مشکل خود را ارسال کنید.\n"
        "پس از ارسال تمام عکس‌ها، روی دکمه 'پایان ثبت‌نام' کلیک کنید.\n"
        "اگر نمیخواهید عکسی وارد کنید روی دکمه خیر کافی است کلیک کنید",
        reply_markup=get_photo_confirmation_keyboard()
    )

# --- دریافت عکس‌ها ---
@patient_router.message(PatientRegistration.waiting_for_photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo_file_id = message.photo[-1].file_id
    photo_list = data.get("photos", [])
    photo_list.append(photo_file_id)
    await state.update_data(photos=photo_list)
    await state.set_state(PatientRegistration.confirm_photo_upload)
    await message.answer(
        f"عکس شما دریافت شد. (تعداد عکس‌های ارسالی: {len(photo_list)})\nآیا عکس دیگری هم می‌خواهید ارسال کنید؟",
        reply_markup=get_photo_confirmation_keyboard())


# --- کاربر می‌خواهد عکس دیگری ارسال کند ---
@patient_router.callback_query(PatientRegistration.confirm_photo_upload, F.data == "add_another_photo")
async def ask_for_another_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PatientRegistration.waiting_for_photos)
    await callback.message.edit_text("منتظر عکس بعدی شما هستم...")
    await callback.answer()


# (اینجا تمام هندلرهای FSM ثبت‌نام از process_full_name تا finish_registration قرار می‌گیرند)
# من فقط هندلر پایانی را برای اختصار اینجا می‌آورم:
@patient_router.callback_query( StateFilter( PatientRegistration.confirm_photo_upload,PatientRegistration.waiting_for_photos), F.data == "finish_registration")
async def finish_registration(callback: CallbackQuery, state: FSMContext, bot: Bot, api_client: APIClient):
    # ... (کد دانلود عکس‌ها و آماده‌سازی داده‌ها دقیقاً مثل قبل)
    await callback.message.edit_text("⏳ در حال پردازش و ذخیره اطلاعات شما... لطفاً کمی صبر کنید.")

    user_data = await state.get_data()
    telegram_id = callback.from_user.id
    full_name = user_data.get("full_name", "کاربر") # <-- CHANGE: گرفتن نام برای پیام خوش‌آمدگویی


    saved_photo_paths = []

    # بخش دانلود و ذخیره عکس‌ها
    photo_file_ids = user_data.get("photos", [])
    if photo_file_ids:
        user_storage_path = os.path.join("patient_files", str(telegram_id))
        os.makedirs(user_storage_path, exist_ok=True)

        for i, file_id in enumerate(photo_file_ids):
            try:
                file_info = await bot.get_file(file_id)
                file_path_on_telegram = file_info.file_path

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_extension = os.path.splitext(file_path_on_telegram)[1] or ".jpg"
                filename = f"{telegram_id}_{timestamp}_{i + 1}{file_extension}"

                destination_path = os.path.join(user_storage_path, filename)

                await bot.download_file(file_path_on_telegram, destination=destination_path)

                absolute_path = os.path.abspath(destination_path)
                saved_photo_paths.append(absolute_path)

            except Exception as e:
                logging.error(f"Could not download file {file_id} for user {telegram_id}. Error: {e}")

    # بخش آماده‌سازی و ارسال داده‌ها به API
    # نام فیلدها باید دقیقاً با PatientCreate schema در بک‌اند مطابقت داشته باشد
    final_data_to_send = {
        "user_telegram_id": telegram_id,
        "full_name": user_data.get("full_name"),
        "sex": user_data.get("gender"),
        "age": user_data.get("age"),
        "weight": user_data.get("weight"),
        "height": user_data.get("height"),
        "telegram_id": str(telegram_id),
        "specific_diseases": user_data.get("disease_description"),
        "photo_paths": saved_photo_paths,
        "special_conditions" : user_data.get("special_conditions")
    }

    # پس از ارسال به API و ایجاد پروفایل:
    new_patient_id = await api_client.create_patient_profile(final_data_to_send)

    if new_patient_id:
        # ثبت پروفایل موفقیت‌آمیز بود
        logging.info(f"Patient profile created with ID: {new_patient_id}. Now changing patient status.")

        if (await api_client.update_patient_status(telegram_id, PatientStatus.AWAITING_CONSULTATION)):
            logging.info(f"Initial system change status successfully for patient_id: {new_patient_id}")
        else:
            logging.warning(f"Patient profile was created ({new_patient_id}), but failed to change patient status.")

        # آماده‌سازی پیام برای نمایش به کاربر در تلگرام
        response_text = (
            f"✅ {full_name} عزیز، فرآیند ثبت‌نام شما با موفقیت به پایان رسید.\n\n"
            "پرونده شما در سیستم ذخیره شد و یک تیکت پشتیبانی برای شما ایجاد گردید.\n\n"
            f"<b>تعداد عکس‌های ذخیره شده:</b> {len(saved_photo_paths)}\n\n"
            "کارشناسان ما به زودی پرونده شما را بررسی کرده و از طریق همین ربات به شما پاسخ خواهند داد."
        )
    else:
        # ثبت پروفایل با خطا مواجه شد
        logging.error(f"Failed to create patient profile for telegram_id: {telegram_id}. API returned None.")
        response_text = (
            "❌ متاسفانه در هنگام ذخیره اطلاعات شما در سرور مشکلی پیش آمد.\n\n"
            "ممکن است شما قبلاً یک پرونده با این شماره تلگرام ثبت کرده باشید. "
            "در غیر این صورت، لطفاً چند دقیقه دیگر دوباره امتحان کنید یا با پشتیبانی تماس بگیرید."
        )

    await callback.message.edit_text(response_text, parse_mode='HTML')

    await state.clear()

# =============================================================================
# x. هندلرهای وضعیت: انتظار مشاوره (سیستم چت) - جدید
# =============================================================================

# این تابع را قبل از تابع process_consultation_text قرار دهید

@patient_router.message(PatientConsultation.chatting, F.text == "🧾 اتمام مشاوره و درخواست فاکتور")
async def request_invoice_handler(message: Message, state: FSMContext, api_client: APIClient):
    """
    وقتی بیمار دکمه کیبورد پایین صفحه را می‌زند.
    """
    data = await state.get_data()
    patient_id = data.get("chat_patient_id")

    if not patient_id:
        # تلاش برای ریکاوری آیدی اگر در state نباشد
        telegram_id = message.from_user.id
        profile = await api_client.get_patient_details_by_telegram_id(telegram_id)
        if profile:
            patient_id = profile.get("patient_id")

    if not patient_id:
        await message.answer("⚠️ خطا در شناسایی پرونده.")
        return

    # ۱. ارسال پیام به مشاور که بداند بیمار کارش تمام شده
    system_msg = "🛑 **بیمار درخواست صدور فاکتور داد.**"

    success = await api_client.create_message(
        patient_id=patient_id,
        message_content=system_msg,
        messages_sender=True,  # به عنوان پیام بیمار ثبت می‌شود
        user_id=None
    )

    if success:
        # ۲. حذف کیبورد برای اینکه کاربر بداند درخواستش ثبت شده
        await message.answer(
            "✅ درخواست شما برای مشاور ارسال شد.\n"
            "⏳ لطفاً منتظر باشید تا مشاور فاکتور را صادر کند.\n\n"
            "به محض صدور فاکتور، ربات به شما اطلاع می‌دهد.",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer("❌ خطا در برقراری ارتباط با سرور.")


# --- هندلر دریافت متن در چت ---
@patient_router.message(PatientConsultation.chatting, F.text)
async def process_consultation_text(message: Message, state: FSMContext, api_client: APIClient):
    user_telegram_id = message.from_user.id

    # ================== بخش جدید: بررسی وضعیت لحظه‌ای ==================
    # ۱. وضعیت جدید بیمار را از API بگیرید
    user_details = await api_client.get_user_details_by_telegram_id(user_telegram_id)

    # اگر به هر دلیلی دیتا نیامد، ادامه نده
    if not user_details:
        return

    current_status = user_details.get("patient_status")

    # ۲. چک کنید آیا مشاور فاکتور صادر کرده است؟
    # (مطمئن شوید مقدار استرینگ دقیقاً با دیتابیس شما یکی باشد، مثلا awaiting_invoice_approval)
    if current_status == PatientStatus.AWAITING_INVOICE_APPROVAL.value:
        # ۳. تغییر State بیمار
        await state.clear()

        # ۴. نمایش پیام به بیمار که فاکتور صادر شده
        await message.answer(
            "🛑 **توجه:** مشاور برای شما فاکتور صادر کرده است.\n"
            "امکان ارسال پیام جدید وجود ندارد. لطفاً فاکتور را بررسی و پرداخت کنید.",
            reply_markup=None  # حذف کیبورد قبلی اگر هست
        )

        # ۵. هدایت به تابع نمایش فاکتور (که باید جداگانه داشته باشید)
        # فرض میکنیم تابعی به نام show_invoice_details دارید، یا مستقیماً اینجا صدا میزنید
        await handle_awaiting_invoice_approval(message, state, api_client,patient_id=user_details.get("patient_id"))
        return
    # ===================================================================

    if message.text.startswith("/"): return  # دستورات ربات را اجرا نکند

    data = await state.get_data()
    patient_id = data.get("chat_patient_id")

    if not patient_id:
        # اگر به هر دلیلی آیدی نبود، دوباره لود کن
        await main_patient_handler(message, state, api_client, message.bot)
        return

    success = await api_client.create_message(
        patient_id=patient_id,
        message_content=message.text,
        messages_sender=True,  # True = از طرف بیمار
        user_id=None  # در پیام بیمار نیازی به user_id نیست
    )

    if success:
        await message.reply("✔️ ارسال شد.")
    else:
        await message.reply("❌ خطا در ارسال پیام.")


# --- هندلر دریافت مدیا (عکس/ویس) در چت ---
@patient_router.message(PatientConsultation.chatting, F.photo | F.voice)
async def process_consultation_media(message: Message, state: FSMContext, bot: Bot, api_client: APIClient):
    data = await state.get_data()
    patient_id = data.get("chat_patient_id")

    if not patient_id:
        await message.answer("خطا در شناسایی پرونده.")
        return

    msg = await message.answer("⏳ در حال آپلود فایل...")

    try:
        file_id = None
        purpose = "chat_file"

        if message.photo:
            file_id = message.photo[-1].file_id
            purpose = "chat_photo"
        elif message.voice:
            file_id = message.voice.file_id
            purpose = "chat_voice"

        # ذخیره فایل
        telegram_id = message.from_user.id
        saved_path = await save_telegram_file(bot, file_id, telegram_id, purpose=purpose)

        if saved_path:
            # ارسال به API
            success = await api_client.create_message(
                patient_id=patient_id,
                message_content=f"ارسال {('عکس' if message.photo else 'ویس')}",
                messages_sender=True,
                attachments=[saved_path]  # ارسال لیست مسیر فایل
            )

            if success:
                await msg.edit_text("✅ فایل برای مشاور ارسال شد.")
            else:
                await msg.edit_text("❌ خطا در ثبت فایل در سیستم.")
        else:
            await msg.edit_text("❌ خطا در دانلود فایل.")

    except Exception as e:
        logger.error(f"Chat media error: {e}", exc_info=True)
        await msg.edit_text("خطای سیستمی.")


# =============================================================================
# 4. هندلرهای فرآیند ویرایش فاکتور (FSM: EditingInvoice)
# این بخش جدید است و از کدی که قبلاً پیشنهاد دادم استفاده می‌کند.
# =============================================================================

async def display_interactive_invoice(message: Message, state: FSMContext, order: dict):
    """
    یک پیش‌فاکتور را بر اساس داده‌های دریافتی از API نمایش می‌دهد.
    این تابع شامل دکمه‌هایی برای تایید یا درخواست ویرایش فاکتور است.
    """
    # 1. استخراج اطلاعات کلیدی از دیکشنری سفارش
    order_id = order.get('order_id')
    order_items = order.get('order_list', [])

    # 2. ساخت متن پیام فاکتور
    invoice_text = f"📄 **پیش‌فاکتور شماره {order_id}**\n\n"
    total_price = Decimal('0.0')  # مقدار اولیه قیمت کل را Decimal در نظر می‌گیریم

    if not order_items:
        invoice_text += "هیچ آیتمی در این سفارش یافت نشد."
        keyboard = None  # اگر فاکتور خالی است، دکمه‌ای نمایش نده
    else:
        # 3. پیمایش روی آیتم‌ها و استخراج اطلاعات صحیح
        for index, item in enumerate(order_items):
            # اطلاعات دارو از آبجکت تودرتوی 'drug' استخراج می‌شود
            drug_info = item.get('drug', {})
            drug_name = drug_info.get('drug_pname', 'نام دارو نامشخص')

            # استخراج تعداد و قیمت آیتم
            # از .get() برای جلوگیری از خطا در صورت نبودن کلید استفاده می‌کنیم
            quantity = item.get('qty', 0)

            # قیمت به صورت رشته علمی ("5.0E+5") است، باید به عدد تبدیل شود
            try:
                # قیمت در زمان ثبت سفارش در فیلد 'price' خود آیتم ذخیره شده است
                price_str = item.get('price', '0')
                price = Decimal(price_str)
            except (ValueError, TypeError):
                price = Decimal('0.0')

            # محاسبه قیمت کل برای هر آیتم
            item_total = quantity * price
            total_price += item_total  # اضافه کردن به قیمت نهایی

            # اضافه کردن جزئیات آیتم به متن پیام
            invoice_text += f"▪️ **{drug_name}**\n"
            invoice_text += (f"   - تعداد: `{quantity}` عدد\n"
                             f"   - قیمت واحد: `{price:,.0f}` تومان\n"
                             f"   - جمع ردیف: `{item_total:,.0f}` تومان\n\n")

        invoice_text += "-----------------------------------\n"
        # 4. اضافه کردن مبلغ نهایی محاسبه شده
        invoice_text += f"💰 **مبلغ کل قابل پرداخت: {total_price:,.0f} تومان**"

        # 5. ساخت کیبورد مناسب (تایید / ویرایش)
        keyboard = get_invoice_action_keyboard(order_id)

    # 6. ارسال پیام به کاربر
    await message.answer(
        invoice_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
@patient_router.callback_query(F.data.startswith("invoice_approve_"))
async def process_invoice_approval(callback: CallbackQuery, state: FSMContext, api_client: APIClient):



    """هنگامی که کاربر روی دکمه 'تایید نهایی' (بدون ویرایش) کلیک می‌کند."""
    data = await state.get_data()
    order_id = data.get("editing_order_id")
    patient_telegram_id = str(callback.from_user.id)

    # آپدیت وضعیت سفارش و بیمار
    await api_client.update_order(order_id, order_status=OrderStatusEnum.CREATED.value)
    await api_client.update_patient_status(patient_telegram_id, PatientStatus.PROFILE_COMPLETED.value)

    await callback.message.edit_text("فاکتور تایید شد. در حال انتقال به مرحله ورود اطلاعات ارسال...")
    await state.clear()

    # شروع فرآیند دریافت اطلاعات ارسال
    await state.set_state(PatientShippingInfo.waiting_for_national_id)
    await callback.message.answer("لطفاً کد ملی خود را وارد کنید:")


@patient_router.callback_query(F.data.startswith("invoice_edit_"))
async def process_invoice_edit_request(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """
    هنگامی که کاربر روی دکمه 'درخواست ویرایش' با یک order_id مشخص کلیک می‌کند.
    """
    telegram_id = callback.from_user.id
    patient_info = await api_client.get_patient_details_by_telegram_id(telegram_id)
    if not patient_info or "patient_id" not in patient_info:
        await callback.answer("خطا: اطلاعات پروفایل شما یافت نشد.", show_alert=True)
        return

    patient_id = patient_info["patient_id"]


    try:
        order_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("خطا در پردازش درخواست ویرایش. شناسه سفارش نامعتبر است.", show_alert=True)
        return

    # 2. واکشی اطلاعات به‌روز سفارش از API
    order_data_list  = await api_client.get_orders_by_status(patient_id, OrderStatusEnum.CREATED.value)
    order_data = order_data_list[0]  # اولین و تنها عضو لیست را انتخاب می‌کنیم

    if not order_data:
        await callback.answer("متاسفانه اطلاعات این فاکتور یافت نشد.", show_alert=True)
        return

    order_items = order_data.get("order_list", [])

    # 3. آماده‌سازی آیتم‌ها برای کیبورد تعاملی (اضافه کردن فیلد 'selected')
    # در ابتدا، همه آیتم‌ها انتخاب شده در نظر گرفته می‌شوند
    editable_items = []
    for item in order_items:
        drug_info = item.get('drug', {})
        editable_items.append({
            "drug_id": drug_info.get("drugs_id"),
            "drug_name": drug_info.get("drug_pname", "نامشخص"),
            "qty": item.get("qty", 0),
            "price": float(item.get("price", 0)),  # قیمت را به float تبدیل کنید
            "selected": True  # همه آیتم‌ها در ابتدا انتخاب شده هستند
        })

    # 4. ذخیره اطلاعات لازم در FSM state
    await state.update_data(
        editing_order_id=order_id,
        initial_cart=editable_items,  # نسخه اصلی برای بازنشانی (reset)
        current_cart=editable_items.copy()  # نسخه‌ای که تغییر می‌کند
    )

    # 5. تغییر وضعیت FSM به حالت ویرایش
    await state.set_state(PatientRegistration.editing_invoice)

    # 6. ساخت کیبورد تعاملی و ارسال پیام به کاربر
    keyboard = get_interactive_invoice_keyboard(editable_items)
    await callback.message.edit_text(
        "📄 **ویرایش فاکتور**\n\n"
        "برای حذف یک دارو از سفارش، روی آن کلیک کنید (علامت ✅ به ☑️ تغییر می‌کند).\n\n"
        "پس از اتمام تغییرات، دکمه '✅ تایید نهایی ویرایش' را بزنید.",
        reply_markup=keyboard
    )
    await callback.answer()  # برای حذف حالت لودینگ از روی دکم

# (هندلرهای handle_toggle_item، handle_reset_edit و handle_confirm_edit از پاسخ قبلی اینجا قرار می‌گیرند)
# ...

@patient_router.callback_query(PatientRegistration.editing_invoice, F.data == "confirm_invoice_edit")
async def handle_confirm_edit(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    # ... (کد این تابع از پاسخ قبلی)
    await callback.answer("در حال ارسال تغییرات...")
    data = await state.get_data()
    order_id = data.get("editing_order_id")
    current_cart = data.get("current_cart", [])

    # ساخت لیست نهایی برای ارسال به API (فقط آیتم‌های انتخاب شده)
    final_items_for_api = [
        {"drug_id": item["drug_id"], "qty": item["qty"]}
        for item in current_cart if item["selected"]
    ]

    if not final_items_for_api:
        await callback.message.answer(
            "شما تمام داروها را حذف کرده‌اید. برای لغو کامل سفارش لطفاً با پشتیبانی تماس بگیرید یا سفارش جدیدی ثبت کنید."
        )
        await state.clear()
        return

    # استفاده از تابع قدرتمند update_order
    updated_order = await api_client.update_order(
        order_id=order_id,
        order_items=final_items_for_api,
        order_status=OrderStatusEnum.CREATED.value  # وضعیت را به در انتظار پرداخت تغییر می‌دهیم
    )
    # پس از آپدیت موفق سفارش:
    if updated_order:
        await api_client.update_patient_status(str(callback.from_user.id), PatientStatus.PROFILE_COMPLETED.value)
        await callback.message.edit_text("ویرایش با موفقیت ثبت شد. در حال انتقال به مرحله ورود اطلاعات ارسال...")
        await state.clear()

        # شروع فرآیند دریافت اطلاعات ارسال
        await state.set_state(PatientShippingInfo.waiting_for_national_id)
        await callback.message.answer("لطفاً کد ملی خود را وارد کنید:")

# --------------------------------------------

@patient_router.callback_query(PatientRegistration.editing_invoice, F.data.startswith("toggle_item:"))
async def toggle_invoice_item(callback: CallbackQuery, state: FSMContext):
    """
    وضعیت انتخاب یک آیتم در فاکتور ویرایشی را تغییر می‌دهد (select/deselect).
    """
    try:
        # استخراج drug_id از callback_data
        drug_id_to_toggle = int(callback.data.split(":")[1])

        # خواندن سبد خرید فعلی از state
        data = await state.get_data()
        current_cart = data.get("current_cart", [])

        # پیدا کردن آیتم مورد نظر و تغییر وضعیت 'selected' آن
        item_found = False
        for item in current_cart:
            if item["drug_id"] == drug_id_to_toggle:
                item["selected"] = not item.get("selected", True)
                item_found = True
                break

        if not item_found:
            await callback.answer("خطا: این آیتم در سبد خرید شما یافت نشد!", show_alert=True)
            return

        # ذخیره سبد خرید به‌روز شده در state
        await state.update_data(current_cart=current_cart)

        # ساخت کیبورد جدید با اطلاعات به‌روز شده
        new_keyboard = get_interactive_invoice_keyboard(current_cart)

        # ویرایش پیام اصلی برای نمایش کیبورد جدید
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)

        # پاسخ به کلیک برای بستن انیمیشن لودینگ
        await callback.answer()

    except (ValueError, IndexError):
        await callback.answer("خطا در پردازش درخواست.", show_alert=True)
    except Exception as e:
        logging.error(f"Error in toggle_invoice_item: {e}", exc_info=True)
        await callback.answer("یک خطای غیرمنتظره رخ داد.", show_alert=True)


@patient_router.callback_query(PatientRegistration.editing_invoice, F.data == "reset_invoice_edit")
async def reset_invoice_edit(callback: CallbackQuery, state: FSMContext):
    """
    تغییرات اعمال شده در فاکتور را به حالت اولیه بازنشانی می‌کند.
    """
    data = await state.get_data()
    initial_cart = data.get("initial_cart", [])

    # کپی کردن سبد اولیه برای جلوگیری از تغییرات ناخواسته در آینده
    await state.update_data(current_cart=initial_cart.copy())

    new_keyboard = get_interactive_invoice_keyboard(initial_cart)
    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    await callback.answer("تغییرات بازنشانی شد.")


@patient_router.callback_query(PatientRegistration.editing_invoice, F.data == "confirm_invoice_edit")
async def confirm_invoice_edit(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """
    تغییرات نهایی فاکتور را تایید و با استفاده از اندپوینت جامع به API ارسال می‌کند.
    """
    await callback.answer("در حال ثبت تغییرات...")

    try:
        data = await state.get_data()
        order_id = data.get("editing_order_id")
        current_cart = data.get("current_cart", [])

        if not order_id:
            await callback.message.edit_text("خطا: شناسه سفارش یافت نشد. لطفاً فرآیند را از ابتدا شروع کنید.")
            await state.clear()
            return

        # استخراج آیتم‌هایی که انتخاب شده باقی مانده‌اند (به همراه drug_id و qty)
        final_items = [
            {"drug_id": item["drug_id"], "qty": item["qty"]}
            for item in current_cart if item.get("selected", True)
        ]

        if not final_items:
            await callback.message.edit_text(
                "شما نمی‌توانید یک سفارش خالی را تایید کنید. حداقل یک دارو باید انتخاب شود.")
            # کاربر را در حالت ویرایش نگه می‌داریم تا بتواند آیتمی را انتخاب کند.
            return

        # فراخوانی متد جدید API Client
        # در این مرحله وضعیت سفارش را تغییر نمی‌دهیم، پس پارامتر status را ارسال نمی‌کنیم.
        update_result = await api_client.update_order_comprehensively(
            order_id=order_id,
            items=final_items
        )

        if update_result:
            # پاک کردن state و خروج از حالت ویرایش
            await state.clear()

            await callback.message.edit_text(
                "✅ فاکتور شما با موفقیت ویرایش شد.\n"
                "لطفاً پیش‌فاکتور جدید را بررسی و در صورت تمایل، برای پرداخت اقدام کنید:",
                reply_markup=None  # کیبورد قبلی را پاک می‌کنیم
            )

            # واکشی patient_id از تلگرام آیدی کاربر برای نمایش فاکتور نهایی
            patient_response = await api_client.get_patient_details_by_telegram_id(callback.from_user.id)

            if patient_response:
                patient_id = patient_response.get("patient_id")
                orders = await api_client.get_orders_by_status(patient_id, OrderStatusEnum.CREATED.value)
                order_to_approve = orders[-1]

                await display_interactive_invoice(callback.message,state,order_to_approve)
            else:
                await callback.message.answer("خطا در بازیابی اطلاعات بیمار برای نمایش فاکتور نهایی.")

        else:
            await callback.message.edit_text(
                "❌ متاسفانه در هنگام ثبت تغییرات مشکلی پیش آمد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
            )
            # در صورت خطا، کاربر را در حالت ویرایش نگه می‌داریم تا دوباره تلاش کند.

    except Exception as e:
        logging.error(f"Critical error in confirm_invoice_edit: {e}", exc_info=True)
        await callback.message.answer("یک خطای داخلی در ربات رخ داده است. لطفاً مجدداً تلاش کنید.")
        await state.clear()

# =============================================================================
# 5. هندلرهای فرآیند دریافت اطلاعات ارسال (FSM: PatientShippingInfo)
# =============================================================================

@patient_router.message(PatientShippingInfo.waiting_for_national_id)
async def process_national_id(message: Message, state: FSMContext):
    national_id = message.text.strip()

    # بررسی صحت کد ملی
    def is_valid_national_id(code: str) -> bool:
        if not code.isdigit() or len(code) != 10:
            return False
        if len(set(code)) == 1:
            return False
        check = int(code[9])
        s = sum(int(code[i]) * (10 - i) for i in range(9)) % 11
        return (s < 2 and check == s) or (s >= 2 and check + s == 11)

    if not is_valid_national_id(national_id):
        await message.answer("❌ کد ملی وارد شده معتبر نیست. لطفاً دوباره وارد کنید (باید ۱۰ رقم باشد).")
        return
    # اعتبارسنجی کد ملی...
    await state.update_data(national_id=national_id)
    await state.set_state(PatientShippingInfo.waiting_for_phone_number)
    await message.answer("لطفاً شماره تماس خود را وارد کنید:\n"
                         "دقت داشته باشید که شماره تماس باید با 09 شروع شود:")


@patient_router.message(PatientShippingInfo.waiting_for_phone_number)
async def process_phone_number(message: Message, state: FSMContext):
    # اعتبارسنجی شماره...

    phone = message.text.strip()

    if not phone.isdigit() or not phone.startswith("09") or len(phone) != 11:
        await message.answer("❌ شماره تماس باید فقط شامل ۱۱ رقم و با 09 شروع شود. مثال: 09123456789")
        return

    await state.update_data(phone_number=phone)
    await state.set_state(PatientShippingInfo.waiting_for_address)
    await message.answer("لطفاً آدرس دقیق پستی خود را وارد کنید:")



@patient_router.message(PatientShippingInfo.waiting_for_address)
async def process_address(message: Message, state: FSMContext,bot:Bot, api_client: APIClient):
    """آخرین مرحله دریافت اطلاعات ارسال و ذخیره در دیتابیس."""
    await state.update_data(address=message.text)
    data = await state.get_data()
    telegram_id = message.from_user.id

    shipping_details = {
        "national_id": data.get("national_id"),
        "phone_number": data.get("phone_number"),
        "address": data.get("address")
    }

    # آپدیت اطلاعات بیمار در بک‌اند
    updated_patient = await api_client.update_patient(str(telegram_id), shipping_details)

    if updated_patient:
        # **تغییر وضعیت بیمار به پروفایل کامل شده**
        await api_client.update_patient_status(str(telegram_id), PatientStatus.AWAITING_PAYMENT.value)
        await message.answer(
            "✅ اطلاعات ارسال شما با موفقیت ثبت شد.\n"
            "حالا به مرحله پرداخت منتقل می‌شوید."
        )
        # فراخوانی تابع نمایش اطلاعات پرداخت
        await state.clear()
        # فراخوانی مجدد هندلر اصلی برای ورود به مرحله پرداخت
        await main_patient_handler(message, state, api_client, bot)
    else:
        await message.answer("خطایی در ذخیره اطلاعات رخ داد. لطفاً دوباره تلاش کنید.")
        await state.set_state(PatientShippingInfo.waiting_for_address)  # بازگشت به مرحله قبل


# =============================================================================
# 6. هندلرهای فرآیند دریافت اطلاعات پرداخت (FSM: PatientPaymentInfo)
# =============================================================================

@patient_router.message(PatientPaymentInfo.waiting_for_receipt_photo, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext, bot: Bot):

    if not message.photo:
        await message.answer("❌ لطفاً عکس رسید پرداخت را ارسال کنید. فقط فایل تصویر قابل قبول است.")
        return

    await message.answer("⏳ در حال ذخیره عکس رسید...")

    try:
        # گرفتن آخرین سایز تصویر (بیشترین وضوح)
        photo_file_id = message.photo[-1].file_id
        telegram_id = message.from_user.id

        # ✅ ذخیره در سرور (توابع کمکی خودت)
        saved_path = await save_telegram_photo(
            bot=bot,
            file_id=photo_file_id,
            telegram_id=telegram_id,
            purpose="receipt"
        )

        if not saved_path:
            await message.answer("❌ مشکلی در ذخیره عکس پیش آمد. لطفاً دوباره عکس را ارسال کنید.")
            return

        await state.update_data(receipt_photo_path=saved_path)
        await state.set_state(PatientPaymentInfo.waiting_for_amount)
        await message.answer("✅ عکس رسید دریافت شد.\n\nلطفاً مبلغ واریزی را به تومان وارد کنید:")

    except Exception as e:
        await message.answer("⚠️ هنگام پردازش عکس خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        import logging; logging.error(f"Error in process_receipt_photo: {e}", exc_info=True)

@patient_router.message(PatientPaymentInfo.waiting_for_amount)
async def process_payment_amount(message: Message, state: FSMContext):
    # اعتبارسنجی عدد بودن
    await state.update_data(amount=message.text)
    await state.set_state(PatientPaymentInfo.waiting_for_tracking_code)
    await message.answer("کد پیگیری پرداخت (در صورت وجود) را وارد کنید. اگر ندارد، بنویسید 'ندارد'.")


@patient_router.message(PatientPaymentInfo.waiting_for_tracking_code)
async def process_payment_tracking_code(message: Message, state: FSMContext, api_client: APIClient):
    await state.update_data(tracking_code=message.text)
    data = await state.get_data()
    receipt_path = data.get("receipt_photo_path")


    payment_payload = {
        "order_id": data.get("paying_order_id"),
        "payment_value": int(data.get("amount")),
        "payment_refer_code": data.get("tracking_code"),
        "payment_path_file": receipt_path
    }

    # ارسال اطلاعات به API برای ساخت رکورد پرداخت
    created_payment = await api_client.create_payment(payment_payload)


    if created_payment:
        await api_client.update_patient_status(str(message.from_user.id), PatientStatus.PAYMENT_COMPLETED.value)
        await message.answer(
            "✅ اطلاعات پرداخت شما با موفقیت ثبت شد و برای بررسی ارسال گردید.\n"
            "پس از تایید پرداخت توسط بخش مالی، سفارش شما ارسال خواهد شد."
        )
    else:
        await message.answer("❌ خطایی در ثبت اطلاعات پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید.")

    await state.clear()
