import enum



class PatientStatus(str, enum.Enum):
    """
    وضعیت‌های مختلف بیمار در چرخه حیات سیستم.
    """
    AWAITING_PROFILE_COMPLETION = "awaiting_profile_completion" # در حال پر کردن اطلاعات اولیه.
    PROFILE_COMPLETED = "profile_completed"     # اطلاعات اولیه تکمیل شده، منتظر ارسال درخواست مشاوره.
    AWAITING_CONSULTATION = "awaiting_consultation" # درخواست مشاوره ثبت شده، منتظر پاسخ مشاور.
    AWAITING_INVOICE_APPROVAL = "awaiting_invoice_approval" # فاکتور توسط مشاور صادر شده، منتظر تایید بیمار.
    AWAITING_PAYMENT = "awaiting_payment"     # فاکتور تایید شده، منتظر پرداخت.
    PAYMENT_COMPLETED = "payment_completed"     # پرداخت انجام شده، منتظر تایید صندوق‌دار.
    PAYMENT_CONFIRMED = "payment_confirmed"
    AWAITING_SHIPMENT = "awaiting_shipment"   # تایید صندوق‌دار انجام شده، منتظر ارسال.
    SHIPPED = "shipped"                       # بسته ارسال شده.
    COMPLETED = "completed"                   # فرآیند برای این سفارش تمام شده.
    CANCELLED = "cancelled"                   # فرآیند توسط کاربر یا سیستم لغو شد

class GenderEnum(str, enum.Enum):
    """
    Enumeration for gender.
    Values are stored as strings in the database.
    """
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"

class OrderStatusEnum(str, enum.Enum):
    """Enum for payment status"""
    CREATED = "Created"
    CONFIRM = "Confirm"
    REJECTED = "Rejected"
    PAID = "Paid"
    SENT = "Sent"
    DELIVERED = "Delivered"


class PaymentStatusEnum(str, enum.Enum):
    """Enum for payment status"""
    NOT_SEEN = "Not Seen"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"

