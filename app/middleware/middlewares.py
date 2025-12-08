# app/middlewares.py
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.5):
        # ذخیره آخرین زمان درخواست کاربر. کش بعد از 2 ثانیه پاک می‌شود
        self.cache = TTLCache(maxsize=10_000, ttl=limit)

    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id

        # اگر کاربر در کش باشد، یعنی تند تند پیام داده
        if user_id in self.cache:
            # می‌توانیم پیام را نادیده بگیریم
            return

            # کاربر را به کش اضافه کن
        self.cache[user_id] = True

        # ادامه پردازش پیام
        return await handler(event, data)
