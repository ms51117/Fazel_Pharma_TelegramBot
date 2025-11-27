# app/consultant/handlers.py

import logging
import os
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputFile, InputMediaPhoto, ReplyKeyboardRemove
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
    get_main_menu_keyboard,
    get_consultant_chat_keyboard
)

consultant_router = Router()
logger = logging.getLogger(__name__)


# <--- تابع کمکی جدید برای نمایش اطلاعات کامل بیمار --->
async def show_patient_full_info(message: Message, state: FSMContext, api_client: APIClient, patient_telegram_id: str):
    """جزئیات جامع بیمار و تاریخچه چت را نمایش می‌دهد"""
    patient = await api_client.get_patient_details_by_telegram_id(patient_telegram_id)
    if not patient:
        await message.answer("❌ اطلاعات بیمار یافت نشد.")
        return


    info = (
        f"📋 **{patient.get('full_name')}**\n"
        f"شناسه: `{patient.get('telegram_id')}`\n"
        f"جنسیت :  { 'مرد' if patient.get('sex') == 'male' else 'زن'}\n"
        f"سن: {patient.get('age')}  •  وزن: {patient.get('weight')}  •  قد: {patient.get('height')}\n\n"
        f"🩺 بیماری خاص: {patient.get('specific_diseases') or '—'}\n"
        f"🔹 شرایط ویژه: {patient.get('special_conditions') or '—'}"
    )
    await message.answer(info, parse_mode="Markdown")

    photos = patient.get("photo_paths", [])
    if photos:
        try:
            media = [InputMediaPhoto(media=FSInputFile(p)) for p in photos]
            await message.answer_media_group(media=media)
        except Exception as e:
            logger.warning(f"Cannot send photos: {e}")
    patient_id = patient.get("patient_id")

    # تاریخچه چت
    chats = await api_client.read_messages_history_by_patient_id(patient_id)

    if not chats:
        await message.answer("هیچ گفتگویی تا کنون ثبت نشده است.")
    else:
        for msg in chats:
            # حالا msg قطعاً dict است
            sender_is_patient = msg.get("messages_sender", False)
            text_content = msg.get("messages", "")
            attachments = msg.get("attachment_path", [])

            sender_title = "👨‍⚕️ بیمار" if sender_is_patient else "👤 شما"

            if text_content:
                await message.answer(f"{sender_title}:\n{text_content}")
            if attachments:
                # اگر فایل ضمیمه هست (عکس/ویس)
                for path in attachments:
                    if path.endswith(".jpg") or path.endswith(".png"):
                        await message.answer_photo(FSInputFile(path))
                    elif path.endswith(".ogg") or path.endswith(".mp3"):
                        await message.answer_voice(FSInputFile(path))

    await message.answer("اکنون می‌توانید گفتگو را ادامه دهید یا از دکمه‌ها استفاده کنید:",
                         reply_markup=get_consultant_chat_keyboard())
    await state.update_data(selected_patient_id=patient_id)
    await state.set_state(ConsultantFlow.in_chat_with_patient)


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

    patient_ids = [p.get("telegram_id") for p in patients]
    await state.update_data(patient_ids_for_date=patient_ids)

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
    await callback.message.delete()  # <--- پیام قبلی با دکمه‌های اینلاین را حذف می‌کنیم

    try:
        patient_telegram_id = str(callback.data.split("_")[-1])
        await state.update_data(patient_telegram_id=patient_telegram_id)
    except (ValueError, IndexError):
        await callback.message.answer("خطا در پردازش شناسه بیمار.")
        return

    # <--- به‌روزرسانی state با بیمار انتخابی --- >
    data = await state.get_data()

    await state.update_data(selected_date=data.get("selected_date"))

    # <--- فراخوانی تابع کمکی --->
    await show_patient_full_info(callback.message, state, api_client, patient_telegram_id)
    await callback.answer()


@consultant_router.message(ConsultantFlow.in_chat_with_patient, F.text == "✍️ شروع تجویز")
async def handle_start_prescription_from_chat(message: Message, state: FSMContext, api_client: APIClient):
    # کیبورد Reply را حذف می‌کنیم تا برای مراحل بعد مزاحم نباشد
    await message.answer("در حال آماده‌سازی برای تجویز...", reply_markup=ReplyKeyboardRemove())

    # این بخش دقیقا مانند منطق process_start_prescription قبلی شماست
    disease_types = await api_client.get_all_disease_types()
    if not disease_types:
        await message.answer("خطا: هیچ نوع بیماری در سیستم تعریف نشده است.")
        await state.clear()
        return

    keyboard = create_disease_types_keyboard(disease_types)
    await message.answer(
        "لطفاً دسته بندی بیماری را مشخص کنید:",
        reply_markup=keyboard
    )

    await state.update_data(selected_drugs=set())
    await state.set_state(ConsultantFlow.choosing_disease_type)


# --- مرحله ۴.۱: مدیریت دکمه‌های بیمار قبلی و بعدی ---
@consultant_router.message(ConsultantFlow.in_chat_with_patient, F.text == "👤 بیمار بعدی")
async def next_patient(message: Message, state: FSMContext, api_client: APIClient):
    data = await state.get_data()
    date = data.get("selected_date")
    current_id = data.get("selected_patient_id")

    patients_data = await api_client.get_waiting_for_consultation_patients_by_date(date)
    patients = patients_data.get("patients", [])
    ids = [p["telegram_id"] for p in patients]
    if current_id not in ids:
        await message.answer("📅 لیست امروز تغییر کرده است، از ابتدا وارد شوید.")
        await state.clear()
        return

    idx = ids.index(current_id)
    if idx + 1 >= len(ids):
        await message.answer("آخرین بیمار این تاریخ هستید.")
        return
    await show_patient_full_info(message, state, api_client, ids[idx + 1])


@consultant_router.message(ConsultantFlow.in_chat_with_patient, F.text == "👤 بیمار قبلی")
async def prev_patient(message: Message, state: FSMContext, api_client: APIClient):
    data = await state.get_data()
    date = data.get("selected_date")
    current_id = data.get("selected_patient_id")

    patients_data = await api_client.get_waiting_for_consultation_patients_by_date(date)
    patients = patients_data.get("patients", [])
    ids = [p["telegram_id"] for p in patients]
    if current_id not in ids:
        await message.answer("📅 لیست امروز تغییر کرده است، از ابتدا وارد شوید.")
        await state.clear()
        return

    idx = ids.index(current_id)
    if idx - 1 < 0:
        await message.answer("این اولین بیمار امروز است.")
        return
    await show_patient_full_info(message, state, api_client, ids[idx - 1])

# -----------------------------
# --- مرحله ۴.۳: مدیریت ارسال پیام متنی از مشاور به بیمار ---
@consultant_router.message(ConsultantFlow.in_chat_with_patient)
async def handle_consultant_chat_message(message: Message, state: FSMContext, api_client: APIClient, bot: Bot):
    # این هندلر باید بعد از هندلر دکمه‌ها باشد تا اولویت با دکمه‌ها باشد
    data = await state.get_data()
    patient_id = data.get("selected_patient_id")
    patient_telegram_id = data.get("patient_telegram_id")
    consultant_telegram_id = message.from_user.id
    response = await api_client.get_user_details_by_telegram_id(consultant_telegram_id)


    consultant_id = response.get("user_id")

    text_content = None
    attachment_paths = []  # برای ذخیره مسیر فایل‌ها

    user_storage_path = os.path.join("patient_files", str(patient_telegram_id))
    os.makedirs(user_storage_path, exist_ok=True)

    # ===== پیام متنی =====
    if message.text:
        text_content = message.text

    # ===== عکس =====
    elif message.photo:
        photo = message.photo[-1]
        try:
            file_info = await bot.get_file(photo.file_id)
            file_path_on_telegram = file_info.file_path

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = os.path.splitext(file_path_on_telegram)[1] or ".jpg"
            filename = f"photo_{timestamp}{file_extension}"
            destination_path = os.path.join(user_storage_path, filename)

            await bot.download_file(file_path_on_telegram, destination=destination_path)
            absolute_path = os.path.abspath(destination_path)
            attachment_paths.append(absolute_path)

        except Exception as e:
            logging.error(f"Error downloading photo for {patient_telegram_id}: {e}")

    # ===== ویس =====
    elif message.voice:
        voice = message.voice
        try:
            file_info = await bot.get_file(voice.file_id)
            file_path_on_telegram = file_info.file_path

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = os.path.splitext(file_path_on_telegram)[1] or ".ogg"
            filename = f"voice_{timestamp}{file_extension}"
            destination_path = os.path.join(user_storage_path, filename)

            await bot.download_file(file_path_on_telegram, destination=destination_path)
            absolute_path = os.path.abspath(destination_path)
            attachment_paths.append(absolute_path)

        except Exception as e:
            logging.error(f"Error downloading voice for {patient_telegram_id}: {e}")

    else:
        await message.answer("فقط ارسال متن، عکس یا ویس پشتیبانی می‌شود.")
        return

    # --- ساخت و ارسال پیام در API ---
    success = await api_client.create_message(
        patient_id=patient_id,
        user_id=consultant_id,
        message_content=text_content,
        messages_sender=False,
        attachments=attachment_paths  # می‌تونه []
    )

    if success:
        confirm_text = "✅ پیام (یا رسانه) شما ارسال شد."
        await message.answer(confirm_text)
    else:
        await message.answer("❌ خطا در ارسال پیام. لطفاً بعداً امتحان کنید.")
# -----------------------------



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
    patient_telegram_id = data.get('patient_telegram_id')  # <--- نام state را از مرحله ۳ چک کنید (selected_patient_id)
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