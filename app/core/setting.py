# app/core/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    """
    Main settings class for the application.
    Reads environment variables from the .env file.
    """

    # مدل تنظیمات: مشخص می‌کنیم که متغیرها از فایل .env خوانده شوند
    # و به بزرگی و کوچکی حروف حساس نباشد.
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=False)

    # --- Telegram Bot Settings ---
    # SecretStr کمک می‌کند که توکن شما به صورت تصادفی در لاگ‌ها یا خطاها چاپ نشود
    BOT_TOKEN: SecretStr

    # --- Fazel Pharma API Settings ---
    API_BASE_URL: str

    # --- System User for Bot Login ---
    API_BOT_USERNAME: str
    API_BOT_PASSWORD: SecretStr
    ACCESS_TOKEN_EXPIRE_MINUTES: int



# Create a single instance of the settings to be used throughout the application
# این نمونه `settings` از همه جای پروژه import و استفاده خواهد شد
settings = Settings()
