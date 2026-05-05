import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)
from sheets import (
    get_user_points,
    add_points,
    deduct_points,
    redeem_points,
    get_all_users,
    ensure_user_exists,
)
from config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_USER, ENTERING_POINTS = range(2)
REDEEM_USER, REDEEM_POINTS = range(2, 4)

# ── Helpers ──────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text("⛔ You are not authorised to use this bot.")
            return
        return await func(update, context)
    return wrapper


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Check User Points", callback_data="check_points")],
        [InlineKeyboardButton("➕ Add Points", callback_data="add_points")],
        [InlineKeyboardButton("➖ Deduct Points", callback_data="deduct_points")],
        [InlineKeyboardButton("🎁 Redeem Points", callback_data="redeem_points")],
        [InlineKeyboardButton("📋 All Users", callback_data="all_users")],
    ])

# ── /start ────────────────────────────────────────────────────────────────────

@admin_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to the *NovaTCG Loyalty Bot*!\n\nWhat would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )

# ── Menu callback router ──────────────────────────────────────────────────────

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Not authorised.")
        return

    data = query.data

    if data == "check_points":
        await query.edit_message_text("👤 Enter the Telegram user ID to check points:")
        context.user_data["action"] = "check"
        return SELECTING_USER

    elif data == "add_points":
        await query.edit_message_text("➕ Enter the Telegram user ID to *add* points to:", parse_mode="Markdown")
        context.user_data["action"] = "add"
        return SELECTING_USER

    elif data == "deduct_points":
        await query.edit_message_text("➖ Enter the Telegram user ID to *deduct* points from:", parse_mode="Markdown")
        context.user_data["action"] = "deduct"
        return SELECTING_USER

    elif data == "redeem_points":
        await query.edit_message_text("🎁 Enter the Telegram user ID to *redeem* points for:", parse_mode="Markdown")
        context.user_data["action"] = "redeem"
        return REDEEM_USER

    elif data == "all_users":
        users = get_all_users()
        if not users:
            await query.edit_message_text("No users found.", reply_markup=back_keyboard())
            return
        text = "📋 *All Users & Points:*\n\n"
        for u in users:
            text += f"• `{u['user_id']}` — {u['points']} pts\n"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())

    elif data == "back":
        await query.edit_message_text(
            "What would you like to do?",
            reply_markup=main_menu_keyboard(),
        )


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])

# ── ConversationHandler: Add / Deduct / Check ─────────────────────────────────

async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    context.user_data["target_user_id"] = user_input
    action = context.user_data.get("action")

    if action == "check":
        points = get_user_points(user_input)
        if points is None:
            await update.message.reply_text(f"❌ User `{user_input}` not found.", parse_mode="Markdown", reply_markup=back_keyboard())
        else:
            await update.message.reply_text(f"✅ User `{user_input}` has *{points} points*.", parse_mode="Markdown", reply_markup=back_keyboard())
        return ConversationHandler.END

    elif action in ("add", "deduct"):
        await update.message.reply_text(f"How many points would you like to {'add to' if action == 'add' else 'deduct from'} `{user_input}`?", parse_mode="Markdown")
        return ENTERING_POINTS


async def get_points_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        points = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ENTERING_POINTS

    action = context.user_data.get("action")
    target = context.user_data.get("target_user_id")
    admin_name = update.effective_user.full_name

    if action == "add":
        success = add_points(target, points)
        if success:
            new_total = get_user_points(target)
            await update.message.reply_text(
                f"✅ Added *{points} pts* to `{target}`.\nNew balance: *{new_total} pts*",
                parse_mode="Markdown",
                reply_markup=back_keyboard(),
            )
        else:
            await update.message.reply_text(f"❌ Failed to add points. User `{target}` may not exist.", parse_mode="Markdown", reply_markup=back_keyboard())

    elif action == "deduct":
        success = deduct_points(target, points)
        if success:
            new_total = get_user_points(target)
            await update.message.reply_text(
                f"✅ Deducted *{points} pts* from `{target}`.\nNew balance: *{new_total} pts*",
                parse_mode="Markdown",
                reply_markup=back_keyboard(),
            )
        else:
            await update.message.reply_text(f"❌ Failed. User `{target}` may not exist or has insufficient points.", parse_mode="Markdown", reply_markup=back_keyboard())

    return ConversationHandler.END

# ── ConversationHandler: Redeem ───────────────────────────────────────────────

async def redeem_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    context.user_data["redeem_target"] = user_input
    points = get_user_points(user_input)
    if points is None:
        await update.message.reply_text(f"❌ User `{user_input}` not found.", parse_mode="Markdown", reply_markup=back_keyboard())
        return ConversationHandler.END
    await update.message.reply_text(
        f"User `{user_input}` has *{points} pts*.\nHow many points to redeem?",
        parse_mode="Markdown",
    )
    return REDEEM_POINTS


async def redeem_get_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        points = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return REDEEM_POINTS

    target = context.user_data.get("redeem_target")
    admin_id = update.effective_user.id
    admin_name = update.effective_user.full_name

    success = redeem_points(target, points)
    if success:
        new_total = get_user_points(target)
        msg = (
            f"✅ Redeemed *{points} pts* for `{target}`.\n"
            f"New balance: *{new_total} pts*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

        # Notify all other admins
        for admin in ADMIN_IDS:
            if admin != admin_id:
                try:
                    await update.get_bot().send_message(
                        chat_id=admin,
                        text=(
                            f"🔔 *Redemption Alert*\n\n"
                            f"Admin: {admin_name}\n"
                            f"User: `{target}`\n"
                            f"Points redeemed: *{points}*\n"
                            f"New balance: *{new_total} pts*"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning(f"Could not notify admin {admin}: {e}")
    else:
        await update.message.reply_text(
            f"❌ Redemption failed. User `{target}` may not exist or has insufficient points.",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )

    return ConversationHandler.END

# ── Cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Add/Deduct/Check conversation
    points_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^(add_points|deduct_points|check_points)$")],
        states={
            SELECTING_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id)],
            ENTERING_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_points_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Redeem conversation
    redeem_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^redeem_points$")],
        states={
            REDEEM_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_get_user)],
            REDEEM_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_get_points)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(points_conv)
    app.add_handler(redeem_conv)
    app.add_handler(CallbackQueryHandler(menu_handler))  # handles back + all_users

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
