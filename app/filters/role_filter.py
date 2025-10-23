# File: app/filters/role_filter.py

from typing import Union
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from app.core.API_Client import APIClient


class RoleFilter(BaseFilter):
    """
    فیلتری برای بررسی نقش کاربر از طریق API.
    این فیلتر هم برای Message و هم برای CallbackQuery کار می‌کند.
    """

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(
            self,
            update: Union[Message, CallbackQuery],
            api_client: APIClient
    ) -> bool:
        # از هر نوع آپدیتی که باشد (پیام یا کلیک)، آبجکت user را می‌گیریم
        user = update.from_user

        # اگر به هر دلیلی کاربر وجود نداشت، فیلتر را رد می‌کنیم
        if not user:
            return False

        # از کلاینت API که به dispatcher پاس داده شده استفاده می‌کنیم
        user_role = await api_client.get_user_role(telegram_id=user.id)

        # بررسی می‌کنیم آیا نقش کاربر در لیست نقش‌های مجاز این روتر هست یا نه
        if user_role in self.allowed_roles:
            return True

        return False
