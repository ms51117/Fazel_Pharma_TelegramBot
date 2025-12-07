# app/utils/date_helper.py
import jdatetime
from datetime import datetime, date


def to_jalali(date_input, include_time=True) -> str:
    """
    تبدیل تاریخ میلادی به شمسی.
    ورودی می‌تواند رشته (String) یا آبجکت datetime باشد.

    مثال خروجی: "1402/09/09 ساعت 14:30"
    """
    if not date_input:
        return ""

    dt = None
    try:
        # حالت ۱: اگر ورودی رشته است (مثل خروجی API)
        if isinstance(date_input, str):
            # حذف Z و تمیزکاری
            clean_date = date_input.replace("Z", "")
            if "T" in clean_date:
                dt = datetime.fromisoformat(clean_date)
            else:
                # تلاش برای فرمت‌های ساده‌تر
                try:
                    dt = datetime.strptime(clean_date, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    dt = datetime.strptime(clean_date, "%Y-%m-%d")

        # حالت ۲: اگر ورودی خودش آبجکت datetime یا date است
        elif isinstance(date_input, (datetime, date)):
            dt = date_input

        if dt:
            # تبدیل به آبجکت شمسی
            # اگر فقط date بود (ساعت نداشت)، هندل می‌کنیم
            if isinstance(dt, date) and not isinstance(dt, datetime):
                jalali_date = jdatetime.date.fromgregorian(date=dt)
                return jalali_date.strftime("%Y/%m/%d")
            else:
                jalali_date = jdatetime.datetime.fromgregorian(datetime=dt)
                if include_time:
                    return jalali_date.strftime("%Y/%m/%d ساعت %H:%M")
                else:
                    return jalali_date.strftime("%Y/%m/%d")

    except Exception as e:
        # print(f"Jalali conversion error: {e}") # برای دیباگ
        return str(date_input)

    return str(date_input)


def to_gregorian(jalali_str: str) -> str:
    """
    تبدیل رشته تاریخ شمسی به فرمت استاندارد میلادی (ISO).
    مناسب برای ارسال تاریخ تولد یا فیلتر تاریخ به بک‌اند.

    ورودی مثال: "1402/09/09" یا "1402-09-09"
    خروجی مثال: "2023-11-30"
    """
    if not jalali_str:
        return None

    try:
        # 1. نرمال‌سازی جداکننده‌ها (تبدیل همه به /)
        normalized_date = jalali_str.replace("-", "/").replace(".", "/")

        # 2. جدا کردن بخش‌ها
        parts = normalized_date.split("/")
        if len(parts) != 3:
            return None  # فرمت نامعتبر

        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])

        # 3. ساخت آبجکت شمسی و تبدیل به میلادی
        # این تابع خودش کبیسه و تعداد روزها را چک می‌کند
        gregorian_date = jdatetime.date(y, m, d).togregorian()

        # 4. بازگرداندن فرمت استاندارد دیتابیس (YYYY-MM-DD)
        return gregorian_date.strftime("%Y-%m-%d")

    except ValueError:
        # مثلا اگر کاربر بزند 1402/13/01 یا روز نامعتبر
        return None
    except Exception as e:
        # print(f"Gregorian conversion error: {e}")
        return None
