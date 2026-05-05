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


VOUCHER_MAP = {
    2: "Free Tracked Mail",
    3: "$5 Store Credit",
    5: "$10 Store Credit",
    8: "$20 Store Credit",
    12: "PSA 10 Slab / Sealed Pokemon Products (announced in redemption topic)",
    18: "PSA 10 Slab / Sealed Pokemon Products (announced in redemption topic)",
}
}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    keyboard = [
        [InlineKeyboardButton("💰 Check My Balance", callback_data="check_balance")],
        [InlineKeyboardButton("🎁 Redeem Points", callback_data="redeem_points")],
        [InlineKeyboardButton("ℹ️ How to Earn Points", callback_data="how_to_earn")],
    ]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\n"
        "🏆 *NovaTCG Loyalty Points Bot*\n"
        "Earn, track, and redeem your loyalty points here.\n\n"
        "💡 *Earn 1 point for every $100 spent!*\n"
        "❌ *Sealed products do not qualify.*\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    points = get_user_points(user.id)
    await update.message.reply_text(
        f"💰 *Your Points Balance*\n\nYou currently have *{points} points*.\n\n💡 Earn 1 point for every $100 spent!\n❌ Sealed products do not qualify.",
        parse_mode="Markdown",
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data == "check_balance":
        points = get_user_points(user.id)
        await query.edit_message_text(
            f"💰 *Your Points Balance*\n\nYou currently have *{points} points*.\n\n💡 Earn 1 point for every $100 spent!\nKeep shopping to earn more! 🎉",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
        )

    elif data == "how_to_earn":
        await query.edit_message_text(
            "ℹ️ *How to Earn Points*\n\n"
            "🛍 Spend *$100* → Earn *1 point*\n\n"
            "📋 *Eligibility Rules:*\n"
            "✅ Telegram Orders\n"
            "✅ TikTok Live purchases\n"
            "❌ Sealed products do NOT qualify\n"
            "❌ Claim Sales and Auctions do not qualify\n"
            "❌ Shipping cost do not qualify\n\n"
            "🎁 *Redemption Prizes:*\n"
            "2 pts → 📦 Free Tracked Mail\n"
            "3 pts → 💳 $5 Store Credit\n"
            "5 pts → 💳 $10 Store Credit\n"
            "8 pts → 💳 $20 Store Credit\n"
            "12 pts → 🏆 PSA 10 Slab / Sealed Pokemon Products(Will announce in redemption topic)\n"
            "18 pts → 🏆 PSA 10 Slab / Sealed Pokemon Products(Will announce in redemption topic)\n\n"
            "💡 Points are added by admin after each qualifying purchase.\n"
            "📩 Contact @TCGNova if you have any questions!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
        )

    elif data == "redeem_points":
        points = get_user_points(user.id)
        if points < 2:
            await query.edit_message_text(
                f"❌ *Insufficient Points*\n\nYou need at least *2 points* to redeem.\nYou currently have *{points} points*.\n\n💡 Earn 1 point for every $100 spent!\n❌ Sealed products do not qualify.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
            )
        else:
            keyboard = []
            for cost, prize in VOUCHER_MAP.items():
                if points >= cost:
                    keyboard.append([InlineKeyboardButton(f"{prize} — {cost} pts", callback_data=f"redeem_{cost}")])
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_home")])
            await query.edit_message_text(
                f"🎁 *Redeem Points*\n\nYour balance: *{points} points*\n\nAvailable prizes you can redeem:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif data.startswith("redeem_"):
        cost = int(data.split("_")[1])
        prize = VOUCHER_MAP.get(cost, "Unknown Prize")
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
                    f"✅ *Redemption Successful!*\n\nYou redeemed *{cost} points* for:\n*{prize}*\n\nRemaining balance: *{new_balance} points*\n\nAn admin will contact you shortly. 🎉",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]),
                )
                username = f"@{user.username}" if user.username else "No username"
                notify_msg = (
                    f"🔔 *New Redemption Request!*\n\n"
                    f"👤 User: {user.first_name} ({username})\n"
                    f"🆔 User ID: `{user.id}`\n"
                    f"🎟 Redeemed: *{cost} points* → *{prize}*\n"
                    f"💰 Remaining balance: *{new_balance} points*"
                )
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=notify_msg, parse_mode="Markdown")
                    except Exception:
                        pass
            else:
                await query.edit_message_text("⚠️ Something went wrong. Please try again.")

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
            [InlineKeyboardButton("ℹ️ How to Earn Points", callback_data="how_to_earn")],
        ]
        if is_admin(user.id):
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text(
            "🏆 *NovaTCG Loyalty Points Bot*\n\n💡 Earn 1 point for every $100 spent!\n❌ Sealed products do not qualify.\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

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
