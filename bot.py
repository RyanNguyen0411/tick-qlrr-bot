import os
import logging
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- THÔNG TIN CẤU HÌNH ---
TOKEN = "9161885394:AAEsDFlZGL0sdyQ42rge5uA_S0WZmK96vEI"
GROUP_ID = -5299119796
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxWIY0U7L7uRCiCGvdQnrOLhUlD8jovPcb6Sn3NXWscQzzPOHP-t16TwLnQQ2uGJ--u/exec"
SHEET_LINK = "https://docs.google.com/spreadsheets/d/1mM5h6cupkJr4i7oVLNFySbjxCGD8PHQIEUyW0ccu8-Q/edit?usp=sharing"

user_data_cache = {}
sent_alerts = set()  # Lưu các mã đơn đã gửi cảnh báo để tránh spam liên tục
LOAI_OPTIONS = ["Nhã mã", "Hư hỏng", "2 mã", "Nhận tải thiếu", "Tráo SP", "Khác"]


# --- HTTP SERVER MỞ PORT CHO RENDER WEB SERVICE FREE ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        return


def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"🌐 Health check server đang lắng nghe tại cổng {port}")
    server.serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        return
    await update.message.reply_text(
        "🤖 Bot Cập Nhật Đơn Hàng đã sẵn sàng!\n\n"
        "Sử dụng cú pháp mới để thêm đơn:\n"
        "<code>/them [mã đơn] [Link]</code>\n\n"
        "Ví dụ:\n"
        "<code>/them VNGH80462151111 https://noibo.ghn.vn/ghn-ticket/detail/6277364</code>",
        parse_mode="HTML"
    )


async def cmd_them(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != GROUP_ID:
        return

    text = update.message.text.replace("/them", "").strip()
    parts = text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ Sai cú pháp! Vui lòng dùng:\n<code>/them [mã đơn] [Link]</code>\n\nVí dụ:\n<code>/them VNGH80462151111 https://noibo.ghn.vn/ghn-ticket/detail/6277364</code>",
            parse_mode="HTML"
        )
        return

    ma_don = parts[0].strip()
    link_qlrr = parts[1].strip()

    user_id = update.effective_user.id
    user_data_cache[user_id] = {
        "ma_don": ma_don,
        "link_qlrr": link_qlrr
    }

    keyboard = [
        [InlineKeyboardButton(loai, callback_data=f"loai_{loai}") for loai in LOAI_OPTIONS[:3]],
        [InlineKeyboardButton(loai, callback_data=f"loai_{loai}") for loai in LOAI_OPTIONS[3:]]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📋 <b>Mã đơn:</b> <code>{ma_don}</code>\n"
        f"🔗 <b>Link QLRR:</b> {link_qlrr}\n\n"
        f"👉 Vui lòng chọn <b>Loại</b> sự cố bên dưới:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data_key = query.data

    # Xử lý nút bấm cảnh báo quá hạn (Phản hồi giao diện < 0.5s)
    if data_key.startswith("action_"):
        parts = data_key.split("_")
        action = parts[1]  # xuly hoặc luulai
        ma_don = parts[2]

        note_text = "Đã Xử Lý" if action == "xuly" else "Lưu lại thông tin"

        await query.edit_message_text(
            f"✅ <b>ĐÃ CẬP NHẬT PHẢN HỒI</b>\n\n"
            f"• <b>Mã đơn:</b> <code>{ma_don}</code>\n"
            f"• <b>Trạng thái:</b> {note_text}\n"
            f"• <b>Hệ thống phản hồi:</b> Đã hoàn tất",
            parse_mode="HTML"
        )

        def send_background():
            try:
                payload = {
                    "action": "update_am_note",
                    "ma_don": ma_don,
                    "am_note": note_text
                }
                res = requests.post(WEB_APP_URL, json=payload, timeout=15)
                logger.info(f"Cập nhật AM Note [{ma_don}]: HTTP {res.status_code} - {res.text}")
            except Exception as e:
                logger.error(f"Lỗi cập nhật AM Note ngầm: {e}")

        threading.Thread(target=send_background, daemon=True).start()
        return

    if user_id not in user_data_cache:
        expired_msg = (
            "<b>🔍 TRA CỨU VÀ CÚ PHÁP</b>\n"
            f"- <b>Tra cứu tại link:</b> <a href=\"{SHEET_LINK}\">NHẤN VÀO ĐỂ MỞ LINK</a>\n"
            "- <b>Cú pháp cập nhật QLRR:</b> <code>/them [mã đơn] [Link QLRR]</code> (cách nhau bằng dấu cách)"
        )
        await query.edit_message_text(expired_msg, parse_mode="HTML", disable_web_page_preview=True)
        return

    if data_key.startswith("loai_"):
        loai_chon = data_key.replace("loai_", "")
        data = user_data_cache[user_id]
        ma_don = data["ma_don"]
        link_qlrr = data["link_qlrr"]

        # 1. Phản hồi giao diện ngay lập tức (< 0.5s)
        success_msg = (
            f"✅ <b>ĐÃ CẬP NHẬT VÀO DANH SÁCH</b>\n\n"
            f"• <b>Mã đơn:</b> <code>{ma_don}</code>\n"
            f"• <b>Loại:</b> <code>{loai_chon}</code>\n"
            f"• <b>Link QLRR:</b> {link_qlrr}\n\n"
            "<b>🔍 TRA CỨU VÀ CÚ PHÁP</b>\n"
            f"- <b>Tra cứu tại link:</b> <a href=\"{SHEET_LINK}\">NHẤN VÀO ĐỂ MỞ LINK</a>\n"
            "- <b>Cú pháp cập nhật QLRR:</b> <code>/them [mã đơn] [Link QLRR]</code> (cách nhau bằng dấu cách)"
        )

        del user_data_cache[user_id]
        await query.edit_message_text(success_msg, parse_mode="HTML", disable_web_page_preview=True)

        # 2. Đẩy dữ liệu lên Google Sheet ngầm
        def send_background_them():
            try:
                payload = {
                    "ma_don": ma_don,
                    "loai": loai_chon,
                    "link_qlrr": link_qlrr
                }
                res = requests.post(WEB_APP_URL, json=payload, timeout=15)
                logger.info(f"Ghi đơn [{ma_don}] lên Sheet: HTTP {res.status_code} - {res.text}")
            except Exception as e:
                logger.error(f"Lỗi gửi ngầm Google Script: {e}")

        threading.Thread(target=send_background_them, daemon=True).start()


# Hàm chạy nền kiểm tra đơn quá hạn mỗi 60 giây dùng Thread độc lập
def background_checker(application):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def check_loop():
        while True:
            try:
                response = requests.get(WEB_APP_URL, timeout=15)
                if response.status_code == 200:
                    alerts = response.json()
                    for item in alerts:
                        ma_don = item["ma_don"]
                        if ma_don not in sent_alerts:
                            sent_alerts.add(ma_don)

                            ngay_nhap = item["ngay_nhap"]
                            loai = item["loai"]
                            link_qlrr = item["link_qlrr"]
                            so_ngay = item["so_ngay"]

                            keyboard = [
                                [
                                    InlineKeyboardButton("Đã Xử Lý", callback_data=f"action_xuly_{ma_don}"),
                                    InlineKeyboardButton("Lưu lại thông tin", callback_data=f"action_luulai_{ma_don}")
                                ]
                            ]
                            reply_markup = InlineKeyboardMarkup(keyboard)

                            alert_msg = (
                                f"🚨 <b>CẢNH BÁO XỬ LÝ ĐƠN HÀNG</b> @HuyNguyen_AMLA\n\n"
                                f"• <b>Ngày/Giờ Nhập:</b> {ngay_nhap}\n"
                                f"• <b>Mã Đơn:</b> <code>{ma_don}</code>\n"
                                f"• <b>Loại:</b> {loai}\n"
                                f"• <b>Link QLRR:</b> {link_qlrr}\n"
                                f"• <b>Số ngày tạo:</b> {so_ngay} ngày\n\n"
                                f"👉 Vui lòng chọn phương án xử lý bên dưới:"
                            )

                            await application.bot.send_message(
                                chat_id=GROUP_ID,
                                text=alert_msg,
                                reply_markup=reply_markup,
                                parse_mode="HTML",
                                disable_web_page_preview=True
