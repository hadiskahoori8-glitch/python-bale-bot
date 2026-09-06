import bale
from bale import Bot, Message, CallbackQuery

TOKEN = "1976346124"

bot = Bot(token=TOKEN)

# اطلاعات موقت کاربران
reports = {}


@bot.event
async def on_ready():
    print("ربات با موفقیت فعال شد!")


@bot.event
async def on_message(message: Message):
    user_id = message.author.id
    text = message.content.strip()

    if text == "/start":
        await message.reply(
            "سلام 👋🏻\n"
            "به سامانه گزارش کار خوش آمدید 🌷\n\n"
            "برای ثبت گزارش، این دستور را بفرستید:\n"
            "/report"
        )

    elif text == "/report":
        reports[user_id] = {
            "step": "name"
        }

        await message.reply(
            "📝 ثبت گزارش کار\n\n"
            "لطفاً نام و نام خانوادگی خود را وارد کنید:"
        )

    elif user_id in reports:

        report = reports[user_id]
        step = report["step"]

        if step == "name":
            report["name"] = text
            report["step"] = "date"

            await message.reply(
                "📅 تاریخ گزارش را وارد کنید:"
            )

        elif step == "date":
            report["date"] = text
            report["step"] = "entry"

            await message.reply(
                "🕐 ساعت ورود را وارد کنید:"
            )

        elif step == "entry":
            report["entry"] = text
            report["step"] = "exit"

            await message.reply(
                "🕐 ساعت خروج را وارد کنید:"
            )

        elif step == "exit":
            report["exit"] = text
            report["step"] = "activities"

            await message.reply(
                "📋 شرح فعالیت‌های امروز را وارد کنید:"
            )

        elif step == "activities":
            report["activities"] = text

            await message.reply(
                "✅ گزارش شما با موفقیت ثبت شد.\n\n"
                f"👤 نام: {report['name']}\n"
                f"📅 تاریخ: {report['date']}\n"
                f"🕐 ورود: {report['entry']}\n"
                f"🕐 خروج: {report['exit']}\n"
                f"📋 فعالیت‌ها: {report['activities']}"
            )

            del reports[user_id]


bot.run()
