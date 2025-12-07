# app/core/services/api_client.py
import aiohttp
import asyncio

import asyncio
import logging
import os
from http.client import responses
from typing import Optional, Union, List, Dict,Any

import httpx
from httpx import AsyncClient, HTTPStatusError

from app.core.setting import settings


class APIClient:
    """
    یک کلاینت Async برای تعامل با FastAPI بک‌اند.
    این کلاس مسئول لاگین کردن، مدیریت توکن JWT و ارسال درخواست‌ها است.
    """

    def __init__(self, base_url: str):
        self._base_url = base_url
        self._client = AsyncClient()
        self._token: Optional[str] = None
        self._lock = asyncio.Lock()

        self._content_cache: Dict[str, str] = {}


        # خواندن اطلاعات از settings
        self._username = settings.API_USERNAME
        self._password = settings.API_PASSWORD.get_secret_value()
        if not self._base_url.startswith(("http://", "https://")):
            self.base_url = f"http://{self._base_url}"
    async def _login(self) -> None:
        """
        با استفاده از نام کاربری و رمز عبور سیستم، لاگین کرده و توکن JWT را دریافت می‌کند.
        این متد داده‌ها را به صورت JSON ارسال می‌کند تا با بک‌اند FastAPI هماهنگ باشد.
        """
        login_data = {
            "username": self._username,
            "password": self._password,
        }
        try:
            logging.info(f"Attempting to login to the API with JSON payload for user '{self._username}'...")

            # --- تغییر کلیدی اینجاست ---
            response = await self._client.post(
                f"{self._base_url}/login/access-token",
                json=login_data  # استفاده از 'json' برای ارسال application/json
            )
            # --------------------------

            response.raise_for_status()

            token_data = response.json()
            self._token = token_data.get("access_token")

            if not self._token:
                logging.error("Login successful, but no access token found in response.")
                raise ValueError("Access token not in response")

            logging.info("Successfully logged in and got the token.")

        except HTTPStatusError as e:
            error_details = ""
            try:
                error_details = e.response.json()
            except Exception:
                error_details = e.response.text
            logging.error(f"HTTP error during login: {e.response.status_code} - Details: {error_details}")
            raise
        except Exception as e:
            logging.error(f"An unexpected error occurred during login: {e}")
            raise

    async def login_check(self):
        """
        بررسی می‌کند که آیا توکن وجود دارد یا خیر. اگر وجود نداشت، لاگین می‌کند.
        """
        async with self._lock:
            if not self._token:
                logging.warning("Token is missing. Attempting to log in...")
                await self._login()
        return self._token

    async def get_user_role(self, telegram_id: int) -> str:
        """
        نقش کاربر را بر اساس شناسه تلگرام از API دریافت می‌کند.
        اگر کاربر پیدا نشد (404)، نقش پیش‌فرض "Patient" را برمی‌گرداند.
        """
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}

            url = f"{self._base_url}/user/role-by-telegram-id/{telegram_id}"
            response = await self._client.get(url, headers=headers)

            response.raise_for_status()

            user_data = response.json()
            role_name = user_data.get("role_name")
            logging.info(role_name)

            if role_name:
                logging.info(f"Role for telegram_id {telegram_id} is '{role_name}'.")
                return role_name
            elif role_name is None:
                logging.warning(f"User with telegram_id {telegram_id} found, but has no role name.")
                return "Patient"
            else:
                logging.warning(f"User with telegram_id {telegram_id} found, but has no role name.")
                return "Patient"

        except HTTPStatusError as e:
            if e.response.status_code == 404:
                logging.info(f"User with telegram_id {telegram_id} not found. Assigning 'Patient' role.")
                return "Patient"
            else:
                logging.error(
                    f"HTTP error getting user role for {telegram_id}: {e.response.status_code} - {e.response.text}")
                return "Patient"
        except Exception as e:
            logging.error(f"Unexpected error getting user role for {telegram_id}: {e}")
            return "Patient"

    async def create_patient_profile(self, patient_data: dict) -> Optional[Union[int, str]]:
        """
        Sends patient registration data to the backend API and returns the new patient's ID.

        Args:
            patient_data: A dictionary matching the PatientCreate schema.

        Returns:
            The patient_id (int, str, or UUID) if creation was successful.
            None if any error occurred.
        """
        try:
            token = await self.login_check()
            if not token:
                logging.error("Authentication failed. Cannot create patient profile.")
                return None  # اگر توکن دریافت نشد، ادامه نده

            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/patient/"

            logging.info(f"Sending new patient profile to API for telegram_id: {patient_data.get('user_telegram_id')}")

            # ارسال درخواست به API
            response = await self._client.post(url, headers=headers, json=patient_data)

            # بررسی دقیق کد وضعیت؛ فقط 201 به معنای موفقیت است
            if response.status_code == 201:
                # 1. پاسخ را به فرمت JSON تبدیل می‌کنیم
                response_data = response.json()

                # 2. مقدار 'patient_id' را از دیکشنری JSON استخراج می‌کنیم
                patient_id = response_data.get("patient_id")

                if patient_id:
                    logging.info(f"Successfully created patient profile with ID: {patient_id}")
                    # 3. به جای True، مقدار استخراج شده را برمی‌گردانیم
                    return patient_id
                else:
                    # اگر کد 201 بود اما patient_id در پاسخ وجود نداشت، این یک خطای غیرمنتظره در API است
                    logging.error(
                        f"API returned 201 Created but 'patient_id' is missing in the response. Response: {response.text}")
                    return None

            # برای سایر کدها، خطا را لاگ می‌گیریم و None برمی‌گردانیم
            logging.error(
                f"Failed to create patient profile. Status: {response.status_code}, Response: {response.text}")

            # این خط برای دیباگ کردن بسیار مفید است. اگر API خطایی مثل 400 یا 500 برگرداند،
            # این خط یک استثنا (Exception) ایجاد می‌کند که در بلوک except گرفته می‌شود.
            response.raise_for_status()
            return None  # این خط در عمل اجرا نمی‌شود چون خط بالا استثنا ایجاد می‌کند، اما برای خوانایی خوب است

        except httpx.HTTPStatusError as e:
            # این خطا زمانی رخ می‌دهد که response.raise_for_status() فراخوانی شود و کد وضعیت 4xx یا 5xx باشد
            logging.error(f"HTTP error creating patient profile: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            # این خطا برای مشکلات شبکه مثل عدم اتصال به سرور است
            logging.error(f"A network error occurred while creating patient profile: {e}")
            return None
        except Exception as e:
            # گرفتن هر خطای پیش‌بینی نشده دیگر
            logging.error(f"An unexpected error occurred while creating patient profile: {e}", exc_info=True)
            return None

    # ^^^^^^ پایان متد جدید ^^^^^^



    # -------------------------------------------------------

    async def get_waiting_for_consultation_dates(self) -> list[str] | None:
        """Fetches dates with unassigned patients."""
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/patient/waiting-for-consultation-dates/"
            logging.info(url)

            logging.info("Fetching unassigned patient dates from API.")
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()

            dates = response.json()  # API باید لیستی از رشته‌های تاریخ را برگرداند
            dates_list = dates.get("dates", [])

            logging.info(f"Found {len(dates_list)} unassigned dates.")
            return dates_list
        except Exception as e:
            logging.error(f"Error fetching unassigned dates: {e}")
            return None

    async def get_waiting_for_consultation_patients_by_date(self, date: str) -> list[dict] | None:
        """Fetches patients for a specific unassigned date."""
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/patient/awaiting-for-consultation-by-date/{date}"

            logging.info(f"Fetching patients for date: {date}")
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()

            patients = response.json()  # API باید لیستی از دیکشنری‌های بیمار را برگرداند
            patients_list = patients.get("patients", [])

            logging.info(f"Found {len(patients_list)} patients for date {date}.")
            return patients_list
        except Exception as e:
            logging.error(f"Error fetching patients for date {date}: {e}")
            return None

    async def get_patient_details_by_telegram_id(self, telegram_id: str) -> dict | None:
        """Fetches full details of a single patient by their database ID."""
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/patient/{telegram_id}"

            logging.info(f"Fetching details for telegram_id: {telegram_id}")
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()

            patient_details = response.json()
            logging.info(f"Successfully fetched details for telegram_id: {telegram_id}")
            return patient_details
        except Exception as e:
            logging.error(f"Error fetching patient details for telegram_id {telegram_id}: {e}")
            return None

    # -----------------------------------------------------

    async def get_user_details_by_telegram_id(self, telegram_id: int) -> dict | None:
        """Fetches full details of a single patient by their database ID."""
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/user/read-by-telegram-id/{telegram_id}"

            logging.info(f"Fetching details for telegram_id: {telegram_id}")
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()

            patient_details = response.json()
            logging.info(f"Successfully fetched details for telegram_id: {telegram_id}")
            return patient_details
        except Exception as e:
            logging.error(f"Error fetching user details for telegram_id {telegram_id}: {e}")
            return None


    # ---------------------------------------------------

    async def get_all_disease_types(self) -> list[dict] | None:
        """Fetches all available disease types from the API."""
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/disease/"

            logging.info("Fetching all disease types from API.")
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()

            disease_types = response.json()
            logging.info(f"Found {len(disease_types)} disease types.")
            return disease_types
        except Exception as e:
            logging.error(f"Error fetching disease types: {e}")
            return None

    async def get_drugs_by_disease_type(self, disease_type_id: int) -> list[dict] | None:
        """Fetches drugs for a specific disease type ID."""
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/drug/read-drug-by-type/{disease_type_id}"

            logging.info(f"Fetching drugs for disease_type_id: {disease_type_id}")
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()

            drugs = response.json()
            logging.info(f"Found {len(drugs)} drugs for disease type {disease_type_id}.")
            return drugs
        except Exception as e:
            logging.error(f"Error fetching drugs for disease type {disease_type_id}: {e}")
            return None
    # ---------------- create message --------------------------------
    async def create_message(
            self,
            patient_id: int,
            user_id: Optional[int] = None,
            message_content: Optional[str] = None,
            messages_sender: Optional[bool] = True,
            attachments: Optional[List[str]] = None
    ) -> Optional[bytes] | None:
        """
        یک پیام/تیکت جدید در سیستم ایجاد می‌کند. (نسخه کامل و انعطاف‌پذیر)

        این متد می‌تواند برای سناریوهای مختلف استفاده شود:
        1. ایجاد پیام اولیه توسط بیمار (بدون user_id و بدون پیوست).
        2. ارسال پیام متنی توسط بیمار یا مشاور.
        3. ارسال پیام حاوی یک یا چند فایل پیوست (با یا بدون متن).

        Args:
            patient_id (int): شناسه بیمار که این پیام به او تعلق دارد.
            user_id (Optional[int]): شناسه مشاور. در پیام‌های اولیه بیمار، این مقدار None است.
            message_content (Optional[str]): محتوای متنی پیام.
            messages_sender (bool): جهت پیام. True = از طرف بیمار/سیستم، False = از طرف مشاور.
            attachments (Optional[List[str]]): لیستی از مسیرهای فایل‌های پیوست.

        Returns:
            Optional[Dict]: دیکشنری حاوی اطلاعات پیام ایجاد شده در صورت موفقیت، در غیر این صورت None.
        """
        try:
            token = await self.login_check()
            if not token:
                logging.error("Authentication failed. Cannot create message.")
                return None

            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/message/"

            # ساختار payload دقیقاً مطابق با اسکیمای FastAPI/Swagger
            payload = {
                "patient_id": patient_id,
                "user_id": user_id,  # می‌تواند None باشد
                "messages": message_content ,  # می‌تواند None باشد
                "messages_sender": messages_sender,
                "messages_seen": False,  # پیام جدید همیشه خوانده نشده است
                "attachment_path": attachments if attachments else None  # اگر None بود، لیست خالی ارسال شود
            }

            logging.info(f"Sending request to create message with payload: {payload}")

            response = await self._client.post(url, headers=headers, json=payload)

            if response.status_code == 201:  # 201 Created
                created_message = response.json()
                logging.info(f"Successfully created message with ID: {created_message.get('messages_id')}")
                return True
            else:
                # اگر کد وضعیت خطا بود، آن را لاگ و مدیریت کن
                logging.error(f"Failed to create message. Status: {response.status_code}, Response: {response.text}")
                response.raise_for_status()  # این خط جزئیات بیشتری از خطا را نمایش می‌دهد
                return False

        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP status error while creating message for patient {patient_id}: {e}")
            return False
        except Exception as e:
            logging.error(f"An unexpected error occurred while creating message for patient {patient_id}: {e}",
                          exc_info=True)
            return False

    # ---------------------------------------------------------------------------------------------------------
    async def create_order(self, patient_id: int, user_id: int, drug_ids: list[int]) -> dict:
        """
        Calls the backend API to create a new order with its items.
        """
        try:
            token = await self.login_check()
            if not token:
                logging.error("Authentication failed. Cannot create order.")
                return None

            headers = {"Authorization": f"Bearer {token}"}
            # این آدرس باید با آدرسی که در api.py بک‌اند ثبت کرده‌اید مطابقت داشته باشد
            # معمولاً /api/v1/orders/ است.
            url = f"{self._base_url}/order/"

            # Payload بر اساس اسکیمای OrderCreate در بک‌اند
            # همانطور که بحث شد، order_status را اینجا ارسال نمی‌کنیم.
            payload = {
                "patient_id": patient_id,
                "user_id": user_id,
                "drug_ids": drug_ids
            }

            logging.info(f"Sending request to create order with payload: {payload}")
            response = await self._client.post(url, headers=headers, json=payload)

            # FastAPI در صورت موفقیت کد 200 یا 201 را برمی‌گرداند.
            if response.status_code in [200, 201]:
                created_order = response.json()
                logging.info(f"Successfully created order with ID: {created_order.get('order_id')}")
                return created_order
            else:
                logging.error(f"Failed to create order. Status: {response.status_code}, Response: {response.text}")
                response.raise_for_status()  # برای نمایش خطای دقیق‌تر در لاگ‌ها
                return None

        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP status error while creating order: {e}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred while creating order: {e}", exc_info=True)
            return None
    # --------------------------------------------------------------------------------------

    async def update_patient_status(self, patient_id: str, new_status: str) -> bool:
        """
        Updates only the status of a specific patient.
        """
        payload = {"patient_status": new_status}
        try:
            # از متد update_patient موجود استفاده می‌کنیم
            return await self.update_patient(patient_id, payload)
        except Exception as e:
            logging.error(f"Failed to update patient {patient_id} status to {new_status}: {e}")
            return False

    async def update_patient(self, patient_telegram_id: str, patient_data: Dict[str, Any]) -> bool:
        """
        Updates a patient's data. Can be used for full updates or partial ones (like status).
        """
        try:
            token = await self.login_check()
            if not token:
                logging.error("Authentication failed. Cannot update patient.")

                return False

            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/patient/{patient_telegram_id}"  # مطمئن شوید پیشوند /api/v1 یا معادل آن در base_url هست

            response = await  self._client.patch(url, headers=headers, json=patient_data)
            response.raise_for_status()
            logging.info(f"Successfully updated patient {patient_telegram_id} with data: {patient_data}")
            return True
        except Exception as e:
            logging.error(f"Error updating patient {patient_telegram_id}: {e}")
            return False

    # ------------------------------------------------------------------


    # ***********
    async def get_orders_by_status(self, patient_id: int, status: str) -> List[dict] | None:
        """
        سفارشات یک بیمار را بر اساس وضعیت آنها از API دریافت می‌کند.
        e.g., GET /api/v1/orders/?patient_id=123&status=created
        """
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}

            query_params = {
                "patient_id": patient_id,
                "order_status": status
            }

            url = f"{self._base_url}/order/get-order-by-status-by-patient-id/"  # مسیر اصلی endpoint
            logging.info(f"Fetching orders for patient {patient_id} with status '{status}'")

            response = await self._client.get(url, headers=headers, params=query_params)

            if response.status_code == 404:  # اگر endpoint پیدا نشد (بعید است)
                logging.warning(f"Orders endpoint not found.")
                return None

            response.raise_for_status()

            orders = response.json()
            if not orders:
                logging.info(f"No orders with status '{status}' found for patient {patient_id}.")
                return []  # بازگرداندن لیست خالی اگر سفارشی یافت نشد

            return orders

        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP error fetching orders for patient {patient_id}: {e.response.status_code}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error fetching orders for patient {patient_id}: {e}")
            return None

    async def update_order(
            self,
            order_id: int,
            order_status: Optional[str] = None,
            order_items: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        یک سفارش موجود را با استفاده از اندپوینت جامع PATCH به‌روزرسانی می‌کند.

        Args:
            order_id (int): شناسه سفارشی که باید آپدیت شود.
            order_status (Optional[str]): وضعیت جدید سفارش (مثلاً "Awaiting Payment").
                                          اگر None باشد، ارسال نمی‌شود.
            order_items (Optional[List[Dict[str, Any]]]): لیست جدید آیتم‌های سفارش.
                                                        هر آیتم باید دیکشنری با کلیدهای 'drug_id' و 'qty' باشد.
                                                        اگر None باشد، ارسال نمی‌شود.

        Returns:
            Optional[Dict[str, Any]]: دیکشنری حاوی اطلاعات سفارش آپدیت شده در صورت موفقیت،
                                     در غیر این صورت None.
        """
        url = f"{self._base_url}/order/{order_id}"  # توجه: مسیر را به /order/{order_id} تغییر دادم
        token = await self.login_check()
        headers = {"Authorization": f"Bearer {token}"}
        # 1. ساخت Payload به صورت دینامیک
        # فقط فیلدهایی که مقدار دارند (None نیستند) به payload اضافه می‌شوند.
        payload = {}
        if order_status is not None:
            payload["order_status"] = order_status

        if order_items is not None:
            # این بخش اطمینان حاصل می‌کند که ساختار لیست درست است.
            # نیازی به استفاده از OrderItemUpdate در اینجا نیست، چون aiohttp دیکشنری را به JSON تبدیل می‌کند.
            payload["order_items"] = order_items

        # اگر هیچ داده‌ای برای آپدیت وجود نداشت، درخواست را ارسال نکن.
        if not payload:
            logging.warning(f"update_order called for order {order_id} with no data to update.")
            return None

        logging.info(f"Sending PATCH request to {url} with payload: {payload}")

        # 2. ارسال درخواست PATCH
        try:
            response = await self._client.patch(url,json=payload, headers=headers)
            response_data = response.json()
            if response.status_code == 200:
                logging.info(f"Order {order_id} updated successfully. Response: {response_data}")
                return response_data
            else:
                logging.error(
                    f"Failed to update order {order_id}. "
                    f"Status: {response.status_code}, Response: {response_data}"
                )
                return None
        except Exception as e:
            logging.exception(f"An exception occurred while trying to update order {order_id}: {e}")
            return None
    # ----------------------------------------------------------



    async def create_payment(self, payment_data: dict) -> Optional[dict]:
        """
        یک رکورد پرداخت جدید برای یک سفارش ایجاد می‌کند.
        """
        url = f"{self._base_url}/payment/"  # فرض می‌کنیم چنین اندپوینتی دارید
        token = await self.login_check()
        headers = {"Authorization": f"Bearer {token}"}
        logging.info(f"Sending POST request to create a new payment with data: {payment_data}")
        try:

            response = await self._client.post(url, json=payment_data, headers=headers)
            if response.status_code == 201:  # معمولا برای ساخت 201 برمی‌گردد
                response_data = response.json()
                logging.info(f"Payment created successfully: {response_data}")
                return response_data
            else:
                logging.error(
                    f"Failed to create payment. Status: {response.status_code}, Response: {response.json()}")
                return None
        except Exception as e:
            logging.exception(f"An exception occurred while creating payment: {e}")
            return None



    # -----------------------------------------------------------------------------

    async def get_pending_payment_dates(self) -> Optional[list[str]]:
        """Fetches dates with 'NOT_SEEN' payments."""
        # فرض می‌کنیم پاسخ API به شکل {"dates": [...]} است
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/payment/not-seen/"
            # مسیر اندپوینت خود را جایگزین کنید
            response = await self._client.get(url, headers=headers)
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching pending payment dates: {e}")
            return None

    async def get_pending_payments_by_date(self, date_str: str) -> Optional[list[dict]]:
        """Fetches pending payments for a date using the DatePaymentListRead schema."""
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/payment/not-seen/by-date/{date_str}"
            # مسیر اندپوینت خود را جایگزین کنید
            response = await self._client.get(url, headers=headers)
            return response.json()  # API باید مستقیما لیست را برگرداند
        except Exception as e:
            logging.error(f"Error fetching pending payments for date {date_str}: {e}")
            return None

    async def update_payment(self, payment_id: int, payload: dict) -> Optional[dict]:
        """
        Updates a payment record using PATCH.
        Used for approving or rejecting a payment.
        """
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"{self._base_url}/payment/{payment_id}"

            logging.info(f"Sending PATCH to {url} with payload: {payload}")  # لاگ کردن دیتای ارسالی

            response = await self._client.patch(url, headers=headers, json=payload)

            # اگر کد وضعیت 400 تا 500 باشد، اینجا خطا پرتاب می‌شود و متن آن را می‌خوانیم
            response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as e:
            # === این بخش دلیل دقیق ارور 422 را چاپ می‌کند ===
            logging.error(f"HTTP Error {e.response.status_code} for payment {payment_id}.")
            logging.error(f"Server Response: {e.response.text}")
            return None

        except Exception as e:
            logging.error(f"Unexpected error updating payment {payment_id}: {e}", exc_info=True)
            return None

    async def read_messages_history_by_patient_id(self, patient_id: int) -> list[dict]:
        """
        تاریخچه چت بین مشاور و بیمار را از سرور دریافت می‌کند.
        پاسخ باید شامل لیست پیام‌ها باشد.
        """
        token = await self.login_check()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self._base_url}/message/history/{patient_id}"

        try:
            response = await self._client.get(url, headers=headers)
            if response.status_code == 200 or response.status_code == 200:
                # ✅ await برای json ضروری است
                data = response.json()
                # بررسی نوع داده – بک‌اند گاهی ممکن است dict برگرداند
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return [data]
                else:
                    logging.error(f"Unexpected data type from /message/history/: {type(data)}")
                    return []
            else:
                text = response.text
                logging.error(
                    f"Error response {response.status_code if hasattr(response, 'status_code') else response.status_code}: {text}")
                return []
        except Exception as e:
            logging.error(f"Error fetching messages: {e}", exc_info=True)
            return []

    # app/core/services/api_client.py

    async def get_order_items(self, order_id: int) -> list[dict]:
        """
        دریافت لیست اقلام یک سفارش خاص.
        """
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            # فرض بر این است که اندپوینتی برای گرفتن جزئیات سفارش دارید
            # اگر ندارید، باید بر اساس ساختار دیتابیس خودتان پیاده‌سازی کنید
            url = f"{self._base_url}/order/{order_id}"

            response = await self._client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # فرض می‌کنیم خروجی شامل لیستی به نام items یا drugs است
                return data.get("items", [])
            return []
        except Exception as e:
            logging.error(f"Error fetching order items: {e}")
            return []

    async def get_order_by_id(self, order_id: int) -> dict | None:
        """
        دریافت جزئیات کامل یک سفارش با استفاده از ID
        """
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            # طبق روت‌های شما در full_project_code، روت سفارش /order است
            url = f"{self._base_url}/order/{order_id}"

            logging.info(f"Fetching order details for ID: {order_id}")
            response = await self._client.get(url, headers=headers)

            # اگر 404 بدهد یعنی پیدا نشده
            if response.status_code == 404:
                logging.warning(f"Order {order_id} not found.")
                return None

            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching order {order_id}: {e}")
            return None

    async def get_drug_details_by_id(self, drug_id: int) -> dict | None:
        """
        دریافت مشخصات یک دارو (نام، قیمت و...) با استفاده از ID
        """
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            # طبق روت‌های شما، روت دارو /drug است
            url = f"{self._base_url}/drug/{drug_id}"

            # logging.info(f"Fetching drug details for ID: {drug_id}") # لاگ زیاد نشود کامنت کردم
            response = await self._client.get(url, headers=headers)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching drug {drug_id}: {e}")
            return None

    async def get_user_details_by_id(self, user_id: int) -> dict | None:
        """
        دریافت مشخصات کاربر (مشاور/پزشک) با استفاده از ID دیتابیس
        (متد قبلی شما با telegram_id کار می‌کرد، این با id کار می‌کند)
        """
        try:
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"}
            # فرض بر این است که روت user امکان خواندن با ID را دارد (مثلا /user/{id})
            # اگر روت خاصی دارید مثل /user/read/{id} آدرس را تغییر دهید
            url = f"{self._base_url}/user/{user_id}"

            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching user {user_id}: {e}")
            return None

    # ---------------- BOT CONTENT MANAGEMENT (CMS) ----------------

    async def get_bot_message(self, key: str, default: str = "") -> str:
        """
        متن پیام را بر اساس کلید (key) از سیستم دریافت می‌کند.

        الگوریتم:
        1. ابتدا کش (حافظه رم) بررسی می‌شود.
        2. اگر نبود، به API درخواست می‌زند.
        3. پاسخ API را در کش ذخیره می‌کند تا دفعات بعد سریع‌تر باشد.
        """
        # 1. بررسی کش
        if key in self._content_cache:
            return self._content_cache[key]

        try:
            # اطمینان از وجود توکن (هرچند روت ممکن است پابلیک باشد، ارسال توکن استانداردتر است)
            token = await self.login_check()
            headers = {"Authorization": f"Bearer {token}"} if token else {}

            # آدرس اندپوینت جدیدی که ساختیم
            url = f"{self._base_url}/bot-message/key/{key}"

            # 2. درخواست به سرور
            response = await self._client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                # طبق اسکیمای BotMessageRead، فیلد متن پیام message_text است
                text = data.get("message_text")

                if text:
                    # 3. ذخیره در کش
                    self._content_cache[key] = text
                    return text
                else:
                    return default

            elif response.status_code == 404:
                logging.warning(f"CMS: Message key '{key}' not found in DB. Using default text.")
                return default
            else:
                logging.error(f"CMS: Error fetching '{key}'. Status: {response.status_code}")
                return default

        except Exception as e:
            logging.error(f"CMS: Unexpected error fetching '{key}': {e}")
            return default

    def clear_content_cache(self):
        """
        پاک کردن حافظه موقت پیام‌ها.
        این متد زمانی کاربرد دارد که ادمین متنی را تغییر داده و می‌خواهد
        ربات بدون ریستارت شدن، متن جدید را بگیرد.
        """
        self._content_cache.clear()
        logging.info("CMS: Bot content cache cleared successfully.")

    async def close(self):
        """
        کلاینت HTTP را به درستی می‌بندد.
        """
        await self._client.aclose()
