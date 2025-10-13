# app/filters/role_filter.py

from typing import Union, Dict, Any
from aiogram.filters import BaseFilter
from aiogram.types import Message
from app.core.API_Client import APIClient


class RoleFilter(BaseFilter):
    """
    فیلتری برای بررسی نقش کاربر از طریق API.
    """

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, message: Message, api_client: APIClient) -> bool:
        # از کلاینت API که به dispatcher پاس داده شده استفاده می‌کنیم
        user_role = await api_client.get_user_role(telegram_id=message.from_user.id)

        # بررسی می‌کنیم آیا نقش کاربر در لیست نقش‌های مجاز این روتر هست یا نه
        if user_role in self.allowed_roles:
            return True
        return False
