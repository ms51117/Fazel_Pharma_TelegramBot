# app/patient/handlers.py

import logging
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

# --- ورودی‌های مورد نیاز ---
from app.core.API_Client import APIClient
from app.patient.states import PatientRegistration
from app.patient.keyboards import (
    get_start_keyboard,
    get_gender_keyboard,
    get_main_menu_keyboard,
    get_invoice_action_keyboard,  # جدید
    get_cancel_keyboard  # جدید
)
from app.core.enums import PatientStatus

patient_router = Router()


# =========================================================================
# بخش کمکی: نمایش فاکتور
# =========================================================================
async def show_invoice_to_patient(message: Message, patient_id: int, api_client: APIClient):
    """
    فاکتور فعال بیمار را پیدا کرده و با دکمه‌های مناسب به او نمایش می‌دهد.
    """
    await message.answer("در حال دریافت اطلاعات پیش‌فاکتور شما...")
    active_order = await api_client.get_orders_by_status(patient_id)

    if not active_order:
        await message.answer(
            "پیش‌فاکتوری در انتظار تایید برای شما یافت نشد. به منوی اصلی بازگشتید.",
            reply_markup=get_main_menu_keyboard()
        )
        # وضعیت بیمار را هم اصلاح می‌کنیم تا در حلقه نیفتد
        await api_client.update_patient_status(patient_id, PatientStatus.PROFILE_COMPLETED.value)
        return

    order_id = active_order['order_id']
    drugs = active_order.get('drugs', [])
    total_price = active_order.get('total_price', 0)

    # ساخت متن فاکتور
    invoice_text = "📄 **پیش‌فاکتور سفارش شما** 📄\n\n"
    if drugs:
        invoice_text += "لیست داروها:\n"
        for i, drug in enumerate(drugs, 1):
            invoice_text += f"{i}. **{drug['name']}** - تعداد: {drug['quantity']}\n"
    else:
        invoice_text += "هنوز دارویی برای این سفارش ثبت نشده است.\n"

    invoice_text += f"\n-----------------------------------\n"
    invoice_text += f"💰 **مبلغ نهایی:** `{total_price:,.0f}` تومان\n\n"
    invoice_text += "لطفاً پیش‌فاکتور را بررسی و در صورت تایید، به مرحله پرداخت بروید. در غیر این صورت، می‌توانید درخواست ویرایش ثبت کنید."

    await message.answer(
        invoice_text,
        reply_markup=get_invoice_action_keyboard(order_id),
        parse_mode="Markdown"
    )


# =========================================================================
# 1. مرکز فرماندهی: هندلر /start (نسخه پیشرفته)
# =========================================================================
@patient_router.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext, api_client: APIClient):
    """
    نقطه شروع و مرکز فرماندهی ربات برای بیماران.
    """
    await state.clear()
    telegram_id = message.from_user.id

    await message.answer("سلام! خوش آمدید. لطفاً چند لحظه صبر کنید...", reply_markup=ReplyKeyboardRemove())

    patient_data = await api_client.get_patient_details_by_telegram_id(telegram_id)

    if not patient_data:
        new_patient_payload = {"user": {"telegram_id": str(telegram_id)}, "status": PatientStatus.AWAITING_CONSULTATION.value}
        created_patient = await api_client.create_patient_profile(new_patient_payload)

        if not created_patient:
            await message.answer("متاسفانه در حال حاضر امکان ثبت‌نام وجود ندارد. لطفاً بعداً دوباره تلاش کنید.")
            return

        await state.update_data(patient_id=created_patient['patient_id'])
        await message.answer(
            "به داروخانه آنلاین ما خوش آمدید! برای استفاده از خدمات، ابتدا باید پروفایل خود را تکمیل کنید.",
            reply_markup=get_start_keyboard()
        )
        return

    patient_id = patient_data['patient_id']
    await state.update_data(patient_id=patient_id)

    try:
        current_status = PatientStatus(patient_data.get("status"))
    except (ValueError, TypeError):
        logging.error(f"وضعیت نامعتبر '{patient_data.get('status')}' برای بیمار با شناسه {patient_id}")
        await message.answer("وضعیت شما در سیستم نامشخص است. لطفاً با پشتیبانی تماس بگیرید.")
        return

    # مسیردهی هوشمند بر اساس وضعیت
    if current_status in [PatientStatus.AWAITING_CONSULTATION, PatientStatus.AWAITING_PROFILE_COMPLETION]:
        await message.answer("پروفایل شما هنوز کامل نشده است. لطفاً فرآیند ثبت‌نام را تکمیل کنید.",
                             reply_markup=get_start_keyboard())
    elif current_status == PatientStatus.AWAITING_INVOICE_APPROVAL:
        await show_invoice_to_patient(message, patient_id, api_client)
    elif current_status == PatientStatus.PROFILE_COMPLETED:
        await message.answer("خوش آمدید! از منوی زیر، خدمت مورد نظر خود را انتخاب کنید:",
                             reply_markup=get_main_menu_keyboard())
    else:  # برای سایر وضعیت‌ها مثل AWAITING_PAYMENT و...
        # می‌توانید منطق مشابهی را اضافه کنید
        await message.answer("خوش آمدید!", reply_markup=get_main_menu_keyboard())


# =========================================================================
# 2. فرآیند ثبت‌نام پروفایل (با اعتبارسنجی ورودی)
# =========================================================================
@patient_router.callback_query(F.data == "start_registration")
async def start_registration_callback(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    data = await state.get_data()
    patient_id = data.get("patient_id")
    if patient_id:
        await api_client.update_patient_status(patient_id, PatientStatus.AWAITING_PROFILE_COMPLETION.value)

    await callback.message.edit_text("لطفاً نام و نام خانوادگی خود را وارد کنید:")
    await state.set_state(PatientRegistration.waiting_for_full_name)
    await callback.answer()


@patient_router.message(PatientRegistration.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    if len(message.text) < 3:  # اعتبارسنجی ساده
        await message.answer("نام وارد شده بسیار کوتاه است. لطفاً نام و نام خانوادگی کامل خود را وارد کنید.")
        return
    await state.update_data(full_name=message.text)
    await message.answer("لطفاً جنسیت خود را انتخاب کنید:", reply_markup=get_gender_keyboard())
    await state.set_state(PatientRegistration.waiting_for_gender)


@patient_router.callback_query(PatientRegistration.waiting_for_gender, F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    await state.update_data(gender="male" if callback.data == "gender_male" else "female")
    await callback.message.edit_text("لطفاً سن خود را (به عدد) وارد کنید:")
    await state.set_state(PatientRegistration.waiting_for_age)
    await callback.answer()


@patient_router.message(PatientRegistration.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 120):
        await message.answer("⚠️ ورودی نامعتبر! لطفاً سن خود را به صورت یک عدد صحیح (مثلاً 35) وارد کنید.")
        return
    await state.update_data(age=int(message.text))
    await message.answer("لطفاً وزن خود را (به کیلوگرم) وارد کنید. برای مثال: 75 یا 75.5")
    await state.set_state(PatientRegistration.waiting_for_weight)


@patient_router.message(PatientRegistration.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(',', '.'))
        if not (10 <= weight <= 300):
            raise ValueError
        await state.update_data(weight=weight)
        await message.answer("لطفاً قد خود را (به سانتی‌متر) وارد کنید. برای مثال: 180")
        await state.set_state(PatientRegistration.waiting_for_height)
    except ValueError:
        await message.answer("⚠️ ورودی نامعتبر! لطفاً وزن خود را به صورت یک عدد (مثلاً 75.5) وارد کنید.")


@patient_router.message(PatientRegistration.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit() or not (50 <= int(message.text) <= 250):
        await message.answer(
            "⚠️ ورودی نامعتبر! لطفاً قد خود را به سانتی‌متر و به صورت یک عدد صحیح (مثلاً 180) وارد کنید.")
        return
    await state.update_data(height=int(message.text))
    await message.answer(
        "در انتها، لطفاً توضیحات مختصری در مورد بیماری یا نیاز دارویی خود بنویسید (اختیاری).\nمی‌توانید بنویسید 'ندارم'.")
    await state.set_state(PatientRegistration.waiting_for_disease_description)


@patient_router.message(PatientRegistration.waiting_for_disease_description)
async def process_disease_description_and_finish(message: Message, state: FSMContext, api_client: APIClient):
    await state.update_data(disease_description=message.text)
    user_data = await state.get_data()
    patient_id = user_data.get("patient_id")

    if not patient_id:
        await message.answer("خطای داخلی: شناسه بیمار یافت نشد. لطفاً با /start مجدداً شروع کنید.")
        await state.clear()
        return

    update_payload = {k: v for k, v in {
        "full_name": user_data.get("full_name"),
        "sex": user_data.get("gender"),
        "age": user_data.get("age"),
        "weight": user_data.get("weight"),
        "height": user_data.get("height"),
        "specific_diseases": user_data.get("disease_description")
    }.items() if v is not None}

    success = await api_client.update_patient(patient_id, update_payload)

    if not success:
        await message.answer("خطایی در ذخیره‌سازی اطلاعات رخ داد. لطفاً با پشتیبانی تماس بگیرید.")
        await state.clear()
        return

    await api_client.update_patient_status(patient_id, PatientStatus.PROFILE_COMPLETED.value)
    await state.clear()

    await message.answer(
        "🎉 پروفایل شما با موفقیت تکمیل شد! 🎉\nاکنون می‌توانید از خدمات ربات استفاده کنید.",
        reply_markup=get_main_menu_keyboard()
    )


# =========================================================================
# 3. هندلرهای مربوط به فاکتور و سایر عملیات
# =========================================================================
@patient_router.callback_query(F.data.startswith("invoice_approve_"))
async def approve_invoice_callback(callback: CallbackQuery, state: FSMContext, api_client: APIClient):
    order_id = int(callback.data.split("_")[-1])
    # وضعیت سفارش را به "منتظر پرداخت" تغییر می‌دهیم
    # success = await api_client.update_order_status(order_id, OrderStatus.AWAITING_PAYMENT.value)
    # await api_client.update_patient_status(patient_id, PatientStatus.AWAITING_PAYMENT.value)

    # فعلا فقط یک پیام نمایش می‌دهیم
    await callback.message.edit_text(
        f"فاکتور شما برای سفارش شماره {order_id} تایید شد.\n"
        "در حال حاضر درگاه پرداخت متصل نیست. این مرحله به زودی تکمیل خواهد شد."
    )
    await callback.answer()


@patient_router.callback_query(F.data.startswith("invoice_edit_"))
async def edit_invoice_callback(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    await state.update_data(editing_order_id=order_id)
    await callback.message.edit_text(
        "لطفاً توضیحات خود برای ویرایش فاکتور را در یک پیام برای ما ارسال کنید.\n"
        "مثال: «لطفاً داروی X را حذف و داروی Y را اضافه کنید.»",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(PatientRegistration.waiting_for_edit_request)
    await callback.answer()


@patient_router.message(PatientRegistration.waiting_for_edit_request)
async def process_edit_request(message: Message, state: FSMContext, api_client: APIClient):
    data = await state.get_data()
    order_id = data.get("editing_order_id")
    edit_message = message.text

    if order_id:
        success = await api_client.request_order_edit(order_id, edit_message)
        if success:
            await message.answer(
                "✅ درخواست ویرایش شما با موفقیت ثبت شد.\n"
                "پس از بررسی توسط مشاور، نتیجه به شما اطلاع داده خواهد شد. به منوی اصلی بازگشتید."
            )
            # وضعیت بیمار را تغییر می‌دهیم تا دوباره به او فاکتور نمایش داده نشود
            patient_id = data.get("patient_id")
            if patient_id:
                await api_client.update_patient_status(patient_id, PatientStatus.AWAITING_CONSULTATION.value)
        else:
            await message.answer("خطایی در ثبت درخواست ویرایش رخ داد. لطفاً با پشتیبانی تماس بگیرید.")

    await state.clear()


@patient_router.callback_query(F.data == "cancel_action")
async def cancel_action_callback(callback: CallbackQuery, state: FSMContext):
    """عملیات فعلی در FSM را لغو کرده و به کاربر پیام مناسب می‌دهد."""
    await state.clear()
    await callback.message.edit_text("عملیات لغو شد. برای شروع مجدد از دستور /start استفاده کنید.")
    await callback.answer()


# =========================================================================
# 4. هندلر پیام‌های پیش‌بینی نشده (Catch-all Handler)
# =========================================================================
@patient_router.message()
async def unhandled_message_handler(message: Message):
    """
    هر پیامی که توسط هندلرهای قبلی مدیریت نشود، به اینجا می‌رسد.
    """
    await message.answer(
        "⛔️ دستور یا پیام شما را متوجه نشدم.\n"
        "لطفاً از دکمه‌های موجود استفاده کنید یا برای شروع مجدد، دستور /start را ارسال کنید."
    )
