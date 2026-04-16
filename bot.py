import asyncio
import logging
import re
from datetime import datetime

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, Update)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from mytel_api import MytelProAPI
from database import (
    init_db, add_account, get_accounts, delete_account, get_account_by_phone, get_account_by_user_id_and_phone
)

# Configuration (assuming these are in config.py or environment variables)
# BOT_TOKEN = "YOUR_BOT_TOKEN"
# ADMIN_ID = YOUR_ADMIN_ID # Optional, for admin features

# For now, using placeholder BOT_TOKEN if not defined
import os
BOT_TOKEN = os.getenv("BOT_TOKEN", "8425866664:AAELO6CYz0Feb-ZEELceCGpkd-s0dHQUr2M")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Mytel API
api = MytelProAPI()

# --- Keyboard Markups (VIP/Cyberpunk Style) ---

def get_start_keyboard(has_accounts: bool):
    keyboard = []
    if not has_accounts:
        keyboard.append([InlineKeyboardButton("➕ အကောင့်ထည့်မည်", callback_data="add_account")])
    else:
        keyboard.append([InlineKeyboardButton("➕ အကောင့်ထည့်မည်", callback_data="add_account")])
        keyboard.append([InlineKeyboardButton("📊 လက်ကျန်ကြည့်မည်", callback_data="check_balance_menu")])
        keyboard.append([InlineKeyboardButton("👥 အကောင့်များကြည့်မည်", callback_data="view_accounts")])
        keyboard.append([InlineKeyboardButton("⚡ Claim All Rewards", callback_data="claim_all_rewards")])
    return InlineKeyboardMarkup(keyboard)

def get_login_options_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔑 Token ဖြင့် ဝင်မည်", callback_data="login_token")],
        [InlineKeyboardButton("⚡ OTP ဖြင့် ဝင်မည်", callback_data="login_otp")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_account_manage_keyboard(phone_number):
    keyboard = [
        [InlineKeyboardButton("📊 လက်ကျန်ကြည့်မည်", callback_data=f"balance_{phone_number}")],
        [InlineKeyboardButton("🎮 Game Profile", callback_data=f"game_profile_{phone_number}")],
        [InlineKeyboardButton("🔑 Token ကြည့်မည်", callback_data=f"token_{phone_number}")],
        [InlineKeyboardButton("🗑️ ဖျက်မည်", callback_data=f"delete_{phone_number}")],
        [InlineKeyboardButton("⬅️ နောက်သို့", callback_data="view_accounts")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_balance_list_keyboard():
    keyboard = [
        [InlineKeyboardButton("⬅️ နောက်သို့", callback_data="check_balance_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_claim_reward_keyboard(phone_number):
    keyboard = [
        [InlineKeyboardButton("🎁 Claim Daily Reward", callback_data=f"claim_reward_{phone_number}")],
        [InlineKeyboardButton("⬅️ နောက်သို့", callback_data=f"game_profile_{phone_number}")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- State Management (Simple Dictionary for now) ---
user_states = {}

# --- Helper Functions ---
async def send_loading_message(update: Update, context, text="📡 <i>Processing... Please wait.</i>"):
    return await update.effective_message.reply_html(text)

async def delete_loading_message(message):
    if message:
        try:
            await message.delete()
        except Exception as e:
            logger.warning(f"Could not delete loading message: {e}")

async def get_user_accounts(user_id):
    return await get_accounts(user_id)

# --- Command Handlers ---
async def start(update: Update, context):
    user_id = update.effective_user.id
    accounts = await get_user_accounts(user_id)
    has_accounts = bool(accounts)

    if not has_accounts:
        message = "⚡ <b>Mytel Multi-Account Bot</b> ⚡\n\n🛡️ သင်၏ Mytel အကောင့်များကို စီမံရန် အသင့်တော်ဆုံး Bot ဖြစ်ပါသည်။\n\n<i>စတင်ရန် Login ဝင်ပါ</i>"
        keyboard = [[InlineKeyboardButton("🛡️ Login ဝင်ပါ", callback_data="login_start")]]
    else:
        message = "⚡ <b>Mytel Multi-Account Bot</b> ⚡\n\n<i>သင်၏ အကောင့်များကို စီမံရန် အောက်ပါခလုတ်များကို အသုံးပြုပါ။</i>"
        keyboard = get_start_keyboard(has_accounts).inline_keyboard

    await update.effective_message.reply_html(message, reply_markup=InlineKeyboardMarkup(keyboard))

async def login_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    message = "🔑 <b>Login Method ရွေးချယ်ပါ</b>\n\n<i>မည်သည့်နည်းလမ်းဖြင့် Login ဝင်လိုပါသနည်း။</i>"
    await query.edit_message_text(message, reply_markup=get_login_options_keyboard(), parse_mode=\
