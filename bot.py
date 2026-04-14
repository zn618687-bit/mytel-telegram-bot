import logging
import re
import os
import asyncio
from flask import Flask
import threading
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

from config import BOT_TOKEN
from database import init_db, add_user, add_account, get_accounts, delete_account, set_user_state, get_user_state, delete_user_state, get_account_by_id
from mytel_api import MytelProAPI
from keyboards import login_method_keyboard, back_to_main_menu_keyboard, account_list_keyboard, account_management_keyboard, cancel_keyboard
from messages import MESSAGES

# --- Render/Keep-Alive Flask App ---
app = Flask(__name__)

@app.route('/')
def home():
    return "⚡ Mytel Multi-Account Bot Professional Overhaul is Online!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize MytelProAPI
api = MytelProAPI()

# --- Cyberpunk Style Message Formatter ---
def format_premium_msg(text, icon="⚡"):
    return f"<b>{icon} SYSTEM:</b>\n\n{text}"

def format_balance_pro(phone, data, points="0"):
    """Professional balance formatting with robust parsing."""
    try:
        # Standard Mytel result path
        result_list = data.get("result", [])
        if not result_list:
            return f"❌ <b>Error:</b> Balance data empty for {phone}"
            
        res = result_list[0].get("mainBalance", {})
        main = res.get("main", {}).get("amount", 0)
        promo = res.get("promo", {}).get("amount", 0)
        voice = res.get("voice", {}).get("amount", 0)
        data_amt = res.get("data", {}).get("amount", 0)
        total = main + promo
        
        msg = (
            f"📡 <b>NETWORK STATUS: {phone}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>ACCOUNT:</b> <code>{phone}</code>\n"
            f"💰 <b>MAIN:</b> {main:,} MMK\n"
            f"🎁 <b>PROMO:</b> {promo:,} MMK\n"
            f"📞 <b>VOICE:</b> {voice:,} min\n"
            f"🌐 <b>DATA:</b> {data_amt:,} MB\n"
            f"💎 <b>POINTS:</b> {points}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <b>TOTAL BALANCE:</b> <u>{total:,} MMK</u>"
        )
        return msg
    except Exception as e:
        logger.error(f"Formatting error: {e}")
        return f"❌ <b>Parsing Error:</b> {str(e)} for {phone}"

# --- Dynamic Keyboard Logic ---
async def get_dynamic_main_menu(user_id):
    """Generate menu based on account existence."""
    accounts = await get_accounts(user_id)
    keyboard = []
    
    if not accounts:
        keyboard.append([InlineKeyboardButton("➕ အကောင့်ထည့်မည်", callback_data="add_account")])
    else:
        keyboard.append([InlineKeyboardButton("➕ အကောင့်ထည့်မည်", callback_data="add_account")])
        keyboard.append([InlineKeyboardButton("📊 လက်ကျန်ကြည့်မည်", callback_data="select_account_for_balance")])
        keyboard.append([InlineKeyboardButton("👥 အကောင့်များကြည့်မည်", callback_data="manage_accounts")])
        keyboard.append([InlineKeyboardButton("🎮 Claim All Free Turns", callback_data="claim_all_turns")])
        
    return InlineKeyboardMarkup(keyboard)

# --- Handlers ---

async def start(update: Update, context) -> None:
    user = update.effective_user
    await add_user(user.id, user.first_name, user.username)
    keyboard = await get_dynamic_main_menu(user.id)
    await update.message.reply_html(
        format_premium_msg(MESSAGES["start"].format(name=user.mention_html()), "🛡️"),
        reply_markup=keyboard
    )
    await delete_user_state(user.id)

async def main_menu(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    keyboard = await get_dynamic_main_menu(user_id)
    await query.edit_message_text(
        format_premium_msg(MESSAGES["main_menu"], "⚡"),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await delete_user_state(user_id)

async def add_account_prompt(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        format_premium_msg(MESSAGES["login_method_menu"], "🔑"),
        parse_mode=ParseMode.HTML,
        reply_markup=login_method_keyboard()
    )
    await set_user_state(query.from_user.id, "ADD_ACCOUNT_METHOD")

async def login_otp_start(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        format_premium_msg(MESSAGES["enter_phone_number"], "📡"),
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard()
    )
    await set_user_state(query.from_user.id, "WAITING_FOR_PHONE_NUMBER")

async def receive_phone_number(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if user_state and user_state[0] == "WAITING_FOR_PHONE_NUMBER":
        phone_number = update.message.text
        if not re.fullmatch(r"^09\d{7,9}$", phone_number):
            await update.message.reply_html(format_premium_msg(MESSAGES["invalid_phone_number"], "❌"))
            return
        loading_msg = await update.message.reply_html("📡 <i>Processing... Requesting OTP.</i>")
        response = await api.send_otp(phone_number)
        await loading_msg.delete()
        if response["status"] == "success":
            await update.message.reply_html(
                format_premium_msg(MESSAGES["otp_sent"].format(phone_number=phone_number), "📨"),
                reply_markup=cancel_keyboard()
            )
            await set_user_state(user_id, "WAITING_FOR_OTP_CODE", phone_number)
        else:
            await update.message.reply_html(
                format_premium_msg(f"❌ <b>Error:</b> {response['message']}", "⚠️"),
                reply_markup=back_to_main_menu_keyboard()
            )
            await delete_user_state(user_id)

async def receive_otp_code(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if user_state and user_state[0] == "WAITING_FOR_OTP_CODE":
        otp_code = update.message.text
        phone_number = user_state[1]
        loading_msg = await update.message.reply_html("📡 <i>Verifying OTP... Please wait.</i>")
        response = await api.validate_otp(phone_number, otp_code)
        await loading_msg.delete()
        if response["status"] == "success":
            data = response["data"]
            token = data["result"]["access_token"] if "result" in data else data.get("access_token")
            if not token:
                await update.message.reply_html(format_premium_msg("❌ <b>Security Breach:</b> Token not found.", "⚠️"))
                return
            context.user_data["new_account_phone"] = phone_number
            context.user_data["new_account_token"] = token
            await update.message.reply_html(format_premium_msg(MESSAGES["otp_login_success"], "✅"))
            await update.message.reply_html(format_premium_msg(MESSAGES["enter_alias"], "👤"), reply_markup=cancel_keyboard())
            await set_user_state(user_id, "WAITING_FOR_ALIAS")
        else:
            await update.message.reply_html(format_premium_msg(f"❌ <b>Invalid:</b> {response['message']}", "⚠️"), reply_markup=cancel_keyboard())

async def login_token_start(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        format_premium_msg(MESSAGES["enter_token"], "🔑"),
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard()
    )
    await set_user_state(query.from_user.id, "WAITING_FOR_TOKEN")

async def receive_token(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if user_state and user_state[0] == "WAITING_FOR_TOKEN":
        token = update.message.text
        loading_msg = await update.message.reply_html("📡 <i>Validating Token...</i>")
        response = await api.get_balance(token, "09688888888")
        await loading_msg.delete()
        if response["status"] == "success":
            phone_number = response["data"]["result"][0]["msisdn"]
            context.user_data["new_account_phone"] = phone_number
            context.user_data["new_account_token"] = token
            await update.message.reply_html(format_premium_msg(MESSAGES["token_login_success"], "✅"))
            await update.message.reply_html(format_premium_msg(MESSAGES["enter_alias"], "👤"), reply_markup=cancel_keyboard())
            await set_user_state(user_id, "WAITING_FOR_ALIAS")
        else:
            await update.message.reply_html(format_premium_msg(f"❌ <b>Access Denied:</b> {response['message']}", "⚠️"), reply_markup=cancel_keyboard())

async def receive_alias(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if user_state and user_state[0] == "WAITING_FOR_ALIAS":
        alias = update.message.text
        if alias == "/skip":
            alias = None
            await update.message.reply_html(format_premium_msg(MESSAGES["skip_alias"], "👤"))
        else:
            await update.message.reply_html(format_premium_msg(MESSAGES["alias_set_success"], "✅"))
        phone_number = context.user_data.get("new_account_phone")
        token = context.user_data.get("new_account_token")
        if phone_number and token:
            try:
                await add_account(user_id, phone_number, token, alias)
                keyboard = await get_dynamic_main_menu(user_id)
                await update.message.reply_html(format_premium_msg(MESSAGES["account_added_success"], "🛡️"), reply_markup=keyboard)
            except:
                keyboard = await get_dynamic_main_menu(user_id)
                await update.message.reply_html(format_premium_msg(MESSAGES["account_already_exists"], "⚠️"), reply_markup=keyboard)
            finally:
                await delete_user_state(user_id)
        else:
            keyboard = await get_dynamic_main_menu(user_id)
            await update.message.reply_html(format_premium_msg(MESSAGES["something_went_wrong"], "❌"), reply_markup=keyboard)
            await delete_user_state(user_id)

# --- Interactive Balance Check ---

async def select_account_for_balance(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    accounts = await get_accounts(user_id)
    if not accounts:
        keyboard = await get_dynamic_main_menu(user_id)
        await query.edit_message_text(format_premium_msg(MESSAGES["no_accounts"], "⚠️"), parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return
    keyboard = []
    for acc_id, phone, alias, _ in accounts:
        display_name = f"👤 {alias if alias else phone}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"view_balance_id_{acc_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")])
    await query.edit_message_text(
        format_premium_msg("📊 <b>လက်ကျန်စစ်ဆေးရန် အကောင့်ရွေးချယ်ပါ:</b>", "📡"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def view_single_balance(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account:
        await query.edit_message_text(format_premium_msg("❌ Account not found.", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=back_to_main_menu_keyboard())
        return
    _, phone, alias, token = account
    await query.edit_message_text(f"📡 <i>Scanning Network for {phone}...</i>", parse_mode=ParseMode.HTML)
    response = await api.get_balance(token, phone)
    if response["status"] == "success":
        points = response.get("points", "0")
        msg = format_balance_pro(alias if alias else phone, response["data"], points)
        keyboard = [[InlineKeyboardButton("⬅️ Back to List", callback_data="select_account_for_balance")]]
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    elif response["message"] == "Unauthorized/Expired":
        await delete_account(account_id, user_id)
        keyboard = [[InlineKeyboardButton("⬅️ Back to List", callback_data="select_account_for_balance")]]
        await query.edit_message_text(format_premium_msg(f"❌ <b>{phone}:</b> Token Expired (Auto-Removed)", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [[InlineKeyboardButton("⬅️ Back to List", callback_data="select_account_for_balance")]]
        await query.edit_message_text(format_premium_msg(f"❌ <b>Error:</b> {response['message']}", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Game Claim & Manage Accounts ---

async def manage_accounts_list(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    accounts = await get_accounts(user_id)
    if not accounts:
        keyboard = await get_dynamic_main_menu(user_id)
        await query.edit_message_text(format_premium_msg(MESSAGES["no_accounts"], "⚠️"), parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return
    await query.edit_message_text(
        format_premium_msg(MESSAGES["your_accounts"], "👥"),
        parse_mode=ParseMode.HTML,
        reply_markup=account_list_keyboard(accounts)
    )

async def claim_all_turns(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    accounts = await get_accounts(user_id)
    if not accounts:
        await query.edit_message_text(format_premium_msg("❌ No accounts found.", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=back_to_main_menu_keyboard())
        return
    await query.edit_message_text("🎮 <i>Scanning Game Engine for Free Turns...</i>", parse_mode=ParseMode.HTML)
    success_count = 0
    fail_count = 0
    for _, phone, _, token in accounts:
        res = await api.claim_game_turns(token)
        if res["status"] == "success":
            success_count += 1
        else:
            fail_count += 1
        await asyncio.sleep(0.5)
    summary = (
        f"🎮 <b>GAME ENGINE SUMMARY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>SUCCESS:</b> {success_count} accounts\n"
        f"❌ <b>FAILED:</b> {fail_count} accounts\n"
        f"📊 <b>TOTAL:</b> {len(accounts)} accounts\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <i>Daily free turns triggered.</i>"
    )
    keyboard = await get_dynamic_main_menu(user_id)
    await query.edit_message_text(summary, parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def select_account_to_manage(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account:
        await query.edit_message_text(format_premium_msg("❌ Account not found.", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=back_to_main_menu_keyboard())
        return
    _, phone, alias, _ = account
    display_name = alias if alias else phone
    await query.edit_message_text(
        format_premium_msg(f"<b>ACCOUNT:</b> {display_name}", "🛡️"),
        parse_mode=ParseMode.HTML,
        reply_markup=account_management_keyboard(account_id)
    )

async def check_balance_single_from_manage(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, token = account
    await query.edit_message_text("📡 <i>Scanning Network Data...</i>", parse_mode=ParseMode.HTML)
    response = await api.get_balance(token, phone)
    if response["status"] == "success":
        points = response.get("points", "0")
        await query.edit_message_text(format_balance_pro(alias if alias else phone, response["data"], points), parse_mode=ParseMode.HTML, reply_markup=account_management_keyboard(account_id))
    else:
        await query.edit_message_text(format_premium_msg(f"❌ {response['message']}", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=account_management_keyboard(account_id))

async def view_token(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, token = account
    token_msg = (
        f"🛡️ <b>SECURITY ACCESS GRANTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 <b>TOKEN:</b> <code>{token}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Auto-hiding in 5 seconds...</i>"
    )
    await query.edit_message_text(token_msg, parse_mode=ParseMode.HTML)
    await asyncio.sleep(5)
    display_name = alias if alias else phone
    try:
        await query.edit_message_text(
            format_premium_msg(f"<b>ACCOUNT:</b> {display_name}\n(Token hidden)", "🛡️"),
            parse_mode=ParseMode.HTML,
            reply_markup=account_management_keyboard(account_id)
        )
    except: pass

async def delete_account_confirm(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split('_')[-1])
    await delete_account(account_id, user_id)
    keyboard = await get_dynamic_main_menu(user_id)
    await query.edit_message_text(format_premium_msg(MESSAGES["account_deleted_success"], "🗑️"), parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def cancel_operation(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    keyboard = await get_dynamic_main_menu(user_id)
    await query.edit_message_text(format_premium_msg(MESSAGES["operation_cancelled"], "❌"), parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await delete_user_state(user_id)

async def unknown_message(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if not user_state:
        keyboard = await get_dynamic_main_menu(user_id)
        await update.message.reply_html(format_premium_msg(MESSAGES["main_menu"], "⚡"), reply_markup=keyboard)
        return
    state = user_state[0]
    if state == "WAITING_FOR_PHONE_NUMBER": await receive_phone_number(update, context)
    elif state == "WAITING_FOR_OTP_CODE": await receive_otp_code(update, context)
    elif state == "WAITING_FOR_TOKEN": await receive_token(update, context)
    elif state == "WAITING_FOR_ALIAS": await receive_alias(update, context)
    else:
        keyboard = await get_dynamic_main_menu(user_id)
        await update.message.reply_html(format_premium_msg(MESSAGES["main_menu"], "⚡"), reply_markup=keyboard)

def main() -> None:
    threading.Thread(target=run_flask, daemon=True).start()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(add_account_prompt, pattern="^add_account$"))
    application.add_handler(CallbackQueryHandler(login_otp_start, pattern="^login_otp$"))
    application.add_handler(CallbackQueryHandler(login_token_start, pattern="^login_token$"))
    application.add_handler(CallbackQueryHandler(select_account_for_balance, pattern="^select_account_for_balance$"))
    application.add_handler(CallbackQueryHandler(view_single_balance, pattern="^view_balance_id_\\d+$"))
    application.add_handler(CallbackQueryHandler(manage_accounts_list, pattern="^manage_accounts$"))
    application.add_handler(CallbackQueryHandler(claim_all_turns, pattern="^claim_all_turns$"))
    application.add_handler(CallbackQueryHandler(select_account_to_manage, pattern="^select_account_\\d+$"))
    application.add_handler(CallbackQueryHandler(check_balance_single_from_manage, pattern="^check_balance_single_\\d+$"))
    application.add_handler(CallbackQueryHandler(view_token, pattern="^view_token_\\d+$"))
    application.add_handler(CallbackQueryHandler(delete_account_confirm, pattern="^delete_account_\\d+$"))
    application.add_handler(CallbackQueryHandler(cancel_operation, pattern="^cancel$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
