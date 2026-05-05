import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters, ConversationHandler,
)
from sheets import (
    get_user_points, add_points, deduct_points,
    redeem_points, get_all_users, ensure_user_exists,
)
from config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_FOR_USER_ID, WAITING_FOR_POINTS = range(2)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    keyboard = [
        [InlineKeyboardButton("💰 Check My Balance", callback_data="check_balance")],
        [InlineKeyboardButton("🎁 Redeem Points", callback_data="redeem_points")],
    ]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\n🏆 *NovaTCG Loyalty Points Bot*\nEarn, track, and redeem your loyalty points here.\n\nWhat would you like to do?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    points = get_user_points(user.id)
    await update.message.reply_text(f"💰 *Your Points Balance*\n\nYou currently have *{points} points*.", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data == "check_balance":
        points = get_user_points(user.id)
        await query.edit_message_text(
            f"💰 *Your Points Balance*\n\nYou currently have *{points} points*.\n\nKeep engaging to earn more! 🎉",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
        )

    elif data == "redeem_points":
        points = get_user_points(user.id)
        if points < 100:
            await query.edit_message_text(
                f"❌ *Insufficient Points*\n\nYou need at least *100 points* to redeem.\nYou currently have *{points} points*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
            )
        else:
            keyboard = [
                [InlineKeyboardButton("🎟 Redeem 100 pts → $1 voucher", callback_data="redeem_100")],
                [InlineKeyboardButton("🎟 Redeem 500 pts → $6 voucher", callback_data="redeem_500")],
                [InlineKeyboardButton("🎟 Redeem 1000 pts → $15 voucher", callback_data="redeem_1000")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_home")],
            ]
            await query.edit_message_text(
                f"🎁 *Redeem Points*\n\nYour balance: *{points} points*\n\nChoose a redemption option:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif data.startswith("redeem_"):
        cost = int(data.split("_")[1])
        voucher_map = {100: "$1", 500: "$6", 1000: "$15"}
        points = get_user_points(user.id)
        if points < cost:
            await query.edit_message_text(
                f"❌ You need *{cost} points* but only have *{points}*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
            )
        else:
            success = redeem_points(user.id, cost)
            if success:
                new_balance = get_user_points(user.id)
                await query.edit_message_text(
                    f"✅ *Redemption Successful!*\n\nYou redeemed *{cost} points* for a *{voucher_map[cost]} voucher*.\nRemaining balance: *{new_balance} points*\n\nAn admin will contact you shortly with your voucher. 🎉",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
                )

    elif data == "admin_panel":
        if not is_admin(user.id):
            await query.edit_message_text("⛔ You are not authorised.")
            return
        keyboard = [
            [InlineKeyboardButton("➕ Add Points", callback_data="admin_add")],
            [InlineKeyboardButton("➖ Deduct Points", callback_data="admin_deduct")],
            [InlineKeyboardButton("👥 View All Users", callback_data="admin_users")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_home")],
        ]
        await query.edit_message_text("⚙️ *Admin Panel*\n\nSelect an action:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_users":
        if not is_admin(user.id):
            return
        users = get_all_users()
        msg = "👥 *All Users & Points*\n\n" if users else "No users found."
        for u in users:
            msg += f"• {u['name']} (@{u['username']}) — *{u['points']} pts*\n"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]]))

    elif data == "back_home":
        keyboard = [
            [InlineKeyboardButton("💰 Check My Balance", callback_data="check_balance")],
            [InlineKeyboardButton("🎁 Redeem Points", callback_data="redeem_points")],
        ]
        if is_admin(user.id):
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text("🏆 *NovaTCG Loyalty Points Bot*\n\nWhat would you like to do?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text.strip())
        points = get_user_points(target_id)
        if points is None:
            await update.message.reply_text("❌ User not found in the system.")
            return ConversationHandler.END
        context.user_data["target_id"] = target_id
        action = context.user_data.get("admin_action")
        await update.message.reply_text(
            f"User found! Current balance: *{points} pts*\n\nHow many points do you want to {'add ➕' if action == 'add' else 'deduct ➖'}?",
            parse_mode="Markdown",
        )
        return WAITING_FOR_POINTS
    except ValueError:
        await update.message.reply_text("⚠️ Please send a valid numeric Telegram User ID.")
        return WAITING_FOR_USER_ID

async def receive_points_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            raise ValueError
        target_id = context.user_data["target_id"]
        action = context.user_data["admin_action"]
        if action == "add":
            new_balance = add_points(target_id, amount)
            await update.message.reply_text(f"✅ *{amount} points added!*\nNew balance: *{new_balance} pts*", parse_mode="Markdown")
        else:
            result = deduct_points(target_id, amount)
            if result is None:
                await update.message.reply_text("❌ Insufficient points to deduct.")
            else:
                await update.message.reply_text(f"✅ *{amount} points deducted!*\nNew balance: *{result} pts*", parse_mode="Markdown")
        return ConversationHandler.END
    except (ValueError, KeyError):
        await update.message.reply_text("⚠️ Please enter a valid positive number.")
        return WAITING_FOR_POINTS

async def admin_action_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not is_admin(user.id):
        return ConversationHandler.END
    action = "add" if query.data == "admin_add" else "deduct"
    context.user_data["admin_action"] = action
    await query.edit_message_text(
        f"{'➕ Add' if action == 'add' else '➖ Deduct'} Points\n\nPlease reply with the *Telegram User ID* of the user:",
        parse_mode="Markdown",
    )
    return WAITING_FOR_USER_ID

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action cancelled.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_action_entry, pattern="^admin_(add|deduct)$")],
        states={
            WAITING_FOR_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id)],
            WAITING_FOR_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_points_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("Bot is running...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling()

if __name__ == "__main__":
    main()