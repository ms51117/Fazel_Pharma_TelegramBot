# app/core/services/api_client.py

import asyncio
import logging
from typing import Optional

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

        # خواندن اطلاعات از settings
        self._username = settings.API_USERNAME
        self._password = settings.API_PASSWORD.get_secret_value()

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

            url = f"{self._base_url}/users/by-telegram-id/{telegram_id}"
            response = await self._client.get(url, headers=headers)

            response.raise_for_status()

            user_data = response.json()
            role_name = user_data.get("role", {}).get("roleName")

            if role_name:
                logging.info(f"Role for telegram_id {telegram_id} is '{role_name}'.")
                return role_name
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

    async def close(self):
        """
        کلاینت HTTP را به درستی می‌بندد.
        """
        await self._client.aclose()
