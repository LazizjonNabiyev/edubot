"""
EduBot - O'zbekiston talabalari uchun AI yordamchi bot
Prezentatsiya, mustaqil ish, amaliy ish, referat generatsiya qiladi
"""

import os
import asyncio
import logging
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from ai_generator import AIGenerator
from doc_creator import create_pptx, create_docx
from database import Database

load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PRICE = 8000  # so'm

# Conversation states
CHOOSING_TYPE, ENTERING_TOPIC, WAITING_PAYMENT = range(3)

db = Database()
ai = AIGenerator()

DOC_TYPES = {
    "pptx": "📊 Prezentatsiya (PPTX)",
    "mustaqil": "📝 Mustaqil ish (DOCX)",
    "amaliy": "🔬 Amaliy ish (DOCX)",
    "referat": "📖 Referat (DOCX)",
}

WELCOME_TEXT = """👋 *EduBot*ga xush kelibsiz!

🎓 Men sizga quyidagi akademik materiallarni tayyorlab beraman:

📊 *Prezentatsiya* — chiroyli slaydlar (PPTX)
📝 *Mustaqil ish* — to'liq rasmiylashtirilgan (DOCX)
🔬 *Amaliy ish* — amaliy qism bilan (DOCX)
📖 *Referat* — kirish, asosiy qism, xulosa (DOCX)

💡 *Narx:* Birinchi marta — *BEPUL*!
Keyingi har bir hujjat — *8,000 so'm*

Boshlaylik! 👇"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.first_name, user.username)

    keyboard = [
        [InlineKeyboardButton("📊 Prezentatsiya", callback_data="type_pptx"),
         InlineKeyboardButton("📝 Mustaqil ish", callback_data="type_mustaqil")],
        [InlineKeyboardButton("🔬 Amaliy ish", callback_data="type_amaliy"),
         InlineKeyboardButton("📖 Referat", callback_data="type_referat")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    free_used = db.get_free_used(user.id)
    status_text = "🎁 Sizda 1 ta *bepul* generatsiya bor!" if not free_used else f"💳 Narx: *8,000 so'm* / hujjat"

    await update.message.reply_text(
        WELCOME_TEXT + f"\n\n{status_text}\n\nQaysi hujjat kerak?",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return CHOOSING_TYPE


async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    doc_type = query.data.replace("type_", "")
    context.user_data["doc_type"] = doc_type

    type_name = DOC_TYPES[doc_type]

    await query.edit_message_text(
        f"✅ Tanlandi: *{type_name}*\n\n"
        f"📌 Endi mavzuni yozing.\n\n"
        f"_Misol: \"Süni intellekt va uning turmushda qo'llanilishi\"_",
        parse_mode="Markdown"
    )
    return ENTERING_TOPIC


async def enter_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    topic = update.message.text.strip()

    if len(topic) < 5:
        await update.message.reply_text("❌ Mavzu juda qisqa. Iltimos to'liqroq yozing.")
        return ENTERING_TOPIC

    if len(topic) > 200:
        await update.message.reply_text("❌ Mavzu juda uzun. 200 ta belgigacha yozing.")
        return ENTERING_TOPIC

    context.user_data["topic"] = topic
    doc_type = context.user_data.get("doc_type", "pptx")
    free_used = db.get_free_used(user.id)

    if not free_used:
        # Bepul generatsiya
        await update.message.reply_text(
            f"⏳ *{DOC_TYPES[doc_type]}* tayyorlanmoqda...\n\n"
            f"📌 Mavzu: _{topic}_\n\n"
            f"🤖 AI ishlayapti, biroz kuting...",
            parse_mode="Markdown"
        )
        await generate_and_send(update, context, user.id, topic, doc_type)
        db.mark_free_used(user.id)
        return ConversationHandler.END
    else:
        # To'lov kerak
        balance = db.get_balance(user.id)
        if balance >= PRICE:
            # Balansdan yeching
            await update.message.reply_text(
                f"⏳ *{DOC_TYPES[doc_type]}* tayyorlanmoqda...\n\n"
                f"📌 Mavzu: _{topic}_\n"
                f"💳 Balansdan {PRICE:,} so'm yechildi\n\n"
                f"🤖 AI ishlayapti...",
                parse_mode="Markdown"
            )
            db.deduct_balance(user.id, PRICE)
            await generate_and_send(update, context, user.id, topic, doc_type)
            return ConversationHandler.END
        else:
            # To'lov so'rash
            keyboard = [
                [InlineKeyboardButton("💳 To'lov qilish", callback_data="pay_now")],
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"💰 *To'lov kerak*\n\n"
                f"Hujjat: *{DOC_TYPES[doc_type]}*\n"
                f"Mavzu: _{topic}_\n\n"
                f"💵 To'lov: *{PRICE:,} so'm*\n\n"
                f"To'lovni amalga oshirish uchun quyidagi tugmani bosing:",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return WAITING_PAYMENT


async def pay_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    # To'lov ma'lumotlari - o'zingizning karta/payme/click ma'lumotlaringizni qo'ying
    CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 XXXX XXXX XXXX")
    CARD_OWNER = os.getenv("CARD_OWNER", "Ism Familiya")

    keyboard = [
        [InlineKeyboardButton("✅ To'lov qildim", callback_data="paid_confirm")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"💳 *To'lov ma'lumotlari*\n\n"
        f"Karta raqami: `{CARD_NUMBER}`\n"
        f"Karta egasi: *{CARD_OWNER}*\n"
        f"Summa: *{PRICE:,} so'm*\n\n"
        f"📸 To'lov chekini adminga yuboring: @{os.getenv('ADMIN_USERNAME', 'admin')}\n\n"
        f"⚠️ To'lov tasdiqlangandan so'ng hujjat tayyorlanadi.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    return WAITING_PAYMENT


async def paid_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    topic = context.user_data.get("topic", "")
    doc_type = context.user_data.get("doc_type", "pptx")

    # Adminga xabar yuborish
    if ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton(
                f"✅ Tasdiqlash ({PRICE:,} so'm)",
                callback_data=f"admin_approve_{user.id}_{doc_type}"
            )],
            [InlineKeyboardButton("❌ Rad etish", callback_data=f"admin_reject_{user.id}")],
        ]
        admin_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            ADMIN_ID,
            f"💰 *Yangi to'lov so'rovi*\n\n"
            f"👤 Foydalanuvchi: {user.first_name} (@{user.username})\n"
            f"🆔 ID: `{user.id}`\n"
            f"📄 Hujjat: {DOC_TYPES[doc_type]}\n"
            f"📌 Mavzu: _{topic}_\n"
            f"💵 Summa: *{PRICE:,} so'm*",
            parse_mode="Markdown",
            reply_markup=admin_markup
        )

    await query.edit_message_text(
        "⏳ *To'lov tekshirilmoqda...*\n\n"
        "Admin tomonidan tasdiqlanishi bilanoq hujjatingiz tayyorlanadi.\n"
        "Odatda 5-15 daqiqa ichida.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin to'lovni tasdiqlaydi"""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Ruxsat yo'q")
        return

    parts = query.data.split("_")
    target_user_id = int(parts[2])
    doc_type = parts[3]

    await query.answer("✅ Tasdiqlandi")
    await query.edit_message_text("✅ To'lov tasdiqlandi, hujjat tayyorlanmoqda...")

    # Foydalanuvchiga xabar
    await context.bot.send_message(
        target_user_id,
        "✅ *To'lovingiz tasdiqlandi!*\n\n⏳ Hujjat tayyorlanmoqda...",
        parse_mode="Markdown"
    )

    # Hujjatni generatsiya qilish
    # Mavzuni qayta so'rash kerak - context.user_data boshqa foydalanuvchida
    # Shuning uchun pending_requests da saqlaymiz
    pending = db.get_pending_request(target_user_id)
    if pending:
        topic = pending.get("topic", "")
        fake_update = type('Update', (), {
            'effective_user': type('User', (), {'id': target_user_id})(),
            'message': type('Message', (), {
                'reply_text': lambda text, **kwargs: context.bot.send_message(target_user_id, text, **kwargs)
            })()
        })()
        context.user_data["topic"] = topic
        context.user_data["doc_type"] = doc_type
        await generate_and_send_direct(context.bot, target_user_id, topic, doc_type)
        db.clear_pending(target_user_id)


async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Ruxsat yo'q")
        return

    target_user_id = int(query.data.split("_")[2])
    await query.answer("❌ Rad etildi")
    await query.edit_message_text("❌ To'lov rad etildi")
    await context.bot.send_message(
        target_user_id,
        "❌ *To'lovingiz tasdiqlanmadi.*\n\nQo'shimcha ma'lumot uchun adminга murojaat qiling.",
        parse_mode="Markdown"
    )


async def generate_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             user_id: int, topic: str, doc_type: str):
    """AI yordamida hujjat yaratib yuborish"""
    try:
        # Pending saqla (to'lov holati uchun)
        db.save_pending_request(user_id, {"topic": topic, "doc_type": doc_type})

        # AI dan kontent olish
        progress_msg = await update.message.reply_text(
            "🤖 *AI kontent yozmoqda...* (1/3)",
            parse_mode="Markdown"
        )

        content = await ai.generate_content(topic, doc_type)

        await progress_msg.edit_text(
            "📄 *Hujjat yaratilmoqda...* (2/3)",
            parse_mode="Markdown"
        )

        # Fayl yaratish
        if doc_type == "pptx":
            file_path = await create_pptx(topic, content)
            file_name = f"Prezentatsiya_{topic[:30]}.pptx"
        else:
            file_path = await create_docx(topic, content, doc_type)
            type_names = {"mustaqil": "Mustaqil_ish", "amaliy": "Amaliy_ish", "referat": "Referat"}
            file_name = f"{type_names.get(doc_type, 'Hujjat')}_{topic[:30]}.docx"

        await progress_msg.edit_text(
            "📤 *Yuborilmoqda...* (3/3)",
            parse_mode="Markdown"
        )

        # Faylni yuborish
        with open(file_path, "rb") as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=file_name,
                caption=f"✅ *{DOC_TYPES[doc_type]}* tayyor!\n\n📌 Mavzu: _{topic}_\n\n"
                        f"📱 Yana hujjat kerak bo'lsa /start ni bosing",
                parse_mode="Markdown"
            )

        await progress_msg.delete()
        db.log_generation(user_id, doc_type, topic)

        # Faylni o'chirish
        os.remove(file_path)

    except Exception as e:
        logger.error(f"Generate error: {e}")
        await update.message.reply_text(
            "❌ Xatolik yuz berdi. Iltimos qayta urinib ko'ring yoki /start bosing.",
        )


async def generate_and_send_direct(bot, user_id: int, topic: str, doc_type: str):
    """Admin tasdiqlagandan keyin to'g'ridan-to'g'ri yuborish"""
    try:
        content = await ai.generate_content(topic, doc_type)

        if doc_type == "pptx":
            file_path = await create_pptx(topic, content)
            file_name = f"Prezentatsiya_{topic[:30]}.pptx"
        else:
            file_path = await create_docx(topic, content, doc_type)
            type_names = {"mustaqil": "Mustaqil_ish", "amaliy": "Amaliy_ish", "referat": "Referat"}
            file_name = f"{type_names.get(doc_type, 'Hujjat')}_{topic[:30]}.docx"

        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=user_id,
                document=f,
                filename=file_name,
                caption=f"✅ *{DOC_TYPES[doc_type]}* tayyor!\n\n📌 Mavzu: _{topic}_",
                parse_mode="Markdown"
            )
        os.remove(file_path)

    except Exception as e:
        logger.error(f"Direct generate error: {e}")
        await bot.send_message(user_id, "❌ Xatolik yuz berdi. Admin bilan bog'laning.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Bekor qilindi. /start bosing.")
    else:
        await update.message.reply_text("❌ Bekor qilindi. /start bosing.")
    return ConversationHandler.END


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    balance = db.get_balance(user.id)
    free_used = db.get_free_used(user.id)
    total_docs = db.get_total_generations(user.id)

    free_status = "✅ Ishlatilgan" if free_used else "🎁 Mavjud"

    await update.message.reply_text(
        f"👤 *Hisobingiz*\n\n"
        f"💰 Balans: *{balance:,} so'm*\n"
        f"🎁 Bepul generatsiya: {free_status}\n"
        f"📄 Jami hujjatlar: *{total_docs}* ta\n\n"
        f"Balansni to'ldirish uchun /pay buyrug'ini yuboring",
        parse_mode="Markdown"
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 *Bot statistikasi*\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['users']}*\n"
        f"📄 Jami hujjatlar: *{stats['docs']}*\n"
        f"💰 Jami daromad: *{stats['revenue']:,} so'm*\n"
        f"📅 Bugun: *{stats['today']}* ta hujjat",
        parse_mode="Markdown"
    )


async def add_balance_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin foydalanuvchiga balans qo'shadi: /addbalance USER_ID SUMMA"""
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        args = context.args
        user_id = int(args[0])
        amount = int(args[1])
        db.add_balance(user_id, amount)
        await update.message.reply_text(f"✅ {user_id} ga {amount:,} so'm qo'shildi")
        await context.bot.send_message(
            user_id,
            f"✅ Hisobingizga *{amount:,} so'm* qo'shildi!\n\n"
            f"Hujjat uchun /start bosing.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}\nFoydalanish: /addbalance USER_ID SUMMA")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_TYPE: [CallbackQueryHandler(choose_type, pattern="^type_")],
            ENTERING_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_topic)],
            WAITING_PAYMENT: [
                CallbackQueryHandler(pay_now, pattern="^pay_now$"),
                CallbackQueryHandler(paid_confirm, pattern="^paid_confirm$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("addbalance", add_balance_admin))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern="^admin_approve_"))
    app.add_handler(CallbackQueryHandler(admin_reject, pattern="^admin_reject_"))

    logger.info("EduBot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
