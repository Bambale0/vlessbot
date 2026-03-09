import io
from datetime import datetime, timedelta

import qrcode
from PIL import Image


def generate_qr(data: str) -> io.BytesIO:
    """Генерация QR кода"""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def format_bytes(bytes_count: int) -> str:
    """Форматирование байтов в человекочитаемый вид"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.2f} PB"


def calculate_expiry(period_months: int) -> datetime:
    """Расчет даты окончания подписки"""
    return datetime.now() + timedelta(days=30 * period_months)


def format_expiry(date_str: str) -> str:
    """Форматирование даты"""
    if not date_str:
        return "Бессрочно"
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d.%m.%Y")
    except:
        return date_str
