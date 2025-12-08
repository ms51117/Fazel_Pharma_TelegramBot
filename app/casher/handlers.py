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
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, InputMediaPhoto

from ..core.enums import PatientStatus
from ..utils.date_helper import to_jalali

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
    jalali_text = to_jalali(date, include_time=False)

    if not payments:
        await message_obj.edit_text(f"✅ تمام تراکنش‌های تاریخ {jalali_text} بررسی شدند.")
        # بازگشت به صفحه اصلی
        await start_casher_panel_from_message(message_obj, state, api_client)
        return

    await state.update_data(pending_payments=payments)

    keyboard = create_pending_payments_keyboard(payments)
    await message_obj.edit_text(
        f"📂 **تراکنش‌های تاریخ {jalali_text}**\n\n"
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
    نسخه جدید: نمایش آلبوم تمام رسیدها + دریافت صحیح نام بیمار
    """
    # 1. دریافت شناسه پرداخت انتخابی
    try:
        payment_list_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("شناسه نامعتبر.")
        return

    await callback.answer("⏳ دریافت اطلاعات کامل...")

    # 2. دریافت اطلاعات دقیق پرداخت از API
    current_payment = await api_client.get_payment_by_id(payment_list_id)
    if not current_payment:
        # فال‌بک به حافظه اگر API جواب نداد
        data = await state.get_data()
        payments = data.get("pending_payments", [])
        current_payment = next((p for p in payments if int(p.get("payment_list_id")) == payment_list_id), None)

    if not current_payment:
        await callback.message.answer("اطلاعات پرداخت یافت نشد.")
        return

    order_id = current_payment.get("order_id")
    order_info = await api_client.get_order_by_id(order_id)

    if not order_info :
        await callback.message.answer("اطلاعات سفارش یافت نشد.")

    patient_id = order_info.get("patient_id")

    # 3. دریافت اطلاعات بیمار (حل مشکل نام و تلگرام آیدی)
    patient_name = "ناشناس"
    patient_tg_id = "---"

    if patient_id:
        # فراخوانی متد جدیدی که اضافه کردیم
        patient_info = await api_client.get_patient_by_id(patient_id)
        if patient_info:
            patient_name = patient_info.get("full_name") or "بدون نام"
            patient_tg_id = patient_info.get("user_telegram_id") or patient_info.get("telegram_id") or "---"

            # آپدیت کردن آبجکت پرداخت با اطلاعات دقیق برای مراحل بعد (مثل رد کردن)
            current_payment["full_name"] = patient_name
            current_payment["telegram_id"] = patient_tg_id

    # 4. دریافت تمام پرداختی‌های این سفارش (برای گالری عکس و تاریخچه)
    all_payments = []
    if order_id:
        all_payments = await api_client.get_all_payments_by_order_id(order_id)
        # مرتب‌سازی: قدیمی‌ترین اول باشد
        if all_payments:
            all_payments.sort(key=lambda x: x.get('created_at', ''), reverse=False)

    # 5. محاسبات مالی
    total_order_price = 0
    paid_approved = 0

    if order_id:
        order_details = await api_client.get_order_by_id(order_id)
        if order_details:
            for item in order_details.get("order_list", []):
                try:
                    total_order_price += int(float(item.get("price", 0))) * int(item.get("qty", 1))
                except:
                    pass

    # ساخت لیست مدیا (عکس‌ها) و متن تاریخچه
    media_group = []
    history_text = "\n📋 **سابقه تراکنش‌ها (به ترتیب عکس‌ها):**\n"

    counter = 1
    has_current_receipt_photo = False

    if all_payments:
        for p in all_payments:
            # استخراج داده‌ها
            try:
                p_val = int(float(p.get('payment_value', 0)))
            except:
                p_val = 0

            p_status = p.get('payment_status')
            p_date = to_jalali(p.get('created_at'), include_time=False)
            p_path = p.get('payment_path_file')
            p_id = int(p.get('payment_list_id'))

            if p_status == "Accepted":
                paid_approved += p_val
                status_icon = "✅ تایید شده"
            elif p_status == "Rejected":
                status_icon = "❌ رد شده"
            else:
                status_icon = "⏳ در انتظار"

            # علامت‌گذاری رسید فعلی
            is_current = "👈 **(این رسید)**" if p_id == payment_list_id else ""

            # افزودن به متن تاریخچه
            history_text += f"{counter}. {status_icon} | مبلغ: `{p_val:,}` | {p_date} {is_current}\n"

            # افزودن به آلبوم عکس (اگر فایل دارد)
            if p_path:
                try:
                    # کپشن برای هر عکس (فقط در برخی کلاینت‌ها نمایش داده می‌شود، اما بودنش خوب است)
                    caption_part = f"رسید #{counter} - {status_icon} - مبلغ: {p_val:,}"
                    media_group.append(InputMediaPhoto(media=FSInputFile(p_path), caption=caption_part))

                    if p_id == payment_list_id:
                        has_current_receipt_photo = True
                except Exception as e:
                    logging.error(f"Error adding photo to album: {p_path} - {e}")

            counter += 1
    else:
        # اگر لیست خالی بود، حداقل اطلاعات پرداخت فعلی را اضافه کن
        history_text = "⚠️ سوابق یافت نشد."
        path = current_payment.get("payment_path_file")
        if path:
            media_group.append(InputMediaPhoto(media=FSInputFile(path), caption="رسید فعلی"))
            has_current_receipt_photo = True

    # 6. نمایش خروجی

    # حذف پیام قبلی (لیست دکمه‌ها) برای تمیز شدن صفحه
    await callback.message.delete()

    # الف) ارسال آلبوم عکس‌ها (اگر عکسی موجود است)
    if media_group:
        try:
            await callback.message.answer_media_group(media=media_group)
        except Exception as e:
            await callback.message.answer(f"⚠️ خطا در نمایش عکس‌ها: فایل‌ها در سرور موجود نیستند.\n{e}")
    else:
        await callback.message.answer("🖼 **هیچ عکس رسیدی برای این سفارش یافت نشد!**")

    # ب) ارسال متن جزئیات + دکمه‌های عملیات (در یک پیام جداگانه زیر عکس‌ها)
    try:
        current_amount = int(float(current_payment.get("payment_value", 0)))
    except:
        current_amount = 0

    remaining = total_order_price - paid_approved

    info_text = (
        f"👤 **بیمار:** {patient_name}\n"
        f"🆔 **آیدی:** `{patient_tg_id}`\n"
        f"🔢 **شماره سفارش:** `{order_id}`\n"
        "------------------------------\n"
        f"💰 **کل سفارش:** `{total_order_price:,}`\n"
        f"💵 **پرداخت شده (تایید شده):** `{paid_approved:,}`\n"
        f"📊 **مانده حساب:** `{remaining:,}`\n"
        "------------------------------\n"
        f"🖼 **مبلغ این رسید (در حال بررسی):** `{current_amount:,}` تومان\n"
        f"{history_text}"
    )

    # ذخیره در state
    await state.update_data(current_payment=current_payment)

    # کیبورد عملیات (تایید / رد)
    keyboard = create_payment_verification_keyboard(payment_list_id)

    await callback.message.answer(
        text=info_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
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
            jalali_text = to_jalali(today_str, include_time=False)

            invoice_context = {
                "invoice_date": jalali_text,
                "invoice_number": str(order_id),
                "payment_date": jalali_text,
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
# 1. شروع فرآیند رد کردن
@casher_router.callback_query(CasherReview.verifying_payment, F.data.startswith("reject_payment_"))
async def process_reject_payment_start(callback: CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[-1])
    # ذخیره آیدی پرداخت
    await state.update_data(current_payment_id_to_reject=payment_id)

    await callback.message.delete()
    await callback.message.answer(
        "❌ **قدم اول:**\nلطفاً **دلیل رد کردن** این رسید را بنویسید (این متن برای کاربر ارسال می‌شود):",
        reply_markup=create_rejection_back_keyboard(),
        parse_mode="Markdown"
    )
    # رفتن به وضعیت دریافت دلیل
    await state.set_state(CasherReview.entering_rejection_reason)
    await callback.answer()


# 2. دریافت دلیل و پرسش مبلغ واقعی
@casher_router.message(CasherReview.entering_rejection_reason, F.text)
async def process_rejection_reason(message: Message, state: FSMContext):
    reason = message.text
    # ذخیره دلیل در State
    await state.update_data(reject_reason=reason)

    # حالا مبلغ صحیح را می‌پرسیم
    await message.answer(
        "💰 **قدم دوم:**\n"
        "لطفاً **مبلغ واقعی** که در عکس رسید مشاهده می‌کنید را به تومان وارد کنید.\n"
        "(این مبلغ جایگزین مبلغی می‌شود که کاربر وارد کرده بود).\n\n"
        "اگر مبلغ در عکس ناخوانا است یا رسید نامعتبر است، عدد 0 را وارد کنید.",
        reply_markup=create_rejection_back_keyboard()
    )
    # رفتن به وضعیت دریافت مبلغ واقعی
    await state.set_state(CasherReview.entering_real_amount)


# 3. دریافت مبلغ واقعی و اعمال تغییرات در دیتابیس
@casher_router.message(CasherReview.entering_real_amount)
async def process_real_amount_and_reject(message: Message, state: FSMContext, api_client: APIClient, bot: Bot):
    # بررسی عدد بودن ورودی
    if not message.text.isdigit():
        await message.answer("❌ لطفاً مبلغ را فقط به صورت عدد (لاتین) وارد کنید.")
        return

    real_amount = int(message.text)

    # دریافت اطلاعات از State
    data = await state.get_data()
    payment_id = data.get("current_payment_id_to_reject")
    reason = data.get("reject_reason")
    casher_id = message.from_user.id

    # دریافت اطلاعات صندوق‌دار برای ثبت در لاگ
    user_info = await api_client.get_user_details_by_telegram_id(casher_id)
    db_user_id = int(user_info.get('user_id') or 1) if user_info else 1

    # آماده‌سازی پلود برای آپدیت
    payload = {
        "payment_status": "Rejected",
        "payment_status_explain": reason,
        "payment_value": real_amount,  # <--- آپدیت مبلغ با عدد واقعی که صندوق‌دار دیده
        "user_id": db_user_id,
    }

    wait_msg = await message.answer("⏳ در حال ثبت رد و اصلاح مبلغ...")

    # فراخوانی API
    result = await api_client.update_payment(payment_id, payload)

    if result:
        # اطلاع‌رسانی به کاربر (اختیاری)
        current_payment = data.get("current_payment", {})
        patient_tid = current_payment.get("telegram_id")
        await api_client.update_patient_status(str(current_payment.get("telegram_id")),PatientStatus.AWAITING_PAYMENT.value)

        if patient_tid:
            try:
                await bot.send_message(
                    patient_tid,
                    f"❌ پرداخت شما تایید نشد.\n"
                    f"📝 **علت:** {reason}\n"
                    f"🔢 **مبلغ اصلاح شده توسط صندوق‌دار:** {real_amount:,} تومان\n"
                    "لطفاً مجدداً بررسی کنید."
                )
            except:
                pass

        await wait_msg.delete()
        temp_msg = await message.answer(f"✅ رسید رد شد و مبلغ به {real_amount:,} تغییر یافت.\n🔄 بازگشت به لیست...")

        # بازگشت به لیست پرداخت‌ها
        await refresh_payment_list(temp_msg, state, api_client, data.get("selected_date"))
    else:
        await wait_msg.edit_text("❌ خطا در ثبت اطلاعات در سیستم.")


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
