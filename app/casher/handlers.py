# app/casher/handlers.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.state import default_state
from app.core.API_Client import APIClient
from .states import CasherReview
from .keyboards import (
    create_payment_dates_keyboard,
    create_pending_payments_keyboard,
    create_payment_verification_keyboard,
    create_rejection_back_keyboard,
    create_after_action_keyboard,
    get_main_menu_keyboard,
)

casher_router = Router()
logger = logging.getLogger(__name__)


# --- مرحله ۱: شروع فرآیند با دستور /casher_panel ---
@casher_router.callback_query(CasherReview.main_menu,F.data == "start_box")
async def start_casher_panel(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    await state.clear()
    await callback.message.answer("در حال دریافت لیست تاریخ‌های نیازمند بررسی پرداخت...")

    dates_response = await api_client.get_pending_payment_dates()
    dates = dates_response if isinstance(dates_response, list) else []

    if not dates:
        await callback.message.answer("✅ در حال حاضر هیچ پرداخت جدیدی برای بررسی وجود ندارد.")
        return

    keyboard = create_payment_dates_keyboard(dates)
    await callback.message.answer(
        "📅 لطفاً تاریخی که می‌خواهید پرداخت‌های آن را بررسی کنید، انتخاب نمایید:",
        reply_markup=keyboard,
    )
    await state.set_state(CasherReview.choosing_date)


# --- مرحله ۲: انتخاب تاریخ و نمایش لیست پرداخت‌ها ---
@casher_router.callback_query(CasherReview.choosing_date, F.data.startswith("casher_date_"))
async def process_date_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    date = callback.data.split("_")[-1]
    await state.update_data(selected_date=date)

    await callback.message.edit_text(f"⏳ در حال دریافت لیست پرداخت‌های تاریخ {date}...")

    payments = await api_client.get_pending_payments_by_date(date)
    if not payments:
        await callback.message.edit_text(f"برای تاریخ {date} پرداخت در انتظار بررسی یافت نشد.")
        # بازگشت به منوی اصلی تاریخ ها
        await start_casher_panel(callback.message, state, api_client)
        await callback.answer()
        return

    await state.update_data(pending_payments=payments)

    keyboard = create_pending_payments_keyboard(payments)
    await callback.message.edit_text(
        f"👥 لیست پرداخت‌های ثبت شده در تاریخ {date}:\nلطفاً بیمار مورد نظر را برای بررسی انتخاب کنید.",
        reply_markup=keyboard,
    )
    await state.set_state(CasherReview.choosing_payment)
    await callback.answer()


# --- مرحله ۳: انتخاب پرداخت و نمایش جزئیات ---
@casher_router.callback_query(CasherReview.choosing_payment, F.data.startswith("casher_payment_"))
async def process_payment_choice(callback: CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    payments = data.get("pending_payments", [])

    selected_payment = next((p for p in payments if p.get("payment_list_id") == payment_id), None)

    if not selected_payment:
        await callback.message.edit_text("خطا: اطلاعات این پرداخت یافت نشد. لطفاً دوباره تلاش کنید.")
        await callback.answer(show_alert=True)
        return

    await state.update_data(current_payment=selected_payment)

    info_text = (
        f"🔍 **بررسی پرداخت بیمار: {selected_payment.get('full_name')}**\n\n"
        f"🆔 شناسه تلگرام بیمار: `{selected_payment.get('telegram_id')}`\n"
        f"💵 مبلغ فاکتور: `{int(selected_payment.get('payment_value', 0)):,} ریال`\n"
        f"🗓️ تاریخ ثبت: `{data.get('selected_date')}`"
    )

    await callback.message.delete()
    receipt_photo_path = selected_payment.get("payment_path_file")
    keyboard = create_payment_verification_keyboard(payment_id)

    if receipt_photo_path:
        try:
            await callback.message.answer_photo(
                photo=FSInputFile(receipt_photo_path),
                caption=info_text,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Failed to send receipt photo from path {receipt_photo_path}: {e}")
            await callback.message.answer(
                f"{info_text}\n\n⚠️ **خطا در بارگذاری تصویر رسید!**",
                parse_mode='HTML',
                reply_markup=keyboard,
            )
    else:
        await callback.message.answer(
            f"{info_text}\n\n**هشدار: این پرداخت فاقد تصویر رسید است!**",
            parse_mode='HTML',
            reply_markup=keyboard,
        )

    await state.set_state(CasherReview.verifying_payment)
    await callback.answer()


# --- مرحله ۴-الف: تایید پرداخت ---
@casher_router.callback_query(CasherReview.verifying_payment, F.data.startswith("approve_payment_"))
async def process_approve_payment(callback: CallbackQuery, state: FSMContext, api_client: APIClient, bot: Bot):
    """پرداخت را تایید کرده و به بیمار و صندوق‌دار اطلاع می‌دهد."""
    payment_id = int(callback.data.split("_")[-1])

    casher_telegram_id = callback.from_user.id
    casher_profile = await api_client.get_user_details_by_telegram_id(casher_telegram_id)
    if not casher_profile or "user_id" not in casher_profile:
        await callback.answer("خطا: اطلاعات شما در سیستم یافت نشد.", show_alert=True)
        return
    casher_user_id = casher_profile["user_id"]

    data = await state.get_data()
    current_payment = data.get("current_payment")
    patient_telegram_id = current_payment.get("telegram_id")

    payload = {"payment_status": "ACCEPTED", "user_id": casher_user_id}

    # ==================== اصلاحیه اصلی اینجاست ====================
    # 1. گرفتن متن اصلی، چه از کپشن باشد چه از متن پیام
    original_text = callback.message.caption or callback.message.text
    loading_text = f"{original_text}\n\n⏳ **در حال تایید پرداخت...**"

    # 2. ویرایش پیام بر اساس نوع آن (عکس یا متن)
    if callback.message.photo:
        await callback.message.edit_caption(caption=loading_text, parse_mode="Markdown")
    else:
        await callback.message.edit_text(loading_text, parse_mode="Markdown")
    # =============================================================

    result = await api_client.update_payment(payment_id, payload)

    if result:
        final_text = f"✅ پرداخت بیمار **{current_payment.get('full_name')}** با موفقیت تایید شد."

        # ==================== اصلاحیه برای ویرایش نهایی ====================
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=final_text,
                parse_mode="Markdown",
                reply_markup=create_after_action_keyboard(data.get("selected_date"))
            )
        else:
            await callback.message.edit_text(
                text=final_text,
                parse_mode="Markdown",
                reply_markup=create_after_action_keyboard(data.get("selected_date"))
            )
        # =============================================================

        try:
            await bot.send_message(patient_telegram_id,
                                   "✅ پرداخت شما با موفقیت تایید شد. سفارش شما به زودی ارسال خواهد شد.")
        except Exception as e:
            logger.error(f"Failed to send approval message to {patient_telegram_id}: {e}")
    else:
        # در صورت خطا، پیام جدیدی ارسال می‌کنیم تا کاربر متوجه شود
        await callback.message.answer("❌ خطایی در تایید پرداخت رخ داد. لطفاً دوباره تلاش کنید.")

    await state.set_state(CasherReview.choosing_payment)  # بازگشت به حالت انتخاب پرداخت برای نفر بعدی
    await callback.answer()


# --- مرحله ۴-ب: شروع فرآیند رد پرداخت ---
@casher_router.callback_query(CasherReview.verifying_payment, F.data.startswith("reject_payment_"))
async def process_reject_payment_start(callback: CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[-1])
    await state.update_data(current_payment_id_to_reject=payment_id)

    await callback.message.delete()
    await callback.message.answer(
        "لطفاً دلیل رد شدن این پرداخت را در یک پیام بنویسید:",
        reply_markup=create_rejection_back_keyboard()
    )
    await state.set_state(CasherReview.entering_rejection_reason)
    await callback.answer()


# --- مرحله ۵: دریافت دلیل رد و ارسال به API ---
@casher_router.message(CasherReview.entering_rejection_reason, F.text)
async def process_rejection_reason(message: Message, state: FSMContext, api_client: APIClient, bot: Bot):
    rejection_reason = message.text

    # واکشی اطلاعات صندوق‌دار از API
    casher_telegram_id = message.from_user.id
    casher_profile = await api_client.get_user_details_by_telegram_id(casher_telegram_id)
    if not casher_profile or "user_id" not in casher_profile:
        await message.answer("خطا: اطلاعات شما در سیستم یافت نشد.")
        return
    casher_user_id = casher_profile["user_id"]

    data = await state.get_data()
    payment_id = data.get("current_payment_id_to_reject")
    current_payment = data.get("current_payment")
    patient_telegram_id = current_payment.get("telegram_id")

    payload = {
        "payment_status": "REJECTED",
        "payment_status_explain": rejection_reason,
        "user_id": casher_user_id,
    }

    await message.answer("⏳ در حال ثبت دلیل و رد کردن پرداخت...")

    result = await api_client.update_payment(payment_id, payload)

    if result:
        await message.answer(
            f"❌ پرداخت بیمار **{current_payment.get('full_name')}** با موفقیت رد شد.",
            parse_mode="Markdown",
            reply_markup=create_after_action_keyboard(data.get("selected_date"))
        )
        try:
            await bot.send_message(
                patient_telegram_id,
                f"⚠️ متاسفانه پرداخت شما رد شد.\n\n**دلیل:** {rejection_reason}\n\nلطفاً مشکل را برطرف کرده و مجدداً اقدام به پرداخت نمایید.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send rejection message to {patient_telegram_id}: {e}")
    else:
        await message.answer("❌ خطایی در فرآیند رد کردن پرداخت رخ داد.")

    await state.set_state(CasherReview.choosing_payment)


# --- هندلرهای بازگشت (Back) ---
# (این بخش بدون تغییر باقی می‌ماند)


# --- هندلرهای بازگشت (Back) ---
@casher_router.callback_query(F.data == "casher_back_to_dates")
async def back_to_dates(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """از لیست بیماران به لیست تاریخ‌ها برمی‌گردد."""
    await start_casher_panel(callback, state, api_client)
    await callback.answer()


@casher_router.callback_query(CasherReview.verifying_payment, F.data == "casher_back_to_list")
async def back_to_patient_list(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """از صفحه جزئیات پرداخت به لیست بیماران برمی‌گردد."""
    data = await state.get_data()
    # ما از قبل در FSM state داریم که در چه تاریخی هستیم
    # پس می‌توانیم دوباره آن را فراخوانی کنیم
    await callback.message.delete()  # حذف پیام عکس
    await process_date_choice(callback, state, api_client)


@casher_router.callback_query(CasherReview.entering_rejection_reason, F.data == "cancel_rejection")
async def cancel_rejection_process(callback: CallbackQuery, state: FSMContext):
    """فرآیند وارد کردن دلیل رد را لغو می‌کند و به جزئیات پرداخت برمی‌گردد."""
    await callback.message.delete()
    await process_payment_choice(callback, state)


@casher_router.message(StateFilter(default_state), F.text)
async def handle_any_text(message: Message, state: FSMContext):

    """
    این هندلر به هر پیام متنی در حالت پیش‌فرض (وقتی کاربر در حال انجام کاری نیست)
    پاسخ می‌دهد و منوی اصلی را نمایش می‌دهد.
    """
    await state.set_state(CasherReview.main_menu)

    await message.answer(
        "به پنل مشاوران خوش آمدید. لطفاً از منوی زیر برای شروع کار استفاده کنید:",
        reply_markup=get_main_menu_keyboard()
    )