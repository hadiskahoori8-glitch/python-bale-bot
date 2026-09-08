import os
import re
import sqlite3
import asyncio
from datetime import datetime

from bale import Bot, Message
from bale import MenuKeyboardMarkup, MenuKeyboardButton


# =========================================================
# تنظیمات
# =========================================================

TOKEN = os.getenv("BALE_BOT_TOKEN", "").strip()
ADMIN_ID = os.getenv("ADMIN_ID", "").strip()

if not TOKEN:
    raise RuntimeError(
        "BALE_BOT_TOKEN تنظیم نشده است. "
        "توکن ربات را به صورت Environment Variable قرار دهید."
    )

bot = Bot(token=TOKEN)

DB_NAME = "reports.db"

# جلوگیری از شروع همزمان چند گزارش برای یک کاربر
active_users = set()


# =========================================================
# دیتابیس
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_database():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            report_date TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT NOT NULL,
            activities TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# ابزارهای کمکی
# =========================================================

def get_user_id(message):
    return str(message.author.id)


def get_user_name(message):
    name = getattr(message.author, "first_name", None)

    if name:
        return str(name).strip()

    return "پرسنل"


def get_text(message):
    text = getattr(message, "content", "")

    if text is None:
        return ""

    return str(text).strip()


def is_admin(message):
    if not ADMIN_ID:
        return False

    return get_user_id(message) == ADMIN_ID


def main_menu(admin=False):
    keyboard = MenuKeyboardMarkup()

    keyboard.add(
        MenuKeyboardButton("📝 ثبت گزارش کار"),
        row=1
    )

    keyboard.add(
        MenuKeyboardButton("📋 گزارش‌های من"),
        row=2
    )

    keyboard.add(
        MenuKeyboardButton("🆔 شناسه من"),
        row=3
    )

    if admin:
        keyboard.add(
            MenuKeyboardButton("📊 همه گزارش‌ها"),
            row=4
        )

        keyboard.add(
            MenuKeyboardButton("👥 لیست پرسنل"),
            row=5
        )

    return keyboard


def normalize_time(text):
    text = text.strip()

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        text
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour > 23 or minute > 59:
        return None

    return f"{hour:02d}:{minute:02d}"


def valid_date(text):
    text = text.strip()

    # تاریخ شمسی را به صورت متنی ذخیره می‌کنیم
    # تا تبدیل اشتباه تقویم اتفاق نیفتد.
    return bool(
        re.fullmatch(
            r"\d{4}/\d{1,2}/\d{1,2}",
            text
        )
    )


def normalize_date(text):
    parts = text.strip().split("/")

    if len(parts) != 3:
        return text.strip()

    year = parts[0]
    month = parts[1].zfill(2)
    day = parts[2].zfill(2)

    return f"{year}/{month}/{day}"


# =========================================================
# ذخیره کارمند
# =========================================================

def save_employee(user_id, name):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO employees (user_id, name, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET name = excluded.name
    """, (
        user_id,
        name,
        datetime.now().isoformat(timespec="seconds")
    ))

    conn.commit()
    conn.close()


# =========================================================
# ذخیره گزارش
# =========================================================

def save_report(
    user_id,
    name,
    report_date,
    entry_time,
    exit_time,
    activities
):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reports (
            user_id,
            name,
            report_date,
            entry_time,
            exit_time,
            activities,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        name,
        report_date,
        entry_time,
        exit_time,
        activities,
        datetime.now().isoformat(timespec="seconds")
    ))

    conn.commit()
    conn.close()


# =========================================================
# دریافت پیام از همان کاربر
# =========================================================

async def wait_for_user_message(original_message, timeout=300):

    user_id = get_user_id(original_message)
    chat_id = str(original_message.chat.id)

    def check(message):
        try:
            return (
                str(message.author.id) == user_id
                and str(message.chat.id) == chat_id
                and bool(get_text(message))
            )
        except Exception:
            return False

    return await bot.wait_for(
        "message",
        check=check,
        timeout=timeout
    )


# =========================================================
# گرفتن اطلاعات گزارش
# =========================================================

async def create_report(message):

    user_id = get_user_id(message)

    if user_id in active_users:
        await message.reply(
            "⚠️ شما در حال ثبت یک گزارش هستید.\n"
            "لطفاً همان گزارش را کامل کنید."
        )
        return

    active_users.add(user_id)

    try:

        # -----------------------------------------
        # نام
        # -----------------------------------------

        await message.reply(
            "👤 **مرحله ۱ از ۵**\n\n"
            "لطفاً نام و نام خانوادگی خود را وارد کنید:"
        )

        name_message = await wait_for_user_message(message)
        name = get_text(name_message)

        if len(name) < 2:
            await message.reply(
                "❌ نام واردشده صحیح نیست.\n"
                "لطفاً دوباره از «ثبت گزارش کار» شروع کنید."
            )
            return

        # -----------------------------------------
        # تاریخ
        # -----------------------------------------

        while True:

            await name_message.reply(
                "📅 **مرحله ۲ از ۵**\n\n"
                "تاریخ گزارش را وارد کنید.\n"
                "مثال:\n"
                "`1405/06/17`"
            )

            date_message = await wait_for_user_message(message)
            report_date = get_text(date_message)

            if valid_date(report_date):
                report_date = normalize_date(report_date)
                break

            await date_message.reply(
                "❌ فرمت تاریخ صحیح نیست.\n\n"
                "لطفاً به شکل زیر وارد کنید:\n"
                "`1405/06/17`"
            )

        # -----------------------------------------
        # ساعت ورود
        # -----------------------------------------

        while True:

            await date_message.reply(
                "🕐 **مرحله ۳ از ۵**\n\n"
                "ساعت ورود را وارد کنید.\n"
                "مثال: `09:45`"
            )

            entry_message = await wait_for_user_message(message)
            entry_time = normalize_time(
                get_text(entry_message)
            )

            if entry_time:
                break

            await entry_message.reply(
                "❌ ساعت صحیح نیست.\n"
                "مثال درست: `09:45`"
            )

        # -----------------------------------------
        # ساعت خروج
        # -----------------------------------------

        while True:

            await entry_message.reply(
                "🕐 **مرحله ۴ از ۵**\n\n"
                "ساعت خروج را وارد کنید.\n"
                "مثال: `23:00`"
            )

            exit_message = await wait_for_user_message(message)
            exit_time = normalize_time(
                get_text(exit_message)
            )

            if exit_time:
                break

            await exit_message.reply(
                "❌ ساعت صحیح نیست.\n"
                "مثال درست: `23:00`"
            )

        # -----------------------------------------
        # شرح فعالیت
        # -----------------------------------------

        await exit_message.reply(
            "📝 **مرحله ۵ از ۵**\n\n"
            "شرح کامل فعالیت‌های امروز را بنویسید.\n\n"
            "مثال:\n"
            "• آماده‌سازی کافه\n"
            "• مرتب کردن میزها\n"
            "• سرویس‌دهی به مشتریان\n"
            "• نظافت بخش مربوطه"
        )

        activities_message = await wait_for_user_message(message)
        activities = get_text(activities_message)

        if len(activities) < 3:
            await activities_message.reply(
                "❌ شرح فعالیت خیلی کوتاه است.\n"
                "لطفاً دوباره گزارش را از ابتدا ثبت کنید."
            )
            return

        # -----------------------------------------
        # تأیید نهایی
        # -----------------------------------------

        confirmation_keyboard = MenuKeyboardMarkup()

        confirmation_keyboard.add(
            MenuKeyboardButton("✅ تأیید و ثبت"),
            row=1
        )

        confirmation_keyboard.add(
            MenuKeyboardButton("❌ لغو"),
            row=1
        )

        summary = (
            "📋 **پیش‌نمایش گزارش کار**\n\n"
            f"👤 نام: {name}\n"
            f"📅 تاریخ: {report_date}\n"
            f"🟢 ورود: {entry_time}\n"
            f"🔴 خروج: {exit_time}\n\n"
            f"📝 فعالیت‌ها:\n"
            f"{activities}\n\n"
            "آیا اطلاعات بالا صحیح است؟"
        )

        await activities_message.reply(
            summary,
            components=confirmation_keyboard
        )

        # -----------------------------------------
        # دریافت تأیید
        # -----------------------------------------

        while True:

            confirmation_message = await wait_for_user_message(message)

            confirmation = get_text(
                confirmation_message
            )

            if confirmation == "❌ لغو":

                await confirmation_message.reply(
                    "❌ ثبت گزارش لغو شد.",
                    components=main_menu(
                        is_admin(message)
                    )
                )

                return

            if confirmation == "✅ تأیید و ثبت":
                break

            await confirmation_message.reply(
                "لطفاً یکی از دو گزینه را انتخاب کنید:\n"
                "✅ تأیید و ثبت\n"
                "❌ لغو"
            )

        # -----------------------------------------
        # ذخیره
        # -----------------------------------------

        save_employee(
            user_id,
            name
        )

        save_report(
            user_id,
            name,
            report_date,
            entry_time,
            exit_time,
            activities
        )

        await confirmation_message.reply(
            "🎉 **گزارش کار با موفقیت ثبت شد.**\n\n"
            f"👤 {name}\n"
            f"📅 {report_date}\n"
            f"🟢 ورود: {entry_time}\n"
            f"🔴 خروج: {exit_time}\n\n"
            "گزارش شما فقط برای خودتان و مدیر قابل مشاهده است.",
            components=main_menu(
                is_admin(message)
            )
        )

    except asyncio.TimeoutError:

        await message.reply(
            "⏰ زمان ثبت گزارش تمام شد.\n\n"
            "برای شروع دوباره، روی «📝 ثبت گزارش کار» بزنید.",
            components=main_menu(
                is_admin(message)
            )
        )

    except Exception as error:

        print("REPORT ERROR:", repr(error))

        await message.reply(
            "❌ هنگام ثبت گزارش مشکلی پیش آمد.\n\n"
            "لطفاً دوباره تلاش کنید.",
            components=main_menu(
                is_admin(message)
            )
        )

    finally:
        active_users.discard(user_id)


# =========================================================
# گزارش‌های خود کاربر
# =========================================================

async def show_my_reports(message):

    user_id = get_user_id(message)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            report_date,
            entry_time,
            exit_time,
            activities
        FROM reports
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 20
    """, (user_id,))

    reports = cursor.fetchall()
    conn.close()

    if not reports:
        await message.reply(
            "📭 هنوز هیچ گزارشی برای شما ثبت نشده است.",
            components=main_menu(
                is_admin(message)
            )
        )
        return

    text = "📋 **گزارش‌های کار شما**\n\n"

    for report in reports:

        report_id, name, date, entry, exit_, activities = report

        text += (
            f"━━━━━━━━━━━━━━\n"
            f"🆔 گزارش شماره: {report_id}\n"
            f"👤 {name}\n"
            f"📅 تاریخ: {date}\n"
            f"🟢 ورود: {entry}\n"
            f"🔴 خروج: {exit_}\n"
            f"📝 فعالیت‌ها:\n{activities}\n\n"
        )

    await message.reply(
        text,
        components=main_menu(
            is_admin(message)
        )
    )


# =========================================================
# همه گزارش‌ها برای مدیر
# =========================================================

async def show_all_reports(message):

    if not is_admin(message):
        await message.reply(
            "⛔ شما دسترسی مدیر ندارید."
        )
        return

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            report_date,
            entry_time,
            exit_time,
            activities
        FROM reports
        ORDER BY id DESC
        LIMIT 50
    """)

    reports = cursor.fetchall()
    conn.close()

    if not reports:
        await message.reply(
            "📭 هنوز گزارشی ثبت نشده است.",
            components=main_menu(True)
        )
        return

    text = "📊 **همه گزارش‌های ثبت‌شده**\n\n"

    for report in reports:

        report_id, name, date, entry, exit_, activities = report

        text += (
            f"━━━━━━━━━━━━━━\n"
            f"🆔 شماره: {report_id}\n"
            f"👤 نام: {name}\n"
            f"📅 تاریخ: {date}\n"
            f"🟢 ورود: {entry}\n"
            f"🔴 خروج: {exit_}\n"
            f"📝 فعالیت‌ها:\n{activities}\n\n"
        )

        # جلوگیری از بیش از حد طولانی شدن پیام
        if len(text) > 3500:
            await message.reply(text)
            text = "📊 **ادامه گزارش‌ها**\n\n"

    if text.strip():
        await message.reply(
            text,
            components=main_menu(True)
        )


# =========================================================
# لیست پرسنل
# =========================================================

async def show_employees(message):

    if not is_admin(message):
        await message.reply(
            "⛔ شما دسترسی مدیر ندارید."
        )
        return

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, name, created_at
        FROM employees
        ORDER BY id DESC
    """)

    employees = cursor.fetchall()
    conn.close()

    if not employees:
        await message.reply(
            "👥 هنوز هیچ پرسنلی ثبت نشده است.",
            components=main_menu(True)
        )
        return

    text = "👥 **لیست پرسنل**\n\n"

    for number, employee in enumerate(employees, 1):

        user_id, name, created_at = employee

        text += (
            f"{number}. 👤 {name}\n"
            f"🆔 شناسه: `{user_id}`\n\n"
        )

    await message.reply(
        text,
        components=main_menu(True)
    )


# =========================================================
# رویداد آماده شدن ربات
# =========================================================

@bot.event
async def on_ready():

    init_database()

    print("===================================")
    print("کافه گوهر - ربات گزارش کار")
    print("BOT IS READY")
    print("===================================")


# =========================================================
# دریافت پیام‌ها
# =========================================================

@bot.event
async def on_message(message: Message):

    text = get_text(message)

    if not text:
        return

    # -----------------------------------------
    # شروع
    # -----------------------------------------

    if text in ["/start", "/menu"]:

        await message.reply(
            "☕ **به ربات گزارش کار کافه گوهر خوش آمدید**\n\n"
            "از منوی زیر گزینه موردنظر را انتخاب کنید:",
            components=main_menu(
                is_admin(message)
            )
        )

        return

    # -----------------------------------------
    # شناسه کاربر
    # -----------------------------------------

    if text in ["/myid", "🆔 شناسه من"]:

        await message.reply(
            "🆔 **شناسه کاربری شما:**\n\n"
            f"`{get_user_id(message)}`\n\n"
            "این شناسه برای تنظیم دسترسی مدیر استفاده می‌شود."
        )

        return

    # -----------------------------------------
    # ثبت گزارش
    # -----------------------------------------

    if text == "📝 ثبت گزارش کار":

        await create_report(message)
        return

    # -----------------------------------------
    # گزارش‌های من
    # -----------------------------------------

    if text == "📋 گزارش‌های من":

        await show_my_reports(message)
        return

    # -----------------------------------------
    # همه گزارش‌ها
    # -----------------------------------------

    if text == "📊 همه گزارش‌ها":

        await show_all_reports(message)
        return

    # -----------------------------------------
    # لیست پرسنل
    # -----------------------------------------

    if text == "👥 لیست پرسنل":

        await show_employees(message)
        return

    # -----------------------------------------
    # پیام ناشناخته
    # -----------------------------------------

    await message.reply(
        "لطفاً از گزینه‌های منوی ربات استفاده کنید.",
        components=main_menu(
            is_admin(message)
        )
    )


# =========================================================
# اجرای ربات
# =========================================================

if __name__ == "__main__":

    init_database()

    print("در حال اجرای ربات گزارش کار کافه گوهر...")

    bot.run()
