# app/consultant/handlers.py

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputFile, InputMediaPhoto
from aiogram.types import Message, CallbackQuery, FSInputFile # <--- این را اضافه کنید
from aiogram.fsm.context import FSMContext
from decimal import Decimal # <--- این خط را اضافه کنید

from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.state import default_state
from aiogram import Bot



from app.core.enums import PatientStatus  # <-- Enum را وارد کنید

from app.core.API_Client import APIClient
from .states import ConsultantFlow
from .keyboards import create_dates_keyboard, create_patients_keyboard, get_next_patient_keyboard
from .keyboards import (
    create_dates_keyboard,
    create_patients_keyboard,
    get_start_prescription_keyboard, # <--- جدید
    create_disease_types_keyboard,   # <--- جدید
    create_drugs_keyboard,
    get_main_menu_keyboard# <--- جدید
)

consultant_router = Router()
logger = logging.getLogger(__name__)


# --- مرحله ۱: شروع کار مشاور با دستور /start ---
@consultant_router.callback_query(ConsultantFlow.main_menu,F.data == "consultant_panel")
async def consultant_start(callback: CallbackQuery, state: FSMContext, api_client: APIClient):

    await callback.message.edit_text("در حال دریافت لیست تاریخ‌های نیازمند بررسی...")

    unassigned_dates = await api_client.get_waiting_for_consultation_dates()

    logging.info(unassigned_dates)

    if not unassigned_dates:
        await callback.message.edit_text("در حال حاضر هیچ بیماری در صف انتظار برای بررسی وجود ندارد. ✅")

        return

    keyboard = create_dates_keyboard(unassigned_dates)
    await callback.message.edit_text(
        "📅 لطفاً تاریخی که می‌خواهید بیماران آن را بررسی کنید، انتخاب نمایید:",
        reply_markup=keyboard
    )
    await state.set_state(ConsultantFlow.choosing_date)




# --- مرحله ۲: دریافت تاریخ و نمایش بیماران آن روز ---
@consultant_router.callback_query(ConsultantFlow.choosing_date, F.data.startswith("consultant_date_"))
async def process_date_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    date = callback.data.split("_")[-1]
    await state.update_data(selected_date=date)

    await callback.message.edit_text(f"⏳ در حال دریافت لیست بیماران برای تاریخ {date}...")

    patients = await api_client.get_waiting_for_consultation_patients_by_date(date)

    if not patients:
        await callback.message.edit_text(f"خطا: بیماری برای تاریخ {date} یافت نشد. لطفاً دوباره تلاش کنید.")
        # می‌توانیم به مرحله قبل برگردیم یا فرآیند را تمام کنیم
        await state.clear()
        return

    keyboard = create_patients_keyboard(patients)
    await callback.message.edit_text(
        f"👥 لیست بیماران ثبت‌نام شده در تاریخ {date}:\nلطفاً بیمار مورد نظر را برای مشاهده جزئیات انتخاب کنید.",
        reply_markup=keyboard
    )
    await state.set_state(ConsultantFlow.choosing_patient)
    await callback.answer()


# --- مرحله ۳: دریافت بیمار و نمایش اطلاعات کامل او ---
@consultant_router.callback_query(ConsultantFlow.choosing_patient, F.data.startswith("consultant_patient_"))
async def process_patient_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):

    await callback.answer("✅ انتخاب دریافت شد. در حال بارگذاری اطلاعات...")
    try:
        patient_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.message.edit_text("خطا در پردازش شناسه بیمار.")
        return

    await state.update_data(selected_patient_id=patient_id)

    await callback.message.edit_text(f"🔍 در حال دریافت اطلاعات کامل بیمار با شناسه {patient_id}...")

    patient_details = await api_client.get_patient_details_by_telegram_id(patient_id)

    if not patient_details:
        await callback.message.edit_text("خطا: اطلاعات این بیمار یافت نشد!")
        await state.clear()
        return

    # ذخیره اطلاعات کلیدی برای مراحل بعدی
    await state.update_data(patient_telegram_id=patient_details.get("user", {}).get("telegram_id"))
    await state.update_data(full_name=patient_details.get("user", {}).get("full_name"))

    # آماده‌سازی متن نمایش اطلاعات
    info_text = (
        f"📄 **اطلاعات بیمار:** `{patient_details.get('full_name')}`\n\n"
        f"▪️ **شناسه تلگرام:** `{patient_details.get('telegram_id')}`\n"
        f"▪️ **جنسیت:** {'زن' if patient_details.get('gender') == 'male' else 'مرد'}\n"
        f"▪️ **سن:** {patient_details.get('age')} سال\n"
        f"▪️ **وزن:** {patient_details.get('weight')} کیلوگرم\n"
        f"▪️ **قد:** {patient_details.get('height')} سانتی‌متر\n\n"
        f"📝 **شرح مشکل بیمار:**\n"
        f"{patient_details.get('specific_diseases')}"
        f"▪️ **شرایط خاص:** {patient_details.get('special_conditions')} \n"

    )

    await callback.message.edit_text(info_text, parse_mode="Markdown")

    # ارسال عکس‌ها
    photo_paths = patient_details.get("photo_paths", [])
    if photo_paths:
        await callback.message.answer("🖼️ در حال ارسال تصاویر ارسالی بیمار...")

        try:
            # --- اصلاح اصلی اینجاست ---
            # تبدیل لیست مسیرهای فایل به لیست آبجکت‌های FSInputFile
            media_group = [InputMediaPhoto(media=FSInputFile(path)) for path in photo_paths]

            await callback.message.answer_media_group(media=media_group)

        except Exception as e:
            # لاگ خطا را بهبود می‌بخشیم
            logger.error(f"Failed to send media group for patient {patient_id}. Error: {e}")
    else:
        # اگر عکسی وجود نداشت، فقط متن را بفرست
        await callback.message.answer("این بیمار عکسی ارسال نکرده است.")

    await callback.message.answer(
        "برای ادامه، روی دکمه زیر کلیک کنید:",
        reply_markup=get_start_prescription_keyboard()
    )

    await state.set_state(ConsultantFlow.viewing_patient_details)
    await callback.answer()


@consultant_router.callback_query(ConsultantFlow.viewing_patient_details, F.data == "start_prescription")
async def process_start_prescription(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    await callback.message.edit_text("در حال دریافت لیست انواع بیماری‌ها...")

    disease_types = await api_client.get_all_disease_types()
    if not disease_types:
        await callback.message.edit_text("خطا: هیچ نوع بیماری در سیستم تعریف نشده است.")
        await state.clear()
        return

    keyboard = create_disease_types_keyboard(disease_types)
    await callback.message.edit_text(
        "لطفاً دسته بندی بیماری را مشخص کنید:",
        reply_markup=keyboard
    )

    # در FSM Storage یک مجموعه خالی برای داروهای انتخابی ایجاد می‌کنیم
    await state.update_data(selected_drugs=set())
    await state.set_state(ConsultantFlow.choosing_disease_type)
    await callback.answer()


# --- مرحله ۵: انتخاب نوع بیماری و نمایش داروها ---
@consultant_router.callback_query(ConsultantFlow.choosing_disease_type, F.data.startswith("disease_type_"))
async def process_disease_type_choice(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    disease_type_id = int(callback.data.split("_")[2])
    await state.update_data(selected_disease_type_id=disease_type_id)

    await callback.message.edit_text(f"در حال دریافت لیست داروها برای دسته بندی انتخابی...")

    drugs = await api_client.get_drugs_by_disease_type(disease_type_id)
    if not drugs:
        await callback.message.edit_text("هیچ دارویی برای این دسته بندی یافت نشد.")
        # می‌توانیم به کاربر اجازه دهیم دسته دیگری را انتخاب کند
        # فعلا فرآیند را متوقف می‌کنیم
        await state.clear()
        return

    # ذخیره لیست کامل داروها برای این دسته در state
    # این کار باعث می‌شود برای هر بار تیک زدن، دوباره از API دارو نگیریم
    await state.update_data(available_drugs=drugs)

    keyboard = create_drugs_keyboard(drugs)  # در ابتدا هیچ دارویی انتخاب نشده
    await callback.message.edit_text(
        "لطفاً دارو(های) مورد نظر را انتخاب کنید.\n"
        "با هر کلیک، دارو به لیست شما اضافه یا از آن حذف می‌شود.",
        reply_markup=keyboard
    )

    await state.set_state(ConsultantFlow.choosing_drugs)
    await callback.answer()


# --- مرحله ۶: انتخاب/حذف یک دارو (منطق تیک زدن) ---
@consultant_router.callback_query(ConsultantFlow.choosing_drugs, F.data.startswith("drug_select_"))
async def process_drug_selection(callback: CallbackQuery, state: FSMContext):
    drug_id = int(callback.data.split("_")[2])

    data = await state.get_data()
    selected_drugs = set(data.get("selected_drugs", []))
    available_drugs = data.get("available_drugs", [])

    # اگر دارو در لیست بود، حذفش کن. اگر نبود، اضافه‌اش کن.
    if drug_id in selected_drugs:
        selected_drugs.remove(drug_id)
    else:
        selected_drugs.add(drug_id)

    await state.update_data(selected_drugs=selected_drugs)

    # کیبورد را با لیست به‌روز شده داروها دوباره بساز و ویرایش کن
    new_keyboard = create_drugs_keyboard(available_drugs, selected_drugs)

    try:
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    except Exception as e:
        logger.warning(f"Could not edit keyboard, probably unchanged. {e}")

    await callback.answer()


# --- مرحله ۷: کلیک روی "ثبت نهایی داروها" ---
# این هندلر در گام بعدی که ثبت سفارش است، پیاده‌سازی خواهد شد.
# فعلا فقط اطلاعات را نمایش می‌دهیم تا از صحت عملکرد مطمئن شویم.
@consultant_router.callback_query(ConsultantFlow.choosing_drugs, F.data == "confirm_drugs")
async def handle_confirm_drugs(callback: CallbackQuery, state: FSMContext, api_client: APIClient , bot : Bot):  # <--- user_id مشاور از میدل‌ور اضافه شد
    await callback.answer("در حال ثبت تجویز...", show_alert=False)

    data = await state.get_data()
    selected_drugs_ids = data.get('selected_drugs')
    patient_telegram_id = data.get('selected_patient_id')  # <--- نام state را از مرحله ۳ چک کنید (selected_patient_id)
    patient_full_name = data.get('full_name', 'بیمار')  # <--- نام بیمار را هم از state می‌خوانیم
    consultant_telegram_id = callback.from_user.id


    # -----------------------------------------
    consultant_details = await api_client.get_user_details_by_telegram_id(consultant_telegram_id)
    if not consultant_details:
        await callback.message.answer("خطا: اطلاعات شما به عنوان مشاور در سیستم یافت نشد.")
        return
    else:
        user_id = int(consultant_details['user_id'])

    # گرفتن اطلاعات کامل بیمار با استفاده از متد جدید
    patient_details = await api_client.get_patient_details_by_telegram_id(patient_telegram_id)
    if not patient_details:
        await callback.message.answer(f"خطا: اطلاعات بیمار با شناسه تلگرام {patient_telegram_id} در سیستم یافت نشد.")
        return
    else:
        patient_id = int(patient_details['patient_id'])
    # -------------------------------------------


    # ۱. اعتبارسنجی داده‌های موجود در state
    if not selected_drugs_ids:
        await callback.answer("خطا: هیچ دارویی انتخاب نشده است!", show_alert=True)
        return

    if not patient_id or not user_id:
        await callback.message.edit_text(
            "❌ **خطای سیستمی:** اطلاعات بیمار یا مشاور یافت نشد.\n"
            "لطفاً فرآیند را از ابتدا شروع کنید."
        )
        await state.clear()
        return

    try:
        # ۲. فراخوانی API برای ساخت سفارش
        # تبدیل set به list چون JSON از set پشتیبانی نمی‌کند
        drug_ids_list = list(selected_drugs_ids)

        new_order = await api_client.create_order(
            patient_id=patient_id,
            user_id=user_id,
            drug_ids=drug_ids_list
        )

        if not new_order or 'order_id' not in new_order:
            raise ValueError("پاسخ نامعتبر از API هنگام ساخت سفارش.")

        order_id = new_order.get('order_id')

        if not (await api_client.update_patient_status(patient_telegram_id,PatientStatus.AWAITING_INVOICE_APPROVAL)):
            raise ValueError("خطا در تغییر وضعیت.")


        # ۳. ساخت پیام موفقیت‌آمیز برای نمایش به مشاور (شبیه فاکتور)
        available_drugs = data.get('available_drugs', [])
        selected_drugs_details = [
            drug for drug in available_drugs if drug['drugs_id'] in selected_drugs_ids
        ]

        total_price = sum(Decimal(d['price']) for d in selected_drugs_details)

        # ساخت متن لیست داروها
        prescription_text = ""
        for i, drug in enumerate(selected_drugs_details, 1):
            # تبدیل قیمت به عدد صحیح و فرمت با کاما
            price_formatted = f"{int(Decimal(drug['price'])):,}"
            prescription_text += f"{i}. {drug['drug_pname']} - {price_formatted} ریال\n"

        total_price_formatted = f"{int(total_price):,}"

        success_message = (
            f"✅ **تجویز با موفقیت ثبت شد.**\n\n"
            f"📄 **شماره سفارش:** `{order_id}`\n"
            f"👤 **برای بیمار:** {patient_full_name}\n\n"
            f"📋 **لیست داروها:**\n"
            f"{prescription_text}\n"
            f"---------------------------\n"
            f"💰 **جمع کل:** **{total_price_formatted} ریال**\n\n"
            f"ℹ️ وضعیت سفارش: `ایجاد شده` (created)\n"
            f"این سفارش جهت تایید نهایی به بیمار ارجاع داده شد."
        )

        try:
            if patient_telegram_id:
                await bot.send_message(
                    chat_id=patient_telegram_id,
                    text=(
                        "✅ مشاوره شما توسط دکتر انجام شد.\n"
                        "لطفاً فاکتور داروهای پیشنهادی خود را در همین ربات بررسی و تأیید کنید 🙏"
                    )
                )
            else:
                logging.warning("Patient telegram ID not found in FSM data; cannot send consultation notification.")
        except Exception as e:
            logging.error(f"Failed to send consultation-done message to patient: {e}")

        # ۴. پایان فلو و پاک کردن state
        await callback.message.edit_text(success_message, parse_mode="Markdown",reply_markup=get_next_patient_keyboard())


        await state.clear()

    except Exception as e:
        logging.error(f"Error during order confirmation process: {e}", exc_info=True)
        await callback.message.edit_text(
            "❌ **خطا در ثبت تجویز!**\n\n"
            "مشکلی در ارتباط با سرور پیش آمده یا داده‌های ارسالی نامعتبر است. "
            "لطفاً لحظاتی بعد دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        )
        await state.clear()


@consultant_router.callback_query(F.data == "next_patient")
async def handle_next_patient(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """نمایش قدیمی‌ترین بیمار در صف بررسی برای مشاور بعد از ثبت دارو."""
    await callback.message.edit_text("در حال دریافت بیمار بعدی بر اساس قدیمی‌ترین درخواست...")

    # ۱) دریافت لیست تاریخ‌های دارای بیمار در انتظار بررسی
    unassigned_dates = await api_client.get_waiting_for_consultation_dates()
    if not unassigned_dates:
        await callback.message.edit_text("✅ هیچ بیمار جدیدی در صف بررسی وجود ندارد.")
        await state.clear()
        return

    # ۲) انتخاب قدیمی‌ترین تاریخ
    oldest_date = sorted(unassigned_dates)[0]

    # ۳) دریافت لیست بیماران آن تاریخ
    patients = await api_client.get_waiting_for_consultation_patients_by_date(oldest_date)
    if not patients:
        await callback.message.edit_text(f"هیچ بیماری برای تاریخ {oldest_date} یافت نشد.")
        await state.clear()
        return

    # انتخاب اولین بیمار لیست (قدیمی‌ترین آن روز)
    next_patient = patients[0]
    patient_id = next_patient.get("telegram_id")

    # دریافت جزئیات کامل بیمار با همان تابعی که قبلاً استفاده می‌کردی
    patient_details = await api_client.get_patient_details_by_telegram_id(patient_id)
    if not patient_details:
        await callback.message.edit_text(f"خطا: اطلاعات بیمار با شناسه {patient_id} یافت نشد.")
        await state.clear()
        return

    # آماده‌سازی متن اطلاعات بیمار
    info_text = (
        f"📄 **اطلاعات بیمار بعدی:** `{patient_details.get('full_name')}`\n\n"
        f"▪️ **شناسه تلگرام:** `{patient_details.get('telegram_id')}`\n"
        f"▪️ **جنسیت:** {'مرد' if patient_details.get('gender') == 'male' else 'زن'}\n"
        f"▪️ **سن:** {patient_details.get('age')} سال\n"
        f"▪️ **وزن:** {patient_details.get('weight')} کیلوگرم\n"
        f"▪️ **قد:** {patient_details.get('height')} سانتی‌متر\n\n"
        f"📝 **شرح مشکل:**\n{patient_details.get('specific_diseases')}\n\n"
        f"▪️ **شرایط خاص:** {patient_details.get('special_conditions', 'نامشخص')}"
    )

    await callback.message.edit_text(info_text, parse_mode="Markdown")

    # ارسال عکس‌ها (در صورت وجود)
    photo_paths = patient_details.get("photo_paths", [])
    if photo_paths:
        try:
            media_group = [InputMediaPhoto(media=FSInputFile(p)) for p in photo_paths]
            await callback.message.answer_media_group(media=media_group)
        except Exception as e:
            logger.error(f"Send patient photo error: {e}")

    # نمایش دکمه شروع تجویز برای بیمار جدید
    await callback.message.answer(
        "برای شروع بررسی و تجویز دارو، روی دکمه زیر کلیک کنید:",
        reply_markup=get_start_prescription_keyboard()
    )

    await state.set_state(ConsultantFlow.viewing_patient_details)


@consultant_router.message(StateFilter(default_state), F.text)
async def handle_any_text(message: Message, state: FSMContext):

    """
    این هندلر به هر پیام متنی در حالت پیش‌فرض (وقتی کاربر در حال انجام کاری نیست)
    پاسخ می‌دهد و منوی اصلی را نمایش می‌دهد.
    """
    await state.set_state(ConsultantFlow.main_menu)

    await message.answer(
        "به پنل مشاوران خوش آمدید. لطفاً از منوی زیر برای شروع کار استفاده کنید:",
        reply_markup=get_main_menu_keyboard()
    )