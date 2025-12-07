# app/casher/handlers.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import StateFilter, CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
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

from app.utils.invoice_generator import generate_complex_invoice
import datetime

casher_router = Router()
logger = logging.getLogger(__name__)


# ==============================================================================
# 0. هندلر شروع و ریست
# ==============================================================================
@casher_router.message(CommandStart())
@casher_router.message(Command("cancel"))
async def cmd_start_casher(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 سلام صندوقدار عزیز.\n"
        "وضعیت شما ریست شد. لطفاً برای شروع بررسی از دکمه زیر استفاده کنید:",
        reply_markup=get_main_menu_keyboard()
    )


# ==============================================================================
# 1. شروع پنل صندوقدار (نمایش تاریخ‌ها)
# ==============================================================================
@casher_router.callback_query(F.data == "start_box")
async def start_casher_panel(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """
    لیست تاریخ‌هایی که پرداخت بررسی نشده دارند را از سرور می‌گیرد.
    اصلاح شده: اگر پیام قبلی فایل بود، حذف می‌شود.
    """
    await state.clear()

    # --- اصلاح برای رفع ارور Bad Request ---
    if callback.message.document or callback.message.photo:
        await callback.message.delete()
        msg = await callback.message.answer("⏳ در حال دریافت لیست تاریخ‌های دارای تراکنش...")
    else:
        await callback.message.edit_text("⏳ در حال دریافت لیست تاریخ‌های دارای تراکنش...")
        msg = callback.message
    # ---------------------------------------

    dates_response = await api_client.get_pending_payment_dates()
    dates = dates_response if isinstance(dates_response, list) else []

    if not dates:
        # برای ادیت کردن باید مطمئن شویم پیام متنی است، که بالا هندل کردیم (msg)
        await msg.edit_text("✅ خسته نباشید! هیچ تراکنش جدیدی برای بررسی وجود ندارد.",
                            reply_markup=get_main_menu_keyboard())
        return

    keyboard = create_payment_dates_keyboard(dates)
    await msg.edit_text(
        "📅 لطفاً تاریخی که می‌خواهید تراکنش‌های آن را بررسی کنید انتخاب نمایید:",
        reply_markup=keyboard,
    )
    await state.set_state(CasherReview.choosing_date)


# ==============================================================================
# 2. نمایش لیست پرداخت‌های یک تاریخ خاص
# ==============================================================================
async def refresh_payment_list(message_obj: Message, state: FSMContext, api_client: APIClient, date: str):
    """
    این تابع کمکی، لیست پرداخت‌ها را برای یک تاریخ مجدداً از سرور می‌گیرد و نمایش می‌دهد.
    """
    await state.update_data(selected_date=date)

    payments = await api_client.get_pending_payments_by_date(date)

    if not payments:
        await message_obj.edit_text(f"✅ تمام تراکنش‌های تاریخ {date} بررسی شدند.")
        # بازگشت به صفحه اصلی
        await start_casher_panel_from_message(message_obj, state, api_client)
        return

    await state.update_data(pending_payments=payments)

    keyboard = create_pending_payments_keyboard(payments)
    await message_obj.edit_text(
        f"📂 **تراکنش‌های تاریخ {date}**\n\n"
        f"تعداد در انتظار: {len(payments)} مورد\n"
        f"لطفاً یک مورد را جهت بررسی انتخاب کنید:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(CasherReview.choosing_payment)


# اصلاح: حذف فیلتر استیت برای اینکه دکمه 'نفر بعدی' کار کند
@casher_router.callback_query(F.data.startswith("casher_date_"))
async def process_date_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    date = callback.data.split("_")[-1]

    # --- اصلاح برای رفع ارور Bad Request (زمانی که از صفحه فاکتور برمی‌گردیم) ---
    if callback.message.document or callback.message.photo:
        await callback.message.delete()
        msg = await callback.message.answer(f"⏳ در حال بارگذاری لیست {date}...")
    else:
        await callback.message.edit_text(f"⏳ در حال بارگذاری لیست {date}...")
        msg = callback.message
    # ---------------------------------------------------------------------------

    await refresh_payment_list(msg, state, api_client, date)
    await callback.answer()


# ==============================================================================
# 3. نمایش جزئیات یک پرداخت
# ==============================================================================
# در handlers.py جایگزین تابع process_payment_choice قبلی کنید

@casher_router.callback_query(CasherReview.choosing_payment, F.data.startswith("casher_payment_"))
async def process_payment_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """
    نمایش جزئیات پرداخت.
    اصلاحیه: دریافت اطلاعات تکمیلی کاربر (نام و تلگرام آیدی) از سرور در لحظه کلیک.
    """
    try:
        payment_list_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("شناسه نامعتبر.")
        return

    data = await state.get_data()
    payments = data.get("pending_payments", [])

    # پیدا کردن پرداخت در لیست موجود
    selected_payment = next((p for p in payments if p.get("payment_list_id") == payment_list_id), None)

    if not selected_payment:
        await callback.answer("اطلاعات قدیمی شده، لیست رفرش می‌شود...")
        current_date = data.get("selected_date")
        if current_date:
            await refresh_payment_list(callback.message, state, api_client, current_date)
        else:
            await start_casher_panel(callback, state, api_client)
        return

    # ==========================================================================
    #  شروع اصلاحیه: تکمیل اطلاعات ناقص (نام و تلگرام آیدی)
    # ==========================================================================
    await callback.answer("⏳ در حال دریافت جزئیات...")

    # 1. استخراج شناسه کاربر از پرداخت
    user_db_id = selected_payment.get("patient_id")

    # 2. دریافت اطلاعات کامل کاربر از سرور
    if user_db_id:
        try:
            # فرض بر این است که این متد در API_Client وجود دارد (در پایین توضیح داده شده)
            user_info = await api_client.get_user_details_by_id(user_db_id)

            if user_info:
                # استخراج نام

                full_name = user_info.get("full_name").strip() or "کاربر بدون نام"


                # استخراج تلگرام آیدی (با چک کردن کلیدهای مختلف)
                tg_id = user_info.get("user_telegram_id") or user_info.get("telegram_id") or user_info.get("id")

                # بروزرسانی دیکشنری selected_payment با اطلاعات جدید
                selected_payment["full_name"] = full_name
                selected_payment["telegram_id"] = tg_id

                # لاگ برای اطمینان
                logging.info(f"User Details Fetched: Name={full_name}, TG_ID={tg_id}")
        except Exception as e:
            logging.error(f"Error fetching user details for ID {user_db_id}: {e}")

    # ذخیره مجدد در State (تا در مرحله تایید/رد دسترسی داشته باشیم)
    await state.update_data(current_payment=selected_payment)
    # ==========================================================================

    # نمایش اطلاعات به صندوقدار
    full_name = selected_payment.get('full_name') or "نامشخص"
    telegram_id = selected_payment.get('telegram_id') or "نامشخص"

    # هندل کردن قیمت (رفع مشکل نمایش None)
    raw_price = selected_payment.get('payment_value') or selected_payment.get('amount') or 0
    try:
        price_val = int(float(raw_price))
        price_str = f"{price_val:,}"
    except (ValueError, TypeError):
        price_str = "0"

    info_text = (
        f"🔍 **بررسی تراکنش**\n\n"
        f"👤 **نام بیمار:** {full_name}\n"
        f"🆔 **آیدی تلگرام:** `{telegram_id}`\n"
        f"💰 **مبلغ:** `{price_str} ریال`\n"
        f"📅 **تاریخ:** `{data.get('selected_date')}`\n"
        f"🔖 **کد پیگیری:** `{selected_payment.get('payment_refer_code') or '---'}`"
    )

    await callback.message.delete()

    receipt_photo_path = selected_payment.get("payment_path_file")
    keyboard = create_payment_verification_keyboard(payment_list_id)

    sent = False
    if receipt_photo_path:
        try:
            await callback.message.answer_photo(
                photo=FSInputFile(receipt_photo_path),
                caption=info_text,
                parse_mode='Markdown',
                reply_markup=keyboard,
            )
            sent = True
        except Exception as e:
            logger.error(f"Failed to send local photo: {e}")

    if not sent:
        await callback.message.answer(
            f"{info_text}\n\n⚠️ **تصویر رسید یافت نشد (فایل حذف شده یا مسیر اشتباه است).**",
            parse_mode='Markdown',
            reply_markup=keyboard,
        )

    await state.set_state(CasherReview.verifying_payment)


# ==============================================================================
# 4. تایید پرداخت (و صدور فاکتور)
# ==============================================================================
@casher_router.callback_query(CasherReview.verifying_payment, F.data.startswith("approve_payment_"))
async def process_approve_payment(callback: CallbackQuery, state: FSMContext, api_client: APIClient, bot: Bot):
    # 1. استخراج ID پرداخت
    payment_parts = callback.data.split("_")
    payment_list_id = int(payment_parts[-1])

    data = await state.get_data()
    current_payment = data.get("current_payment", {})

    patient_tg_id = current_payment.get("telegram_id")
    order_id = current_payment.get("order_id")

    # 2. شناسایی ایمن صندوق‌دار
    casher_telegram_id = callback.from_user.id
    casher_profile = await api_client.get_user_details_by_telegram_id(casher_telegram_id)

    casher_db_id = 1
    casher_name = "صندوق‌دار"

    if casher_profile:
        casher_db_id = casher_profile.get("user_id") or casher_profile.get("id") or 1
        casher_name = casher_profile.get('full_name', '')

    casher_db_id = int(casher_db_id)

    # 3. نمایش پیام لودینگ (هوشمند)
    loading_msg = f"⏳ پرداخت تایید شد (توسط {casher_name}).\n📄 در حال صدور فاکتور PDF..."

    try:
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(caption=loading_msg)
        else:
            await callback.message.edit_text(text=loading_msg)
    except Exception as e:
        await callback.message.answer(loading_msg)

    # 4. ارسال درخواست تایید به API
    payload = {"payment_status": "Accepted", "user_id": casher_db_id}
    update_result = await api_client.update_payment(payment_list_id, payload)

    if update_result:
        try:
            # الف) چک کردن وجود Order ID
            if not order_id:
                await callback.message.answer("✅ پرداخت تایید شد، اما شماره سفارش یافت نشد.")
                return

            # ب) دریافت اطلاعات
            order_data = await api_client.get_order_by_id(order_id)
            if not order_data:
                raise ValueError(f"Order data not found for ID {order_id}")

            patient_details = await api_client.get_patient_details_by_telegram_id(patient_tg_id)

            consultant_name = "ناشناس"
            consultant_id = order_data.get("user_id")
            if consultant_id:
                c_info = await api_client.get_user_details_by_id(consultant_id)
                if c_info:
                    consultant_name = c_info.get('full_name', '')

            # پ) پردازش اقلام
            raw_items = order_data.get("order_list", [])
            invoice_items = []

            for item in raw_items:
                # دسترسی به آبجکت تودرتوی دارو
                drug_obj = item.get("drug", {})

                # 1. استخراج نام دارو (اولویت با نام فارسی، سپس انگلیسی)
                d_name = drug_obj.get("drug_pname") or drug_obj.get("drug_lname") or f"دارو کد {item.get('drug_id')}"

                # 2. استخراج تعداد (در جیسون شما qty است)
                try:
                    count = int(item.get("qty", 1))
                except:
                    count = 1

                # 3. استخراج قیمت (فرمت علمی مثل 2.50E+6 را هندل میکنیم)
                raw_price = item.get("price", 0)
                try:
                    # تبدیل رشته علمی به float و سپس int
                    unit_price = int(float(raw_price))
                except (ValueError, TypeError):
                    unit_price = 0

                total_row = count * unit_price

                invoice_items.append({
                    "name": d_name,
                    "count": count,
                    "unit_price": unit_price,
                    "total_price": total_row
                })



            today_str = datetime.datetime.now().strftime("%Y/%m/%d")

            invoice_context = {
                "invoice_date": today_str,
                "invoice_number": str(order_id),
                "payment_date": today_str,
                "seller_info": {
                    "name": "داروخانه دکتر فاضل",
                    "address": "تهران",
                    "phone": "021-00000000"
                },
                "buyer_info": {
                    "name": current_payment.get("full_name", "مهمان"),
                    "address": patient_details.get("address", "---") if patient_details else "---",
                    "phone": patient_details.get("mobile_number", str(patient_tg_id)) if patient_details else str(
                        patient_tg_id)
                },
                "consultant_name": consultant_name,
                "cashier_name": casher_name,
                "items": invoice_items,
                "final_total_price": int(float(current_payment.get("payment_value", 0)))
            }

            pdf_buffer = generate_complex_invoice(invoice_context)
            pdf_file = BufferedInputFile(pdf_buffer.getvalue(), filename=f"Invoice_{order_id}.pdf")

            # حذف پیام لودینگ قبلی (چون عکس/کپشن بود و الان می‌خواهیم فایل جدید بفرستیم)
            await callback.message.delete()

            await callback.message.answer_document(
                document=pdf_file,
                caption=f"✅ فاکتور سفارش **#{order_id}** صادر شد.",
                reply_markup=create_after_action_keyboard(data.get("selected_date"))
            )

            if patient_tg_id:
                try:
                    await bot.send_message(
                        patient_tg_id,
                        "✅ پرداخت شما تایید شد و فاکتور نهایی صادر گردید.\nسفارش شما در نوبت ارسال قرار گرفت."
                    )
                except Exception:
                    pass
                try:
                    # ساخت پیام جمع‌بندی
                    how_to_use_text = "💊 **نحوه مصرف داروهای شما:**\n\n"

                    for item in raw_items:
                        drug_obj = item.get("drug", {})
                        d_name = drug_obj.get("drug_pname") or "دارو نامشخص"
                        how_use = drug_obj.get("drug_how_to_use")

                        if how_use:
                            how_to_use_text += f"• **{d_name}:**\n{how_use}\n\n"
                        else:
                            how_to_use_text += f"• {d_name}: (اطلاعات نحوه مصرف ثبت نشده است)\n\n"

                    # ارسال به بیمار
                    await bot.send_message(
                        patient_tg_id,
                        how_to_use_text,
                        parse_mode="Markdown"
                    )

                except Exception as e:
                    logger.error(f"Failed to send drug how-to-use instructions: {e}")

        except Exception as e:
            logging.error(f"Invoice generation error: {e}", exc_info=True)
            await callback.message.answer(
                f"⚠️ پرداخت تایید شد اما در صدور فاکتور خطایی رخ داد:\n`{e}`",
                reply_markup=create_after_action_keyboard(data.get("selected_date"))
            )

    else:
        await callback.message.answer("❌ خطا در ثبت تایید پرداخت در دیتابیس.")

    await callback.answer()


# ==============================================================================
# 5. رد پرداخت
# ==============================================================================
@casher_router.callback_query(CasherReview.verifying_payment, F.data.startswith("reject_payment_"))
async def process_reject_payment_start(callback: CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[-1])
    await state.update_data(current_payment_id_to_reject=payment_id)

    await callback.message.delete()
    await callback.message.answer(
        "❌ لطفاً **دلیل رد کردن** را بنویسید:",
        reply_markup=create_rejection_back_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(CasherReview.entering_rejection_reason)
    await callback.answer()


@casher_router.message(CasherReview.entering_rejection_reason, F.text)
async def process_rejection_reason(message: Message, state: FSMContext, api_client: APIClient, bot: Bot):
    reason = message.text
    casher_id = message.from_user.id

    user_info = await api_client.get_user_details_by_telegram_id(casher_id)
    if not user_info:
        await message.answer("خطای دسترسی کاربر.")
        return

    data = await state.get_data()
    payment_id = data.get("current_payment_id_to_reject")

    payload = {
        "payment_status": "Rejected",
        "payment_status_explain": reason,
        "user_id": int(user_info.get('user_id') or 1),
    }

    wait = await message.answer("⏳ در حال ثبت رد...")
    result = await api_client.update_payment(payment_id, payload)

    if result:
        current_payment = data.get("current_payment", {})
        patient_tid = current_payment.get("telegram_id")
        if patient_tid:
            try:
                await bot.send_message(
                    patient_tid,
                    f"❌ پرداخت شما تایید نشد.\nعلت: {reason}"
                )
            except:
                pass

        await wait.delete()
        temp_msg = await message.answer("❌ رد شد. بروزرسانی لیست...")
        await refresh_payment_list(temp_msg, state, api_client, data.get("selected_date"))
    else:
        await wait.edit_text("خطا در انجام عملیات.")


# ==============================================================================
# 6. دکمه‌های بازگشت
# ==============================================================================
@casher_router.callback_query(F.data == "casher_back_to_dates")
async def back_to_dates(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    # چون ممکن است روی دکمه زیر PDF کلیک شده باشد، تابع start_casher_panel
    # به صورت خودکار (با اصلاحات انجام شده) پیام فایل را حذف می‌کند.
    await start_casher_panel(callback, state, api_client)


@casher_router.callback_query(F.data == "casher_back_to_list")
async def back_to_list(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    data = await state.get_data()

    # اصلاح: حذف پیام عکس/فایل قبلی
    await callback.message.delete()
    temp = await callback.message.answer("🔄 بازگشت به لیست...")

    await refresh_payment_list(temp, state, api_client, data.get("selected_date"))


@casher_router.callback_query(F.data == "cancel_rejection")
async def cancel_rejection(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    await back_to_list(callback, state, api_client)


async def start_casher_panel_from_message(message: Message, state: FSMContext, api_client: APIClient):
    await state.clear()
    dates_resp = await api_client.get_pending_payment_dates()
    dates = dates_resp if isinstance(dates_resp, list) else []

    if not dates:
        await message.answer("✅ همه پردازش شده‌اند.", reply_markup=get_main_menu_keyboard())
        return

    keyboard = create_payment_dates_keyboard(dates)
    await message.answer("📅 انتخاب تاریخ:", reply_markup=keyboard)
    await state.set_state(CasherReview.choosing_date)


@casher_router.message(StateFilter(default_state))
async def handle_unknown(message: Message, state: FSMContext):
    await message.answer("دستور نامعتبر. از منو استفاده کنید:", reply_markup=get_main_menu_keyboard())
