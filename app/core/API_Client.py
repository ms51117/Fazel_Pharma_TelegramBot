# app/services/api_client.py

import httpx
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from app.core.setting import settings


class APIClient:
    """
    A client for interacting with the Fazel Pharma API.
    Handles authentication, token management, and API requests.
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self._username = username
        self._password = password
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._client = httpx.AsyncClient(base_url=self.base_url)
        self._token_lock = asyncio.Lock()  # Prevents multiple coroutines from trying to refresh the token at the same time

    async def _login(self) -> None:
        """Logs in to the API and stores the access token."""
        print("🤖 Attempting to log in to the API...")
        try:
            response = await self._client.post(
                "/login/access-token",
                json={"username": self._username, "password": self._password}
            )
            response.raise_for_status()  # Raise exception for 4xx or 5xx status codes

            data = response.json()
            self._token = data["access_token"]

            # Set token expiry time (e.g., 25 minutes for a 30-min token to be safe)
            # This is a client-side expiry check, independent of the actual JWT expiry
            self._token_expiry = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES - 5)

            print("✅ API login successful. Token acquired.")
        except httpx.HTTPStatusError as e:
            print(f"❌ API Login failed! Status: {e.response.status_code}, Response: {e.response.text}")
            raise  # Re-raise the exception to be handled by the caller
        except Exception as e:
            print(f"❌ An unexpected error occurred during API login: {e}")
            raise

    async def _get_valid_token(self) -> str:
        """
        Returns a valid access token, refreshing it if necessary.
        This method is thread-safe (or rather, coroutine-safe).
        """
        async with self._token_lock:
            # Check if token is missing or expired
            if self._token is None or (self._token_expiry and datetime.now(timezone.utc) > self._token_expiry):
                print("⚠️ Token is missing or expired. Refreshing...")
                await self._login()

        if self._token is None:
            # This should not happen if _login is successful
            raise Exception("Failed to obtain a valid token after login attempt.")

        return self._token

    async def get_user_role(self, telegram_id: int) -> Optional[str]:
        """
        Fetches the role of a user from the API by their Telegram ID.
        Returns the role name (e.g., "admin", "Patient") or None if the user has no role.
        Raises an exception if the user is not found or another error occurs.
        """
        token = await self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            response = await self._client.get(
                f"/users/by-telegram-id/{telegram_id}",
                headers=headers
            )

            # If user not found (404), we treat it as a new user (Patient)
            if response.status_code == 404:
                print(f"User with telegram_id {telegram_id} not found in API. Treating as new Patient.")
                return "Patient"  # Default role for unknown users

            response.raise_for_status()  # Raise for other errors

            data = response.json()
            # The API returns {"roleName": "admin"} or {"roleName": null}
            return data.get("roleName") or "Patient"  # If roleName is null, default to Patient

        except httpx.HTTPStatusError as e:
            print(f"Error fetching user role for {telegram_id}: {e.response.status_code} - {e.response.text}")
            # Decide how to handle this. For now, let's re-raise.
            raise
        except Exception as e:
            print(f"An unexpected error occurred while fetching user role: {e}")
            raise

    async def close(self):
        """Closes the underlying HTTPX client."""
        await self._client.aclose()


# Create a single instance of the client to be used throughout the application
# This is an implementation of the Singleton pattern
api_client = APIClient(
    base_url=settings.API_BASE_URL,
    username=settings.API_BOT_USERNAME,
    password=settings.API_BOT_PASSWORD.get_secret_value()
)
