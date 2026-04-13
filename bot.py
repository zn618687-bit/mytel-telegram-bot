import logging
import re
import os
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import BOT_TOKEN
from database import init_db, add_user, add_account, get_accounts, delete_account, set_user_state, get_user_state, delete_user_state, get_account_by_id
from mytel_api import send_otp, validate_otp, get_balance
from keyboards import main_menu_keyboard, login_method_keyboard, back_to_main_menu_keyboard, account_list_keyboard, account_management_keyboard, cancel_keyboard
from messages import MESSAGES

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation handler
PHONE_NUMBER, OTP_CODE, TOKEN_INPUT, ALIAS_INPUT = range(4)

async def start(update: Update, context) -> None:
    user = update.effective_user
    await add_user(user.id, user.first_name, user.username)
    await update.message.reply_html(
        MESSAGES["start"].format(name=user.mention_html()),
        reply_markup=main_menu_keyboard()
    )
    await delete_user_state(user.id)

async def main_menu(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        MESSAGES["main_menu"],
        reply_markup=main_menu_keyboard()
    )
    await delete_user_state(query.from_user.id)

async def add_account_prompt(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        MESSAGES["login_method_menu"],
        reply_markup=login_method_keyboard()
    )
    await set_user_state(query.from_user.id, "ADD_ACCOUNT_METHOD")

async def login_otp_start(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        MESSAGES["enter_phone_number"],
        reply_markup=cancel_keyboard()
    )
    await set_user_state(query.from_user.id, "WAITING_FOR_PHONE_NUMBER")

async def receive_phone_number(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)

    if user_state and user_state[0] == "WAITING_FOR_PHONE_NUMBER":
        phone_number = update.message.text
        if not re.fullmatch(r"^09\d{7,9}$", phone_number):
            await update.message.reply_text(MESSAGES["invalid_phone_number"])
            return

        context.user_data["phone_number"] = phone_number
        try:
            otp_response = await send_otp(phone_number)
            if otp_response and otp_response.get("errorCode") == 200:
                await update.message.reply_text(
                    MESSAGES["otp_sent"].format(phone_number=phone_number),
                    reply_markup=cancel_keyboard()
                )
                await set_user_state(user_id, "WAITING_FOR_OTP_CODE", phone_number)
            else:
                logger.error(f"OTP request failed for {phone_number}: {otp_response}")
                await update.message.reply_text(MESSAGES["something_went_wrong"], reply_markup=back_to_main_menu_keyboard())
                await delete_user_state(user_id)
        except Exception as e:
            logger.error(f"Error sending OTP for {phone_number}: {e}")
            await update.message.reply_text(MESSAGES["something_went_wrong"], reply_markup=back_to_main_menu_keyboard())
            await delete_user_state(user_id)
    else:
        await update.message.reply_text(MESSAGES["main_menu"], reply_markup=main_menu_keyboard())

async def receive_otp_code(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)

    if user_state and user_state[0] == "WAITING_FOR_OTP_CODE":
        otp_code = update.message.text
        phone_number = user_state[1]

        try:
            validate_response = await validate_otp(phone_number, otp_code)
            logger.info(f"OTP Validation Response: {validate_response}")
            
            if validate_response and validate_response.get("errorCode") == 200:
                # Handle both cases: with and without result key
                if "result" in validate_response and "access_token" in validate_response["result"]:
                    access_token = validate_response["result"]["access_token"]
                elif "access_token" in validate_response:
                    access_token = validate_response["access_token"]
                else:
                    logger.error(f"No access_token in OTP response: {validate_response}")
                    await update.message.reply_text(MESSAGES["invalid_otp"], reply_markup=cancel_keyboard())
                    return
                
                context.user_data["new_account_phone"] = phone_number
                context.user_data["new_account_token"] = access_token
                await update.message.reply_text(MESSAGES["otp_login_success"])
                await update.message.reply_text(MESSAGES["enter_alias"], reply_markup=cancel_keyboard())
                await set_user_state(user_id, "WAITING_FOR_ALIAS")
            else:
                logger.error(f"OTP validation failed for {phone_number} with OTP {otp_code}: {validate_response}")
                error_msg = validate_response.get("message", MESSAGES["invalid_otp"]) if validate_response else MESSAGES["invalid_otp"]
                await update.message.reply_text(error_msg, reply_markup=cancel_keyboard())
        except Exception as e:
            logger.error(f"Error validating OTP for {phone_number}: {e}", exc_info=True)
            await update.message.reply_text(MESSAGES["something_went_wrong"], reply_markup=back_to_main_menu_keyboard())
            await delete_user_state(user_id)
    else:
        await update.message.reply_text(MESSAGES["main_menu"], reply_markup=main_menu_keyboard())

async def login_token_start(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        MESSAGES["enter_token"],
        reply_markup=cancel_keyboard()
    )
    await set_user_state(query.from_user.id, "WAITING_FOR_TOKEN")

async def receive_token(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)

    if user_state and user_state[0] == "WAITING_FOR_TOKEN":
        token = update.message.text
        # Try to get balance to validate token and extract phone number
        try:
            # Dummy ISDN for token validation, actual ISDN will be stored with account
            balance_response = await get_balance(token, "09688888888") # Use a dummy Mytel number for validation
            if balance_response and balance_response.get("errorCode") == 0:
                # Extract phone number from balance_response if available, otherwise ask
                phone_number = balance_response["result"][0]["msisdn"]
                context.user_data["new_account_phone"] = phone_number
                context.user_data["new_account_token"] = token
                await update.message.reply_text(MESSAGES["token_login_success"])
                await update.message.reply_text(MESSAGES["enter_alias"], reply_markup=cancel_keyboard())
                await set_user_state(user_id, "WAITING_FOR_ALIAS")
            elif balance_response and balance_response.get("errorCode") == 401:
                await update.message.reply_text(MESSAGES["invalid_token"], reply_markup=cancel_keyboard())
            else:
                logger.error(f"Token validation failed: {balance_response}")
                await update.message.reply_text(MESSAGES["invalid_token"], reply_markup=cancel_keyboard())
        except Exception as e:
            logger.error(f"Error validating token: {e}")
            await update.message.reply_text(MESSAGES["invalid_token"], reply_markup=cancel_keyboard())
    else:
        await update.message.reply_text(MESSAGES["main_menu"], reply_markup=main_menu_keyboard())

async def receive_alias(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)

    if user_state and user_state[0] == "WAITING_FOR_ALIAS":
        alias = update.message.text
        if alias == "/skip":
            alias = None
            await update.message.reply_text(MESSAGES["skip_alias"])
        else:
            await update.message.reply_text(MESSAGES["alias_set_success"])

        phone_number = context.user_data.get("new_account_phone")
        token = context.user_data.get("new_account_token")

        if phone_number and token:
            try:
                await add_account(user_id, phone_number, token, alias)
                await update.message.reply_text(MESSAGES["account_added_success"], reply_markup=main_menu_keyboard())
            except Exception as e:
                logger.error(f"Error adding account for user {user_id}: {e}")
                await update.message.reply_text(MESSAGES["account_already_exists"], reply_markup=main_menu_keyboard())
            finally:
                await delete_user_state(user_id)
                context.user_data.pop("new_account_phone", None)
                context.user_data.pop("new_account_token", None)
        else:
            await update.message.reply_text(MESSAGES["something_went_wrong"], reply_markup=main_menu_keyboard())
            await delete_user_state(user_id)
    else:
        await update.message.reply_text(MESSAGES["main_menu"], reply_markup=main_menu_keyboard())

async def check_balance_all(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    accounts = await get_accounts(user_id)
    if not accounts:
        await query.edit_message_text(MESSAGES["no_accounts"], reply_markup=back_to_main_menu_keyboard())
        return

    response_messages = []
    for acc_id, phone, alias, token in accounts:
        try:
            balance_response = await get_balance(token, phone)
            if balance_response and balance_response.get("errorCode") == 0:
                main_balance = balance_response["result"][0]["mainBalance"]["main"]["amount"]
                promo_balance = balance_response["result"][0]["mainBalance"]["promo"]["amount"]
                voice_balance = balance_response["result"][0]["mainBalance"]["voice"]["amount"]
                data_balance = balance_response["result"][0]["mainBalance"]["data"]["amount"]
                total_balance = main_balance + promo_balance

                response_messages.append(
                    MESSAGES["balance_info"].format(
                        phone=alias if alias else phone,
                        main_balance=main_balance,
                        promo_balance=promo_balance,
                        voice_balance=voice_balance,
                        data_balance=data_balance,
                        total_balance=total_balance
                    )
                )
            elif balance_response and balance_response.get("errorCode") == 401:
                await delete_account(acc_id, user_id)
                response_messages.append(MESSAGES["token_expired_auto_delete"].format(phone=alias if alias else phone))
            else:
                logger.error(f"Balance check failed for {phone}: {balance_response}")
                response_messages.append(MESSAGES["balance_check_failed"].format(phone=alias if alias else phone))
        except Exception as e:
            logger.error(f"Error checking balance for {phone}: {e}")
            response_messages.append(MESSAGES["balance_check_failed"].format(phone=alias if alias else phone))

    if response_messages:
        final_message = "\n\n---\n\n".join(response_messages)
        await query.edit_message_text(final_message, parse_mode="Markdown", reply_markup=back_to_main_menu_keyboard())
    else:
        await query.edit_message_text(MESSAGES["something_went_wrong"], reply_markup=back_to_main_menu_keyboard())
    await delete_user_state(user_id)

async def manage_accounts_list(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    accounts = await get_accounts(user_id)
    if not accounts:
        await query.edit_message_text(MESSAGES["no_accounts"], reply_markup=back_to_main_menu_keyboard())
        return

    await query.edit_message_text(
        MESSAGES["your_accounts"],
        reply_markup=account_list_keyboard(accounts)
    )
    await delete_user_state(user_id)

async def select_account_to_manage(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])

    account = await get_account_by_id(account_id, user_id)
    if not account:
        await query.edit_message_text(MESSAGES["something_went_wrong"], reply_markup=back_to_main_menu_keyboard())
        return

    _, phone, alias, _ = account
    display_name = alias if alias else phone

    await query.edit_message_text(
        MESSAGES["account_details"].format(phone=display_name),
        reply_markup=account_management_keyboard(account_id)
    )
    await delete_user_state(user_id)

async def check_balance_single(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])

    account = await get_account_by_id(account_id, user_id)
    if not account:
        await query.edit_message_text(MESSAGES["something_went_wrong"], reply_markup=back_to_main_menu_keyboard())
        return

    _, phone, alias, token = account
    display_name = alias if alias else phone

    try:
        balance_response = await get_balance(token, phone)
        if balance_response and balance_response.get("errorCode") == 0:
            main_balance = balance_response["result"][0]["mainBalance"]["main"]["amount"]
            promo_balance = balance_response["result"][0]["mainBalance"]["promo"]["amount"]
            voice_balance = balance_response["result"][0]["mainBalance"]["voice"]["amount"]
            data_balance = balance_response["result"][0]["mainBalance"]["data"]["amount"]
            total_balance = main_balance + promo_balance

            message_text = MESSAGES["balance_info"].format(
                phone=display_name,
                main_balance=main_balance,
                promo_balance=promo_balance,
                voice_balance=voice_balance,
                data_balance=data_balance,
                total_balance=total_balance
            )
            await query.edit_message_text(message_text, parse_mode="Markdown", reply_markup=account_management_keyboard(account_id))
        elif balance_response and balance_response.get("errorCode") == 401:
            await delete_account(account_id, user_id)
            await query.edit_message_text(MESSAGES["token_expired_auto_delete"].format(phone=display_name), reply_markup=back_to_main_menu_keyboard())
        else:
            logger.error(f"Single balance check failed for {phone}: {balance_response}")
            await query.edit_message_text(MESSAGES["balance_check_failed"].format(phone=display_name), reply_markup=account_management_keyboard(account_id))
    except Exception as e:
        logger.error(f"Error checking single balance for {phone}: {e}")
        await query.edit_message_text(MESSAGES["balance_check_failed"].format(phone=display_name), reply_markup=account_management_keyboard(account_id))
    await delete_user_state(user_id)

async def view_token(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])

    account = await get_account_by_id(account_id, user_id)
    if not account:
        await query.edit_message_text(MESSAGES["something_went_wrong"], reply_markup=back_to_main_menu_keyboard())
        return

    _, _, _, token = account
    await query.edit_message_text(
        MESSAGES["token_info"].format(token=token),
        parse_mode="MarkdownV2",
        reply_markup=account_management_keyboard(account_id)
    )
    await delete_user_state(user_id)

async def delete_account_confirm(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])

    await delete_account(account_id, user_id)
    await query.edit_message_text(MESSAGES["account_deleted_success"], reply_markup=main_menu_keyboard())
    await delete_user_state(user_id)

async def cancel_operation(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(MESSAGES["operation_cancelled"], reply_markup=main_menu_keyboard())
    await delete_user_state(query.from_user.id)

async def unknown_message(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)

    if user_state and user_state[0] == "WAITING_FOR_PHONE_NUMBER":
        await receive_phone_number(update, context)
    elif user_state and user_state[0] == "WAITING_FOR_OTP_CODE":
        await receive_otp_code(update, context)
    elif user_state and user_state[0] == "WAITING_FOR_TOKEN":
        await receive_token(update, context)
    elif user_state and user_state[0] == "WAITING_FOR_ALIAS":
        await receive_alias(update, context)
    else:
        await update.message.reply_text(MESSAGES["main_menu"], reply_markup=main_menu_keyboard())

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(BOT_TOKEN).build()

    # Initialize database
    import asyncio
    asyncio.run(init_db())

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(add_account_prompt, pattern="^add_account$"))
    application.add_handler(CallbackQueryHandler(login_otp_start, pattern="^login_otp$"))
    application.add_handler(CallbackQueryHandler(login_token_start, pattern="^login_token$"))
    application.add_handler(CallbackQueryHandler(check_balance_all, pattern="^check_balance$"))
    application.add_handler(CallbackQueryHandler(manage_accounts_list, pattern="^manage_accounts$"))
    application.add_handler(CallbackQueryHandler(select_account_to_manage, pattern="^select_account_\\d+$"))
    application.add_handler(CallbackQueryHandler(check_balance_single, pattern="^check_balance_single_\\d+$"))
    application.add_handler(CallbackQueryHandler(view_token, pattern="^view_token_\\d+$"))
    application.add_handler(CallbackQueryHandler(delete_account_confirm, pattern="^delete_account_\\d+$"))
    application.add_handler(CallbackQueryHandler(cancel_operation, pattern="^cancel$"))

    # Message handler for states
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
