"""
EduBot - O'zbekiston talabalari uchun AI yordamchi bot
To'lov: 1 ta = 5,000 so'm | Oylik = 50,000 so'm
"""

import os
import asyncio
import logging
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

BOT_TOKEN   = os.getenv("BOT_TOKEN")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "0"))
CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 XXXX XXXX XXXX")
CARD_OWNER  = os.getenv("CARD_OWNER", "Ism Familiya")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")

PRICE_ONE     = 5000   # 1 ta hujjat
PRICE_MONTHLY = 50000  # Oylik obuna

CHOOSING_TYPE, ENTERING_TOPIC, WAITING_PAYMENT = range(3)

db = Database()
ai = AIGenerator()

DOC_TYPES = {
    "pptx":     "📊 Prezentatsiya (PPTX)",
    "mustaqil": "📝 Mustaqil ish (DOCX)",
    "amaliy":   "🔬 Amaliy ish (DOCX)",
    "referat":  "📖 Referat (DOCX)",
}

WELCOME_TEXT = """👋 *EduBot*ga xush kelibsiz!

🎓 Men sizga akademik materiallar tayyorlab beraman:

📊 *Prezentatsiya* — chiroyli slaydlar (PPTX)
📝 *Mustaqil ish* — to'liq rasmiylashtirilgan (DOCX)
🔬 *Amaliy ish* — amaliy qism bilan (DOCX)
📖 *Referat* — kirish, asosiy qism, xulosa (DOCX)

💰 *Narxlar:*
🎁 Birinchi marta — *BEPUL*
📄 1 ta hujjat — *5,000 so'm*
♾️ Oylik obuna — *50,000 so'm* (cheksiz)

Boshlaylik! 👇"""


# ═══════════════════════════════════════════════
#  START
# ═══════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = db.add_user(user.id, user.first_name, user.username)

    # Admin ga yangi foydalanuvchi xabari
    if is_new and ADMIN_ID:
        total = db.get_stats()["users"]
        await context.bot.send_message(
            ADMIN_ID,
            f"🆕 *Yangi foydalanuvchi!*\n\n"
            f"👤 {user.first_name} (@{user.username or 'username yoq'})\n"
            f"🆔 `{user.id}`\n"
            f"👥 Jami foydalanuvchilar: *{total}*",
            parse_mode="Markdown"
        )

    free_used   = db.get_free_used(user.id)
    is_monthly  = db.is_monthly_active(user.id)

    if not free_used:
        status = "🎁 Sizda 1 ta *bepul* generatsiya bor!"
    elif is_monthly:
        exp = db.get_monthly_expiry(user.id)
        status = f"♾️ *Oylik obuna* — {exp} gacha faol"
    else:
        status = "💳 *5,000 so'm* / hujjat  |  *50,000 so'm* / oy"

    keyboard = [
        [InlineKeyboardButton("📊 Prezentatsiya", callback_data="type_pptx"),
         InlineKeyboardButton("📝 Mustaqil ish",  callback_data="type_mustaqil")],
        [InlineKeyboardButton("🔬 Amaliy ish",    callback_data="type_amaliy"),
         InlineKeyboardButton("📖 Referat",        callback_data="type_referat")],
    ]
    await update.message.reply_text(
        WELCOME_TEXT + f"\n\n{status}\n\nQaysi hujjat kerak?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_TYPE


# ═══════════════════════════════════════════════
#  HUJJAT TURINI TANLASH
# ═══════════════════════════════════════════════
async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    doc_type = query.data.replace("type_", "")
    context.user_data["doc_type"] = doc_type

    await query.edit_message_text(
        f"✅ *{DOC_TYPES[doc_type]}* tanlandi\n\n"
        f"📌 Mavzuni yozing:\n\n"
        f"_Misol: \"Sun'iy intellekt va uning tibbiyotda qo'llanilishi\"_",
        parse_mode="Markdown"
    )
    return ENTERING_TOPIC


# ═══════════════════════════════════════════════
#  MAVZU KIRITISH
# ═══════════════════════════════════════════════
async def enter_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    topic    = update.message.text.strip()
    doc_type = context.user_data.get("doc_type", "pptx")

    if len(topic) < 5:
        await update.message.reply_text("❌ Mavzu juda qisqa. To'liqroq yozing.")
        return ENTERING_TOPIC
    if len(topic) > 300:
        await update.message.reply_text("❌ Mavzu 300 belgidan oshmasin.")
        return ENTERING_TOPIC

    context.user_data["topic"] = topic
    free_used  = db.get_free_used(user.id)
    is_monthly = db.is_monthly_active(user.id)
    balance    = db.get_balance(user.id)

    # ── Bepul ──────────────────────────────────
    if not free_used:
        db.save_pending_request(user.id, {"topic": topic, "doc_type": doc_type})
        msg = await update.message.reply_text(
            f"⏳ Tayyorlanmoqda...\n📌 _{topic}_", parse_mode="Markdown"
        )
        await _generate_and_send(context.bot, user.id, topic, doc_type, msg)
        db.mark_free_used(user.id)
        return ConversationHandler.END

    # ── Oylik obuna ────────────────────────────
    if is_monthly:
        db.save_pending_request(user.id, {"topic": topic, "doc_type": doc_type})
        msg = await update.message.reply_text(
            f"⏳ Tayyorlanmoqda...\n📌 _{topic}_", parse_mode="Markdown"
        )
        await _generate_and_send(context.bot, user.id, topic, doc_type, msg)
        return ConversationHandler.END

    # ── Balansdan ──────────────────────────────
    if balance >= PRICE_ONE:
        db.deduct_balance(user.id, PRICE_ONE)
        db.save_pending_request(user.id, {"topic": topic, "doc_type": doc_type})
        msg = await update.message.reply_text(
            f"⏳ Tayyorlanmoqda...\n💳 Balansdan {PRICE_ONE:,} so'm yechildi\n📌 _{topic}_",
            parse_mode="Markdown"
        )
        await _generate_and_send(context.bot, user.id, topic, doc_type, msg)
        return ConversationHandler.END

    # ── To'lov kerak ───────────────────────────
    keyboard = [
        [InlineKeyboardButton(f"📄 1 ta hujjat — {PRICE_ONE:,} so'm",     callback_data="pay_one")],
        [InlineKeyboardButton(f"♾️ Oylik obuna — {PRICE_MONTHLY:,} so'm", callback_data="pay_monthly")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel")],
    ]
    await update.message.reply_text(
        f"💰 *To'lov kerak*\n\n"
        f"Hujjat: *{DOC_TYPES[doc_type]}*\n"
        f"Mavzu: _{topic}_\n\n"
        f"Tarif tanlang:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_PAYMENT


# ═══════════════════════════════════════════════
#  TO'LOV TANLASH
# ═══════════════════════════════════════════════
async def pay_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    pay_type = query.data  # pay_one | pay_monthly
    context.user_data["pay_type"] = pay_type

    amount = PRICE_ONE if pay_type == "pay_one" else PRICE_MONTHLY
    label  = "1 ta hujjat" if pay_type == "pay_one" else "Oylik obuna (cheksiz)"

    keyboard = [
        [InlineKeyboardButton("✅ To'lov qildim", callback_data="paid_confirm")],
        [InlineKeyboardButton("❌ Bekor",          callback_data="cancel")],
    ]
    await query.edit_message_text(
        f"💳 *To'lov ma'lumotlari*\n\n"
        f"📦 Tarif: *{label}*\n"
        f"💵 Summa: *{amount:,} so'm*\n\n"
        f"🏦 Karta: `{CARD_NUMBER}`\n"
        f"👤 Egasi: *{CARD_OWNER}*\n\n"
        f"📸 To'lov chekini @{ADMIN_USERNAME} ga yuboring\n"
        f"Keyin pastdagi tugmani bosing 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_PAYMENT


# ═══════════════════════════════════════════════
#  TO'LOV TASDIQLASH (foydalanuvchi bosadi)
# ═══════════════════════════════════════════════
async def paid_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    await query.answer()
    user     = update.effective_user
    topic    = context.user_data.get("topic", "")
    doc_type = context.user_data.get("doc_type", "pptx")
    pay_type = context.user_data.get("pay_type", "pay_one")

    amount = PRICE_ONE if pay_type == "pay_one" else PRICE_MONTHLY
    label  = "1 ta hujjat" if pay_type == "pay_one" else "Oylik obuna"

    db.save_pending_request(user.id, {
        "topic": topic, "doc_type": doc_type, "pay_type": pay_type
    })

    # Admin ga xabar
    if ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton(
                f"✅ Tasdiqlash ({amount:,} so'm)",
                callback_data=f"adm_ok_{user.id}_{doc_type}_{pay_type}"
            )],
            [InlineKeyboardButton("❌ Rad etish", callback_data=f"adm_no_{user.id}")],
        ]
        await context.bot.send_message(
            ADMIN_ID,
            f"💰 *Yangi to'lov so'rovi*\n\n"
            f"👤 {user.first_name} (@{user.username or '-'})\n"
            f"🆔 `{user.id}`\n"
            f"📦 Tarif: *{label}*\n"
            f"📄 Hujjat: {DOC_TYPES[doc_type]}\n"
            f"📌 Mavzu: _{topic}_\n"
            f"💵 Summa: *{amount:,} so'm*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    await query.edit_message_text(
        "⏳ *To'lov tekshirilmoqda...*\n\n"
        "Admin tasdiqlashi bilanoq hujjatingiz tayyorlanadi.\n"
        "Odatda 5–15 daqiqa.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  ADMIN: TASDIQLASH
# ═══════════════════════════════════════════════
async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Ruxsat yo'q"); return

    # adm_ok_{user_id}_{doc_type}_{pay_type}
    parts      = query.data.split("_")
    target_id  = int(parts[2])
    doc_type   = parts[3]
    pay_type   = parts[4] if len(parts) > 4 else "pay_one"

    await query.answer("✅ Tasdiqlandi")
    await query.edit_message_text("✅ Tasdiqlandi — hujjat tayyorlanmoqda...")

    # Oylik yoki bitta
    if pay_type == "pay_monthly":
        db.activate_monthly(target_id)
        await context.bot.send_message(
            target_id,
            "✅ *Oylik obunangiz faollashtirildi!*\n\n"
            "Endi 1 oy davomida cheksiz hujjat olishingiz mumkin 🎉\n"
            "Hujjat olish uchun /start bosing.",
            parse_mode="Markdown"
        )
        return
    else:
        db.add_balance(target_id, PRICE_ONE)

    # Hujjatni tayyorlash
    pending = db.get_pending_request(target_id)
    if pending:
        topic    = pending.get("topic", "")
        doc_type = pending.get("doc_type", doc_type)
        await context.bot.send_message(
            target_id,
            "✅ *To'lovingiz tasdiqlandi!*\n⏳ Hujjat tayyorlanmoqda...",
            parse_mode="Markdown"
        )
        db.deduct_balance(target_id, PRICE_ONE)
        await _generate_and_send(context.bot, target_id, topic, doc_type)
        db.clear_pending(target_id)


# ═══════════════════════════════════════════════
#  ADMIN: RAD ETISH
# ═══════════════════════════════════════════════
async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ Ruxsat yo'q"); return

    target_id = int(query.data.split("_")[2])
    await query.answer("❌ Rad etildi")
    await query.edit_message_text("❌ Rad etildi")
    await context.bot.send_message(
        target_id,
        "❌ *To'lovingiz tasdiqlanmadi.*\n\nQo'shimcha ma'lumot: @" + ADMIN_USERNAME,
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════
#  HUJJAT GENERATSIYA — ASOSIY FUNKSIYA
# ═══════════════════════════════════════════════
async def _generate_and_send(bot, user_id: int, topic: str, doc_type: str, progress_msg=None):
    try:
        content = await ai.generate_content(topic, doc_type)

        if doc_type == "pptx":
            file_path = await create_pptx(topic, content)
            file_name = f"Prezentatsiya_{topic[:25]}.pptx"
        else:
            file_path = await create_docx(topic, content, doc_type)
            names = {"mustaqil": "Mustaqil_ish", "amaliy": "Amaliy_ish", "referat": "Referat"}
            file_name = f"{names.get(doc_type, 'Hujjat')}_{topic[:25]}.docx"

        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=user_id,
                document=f,
                filename=file_name,
                caption=(
                    f"✅ *{DOC_TYPES[doc_type]}* tayyor!\n\n"
                    f"📌 Mavzu: _{topic}_\n\n"
                    f"Yana hujjat kerak bo'lsa /start bosing 👇"
                ),
                parse_mode="Markdown"
            )

        if progress_msg:
            try: await progress_msg.delete()
            except: pass

        os.remove(file_path)
        db.log_generation(user_id, doc_type, topic)

    except Exception as e:
        logger.error(f"Generate error: {e}", exc_info=True)
        await bot.send_message(
            user_id,
            "❌ Xatolik yuz berdi. Iltimos /start bosib qayta urining."
        )


# ═══════════════════════════════════════════════
#  BEKOR QILISH
# ═══════════════════════════════════════════════
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Bekor qilindi. /start bosing.")
    else:
        await update.message.reply_text("❌ Bekor qilindi. /start bosing.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  BALANS
# ═══════════════════════════════════════════════
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user       = update.effective_user
    balance    = db.get_balance(user.id)
    free_used  = db.get_free_used(user.id)
    is_monthly = db.is_monthly_active(user.id)
    total_docs = db.get_total_generations(user.id)

    if is_monthly:
        exp = db.get_monthly_expiry(user.id)
        sub_text = f"♾️ Oylik obuna: *faol* ({exp} gacha)"
    else:
        sub_text = "📄 Oylik obuna: *faol emas*"

    await update.message.reply_text(
        f"👤 *Hisobingiz*\n\n"
        f"💰 Balans: *{balance:,} so'm*\n"
        f"🎁 Bepul: {'✅ Ishlatilgan' if free_used else '🎁 Mavjud'}\n"
        f"{sub_text}\n"
        f"📄 Jami hujjatlar: *{total_docs}* ta\n\n"
        f"/start — yangi hujjat",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════
#  ADMIN STATISTIKA
# ═══════════════════════════════════════════════
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    stats = db.get_stats()
    await update.message.reply_text(
        f"📊 *Bot statistikasi*\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['users']}*\n"
        f"📄 Jami hujjatlar: *{stats['docs']}*\n"
        f"♾️ Faol obunalar: *{stats['monthly_active']}*\n"
        f"💰 Taxminiy daromad: *{stats['revenue']:,} so'm*\n"
        f"📅 Bugun: *{stats['today']}* ta hujjat",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════
#  ADMIN: BALANS QO'SHISH
# ═══════════════════════════════════════════════
async def add_balance_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        user_id = int(context.args[0])
        amount  = int(context.args[1])
        db.add_balance(user_id, amount)
        await update.message.reply_text(f"✅ {user_id} ga {amount:,} so'm qo'shildi")
        await context.bot.send_message(
            user_id,
            f"✅ Hisobingizga *{amount:,} so'm* qo'shildi!\n/start bosing.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}\nFoydalanish: /addbalance USER_ID SUMMA")


# ═══════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_TYPE:  [CallbackQueryHandler(choose_type, pattern="^type_")],
            ENTERING_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_topic)],
            WAITING_PAYMENT: [
                CallbackQueryHandler(pay_choose,    pattern="^pay_(one|monthly)$"),
                CallbackQueryHandler(paid_confirm,  pattern="^paid_confirm$"),
                CallbackQueryHandler(cancel,        pattern="^cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("balance",    balance_cmd))
    app.add_handler(CommandHandler("stats",      admin_stats))
    app.add_handler(CommandHandler("addbalance", add_balance_admin))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern="^adm_ok_"))
    app.add_handler(CallbackQueryHandler(admin_reject,  pattern="^adm_no_"))

    logger.info("🚀 EduBot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
