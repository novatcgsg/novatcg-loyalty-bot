# In start()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user_exists(user.id, user.username or user.first_name)
    admin = is_admin(user.id)
    await update.message.reply_text(
        f"👋 Welcome *{user.first_name}*!\n\nWhat would you like to do?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(admin),
    )

# In public_check callback — uses user.id
if data == "public_check":
    points = get_user_points(query.from_user.id)
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

# In public_redeem callback — uses user.id
if data == "public_redeem":
    points = get_user_points(query.from_user.id)
    if points is None or points == 0:
        await query.edit_message_text(
            "❌ You have no points to redeem.",
            reply_markup=back_keyboard(),
        )
        return
    context.user_data["redeem_target"] = query.from_user.id
    context.user_data["redeem_username"] = query.from_user.username or query.from_user.first_name
    await query.edit_message_text(
        f"🎁 You have *{points} pts*.\nHow many points would you like to redeem?",
        parse_mode="Markdown",
    )
    return PUBLIC_REDEEM_POINTS
