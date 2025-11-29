# app/utils/invoice_generator.py

import os
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# کتابخانه‌های مورد نیاز برای متن فارسی
import arabic_reshaper
from bidi.algorithm import get_display

# --- 1. ثبت فونت فارسی ---
# پیدا کردن مسیر دقیق فایل فونت نسبت به محل اجرای فایل
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # به پوشه app اشاره می‌کند
FONT_PATH = os.path.join(BASE_DIR, "assets", "fonts", "Vazir-Regular.ttf")

try:
    pdfmetrics.registerFont(TTFont('Vazir', FONT_PATH))
    PERSIAN_FONT = 'Vazir'
except Exception as e:
    print(f"Warning: Could not load font at {FONT_PATH}. Using default. Error: {e}")
    PERSIAN_FONT = 'Helvetica'  # فال‌بک اگر فونت پیدا نشد


# --- 2. تابع کمکی برای اصلاح متن فارسی ---
def farsi(text):
    if not text or not isinstance(text, str):
        return str(text)
    # 1. تغییر شکل حروف (چسباندن حروف به هم)
    reshaped_text = arabic_reshaper.reshape(text)
    # 2. اصلاح جهت (راست به چپ)
    bidi_text = get_display(reshaped_text)
    return bidi_text


def generate_complex_invoice(data: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1 * cm, leftMargin=1 * cm,
        topMargin=1 * cm, bottomMargin=1 * cm,
        title=f"Invoice_{data.get('invoice_number')}"
    )

    elements = []
    styles = getSampleStyleSheet()

    # تعریف استایل‌های اختصاصی با فونت فارسی
    styles.add(ParagraphStyle(name='FarsiTitle', fontName=PERSIAN_FONT, fontSize=16, leading=20, alignment=1))  # Center
    styles.add(ParagraphStyle(name='FarsiNormal', fontName=PERSIAN_FONT, fontSize=10, leading=14, alignment=2))  # Right
    styles.add(ParagraphStyle(name='FarsiBold', fontName=PERSIAN_FONT, fontSize=12, leading=15, alignment=2))  # Right

    # --- هدر فاکتور ---
    header_data = [
        [farsi("فاکتور فروش"), farsi("داروخانه دکتر فاضل")],
        [farsi(f"شماره: {data.get('invoice_number')}"), farsi(f"تاریخ: {data.get('invoice_date')}")]
    ]

    header_table = Table(header_data, colWidths=[9 * cm, 9 * cm])
    header_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), PERSIAN_FONT),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.darkblue),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SIZE', (0, 0), (1, 0), 16),  # عنوان بزرگتر
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 1), (-1, 1), 1, colors.black),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.5 * cm))

    # --- اطلاعات خریدار و فروشنده ---
    # نکته: تمام متون ثابت هم باید داخل تابع farsi() بروند
    buyer = data.get("buyer_info", {})

    info_data = [
        [farsi("مشخصات خریدار"), farsi("مشخصات فروشنده")],
        [farsi(f"نام: {buyer.get('name')}"), farsi(f"نام: {data['seller_info']['name']}")],
        [farsi(f"تلفن: {buyer.get('phone')}"), farsi(f"تلفن: {data['seller_info']['phone']}")],
        [farsi(f"آدرس: {buyer.get('address')}"), farsi(f"آدرس: {data['seller_info']['address']}")]
    ]

    info_table = Table(info_data, colWidths=[9.5 * cm, 9.5 * cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), PERSIAN_FONT),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # راست چین کردن سلول‌ها
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 1 * cm))

    # --- جدول اقلام سفارش ---
    # هدرهای جدول
    table_headers = [
        farsi("قیمت کل (ریال)"),
        farsi("قیمت واحد (ریال)"),
        farsi("تعداد"),
        farsi("نام کالا/خدمات"),
        farsi("ردیف")
    ]

    table_data = [table_headers]

    # پر کردن ردیف‌ها
    items = data.get("items", [])
    total_quantity = 0

    for idx, item in enumerate(items, 1):
        row = [
            f"{item['total_price']:,}",  # قیمت کل
            f"{item['unit_price']:,}",  # قیمت واحد
            str(item['count']),  # تعداد
            farsi(item['name']),  # نام کالا (فارسی)
            str(idx)  # ردیف
        ]
        table_data.append(row)
        total_quantity += int(item['count'])

    # ردیف جمع کل
    final_price = data.get("final_total_price", 0)
    table_data.append([
        f"{final_price:,}",
        "",
        str(total_quantity),
        farsi("جمع کل"),
        ""
    ])

    # تنظیمات جدول اقلام
    # عرض ستون‌ها (به ترتیب از چپ به راست: قیمت کل، واحد، تعداد، نام، ردیف)
    col_widths = [4 * cm, 4 * cm, 2 * cm, 8 * cm, 1 * cm]

    invoice_table = Table(table_data, colWidths=col_widths)

    # استایل‌دهی جدول
    style_cmds = [
        ('FONTNAME', (0, 0), (-1, -1), PERSIAN_FONT),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),  # هدر جدول
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]

    # رنگی کردن ردیف جمع کل (آخرین ردیف)
    style_cmds.append(('BACKGROUND', (0, -1), (-1, -1), colors.whitesmoke))
    style_cmds.append(('FONTSIZE', (0, -1), (-1, -1), 12))

    invoice_table.setStyle(TableStyle(style_cmds))
    elements.append(invoice_table)

    # --- فوتر و توضیحات ---
    elements.append(Spacer(1, 1 * cm))
    elements.append(Paragraph(farsi(f"مسئول پذیرش: {data.get('cashier_name', '---')}"), styles['FarsiNormal']))
    if data.get('consultant_name'):
        elements.append(Paragraph(farsi(f"پزشک مشاور: {data.get('consultant_name')}"), styles['FarsiNormal']))

    # ساخت فایل
    doc.build(elements)
    buffer.seek(0)
    return buffer
