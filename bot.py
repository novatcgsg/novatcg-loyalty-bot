import logging
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
PUBLIC_REDEEM_POINTS = 4

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def main_menu_keyboard(is_admin_user: bool):
    buttons = [
        [InlineKeyboardButton("🏅 Check My Points", callback_data="public_check")],
        [InlineKeyboardButton("🎁 Redeem My Points", callback_data="public_redeem")],
    ]
    if is_admin_user:
        buttons += [
            [InlineKeyboardButton("── Admin ──", callback_data="noop")],
            [InlineKeyboardButton("👤 Check Any User", callback_data="check_points")],
            [InlineKeyboardButton("➕ Add Points", callback_data="add_points")],
            [InlineKeyboardButton("➖ Deduct Points", callback_data="deduct_points")],
            [InlineKeyboardButton("📋 All Users", callback_data="all_users")],
        ]
    return InlineKeyboardMarkup(buttons)

def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back")]])

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.username or user.first_name)
    admin = is_admin(user.id)
    await update.message.reply_text(
        f"👋 Welcome *{user.first_name}*!\n\nWhat would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(admin),
    )

# ── Callback router ───────────────────────────────────────────────────────────

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    admin = is_admin(user.id)
    data = query.data

    if data == "noop":
        return

    if data == "back":
        await query.edit_message_text(
            "What would you like to do?",
            reply_markup=main_menu_keyboard(admin),
        )
        return

    # ── Public: Check own points ──
    if data == "public_check":
        points = get_user_points(user.id)
        if points is None:
            await query.edit_message_text(
                "❌ No account found. Please type /start to register.",
                reply_markup=back_keyboard(),
            )
        else:
            await query.edit_message_text(
                f"🏅 You have *{points} points*.",
                parse_mode="Markdown",
                reply_markup=back_keyboard(),
            )
        return

    # ── Public: Redeem own points ──
    if data == "public_redeem":
        points = get_user_points(user.id)
        if points is None or points == 0:
            await query.edit_message_text(
                "❌ You have no points to redeem.",
                reply_markup=back_keyboard(),
            )
            return
        context.user_data["redeem_target"] = user.id
        context.user_data["redeem_username"] = user.username or user.first_name
        await query.edit_message_text(
            f"🎁 You have *{points} pts*.\nHow many points would you like to redeem?",
            parse_mode="Markdown",
        )
        return PUBLIC_REDEEM_POINTS

    # ── Admin only below ──
    if not admin:
        await query.edit_message_text("⛔ You are not authorised to do that.")
        return

    if data == "check_points":
        context.user_data["action"] = "check"
        await query.edit_message_text("👤 Enter the Telegram user ID to check:")
        return SELECTING_USER

    elif data == "add_points":
        context.user_data["action"] = "add"
        await query.edit_message_text("➕ Enter the Telegram user ID to *add* points to:", parse_mode="Markdown")
        return SELECTING_USER

    elif data == "deduct_points":
        context.user_data["action"] = "deduct"
        await query.edit_message_text("➖ Enter the Telegram user ID to *deduct* points from:", parse_mode="Markdown")
        return SELECTING_USER

    elif data == "all_users":
        users = get_all_users()
        if not users:
            await query.edit_message_text("No users found.", reply_markup=back_keyboard())
            return
        text = "📋 *All Users & Points:*\n\n"
        for u in users:
            text += f"• `{u['user_id']}` (@{u['username']}) — {u['points']} pts\n"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())

# ── Public redeem: get points amount ─────────────────────────────────────────

async def public_redeem_get_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        points = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return PUBLIC_REDEEM_POINTS

    target = context.user_data.get("redeem_target")
    target_username = context.user_data.get("redeem_username")
    user = update.effective_user

    success = redeem_points(target, points)
    if success:
        new_total = get_user_points(target)
        await update.message.reply_text(
            f"✅ Successfully redeemed *{points} pts*!\nNew balance: *{new_total} pts*",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        # Notify all admins
        for admin_id in ADMIN_IDS:
            try:
                await update.get_bot().send_message(
                    chat_id=admin_id,
                    text=(
                        f"🔔 *Redemption Alert*\n\n"
                        f"User: @{target_username} (`{target}`)\n"
                        f"Points redeemed: *{points}*\n"
                        f"New balance: *{new_total} pts*"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Could not notify admin {admin_id}: {e}")
    else:
        await update.message.reply_text(
            "❌ Redemption failed. You may not have enough points.",
            reply_markup=back_keyboard(),
        )

    return ConversationHandler.END

# ── Admin: get user ID then points ───────────────────────────────────────────

async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_input = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid numeric Telegram user ID.")
        return SELECTING_USER

    context.user_data["target_user_id"] = user_input
    action = context.user_data.get("action")

    if action == "check":
        points = get_user_points(user_input)
        if points is None:
            await update.message.reply_text(f"❌ User `{user_input}` not found.", parse_mode="Markdown", reply_markup=back_keyboard())
        else:
            await update.message.reply_text(
                f"✅ User `{user_input}` has *{points} points*.",
                parse_mode="Markdown",
                reply_markup=back_keyboard(),
            )
        return ConversationHandler.END

    elif action in ("add", "deduct"):
        verb = "add to" if action == "add" else "deduct from"
        await update.message.reply_text(f"How many points to {verb} `{user_input}`?", parse_mode="Markdown")
        return ENTERING_POINTS


async def get_points_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        points = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ENTERING_POINTS

    action = context.user_data.get("action")
    target = context.user_data.get("target_user_id")

    if action == "add":
        success = add_points(target, points)
    else:
        success = deduct_points(target, points)

    if success:
        new_total = get_user_points(target)
        verb = "Added to" if action == "add" else "Deducted from"
        await update.message.reply_text(
            f"✅ {verb} `{target}`: *{points} pts*\nNew balance: *{new_total} pts*",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"❌ Failed. User `{target}` may not exist or has insufficient points.",
            reply_markup=back_keyboard(),
        )

    return ConversationHandler.END

# ── Cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        "❌ Cancelled.",
        reply_markup=main_menu_keyboard(is_admin(user.id)),
    )
    return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Public redeem conversation
    public_redeem_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^public_redeem$")],
        states={
            PUBLIC_REDEEM_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, public_redeem_get_points)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Admin points conversation
    admin_points_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_handler, pattern="^(add_points|deduct_points|check_points)$")],
        states={
            SELECTING_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_id)],
            ENTERING_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_points_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(public_redeem_conv)
    app.add_handler(admin_points_conv)
    app.add_handler(CallbackQueryHandler(menu_handler))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
