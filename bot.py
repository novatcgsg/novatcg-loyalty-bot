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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    keyboard = [
        [InlineKeyboardButton("Check My Balance", callback_data="check_balance")],
        [InlineKeyboardButton("Redeem Points", callback_data="redeem_points")],
        [InlineKeyboardButton("How to Earn Points", callback_data="how_to_earn")],
    ]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    await update.message.reply_text(
        f"Welcome, {user.first_name}!\n\n"
        "*Nova Rewards Bot*\n\n"
        "Something BIG is brewing at NovaTCG... \n\n"
        "💡 *Earn 1 point for every $100 spent!*\n"
        "Sealed products do not qualify.\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.first_name, user.username or "")
    points = get_user_points(user.id)
    await update.message.reply_text(
        f"*Your Points Balance*\n\nYou currently have *{points} points*.\n\n"
        "Big rewards are coming... stay tuned!",
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
            f"*Your Points Balance*\n\n"
            f"You currently have *{points} points*.\n\n"
            "Big rewards are coming... stay tuned! ",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]),
        )

    elif data == "how_to_earn":
        await query.edit_message_text(
            "*How to Earn Points*\n\n"
            "Spend *$100* and earn *1 point*\n\n"
            "*Eligibility Rules:*\n"
            "- In-store purchases\n"
            "- Online orders\n"
            "- TikTok Live purchases\n"
            "- Sealed products do NOT qualify\n"
            "- Shipping fees do not qualify\n\n"
            "*Redemption Prizes:*\n\n"
            "Something is brewing...\n\n"
            "Stack your points now and be ready to redeem amazing prizes!\n\n"
            "Stay tuned for the big reveal!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]),
        )

    elif data == "redeem_points":
        await query.edit_message_text(
            "*Redemption Coming Soon!*\n\n"
            "Something is brewing at NovaTCG...\n\n"
            "Stay tuned for the big reveal!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_home")]]),
        )

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
        await query.edit_message_text("*Admin Panel*\n\nSelect an action:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_users":
        if not is_admin(user.id):
            return
        users = get_all_users()
        msg = "*All Users and Points*\n\n" if users else "No users found."
        for u in users:
            msg += f"- {u['name']} (@{u['username']}) - *{u['points']} pts*\n"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]]))

    elif data == "back_home":
        keyboard = [
            [InlineKeyboardButton("Check My Balance", callback_data="check_balance")],
            [InlineKeyboardButton("Redeem Points", callback_data="redeem_points")],
            [InlineKeyboardButton("How to Earn Points", callback_data="how_to_earn")],
        ]
        if is_admin(user.id):
            keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
        await query.edit_message_text(
            "*Nova Rewards Bot*\n\n"
            "Something BIG is brewing at NovaTCG...\n\n"
            "What would you like to do?",
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
            await update.message.reply_text(f"*{amount} points added!*\nNew balance: *{new_balance} pts*", parse_mode="Markdown")
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
                await update.message.reply_text(f"*{amount} points deducted!*\nNew balance: *{result} pts*", parse_mode="Markdown")
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=f"*Points Update!*\n\nAn admin has deducted *{amount} point(s)* from your account.\n\nYour new balance: *{result} points*\n\nThank you for shopping with NovaTCG!",
                        parse_mode="Markdown",
                    )
                except Exception:
                    await update.message.reply_text("Note: Could not notify the user directly.")
        return ConversationHandler.END
    except (ValueError, KeyError):
        await update.message.reply_text("Please enter a valid positive number.")
        return WAITING_FOR_POINTS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Action cancelled.")
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
    app.job_queue.run_repeating(process_purchases, interval=300, first=10)
    logger.info("Bot is running...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app.run_polling()

if __name__ == "__main__":
    main()
