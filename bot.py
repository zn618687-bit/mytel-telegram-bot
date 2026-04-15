import logging
import re
import os
import asyncio
import threading
import json
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

from config import BOT_TOKEN
from database import init_db, add_user, add_account, get_accounts, delete_account, set_user_state, get_user_state, delete_user_state, get_account_by_id
from mytel_api import MytelProAPI
from keyboards import login_method_keyboard, back_to_main_menu_keyboard, account_list_keyboard, account_management_keyboard, cancel_keyboard
from messages import MESSAGES

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize MytelProAPI
api = MytelProAPI()

# --- VIP Premium Style Message Formatter ---
def format_vip_msg(text, icon="🛡️"):
    return f"<b>{icon} VIP SYSTEM:</b>\n\n{text}"

def format_balance_vip(phone, api_data, points="0"):
    """Premium balance formatting for VIP users."""
    try:
        result_list = api_data.get("result", [])
        if not result_list: return f"❌ <b>Error:</b> No balance data found for {phone}"
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
            f"💎 <b>POINTS:</b> {points}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <b>TOTAL:</b> <u>{total:,} MMK</u>"
        )
        return msg
    except Exception as e:
        logger.error(f"Error formatting balance for {phone}: {e}")
        return f"❌ <b>Parsing Error:</b> {str(e)}"

# --- Dynamic Keyboard Logic ---
async def get_vip_main_menu_keyboard(user_id):
    """Generate dynamic main menu based on user's accounts."""
    accounts = await get_accounts(user_id)
    keyboard = [
        [InlineKeyboardButton("➕ အကောင့်ထည့်မည်", callback_data="add_account")]
    ]
    if accounts:
        keyboard.append([InlineKeyboardButton("📊 လက်ကျန်ကြည့်မည်", callback_data="interactive_balance_check")])
        keyboard.append([InlineKeyboardButton("👥 အကောင့်များကြည့်မည်", callback_data="manage_accounts")])
        keyboard.append([InlineKeyboardButton("⚡ Claim All Rewards", callback_data="claim_all_rewards")])
    return InlineKeyboardMarkup(keyboard)

# --- Handlers ---

async def start(update: Update, context) -> None:
    user = update.effective_user
    await add_user(user.id, user.first_name, user.username)
    keyboard = await get_vip_main_menu_keyboard(user.id)
    await update.message.reply_html(
        format_vip_msg(f"မင်္ဂလာပါ {user.mention_html()}! 👋\n\n<b>Mytel VIP Multi-Account Bot</b> မှ ကြိုဆိုပါတယ်။\n\nအောက်ပါ လုပ်ဆောင်ချက်များကို ရွေးချယ်နိုင်ပါပြီ။", "⚡"),
        reply_markup=keyboard
    )
    await delete_user_state(user.id)

async def main_menu(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    keyboard = await get_vip_main_menu_keyboard(user_id)
    await query.edit_message_text(
        format_vip_msg("<b>VIP MAIN MENU</b>\n\nအောက်ပါ လုပ်ဆောင်ချက်များကို ရွေးချယ်နိုင်ပါပြီ။", "⚡"),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await delete_user_state(user_id)

async def add_account_prompt(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        format_vip_msg("<b>🛡️ LOGIN METHOD</b>\n\nဘယ်လိုနည်းလမ်းနဲ့ Login ဝင်မလဲ ရွေးချယ်ပေးပါခင်ဗျာ။", "🔑"),
        parse_mode=ParseMode.HTML,
        reply_markup=login_method_keyboard()
    )
    await set_user_state(query.from_user.id, "ADD_ACCOUNT_METHOD")

async def login_otp_start(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        format_vip_msg("<b>📡 OTP LOGIN</b>\n\nဖုန်းနံပါတ် (ဥပမာ- 0969...) ကို ရိုက်ထည့်ပေးပါခင်ဗျာ။", "📱"),
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
            await update.message.reply_html(format_vip_msg("❌ <b>ဖုန်းနံပါတ် မှားယွင်းနေပါသည်။</b>\n\nကျေးဇူးပြု၍ 09... ဖြင့် ပြန်လည်ရိုက်ထည့်ပေးပါခင်ဗျာ။", "⚠️"))
            return
        loading_msg = await update.message.reply_html("📡 <i>Processing... Requesting Secure OTP.</i>")
        response = await api.send_otp(phone_number)
        await loading_msg.delete()
        if response["status"] == "success":
            await update.message.reply_html(
                format_vip_msg(f"📨 <b>OTP ပို့လိုက်ပါပြီ!</b>\n\nဖုန်းနံပါတ် <code>{phone_number}</code> ဆီသို့ ပို့လိုက်သော OTP ကုဒ်ကို ကျွန်တော့်ဆီ ပေးပို့ပေးပါခင်ဗျာ။", "📩"),
                reply_markup=cancel_keyboard()
            )
            await set_user_state(user_id, "WAITING_FOR_OTP_CODE", phone_number)
        else:
            await update.message.reply_html(format_vip_msg(f"❌ <b>Error:</b> {response['message']}", "⚠️"), reply_markup=back_to_main_menu_keyboard())
            await delete_user_state(user_id)

async def receive_otp_code(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if user_state and user_state[0] == "WAITING_FOR_OTP_CODE":
        otp_code = update.message.text
        phone_number = user_state[1]
        loading_msg = await update.message.reply_html("📡 <i>Verifying OTP... Accessing VIP Server.</i>")
        response = await api.validate_otp(phone_number, otp_code)
        await loading_msg.delete()
        if response["status"] == "success":
            data = response["data"]
            token = data["result"]["access_token"] if "result" in data and "access_token" in data["result"] else data.get("access_token")
            if not token:
                await update.message.reply_html(format_vip_msg("❌ <b>Security Breach:</b> Token not found.", "⚠️"))
                return
            context.user_data["new_account_phone"] = phone_number
            context.user_data["new_account_token"] = token
            await update.message.reply_html(format_vip_msg("✅ <b>OTP Login အောင်မြင်ပါသည်!</b>", "🛡️"))
            await update.message.reply_html(format_vip_msg("👤 <b>အကောင့်အမည်ပေးပါ</b>\n\n(ဥပမာ- My VIP Acc) စသဖြင့် အထာကျကျ တစ်ခုခု ပေးပါခင်ဗျာ။", "✍️"), reply_markup=cancel_keyboard())
            await set_user_state(user_id, "WAITING_FOR_ALIAS")
        else:
            await update.message.reply_html(format_vip_msg(f"❌ <b>OTP မှားယွင်းနေပါသည်။</b>\n\nကျေးဇူးပြု၍ ပြန်လည်စစ်ဆေးပေးပါခင်ဗျာ။\n\n(Error: {response['message']})", "⚠️"), reply_markup=cancel_keyboard())

async def login_token_start(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        format_vip_msg("<b>🔑 TOKEN LOGIN</b>\n\nသင်၏ Access Token ကို ပေးပို့ပေးပါခင်ဗျာ။", "🛰️"),
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
        response = await api.get_game_profile(token) # Using game profile for token validation
        await loading_msg.delete()
        if response["status"] == "success":
            phone_number = response["data"]["result"]["msisdn"]
            context.user_data["new_account_phone"] = phone_number
            context.user_data["new_account_token"] = token
            await update.message.reply_html(format_vip_msg("✅ <b>Token Login အောင်မြင်ပါသည်!</b>", "🛡️"))
            await update.message.reply_html(format_vip_msg("👤 <b>အကောင့်အမည်ပေးပါ</b>\n\n(ဥပမာ- My Work Phone) စသဖြင့် အထာကျကျ တစ်ခုခု ပေးပါခင်ဗျာ။", "✍️"), reply_markup=cancel_keyboard())
            await set_user_state(user_id, "WAITING_FOR_ALIAS")
        else:
            await update.message.reply_html(format_vip_msg(f"❌ <b>Access Denied:</b> Token မမှန်ကန်ပါ သို့မဟုတ် သက်တမ်းကုန်နေပါသည်။\n\n(Error: {response['message']})", "⚠️"), reply_markup=cancel_keyboard())

async def receive_alias(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if user_state and user_state[0] == "WAITING_FOR_ALIAS":
        alias = update.message.text
        phone_number = context.user_data.get("new_account_phone")
        token = context.user_data.get("new_account_token")
        if phone_number and token:
            try:
                await add_account(user_id, phone_number, token, alias)
                keyboard = await get_vip_main_menu_keyboard(user_id)
                await update.message.reply_html(format_vip_msg(f"🛡️ <b>VIP ACCOUNT SECURED!</b>\n\nအကောင့် <b>{alias}</b> ကို စနစ်တကျ ထည့်သွင်းပြီးပါပြီ။", "✅"), reply_markup=keyboard)
            except Exception as e:
                keyboard = await get_vip_main_menu_keyboard(user_id)
                await update.message.reply_html(format_vip_msg("⚠️ <b>အကောင့်ရှိပြီးသားဖြစ်နေပါသည်။</b>", "⚠️"), reply_markup=keyboard)
            finally:
                await delete_user_state(user_id)
        else:
            keyboard = await get_vip_main_menu_keyboard(user_id)
            await update.message.reply_html(format_vip_msg("❌ <b>တစ်ခုခု မှားယွင်းသွားပါသည်။</b>", "⚠️"), reply_markup=keyboard)
            await delete_user_state(user_id)

# --- Interactive Balance Check ---
async def interactive_balance_check(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    accounts = await get_accounts(user_id)
    if not accounts:
        keyboard = await get_vip_main_menu_keyboard(user_id)
        await query.edit_message_text(format_vip_msg("❌ <b>အကောင့်မရှိသေးပါ။</b>", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return
    keyboard_buttons = []
    for acc_id, phone, alias, _ in accounts:
        keyboard_buttons.append([InlineKeyboardButton(f"👤 {alias if alias else phone}", callback_data=f"check_single_balance_{acc_id}")])
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")])
    await query.edit_message_text(format_vip_msg("📊 <b>လက်ကျန်ကြည့်ရန်</b>\n\nကြည့်လိုသော အကောင့်ကို ရွေးချယ်ပါခင်ဗျာ။", "💎"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_buttons))

async def check_single_balance(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split("_")[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, token = account
    loading_msg = await query.edit_message_text("📡 <i>Scanning Network Data...</i>", parse_mode=ParseMode.HTML)
    response = await api.get_balance(token, phone)
    if response["status"] == "success":
        msg = format_balance_vip(alias if alias else phone, response["data"], response.get("points", "0"))
        keyboard = [[InlineKeyboardButton("⬅️ Back to Account List", callback_data="interactive_balance_check")]]
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [[InlineKeyboardButton("⬅️ Back to Account List", callback_data="interactive_balance_check")]]
        await query.edit_message_text(format_vip_msg(f"❌ <b>Error:</b> {response['message']}", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Manage Accounts & Game Profile ---

async def manage_accounts_list(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    accounts = await get_accounts(user_id)
    if not accounts:
        keyboard = await get_vip_main_menu_keyboard(user_id)
        await query.edit_message_text(format_vip_msg("❌ <b>အကောင့်မရှိသေးပါ။</b>", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return
    keyboard_buttons = []
    for acc_id, phone, alias, _ in accounts:
        keyboard_buttons.append([InlineKeyboardButton(f"👤 {alias if alias else phone}", callback_data=f"select_account_{acc_id}")])
    keyboard_buttons.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")])
    await query.edit_message_text(format_vip_msg("👥 <b>သင်၏ VIP အကောင့်များ</b>\n\nစီမံလိုသော အကောင့်ကို ရွေးချယ်ပါခင်ဗျာ။", "🛡️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_buttons))

async def select_account_to_manage(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split("_")[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, _ = account
    keyboard = [
        [InlineKeyboardButton("📊 လက်ကျန်ကြည့်မည်", callback_data=f"vip_balance_{account_id}")],
        [InlineKeyboardButton("🎮 Game Profile", callback_data=f"game_profile_{account_id}")],
        [InlineKeyboardButton("🔑 Token ကြည့်မည်", callback_data=f"vip_token_{account_id}")],
        [InlineKeyboardButton("🗑️ အကောင့်ဖျက်မည်", callback_data=f"delete_account_{account_id}")],
        [InlineKeyboardButton("⬅️ Back to Account List", callback_data="manage_accounts")]
    ]
    await query.edit_message_text(format_vip_msg(f"🛡️ <b>MANAGE ACCOUNT:</b> {alias if alias else phone}", "⚙️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_balance_from_manage(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split("_")[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, token = account
    await query.edit_message_text("📡 <i>Scanning Network Data...</i>", parse_mode=ParseMode.HTML)
    response = await api.get_balance(token, phone)
    if response["status"] == "success":
        msg = format_balance_vip(alias if alias else phone, response["data"], response.get("points", "0"))
        keyboard = [[InlineKeyboardButton("⬅️ Back to Account Management", callback_data=f"select_account_{account_id}")]]
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [[InlineKeyboardButton("⬅️ Back to Account Management", callback_data=f"select_account_{account_id}")]]
        await query.edit_message_text(format_vip_msg(f"❌ <b>Error:</b> {response['message']}", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def view_game_profile(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split("_")[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, token = account
    await query.edit_message_text("📡 <i>Fetching Game Profile...</i>", parse_mode=ParseMode.HTML)
    response = await api.get_game_profile(token)
    if response["status"] == "success":
        res = response["data"]["result"]
        wallet = res.get("wallet", {})
        stats = res.get("player_stats", {})
        msg = (
            f"🎮 <b>GAME ENGINE PROFILE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Player:</b> {res.get('display_name', 'Unknown')}\n"
            f"🎫 <b>Free Turns:</b> {wallet.get('TURN_FREE', {}).get('balance', 0)}\n"
            f"🔨 <b>Hammers:</b> {wallet.get('HAMMER', {}).get('balance', 0)}\n"
            f"🍹 <b>Mix Items:</b> {wallet.get('MIX', {}).get('balance', 0)}\n"
            f"🏆 <b>Total Jackfruits:</b> {stats.get('total_jackfruits', 0)}\n"
            f"📊 <b>Current Session:</b> {stats.get('total_sessions', 0)}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        keyboard = [
            [InlineKeyboardButton("🎁 Claim Daily Reward", callback_data=f"claim_single_reward_{account_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"select_account_{account_id}")]
        ]
        avatar_url = res.get("avatar_url")
        if avatar_url:
            await query.message.reply_photo(photo=avatar_url, caption=msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            await query.delete_message()
        else:
            await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"select_account_{account_id}")]]
        await query.edit_message_text(format_vip_msg(f"❌ <b>Error:</b> {response['message']}", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def claim_single_reward(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split("_")[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, token = account
    
    # Pre-check logic
    profile = await api.get_game_profile(token)
    if profile["status"] == "success":
        res = profile["data"]["result"]
        wallet = res.get("wallet", {})
        last_granted = wallet.get("TURN_FREE", {}).get("last_granted", "")
        today = datetime.now().strftime("%Y-%m-%d")
        notifications = res.get("notifications", [])
        has_daily = any(n.get("type") == "DAILY_REWARD" for n in notifications)
        
        if last_granted.startswith(today) or not has_daily:
            await query.edit_message_text(format_vip_msg(f"⚠️ <b>ဒီအကောင့်က ဒီနေ့အတွက် ယူပြီးသားဖြစ်နေပါတယ်!</b>", "🎮"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"game_profile_{account_id}")]]))
            return

    await query.edit_message_text("📡 <i>Claiming Daily Reward...</i>", parse_mode=ParseMode.HTML)
    response = await api.claim_daily_reward(token)
    if response["status"] == "success":
        await query.edit_message_text(format_vip_msg("✅ <b>Daily Reward Claim အောင်မြင်ပါသည်!</b>", "🎁"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"game_profile_{account_id}")]]))
    else:
        await query.edit_message_text(format_vip_msg(f"❌ <b>Error:</b> {response['message']}", "⚠️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"game_profile_{account_id}")]]))

async def claim_all_rewards(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    accounts = await get_accounts(user_id)
    if not accounts: return
    
    await query.edit_message_text("📡 <i>Processing Bulk Claim... Please wait.</i>", parse_mode=ParseMode.HTML)
    success, already, failed = 0, 0, 0
    today = datetime.now().strftime("%Y-%m-%d")
    
    for _, phone, _, token in accounts:
        profile = await api.get_game_profile(token)
        if profile["status"] == "success":
            res = profile["data"]["result"]
            wallet = res.get("wallet", {})
            last_granted = wallet.get("TURN_FREE", {}).get("last_granted", "")
            notifications = res.get("notifications", [])
            has_daily = any(n.get("type") == "DAILY_REWARD" for n in notifications)
            
            if last_granted.startswith(today) or not has_daily:
                already += 1
                continue
            
            claim = await api.claim_daily_reward(token)
            if claim["status"] == "success": success += 1
            else: failed += 1
        else: failed += 1
    
    msg = (
        f"🎮 <b>GAME ENGINE UPDATE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>Successfully Claimed:</b> {success}\n"
        f"🕒 <b>Already Claimed Today:</b> {already}\n"
        f"❌ <b>Expired/Failed:</b> {failed}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=back_to_main_menu_keyboard())

async def view_token_vip(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split("_")[-1])
    account = await get_account_by_id(account_id, user_id)
    if not account: return
    _, phone, alias, token = account
    await query.edit_message_text(f"🛡️ <b>SECURITY ACCESS GRANTED</b>\n\n🔑 <b>TOKEN:</b> <code>{token}</code>\n\n⚠️ <i>Auto-hiding in 5 seconds...</i>", parse_mode=ParseMode.HTML)
    await asyncio.sleep(5)
    try:
        keyboard = [[InlineKeyboardButton("📊 လက်ကျန်ကြည့်မည်", callback_data=f"vip_balance_{account_id}")], [InlineKeyboardButton("🎮 Game Profile", callback_data=f"game_profile_{account_id}")], [InlineKeyboardButton("🔑 Token ကြည့်မည်", callback_data=f"vip_token_{account_id}")], [InlineKeyboardButton("🗑️ အကောင့်ဖျက်မည်", callback_data=f"delete_account_{account_id}")], [InlineKeyboardButton("⬅️ Back to Account List", callback_data="manage_accounts")]]
        await query.edit_message_text(format_vip_msg(f"🛡️ <b>MANAGE ACCOUNT:</b> {alias if alias else phone}\n(Token hidden)", "⚙️"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    except: pass

async def delete_account_confirm(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    account_id = int(query.data.split("_")[-1])
    await delete_account(account_id, user_id)
    keyboard = await get_vip_main_menu_keyboard(user_id)
    await query.edit_message_text(format_vip_msg("🗑️ <b>အကောင့်ကို စနစ်တကျ ဖျက်ပြီးပါပြီ။</b>", "✅"), parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def cancel_operation(update: Update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    keyboard = await get_vip_main_menu_keyboard(user_id)
    await query.edit_message_text(format_vip_msg("❌ <b>လုပ်ဆောင်ချက်ကို ပယ်ဖျက်လိုက်ပါပြီ။</b>", "⚡"), parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await delete_user_state(user_id)

async def unknown_message(update: Update, context) -> None:
    user_id = update.effective_user.id
    user_state = await get_user_state(user_id)
    if not user_state:
        keyboard = await get_vip_main_menu_keyboard(user_id)
        await update.message.reply_html(format_vip_msg("<b>VIP MAIN MENU</b>", "⚡"), reply_markup=keyboard)
        return
    state = user_state[0]
    if state == "WAITING_FOR_PHONE_NUMBER": await receive_phone_number(update, context)
    elif state == "WAITING_FOR_OTP_CODE": await receive_otp_code(update, context)
    elif state == "WAITING_FOR_TOKEN": await receive_token(update, context)
    elif state == "WAITING_FOR_ALIAS": await receive_alias(update, context)
    else:
        keyboard = await get_vip_main_menu_keyboard(user_id)
        await update.message.reply_html(format_vip_msg("<b>VIP MAIN MENU</b>", "⚡"), reply_markup=keyboard)

def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(add_account_prompt, pattern="^add_account$"))
    application.add_handler(CallbackQueryHandler(login_otp_start, pattern="^login_otp$"))
    application.add_handler(CallbackQueryHandler(login_token_start, pattern="^login_token$"))
    application.add_handler(CallbackQueryHandler(manage_accounts_list, pattern="^manage_accounts$"))
    application.add_handler(CallbackQueryHandler(select_account_to_manage, pattern="^select_account_\\d+$"))
    application.add_handler(CallbackQueryHandler(check_balance_from_manage, pattern="^vip_balance_\\d+$"))
    application.add_handler(CallbackQueryHandler(interactive_balance_check, pattern="^interactive_balance_check$"))
    application.add_handler(CallbackQueryHandler(check_single_balance, pattern="^check_single_balance_\\d+$"))
    application.add_handler(CallbackQueryHandler(view_game_profile, pattern="^game_profile_\\d+$"))
    application.add_handler(CallbackQueryHandler(claim_single_reward, pattern="^claim_single_reward_\\d+$"))
    application.add_handler(CallbackQueryHandler(claim_all_rewards, pattern="^claim_all_rewards$"))
    application.add_handler(CallbackQueryHandler(view_token_vip, pattern="^vip_token_\\d+$"))
    application.add_handler(CallbackQueryHandler(delete_account_confirm, pattern="^delete_account_\\d+$"))
    application.add_handler(CallbackQueryHandler(cancel_operation, pattern="^cancel$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
