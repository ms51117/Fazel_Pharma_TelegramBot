# app/consultant/handlers.py

import logging
import os
from datetime import datetime

from aiogram.types import FSInputFile


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

import os
import logging
import ast # برای تبدیل رشته به لیست
from aiogram.types import FSInputFile, InputMediaPhoto, Message
from aiogram.fsm.context import FSMContext
from aiogram import Bot


from app.core.enums import PatientStatus  # <-- Enum را وارد کنید

from app.core.API_Client import APIClient
from .states import ConsultantFlow
from .keyboards import create_dates_keyboard, create_patients_keyboard, get_next_patient_keyboard, \
    create_prescription_review_keyboard
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
    """
    نمایش جزئیات پرونده بیمار و تاریخچه کامل چت (شامل فایل‌ها) برای مشاور
    """

    # 1. دریافت اطلاعات پروفایل بیمار
    patient = await api_client.get_patient_details_by_telegram_id(patient_telegram_id)
    if not patient:
        await message.answer("❌ اطلاعات بیمار یافت نشد.")
        return

    # 2. نمایش اطلاعات متنی پرونده
    info = (
        f"📋 **پرونده بیمار: {patient.get('full_name', 'ناشناس')}**\n"
        f"🆔 شناسه تلگرام: `{patient.get('telegram_id')}`\n"
        f"👤 جنسیت: {'مرد' if patient.get('sex') == 'male' else 'زن'}\n"
        f"📊 سن: {patient.get('age')}  •  وزن: {patient.get('weight')}  •  قد: {patient.get('height')}\n\n"
        f"🩺 بیماری خاص: {patient.get('specific_diseases') or '—'}\n"
        f"⚠️ شرایط ویژه: {patient.get('special_conditions') or '—'}"
    )
    await message.answer(info, parse_mode="Markdown")

    # 3. نمایش عکس‌های پروفایل (پزشکی) بیمار
    # نکته: عکس‌های پروفایل معمولاً در زمان ثبت‌نام آپلود شده‌اند
    raw_photos = patient.get("photo_paths", [])
    photos_to_show = []

    # تمیزکاری لیست عکس‌ها
    if isinstance(raw_photos, list):
        photos_to_show = raw_photos
    elif isinstance(raw_photos, str):
        try:
            photos_to_show = ast.literal_eval(raw_photos)
        except:
            photos_to_show = [raw_photos]

    if photos_to_show:
        media_group = []
        for p in photos_to_show:
            path = str(p).strip()
            if os.path.exists(path):
                try:
                    media_group.append(InputMediaPhoto(media=FSInputFile(path)))
                except Exception as e:
                    logging.error(f"Error preparing profile photo {path}: {e}")

        if media_group:
            try:
                await message.answer_media_group(media=media_group)
            except Exception as e:
                await message.answer("⚠️ خطا در نمایش آلبوم عکس‌های بیمار.")
                logging.error(f"Error sending media group: {e}")

    # 4. دریافت و نمایش تاریخچه چت
    patient_id = patient.get("patient_id")
    chats = await api_client.read_messages_history_by_patient_id(patient_id)

    if not chats:
        await message.answer("📭 هیچ گفتگویی تا کنون ثبت نشده است.")
    else:
        await message.answer("💬 **تاریخچه گفتگوها:**")

        for msg in chats:
            # تشخیص فرستنده:
            # True = بیمار فرستاده (Patient)
            # False = سیستم/مشاور فرستاده (You)
            sender_is_patient = msg.get("messages_sender", False)
            sender_title = "👤 بیمار" if sender_is_patient else "👨‍⚕️ شما"

            text_content = msg.get("messages", "")

            # --- پردازش پیوست‌ها (Attachments) ---
            raw_attachments = msg.get("attachment_path")
            attachments = []

            # تبدیل داده دیتابیس به لیست پایتون
            if isinstance(raw_attachments, list):
                attachments = raw_attachments
            elif isinstance(raw_attachments, str) and raw_attachments:
                try:
                    attachments = ast.literal_eval(raw_attachments)
                    if not isinstance(attachments, list):
                        attachments = [raw_attachments]
                except:
                    attachments = [raw_attachments]

            # --- الف: نمایش متن ---
            if text_content and text_content.strip():
                await message.answer(f"**{sender_title}:**\n{text_content}", parse_mode="Markdown")
            elif not attachments:
                # اگر پیام خالی بود و فایلی هم نداشت (خیلی نادر)
                pass

                # --- ب: نمایش فایل‌ها ---
            if attachments:
                for file_path in attachments:
                    file_path = str(file_path).strip()

                    if not os.path.exists(file_path):
                        await message.answer(f"⚠️ **{sender_title}:** [فایل روی سرور یافت نشد]")
                        continue

                    try:
                        file_to_send = FSInputFile(file_path)
                        file_ext = os.path.splitext(file_path)[1].lower()

                        if file_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            await message.answer_photo(
                                photo=file_to_send,
                                caption=f"📷 تصویر ارسالی {sender_title}"
                            )
                        elif file_ext in ['.ogg', '.mp3', '.wav', '.m4a']:
                            await message.answer_voice(
                                voice=file_to_send,
                                caption=f"🎙 ویس ارسالی {sender_title}"
                            )
                        else:
                            # سایر فایل‌ها (PDF و ...)
                            await message.answer_document(
                                document=file_to_send,
                                caption=f"📎 فایل ارسالی {sender_title}"
                            )
                    except Exception as e:
                        logging.error(f"Failed to send chat history file {file_path}: {e}")
                        await message.answer(f"❌ خطا در نمایش فایل: {os.path.basename(file_path)}")

    # 5. تنظیم State و نمایش دکمه‌های مشاور
    await message.answer(
        "🟢 **چت زنده فعال شد**\n"
        "هر متنی، عکسی یا ویسی بفرستید مستقیماً برای بیمار ارسال می‌شود.",
        reply_markup=get_consultant_chat_keyboard()  # اطمینان حاصل کنید این تابع ایمپورت شده باشد
    )

    # ذخیره اطلاعات در State برای هندلرهای بعدی
    await state.update_data(
        selected_patient_id=patient_id,
        patient_telegram_id=patient.get('telegram_id')  # برای ارسال مستقیم پیام مهم است
    )
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
    await message.answer("در حال آماده‌سازی برای تجویز...", reply_markup=ReplyKeyboardRemove())

    disease_types = await api_client.get_all_disease_types()
    if not disease_types:
        await message.answer("خطا: هیچ نوع بیماری در سیستم تعریف نشده است.")
        return

    keyboard = create_disease_types_keyboard(disease_types)
    await message.answer("لطفاً دسته‌بندی بیماری را مشخص کنید:", reply_markup=keyboard)

    # Resetting state data clearly
    await state.update_data(
        selected_drugs=set(),      # فقط آیدی‌ها ذخیره می‌شوند
        drug_cache={},             # دیکشنری برای ذخیره نام و قیمت داروها (ID -> Data)
        current_disease_types=disease_types # برای دکمه بازگشت لازم داریم
    )
    await state.set_state(ConsultantFlow.choosing_disease_type)


# --- هندلر دکمه "بیمار بعدی" (اصلاح شده و ایمن) ---
@consultant_router.message(ConsultantFlow.in_chat_with_patient, F.text == "👤 بیمار بعدی")
async def next_patient(message: Message, state: FSMContext, api_client: APIClient):
    # ۱. دریافت اطلاعات از State
    data = await state.get_data()
    date = data.get("selected_date")
    # نکته مهم: از patient_telegram_id استفاده می‌کنیم چون در لیست بیماران این فیلد یکتا و قابل جستجو است
    current_telegram_id = str(data.get("patient_telegram_id"))

    if not date:
        await message.answer("⚠️ خطای تاریخ: لطفاً از منوی اصلی دوباره وارد شوید.")
        return

    # ۲. دریافت لیست تازه‌ی بیماران
    patients_data = await api_client.get_waiting_for_consultation_patients_by_date(date)

    # هندل کردن فرمت‌های مختلف پاسخ API (لیست یا دیکشنری)
    if isinstance(patients_data, list):
        patients = patients_data
    else:
        patients = patients_data.get("patients", [])

    if not patients:
        await message.answer("✅ لیست بیماران این تاریخ خالی شده یا تمام شده است.")
        return

    # ۳. استخراج لیست آیدی‌های تلگرام (همه را به رشته تبدیل می‌کنیم تا مقایسه درست باشد)
    ids = [str(p["telegram_id"]) for p in patients]

    # ۴. پیدا کردن جایگاه بیمار فعلی
    try:
        current_idx = ids.index(current_telegram_id)
    except ValueError:
        # اگر بیمار فعلی دیگر در لیست نیست (مثلا وضعیتش تغییر کرده)، از اول لیست شروع کن
        await message.answer("⚠️ بیمار فعلی در لیست انتظار نیست. انتقال به نفر اول لیست...")
        # نفر اول را نمایش بده
        await show_patient_full_info(message, state, api_client, ids[0])
        return

    # ۵. محاسبه نفر بعدی
    next_idx = current_idx + 1

    # ۶. بررسی اینکه آیا به ته لیست رسیده‌ایم؟
    if next_idx >= len(ids):
        await message.answer("✅ **پایان لیست:** شما آخرین بیمار این تاریخ را مشاهده کردید.")
        return

    # ۷. نمایش بیمار بعدی
    next_patient_id = ids[next_idx]
    await message.answer(f"⬇️ انتقال به بیمار {next_idx + 1} از {len(ids)}...")
    await show_patient_full_info(message, state, api_client, next_patient_id)


# --- هندلر دکمه "بیمار قبلی" (اصلاح شده و ایمن) ---
@consultant_router.message(ConsultantFlow.in_chat_with_patient, F.text == "👤 بیمار قبلی")
async def prev_patient(message: Message, state: FSMContext, api_client: APIClient):
    data = await state.get_data()
    date = data.get("selected_date")
    current_telegram_id = str(data.get("patient_telegram_id"))

    if not date:
        await message.answer("⚠️ خطای تاریخ.")
        return

    patients_data = await api_client.get_waiting_for_consultation_patients_by_date(date)

    if isinstance(patients_data, list):
        patients = patients_data
    else:
        patients = patients_data.get("patients", [])

    if not patients:
        await message.answer("لیست خالی است.")
        return

    ids = [str(p["telegram_id"]) for p in patients]

    try:
        current_idx = ids.index(current_telegram_id)
    except ValueError:
        await message.answer("⚠️ بیمار در لیست یافت نشد. بازگشت به نفر اول.")
        await show_patient_full_info(message, state, api_client, ids[0])
        return

    # محاسبه نفر قبلی
    prev_idx = current_idx - 1

    # بررسی اینکه آیا به اول لیست رسیده‌ایم؟
    if prev_idx < 0:
        await message.answer("⛔️ **ابتدا لیست:** این اولین بیمار در لیست امروز است.")
        return

    # نمایش بیمار قبلی
    prev_patient_id = ids[prev_idx]
    await message.answer(f"⬆️ بازگشت به بیمار {prev_idx + 1} از {len(ids)}...")
    await show_patient_full_info(message, state, api_client, prev_patient_id)


# --- هندلر جدید: دکمه بازگشت به لیست تاریخ‌ها ---
@consultant_router.message(ConsultantFlow.in_chat_with_patient, F.text == "🏠 بازگشت به لیست تاریخ‌ها")
async def return_to_date_list(message: Message, state: FSMContext, api_client: APIClient):
    """خروج از چت بیمار فعلی و بازگشت به انتخاب تاریخ"""

    # پاک کردن state چت ولی نگه داشتن اطلاعات کلی اگر لازم است (اینجا کامل پاک میکنیم برای امنیت)
    await state.clear()

    # حذف کیبورد پایین صفحه
    await message.answer("🔄 در حال خروج از پرونده...", reply_markup=ReplyKeyboardRemove())

    # نمایش مجدد لیست تاریخ‌ها
    await message.answer("📅 در حال دریافت لیست تاریخ‌های نیازمند بررسی...")
    unassigned_dates = await api_client.get_waiting_for_consultation_dates()

    if not unassigned_dates:
        await message.answer("✅ در حال حاضر هیچ بیماری در صف انتظار وجود ندارد.", reply_markup=get_main_menu_keyboard())
        await state.set_state(ConsultantFlow.main_menu)
        return

    keyboard = create_dates_keyboard(unassigned_dates)
    await message.answer(
        "لطفاً تاریخی که می‌خواهید بیماران آن را بررسی کنید، انتخاب نمایید:",
        reply_markup=keyboard
    )
    await state.set_state(ConsultantFlow.choosing_date)




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
        # ارسال مستقیم متن به بیمار
        await bot.send_message(
            chat_id=patient_telegram_id,
            text=text_content
        )

    # ===== عکس =====
    elif message.photo:
        await bot.send_chat_action(chat_id=patient_telegram_id, action="upload_photo")

        photo = message.photo[-1]
        file_id = photo.file_id
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

            # 2. خواندن از دیسک و ارسال به بیمار (بدون استفاده از file_id)

            photo_from_disk = FSInputFile(absolute_path)
            await bot.send_photo(
                chat_id=patient_telegram_id,
                photo=photo_from_disk,
                caption=message.caption if message.caption else "📷 پیام تصویری از مشاور"
            )


        except Exception as e:
            logging.error(f"Error downloading photo for {patient_telegram_id}: {e}")

    # ===== ویس =====
    elif message.voice:
        voice = message.voice
        file_id = voice.file_id

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

            voice_from_disk = FSInputFile(absolute_path)
            await bot.send_voice(
                chat_id=patient_telegram_id,
                voice=voice_from_disk,
                caption="🎙 پیام صوتی از مشاور"
            )
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

    await callback.message.edit_text(f"در حال دریافت لیست داروها...")

    drugs = await api_client.get_drugs_by_disease_type(disease_type_id)
    if not drugs:
        await callback.message.edit_text("هیچ دارویی برای این دسته‌بندی یافت نشد.")
        # برگشت به لیست دسته‌ها
        data = await state.get_data()
        keyboard = create_disease_types_keyboard(data.get("current_disease_types", []))
        await callback.message.edit_text("لطفاً دسته‌بندی دیگری انتخاب کنید:", reply_markup=keyboard)
        return

    # 1. آپدیت کردن کش داروها (مهم)
    data = await state.get_data()
    drug_cache = data.get("drug_cache", {})
    selected_drugs = data.get("selected_drugs", set())

    for drug in drugs:
        drug_cache[drug['drugs_id']] = {
            'name': drug['drug_pname'],
            'price': drug.get('price', 0)
        }

    # ذخیره مجدد در State
    await state.update_data(
        available_drugs_in_current_view=drugs,  # فقط داروهای همین دسته برای نمایش
        drug_cache=drug_cache
    )

    # 2. نمایش کیبورد
    keyboard = create_drugs_keyboard(drugs, selected_drugs)
    await callback.message.edit_text(
        "داروهای مورد نظر را انتخاب کنید.\n"
        "می‌توانید پس از انتخاب، دکمه 'بازگشت به دسته‌بندی' را بزنید و از دسته‌های دیگر هم دارو بردارید.",
        reply_markup=keyboard
    )

    await state.set_state(ConsultantFlow.choosing_drugs)
    await callback.answer()


# --- مرحله ۶: انتخاب/حذف یک دارو (منطق تیک زدن) ---
@consultant_router.callback_query(ConsultantFlow.choosing_drugs, F.data.startswith("drug_select_"))
async def process_drug_selection(callback: CallbackQuery, state: FSMContext):
    drug_id = int(callback.data.split("_")[2])

    data = await state.get_data()
    selected_drugs = set(data.get("selected_drugs", []))  # تبدیل لیست به set
    available_drugs_view = data.get("available_drugs_in_current_view", [])

    # Toggle Logic
    if drug_id in selected_drugs:
        selected_drugs.remove(drug_id)
    else:
        selected_drugs.add(drug_id)

    # ذخیره به صورت لیست (چون JSON ست را ساپورت نمی‌کند، اما Aiogram هندل می‌کند معمولا. بهتر است set بماند در مموری)
    await state.update_data(selected_drugs=selected_drugs)

    # آپدیت کیبورد
    new_keyboard = create_drugs_keyboard(available_drugs_view, selected_drugs)

    # جلوگیری از خطای تلگرام اگر تغییری نبود
    if callback.message.reply_markup != new_keyboard:
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)

    await callback.answer()


@consultant_router.callback_query(ConsultantFlow.choosing_drugs, F.data == "back_to_categories")
async def handle_back_to_categories(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    """بازگشت به لیست دسته‌بندی‌ها برای انتخاب داروی بیشتر"""
    # لیست دسته‌ها را دوباره نگیریم، از کش state استفاده کنیم یا دوباره بگیریم
    # اینجا فرض می‌کنیم قبلا در current_disease_types ذخیره کردیم (در هندلر شروع)
    # اگر نکرده بودیم، دوباره کال می‌زنیم:
    disease_types = await api_client.get_all_disease_types()

    keyboard = create_disease_types_keyboard(disease_types)

    data = await state.get_data()
    selected_count = len(data.get("selected_drugs", []))

    await callback.message.edit_text(
        f"تا الان {selected_count} دارو انتخاب کرده‌اید.\n"
        "برای افزودن داروهای بیشتر، یک دسته‌بندی دیگر انتخاب کنید:",
        reply_markup=keyboard
    )
    await state.set_state(ConsultantFlow.choosing_disease_type)
    await callback.answer()




@consultant_router.callback_query(ConsultantFlow.choosing_drugs, F.data == "review_prescription")
async def handle_review_prescription(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = data.get("selected_drugs", set())
    drug_cache = data.get("drug_cache", {})  # این دیکشنری شامل نام و قیمت تمام داروهای لود شده است

    if not selected_ids:
        await callback.answer("هیچ دارویی انتخاب نشده است!", show_alert=True)
        return

    # ساخت متن پیش‌فاکتور
    text = "📄 **پیش‌نمایش نسخه تجویزی:**\n\n"
    total_price = 0

    idx = 1
    for d_id in selected_ids:
        details = drug_cache.get(d_id)
        # نکته: اگر دارویی در کش نباشد (که بعید است) هندل می‌کنیم
        if details:
            name = details['name']
            price = float(details['price'])
            total_price += price
            text += f"{idx}. {name} - {int(price):,} R\n"
            idx += 1
        else:
            text += f"{idx}. داروی کد {d_id} (اطلاعات لود نشد)\n"

    text += "\n------------------------\n"
    text += f"💰 **جمع کل: {int(total_price):,} ریال**\n\n"
    text += "آیا این لیست مورد تایید است؟"

    await callback.message.edit_text(text, reply_markup=create_prescription_review_keyboard(), parse_mode="Markdown")
    # اینجا state عوض نمیشود یا میتوانید یک state جدید Review بگذارید
    # اما چون دکمه "ویرایش" داریم که برمیگردد به دسته ها، همین state اوکی است
    # یا state را به ConsultantFlow.reviewing_order تغییر دهید اگر میخواهید دقیق باشد
    await callback.answer()


# --- مرحله ۷: کلیک روی "ثبت نهایی داروها" ---

@consultant_router.callback_query(F.data == "confirm_final_order")
async def handle_final_submit_order(callback: CallbackQuery, state: FSMContext, api_client: APIClient, bot: Bot):
    await callback.answer("در حال ثبت نهایی...", show_alert=False)

    data = await state.get_data()
    selected_drugs_ids = data.get('selected_drugs')
    patient_telegram_id = data.get('patient_telegram_id')
    patient_full_name = data.get('full_name', 'بیمار')

    # --- کد مربوط به شناسایی مشاور و بیمار (مشابه کد خودتان) ---
    consultant_telegram_id = callback.from_user.id
    consultant_details = await api_client.get_user_details_by_telegram_id(consultant_telegram_id)
    user_id = int(consultant_details['user_id'])

    patient_details = await api_client.get_patient_details_by_telegram_id(patient_telegram_id)
    patient_id = int(patient_details['patient_id'])
    # ---------------------------------------------------------

    try:
        # 1. ثبت سفارش
        drug_ids_list = list(selected_drugs_ids)
        new_order = await api_client.create_order(
            patient_id=patient_id,
            user_id=user_id,
            drug_ids=drug_ids_list
        )

        if not new_order or 'order_id' not in new_order:
            raise ValueError("API Response Error")

        order_id = new_order.get('order_id')

        # 2. تغییر وضعیت بیمار
        await api_client.update_patient_status(patient_telegram_id, PatientStatus.AWAITING_INVOICE_APPROVAL)

        # 3. اطلاع رسانی به بیمار
        try:
            await bot.send_message(
                chat_id=patient_telegram_id,
                text=(
                    "✅ نسخه شما توسط پزشک تجویز شد.\n"
                    "لطفاً جهت مشاهده فاکتور و تایید آن، روی لینک زیر کلیک کنید.\n "
                    "/Order"


                )
            )
        except:
            pass

        # 4. پایان کار
        await callback.message.edit_text(
            f"✅ **سفارش شماره {order_id} با موفقیت ثبت و برای بیمار ارسال شد.**\n\n"
            "می‌توانید بیمار بعدی را انتخاب کنید.",
            reply_markup=get_next_patient_keyboard()
        )
        await state.clear()

    except Exception as e:
        logging.error(f"Order submit error: {e}")
        await callback.message.answer("خطا در ثبت سفارش.")


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
    """
    این هندلر وقتی اجرا می‌شود که مشاور نسخه را ثبت کرده و روی دکمه 'بیمار بعدی' در پیام موفقیت کلیک می‌کند.
    چون State پاک شده، باید دوباره از سرور بپرسیم که نوبت کیست.
    """
    await callback.message.edit_text("🔄 در حال دریافت قدیمی‌ترین پرونده در صف انتظار...")

    # ۱. آیا اصلاً تاریخی مانده که بیمار داشته باشد؟
    unassigned_dates = await api_client.get_waiting_for_consultation_dates()
    if not unassigned_dates:
        await callback.message.edit_text("✅ تمام شد! هیچ بیماری در صف انتظار نیست.")
        await state.clear()
        return

    # ۲. انتخاب قدیمی‌ترین تاریخ (اولویت با قدیمی‌هاست)
    oldest_date = sorted(unassigned_dates)[0]

    # ۳. دریافت لیست بیماران آن تاریخ
    patients_data = await api_client.get_waiting_for_consultation_patients_by_date(oldest_date)

    # هندل کردن فرمت‌های مختلف پاسخ API
    if isinstance(patients_data, list):
        patients = patients_data
    else:
        patients = patients_data.get("patients", [])

    if not patients:
        await callback.message.edit_text(f"⚠️ عجیب است! تاریخی وجود دارد اما بیماری در آن یافت نشد ({oldest_date}).")
        await state.clear()
        return

    # ۴. انتخاب اولین نفر
    # نکته مهم: چون بیمار قبلی وضعیتش تغییر کرده، نفر اول این لیست جدید، همان بیمار بعدی است.
    next_patient = patients[0]
    patient_telegram_id = str(next_patient.get("telegram_id"))

    # ۵. تنظیم مجدد State (چون قبلاً clear شده بود)
    await state.update_data(
        selected_date=oldest_date,
        # patient_ids_for_date را هم ذخیره میکنیم تا دکمه‌های متنی (بعدی/قبلی) کار کنند
        patient_ids_for_date=[str(p.get("telegram_id")) for p in patients]
    )

    # ۶. نمایش اطلاعات بیمار
    # از همان تابع مشترکی که ساختیم استفاده می‌کنیم تا ظاهر یکسان باشد
    await show_patient_full_info(callback.message, state, api_client, patient_telegram_id)

    # پاک کردن پیام لودینگ قبلی
    try:
        await callback.message.delete()
    except:
        pass


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