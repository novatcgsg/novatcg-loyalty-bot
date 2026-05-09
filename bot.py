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
    get_unprocessed_purchases, mark_purchase_processed,
    get_user_id_by_username,
)
from config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_FOR_USER_ID, WAITING_FOR_POINTS = range(2)

VOUCHER_MAP = {
    1.0: "Free Tracked Mailing",
    1.5: "1 Chance for Nova Quarterly Giveaway Spin",
    5.0: "$3 Store Credit",
    7.0: "$5 Store Credit",
    11.0: "$8 Store Credit",
    13.0: "$10 Store Credit",
    15.0: "1 Mega Brave or 1 Mega Symp Bundle of 10 Packs",
    17.0: "1 Ninja Spinner Bundle of 10 Packs",
    19.0: "1 First Partner Series 1 Collection (Limited Stock)",
    25.0: "1 x PSA 10 Slab (View catalogue for options)",
    30.0: "1 x ETB / Booster Box Jap/Eng (View catalogue for options)",
}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def process_purchases(context):
    logger.info("Checking for unprocessed purchases...")
    try:
        purchases = get_unprocessed_purchases()
        for purchase in purchases:
            username = purchase["username"].lstrip("@")
            try:
                amount = float(purchase["amount"].replace("$", "").replace(",", ""))
            except ValueError:
                logger.warning(f"Invalid amount for {username}: {purchase['amount']}")
                continue

            points_to_award = int(amount // 100)
            if points_to_award <= 0:
                mark_purchase_processed(purchase["row_index"], 0)
                continue

            user_id, name = get_user_id_by_username(username)
            if user_id is None:
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"Warning: User @{username} not found in Loyalty sheet. Please check and add manually.",
                        )
                    except Exception:
                        pass
                continue

            new_balance = add_points(int(user_id), points_to_award)
            mark_purchase_processed(purchase["row_index"], points_to_award)

            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"*Points Added!*\n\nHi {name}! You have been awarded *{points_to_award} point(s)* for your recent purchase of ${amount:.2f}.\n\nYour new balance: *{new_balance} points*\n\nThank you for shopping with NovaTCG!",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"*Points Auto-Awarded*\n\nUser: @{username}\nPurchase: ${amount:.2f}\nPoints awarded: *{points_to_award}*\nNew balance: *{new_balance} pts*",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Error processing purchases: {e}")


def main_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("Check My Balance", callback_data="check_balance")],
        [InlineKeyboardButton("Redeem Points", callback_data="redeem_points")],
        [InlineKeyboardButton("How to Earn Points", callback_data="how_to_earn")],
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)


def redeem_keyboard(points):
    keyboard = []
    for cost, prize in VOUCHER_MAP.items():
        cost_display = int(cost) if cost == int(cost) else cost
        if points >= cost:
            keyboard.append([InlineKeyboardButton(
                f"✅ {cost_display} pt - {prize}",
                callback_data=f"redeem_{str(cost).replace('.', '_')}"
            )])
        else:
            keyboard.append([InlineKeyboardButton(
                f"🔒 {cost_display} pt - {prize}",
                callback_data="locked"
            )])
    keyboard.append([InlineKeyboardButton("Back", callback_data="back_home")])
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    await update.message.reply_text(
        f"Welcome, {user.first_name}!\n\n"
        "*Nova Rewards Bot is LIVE!*\n\n"
        "Earn points with every qualifying purchase and redeem for amazing prizes!\n\n"
        "Earn 1 point for every $100 spent!\n"
        "Sealed products do not qualify.\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_keyboard(user.id),
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    points = get_user_points(user.id)
    await update.message.reply_text(
        f"*Your Points Balance*\n\nYou currently have *{points} points*.\n\n"
        "Keep shopping to earn more points and redeem amazing prizes!",
        parse_mode="Markdown",
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data == "locked":
        await query.answer("You do not have enough points for this prize yet. Keep shopping!", show_alert=True)
        return

    elif data == "check_balance":
        points = get_user_points(user.id)
        await query.edit_message_text(
            f"*Your Points Balance*\n\n"
            f"You currently have *{points} points*.\n\n"
            "Keep shopping to earn more and redeem amazing prizes!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]),
        )

    elif data == "how_to_earn":
        await query.edit_message_text(
            "*How to Earn Points*\n\n"
            "Spend $100 and earn 1 point\n\n"
            "*Eligibility Rules:*\n"
            "- In-store purchases\n"
            "- Online orders\n"
            "- TikTok Live purchases\n"
            "- Sealed products do NOT qualify\n"
            "- Shipping fees do not qualify\n\n"
            "Points are added by admin after each qualifying purchase.\n"
            "Contact us if you have any questions!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]),
        )

    elif data == "redeem_points":
        points = get_user_points(user.id)
        await query.edit_message_text(
            f"*Redeem Points*\n\n"
            f"Your balance: *{points} points*\n\n"
            "✅ = Available to redeem\n"
            "🔒 = Not enough points yet\n\n"
            "Choose your prize:",
            parse_mode="Markdown",
            reply_markup=redeem_keyboard(points),
        )

    elif data.startswith("redeem_"):
        cost_str = data.replace("redeem_", "").replace("_", ".")
        cost = float(cost_str)
        prize = VOUCHER_MAP.get(cost, "Unknown Prize")
        points = get_user_points(user.id)
        if points < cost:
            await query.edit_message_text(
                f"You need *{cost} points* but only have *{points}*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]),
            )
        else:
            success = redeem_points(user.id, int(cost))
            if success:
                new_balance = get_user_points(user.id)
                cost_display = int(cost) if cost == int(cost) else cost
                await query.edit_message_text(
                    f"*Redemption Successful!*\n\n"
                    f"You redeemed *{cost_display} point(s)* for:\n*{prize}*\n\n"
                    f"Remaining balance: *{new_balance} points*\n\n"
                    f"An admin will contact you shortly.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]),
                )
                username = f"@{user.username}" if user.username else "No username"
                notify_msg = (
                    f"*New Redemption Request!*\n\n"
                    f"User: {user.first_name} ({username})\n"
                    f"User ID: {user.id}\n"
                    f"Redeemed: *{cost_display} points* for *{prize}*\n"
                    f"Remaining balance: *{new_balance} points*"
                )
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(chat_id=admin_id, text=notify_msg, parse_mode="Markdown")
                    except Exception:
                        pass
            else:
                await query.edit_message_text("Something went wrong. Please try again.")

    elif data == "admin_panel":
        if not is_admin(user.id):
            await query.edit_message_text("You are not authorised.")
            return
        keyboard = [
            [InlineKeyboardButton("Add Points", callback_data="admin_add")],
            [InlineKeyboardButton("Deduct Points", callback_data="admin_deduct")],
            [InlineKeyboardButton("View All Users", callback_data="admin_users")],
            [InlineKeyboardButton("Back", callback_data="back_home")],
        ]
        await query.edit_message_text(
            "*Admin Panel*\n\nSelect an action:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "admin_users":
        if not is_admin(user.id):
            return
        users = get_all_users()
        msg = "*All Users and Points*\n\n" if users else "No users found."
        for u in users:
            msg += f"- {u['name']} (@{u['username']}) - *{u['points']} pts*\n"
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]]),
        )

    elif data == "back_home":
        await query.edit_message_text(
            "*Nova Rewards Bot*\n\n"
            "Earn 1 point for every $100 spent!\n"
            "Sealed products do not qualify.\n\n"
            "What would you like to do?",
            parse_mode="Markdown",
            reply_markup=main_keyboard(user.id),
        )

async def admin_action_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not is_admin(user.id):
        return ConversationHandler.END
    action = "add" if query.data == "admin_add" else "deduct"
    context.user_data["admin_action"] = action
    context.user_data["in_admin_conv"] = True
    await query.edit_message_text(
        f"{'Add' if action == 'add' else 'Deduct'} Points\n\nPlease reply with the *Telegram User ID* of the user:",
        parse_mode="Markdown",
    )
    return WAITING_FOR_USER_ID

async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text.strip())
        points = get_user_points(target_id)
        if points is None:
            await update.message.reply_text("User not found in the system.")
            context.user_data["in_admin_conv"] = False
            return ConversationHandler.END
        context.user_data["target_id"] = target_id
        action = context.user_data.get("admin_action")
        await update.message.reply_text(
            f"User found! Current balance: *{points} pts*\n\nHow many points do you want to {'add' if action == 'add' else 'deduct'}?",
            parse_mode="Markdown",
        )
        return WAITING_FOR_POINTS
    except ValueError:
        await update.message.reply_text("Please send a valid numeric Telegram User ID.")
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
            await update.message.reply_text(
                f"*{amount} points added!*\nNew balance: *{new_balance} pts*",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"*Points Added!*\n\nAn admin has added *{amount} point(s)* to your account.\n\nYour new balance: *{new_balance} points*\n\nKeep shopping with NovaTCG!",
                    parse_mode="Markdown",
                )
            except Exception:
                await update.message.reply_text("Note: Could not notify the user directly.")
        else:
            result = deduct_points(target_id, amount)
            if result is None:
                await update.message.reply_text("Insufficient points to deduct.")
            else:
                await update.message.reply_text(
                    f"*{amount} points deducted!*\nNew balance: *{result} pts*",
                    parse_mode="Markdown",
                )
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=f"*Points Update!*\n\nAn admin has deducted *{amount} point(s)* from your account.\n\nYour new balance: *{result} points*\n\nThank you for shopping with NovaTCG!",
                        parse_mode="Markdown",
                    )
                except Exception:
                    await update.message.reply_text("Note: Could not notify the user directly.")
        context.user_data["in_admin_conv"] = False
        return ConversationHandler.END
    except (ValueError, KeyError):
        await update.message.reply_text("Please enter a valid positive number.")
        return WAITING_FOR_POINTS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["in_admin_conv"] = False
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

async def smart_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("in_admin_conv"):
        return

    user = update.effective_user
    text = update.message.text.lower().strip()

    if any(w in text for w in ["balance", "points", "how many", "my points", "check"]):
        ensure_user_exists(user.id, user.first_name, user.username or "")
        points = get_user_points(user.id)
        await update.message.reply_text(
            f"*Your Points Balance*\n\nYou currently have *{points} points*.\n\n"
            "Keep shopping to earn more and redeem amazing prizes!",
            parse_mode="Markdown",
        )

    elif any(w in text for w in ["redeem", "reward", "prize", "voucher", "claim"]):
        await update.message.reply_text(
            "*Nova Rewards - Prize List*\n\n"
            "1 pt - Free Tracked Mailing\n"
            "1.5 pts - 1 Chance for Nova Quarterly Giveaway Spin\n"
            "5 pts - $3 Store Credit\n"
            "7 pts - $5 Store Credit\n"
            "11 pts - $8 Store Credit\n"
            "13 pts - $10 Store Credit\n"
            "15 pts - 1 Mega Brave or 1 Mega Symp Bundle of 10 Packs\n"
            "17 pts - 1 Ninja Spinner Bundle of 10 Packs\n"
            "19 pts - 1 First Partner Series 1 Collection (Limited Stock)\n"
            "25 pts - 1 x PSA 10 Slab (View catalogue for options)\n"
            "30 pts - 1 x ETB / Booster Box Jap/Eng (View catalogue for options)\n\n"
            "Tap Redeem Points in the menu to redeem!",
            parse_mode="Markdown",
            reply_markup=main_keyboard(user.id),
        )

    elif any(w in text for w in ["earn", "how to", "eligible", "qualify", "rules"]):
        await update.message.reply_text(
            "*How to Earn Points*\n\n"
            "Spend $100 and earn 1 point\n\n"
            "*Eligibility Rules:*\n"
            "- In-store purchases\n"
            "- Online orders\n"
            "- TikTok Live purchases\n"
            "- Sealed products do NOT qualify\n"
            "- Shipping fees do not qualify",
            parse_mode="Markdown",
        )

    elif any(w in text for w in ["hi", "hello", "hey", "helo", "hii", "sup", "yo", "good morning", "good afternoon", "good evening"]):
        await update.message.reply_text(
            f"Hey {user.first_name}! Welcome to *Nova Rewards Bot*!\n\n"
            "Earn 1 point for every $100 spent and redeem for amazing prizes!\n\n"
            "What would you like to do?",
            parse_mode="Markdown",
            reply_markup=main_keyboard(user.id),
        )

    elif any(w in text for w in ["help", "menu", "what", "how", "info", "start"]):
        await update.message.reply_text(
            f"Here is what I can do for you, {user.first_name}!\n\n"
            "Use the buttons below or type /start to access the main menu.",
            parse_mode="Markdown",
            reply_markup=main_keyboard(user.id),
        )

    else:
        await update.message.reply_text(
            f"Hey {user.first_name}! I am the *Nova Rewards Bot*.\n\n"
            "I did not quite understand that.\n\n"
            "Use the buttons below or type /start!",
            parse_mode="Markdown",
            reply_markup=main_keyboard(user.id),
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_action_entry, pattern="^admin_(add|deduct)$")],
        states={
            WAITING_FOR_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id)],
            WAITING_FOR_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_points_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
        per_message=False,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(admin_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, smart_reply))
    app.job_queue.run_repeating(process_purchases, interval=300, first=10)
    logger.info("Bot is running...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling()

if __name__ == "__main__":
    main()
