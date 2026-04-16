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
    await query.edit_message_text(message, reply_markup=get_login_options_keyboard(), parse_mode=\"HTML\")

async def login_otp(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_states[user_id] = {"state": "waiting_phone_otp"}
    await query.edit_message_text(
        "⚡ <b>OTP ဖြင့် Login ဝင်မည်</b> ⚡\n\n<i>သင်၏ Mytel ဖုန်းနံပါတ်ကို ထည့်သွင်းပါ။ (ဥပမာ: 09xxxxxxxxx)</i>",
        parse_mode="HTML"
    )

async def login_token(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_states[user_id] = {"state": "waiting_token"}
    await query.edit_message_text(
        "🔑 <b>Token ဖြင့် Login ဝင်မည်</b> 🔑\n\n<i>သင်၏ Mytel Access Token ကို ထည့်သွင်းပါ။</i>",
        parse_mode="HTML"
    )

async def handle_message(update: Update, context):
    user_id = update.effective_user.id
    text = update.effective_message.text
    state_info = user_states.get(user_id, {})
    current_state = state_info.get("state")

    if current_state == "waiting_phone_otp":
        phone_number = text.strip()
        if not re.fullmatch(r"09\[0-9]{9}", phone_number):
            await update.effective_message.reply_html(
                "⚠️ <b>ဖုန်းနံပါတ် မမှန်ကန်ပါ</b>။\n\n<i>09xxxxxxxxx ပုံစံဖြင့် ပြန်လည်ထည့်သွင်းပါ။</i>"
            )
            return
        user_states[user_id]["phone_number"] = phone_number
        user_states[user_id]["state"] = "waiting_otp_code"
        loading_msg = await send_loading_message(update, context, "📡 <i>OTP တောင်းဆိုနေပါသည်... ခဏစောင့်ပါ။</i>")
        res = await api.get_otp(phone_number)
        await delete_loading_message(loading_msg)

        if res["status"] == "success":
            await update.effective_message.reply_html(
                f"✅ <b>OTP ပို့ပြီးပါပြီ။</b>\n\n<i>{phone_number} သို့ ရောက်လာသော OTP Code ကို ထည့်သွင်းပါ။</i>"
            )
        else:
            await update.effective_message.reply_html(
                f"❌ <b>OTP တောင်းဆို၍ မရပါ</b>\n\n<i>{res['message']}</i>"
            )
            del user_states[user_id]

    elif current_state == "waiting_otp_code":
        otp_code = text.strip()
        phone_number = state_info.get("phone_number")
        if not phone_number:
            await update.effective_message.reply_html("⚠️ <b>အမှားအယွင်းတစ်ခုခု ဖြစ်သွားပါပြီ။</b>\n\n<i>ပြန်လည်စတင်ရန် /start ကို နှိပ်ပါ။</i>")
            del user_states[user_id]
            return

        loading_msg = await send_loading_message(update, context, "📡 <i>OTP စစ်ဆေးနေပါသည်... ခဏစောင့်ပါ။</i>")
        res = await api.verify_otp(phone_number, otp_code)
        await delete_loading_message(loading_msg)

        if res["status"] == "success":
            access_token = res["data"]["result"]["accessToken"]
            user_states[user_id]["access_token"] = access_token
            user_states[user_id]["state"] = "waiting_account_name"
            await update.effective_message.reply_html(
                "✅ <b>Login အောင်မြင်ပါပြီ။</b>\n\n<i>ဒီအကောင့်အတွက် မှတ်မိလွယ်တဲ့ နာမည်တစ်ခု ပေးပါ။ (ဥပမာ: အဖေ့ဖုန်း၊ ကိုယ့်ဖုန်း)</i>"
            )
        else:
            await update.effective_message.reply_html(
                f"❌ <b>OTP မမှန်ကန်ပါ သို့မဟုတ် သက်တမ်းကုန်နေပါပြီ။</b>\n\n<i>{res['message']}</i>"
            )
            del user_states[user_id]

    elif current_state == "waiting_token":
        access_token = text.strip()
        user_states[user_id]["access_token"] = access_token
        user_states[user_id]["state"] = "waiting_account_name_token"
        await update.effective_message.reply_html(
            "✅ <b>Token လက်ခံရရှိပါပြီ။</b>\n\n<i>ဒီအကောင့်အတွက် မှတ်မိလွယ်တဲ့ နာမည်တစ်ခု ပေးပါ။ (ဥပမာ: အဖေ့ဖုန်း၊ ကိုယ့်ဖုန်း)</i>"
        )

    elif current_state == "waiting_account_name" or current_state == "waiting_account_name_token":
        account_name = text.strip()
        phone_number = state_info.get("phone_number")
        access_token = state_info.get("access_token")

        if not access_token:
            await update.effective_message.reply_html("⚠️ <b>အမှားအယွင်းတစ်ခုခု ဖြစ်သွားပါပြီ။</b>\n\n<i>ပြန်လည်စတင်ရန် /start ကို နှိပ်ပါ။</i>")
            del user_states[user_id]
            return
        
        # If login via token, we need to get the phone number from the balance API
        if current_state == "waiting_account_name_token" and not phone_number:
            loading_msg = await send_loading_message(update, context, "📡 <i>ဖုန်းနံပါတ် ရယူနေပါသည်...</i>")
            balance_res = await api.get_balance(access_token, "09xxxxxxxxx") # Phone number is not critical here, just to get a response
            await delete_loading_message(loading_msg)
            if balance_res["status"] == "success" and balance_res["data"] and balance_res["data"].get("result"):
                phone_number = balance_res["data"]["result"].get("isdn")
                if not phone_number:
                    await update.effective_message.reply_html("❌ <b>ဖုန်းနံပါတ် ရယူ၍ မရပါ</b>\n\n<i>Token မမှန်ကန်ခြင်း သို့မဟုတ် အခြားအမှားအယွင်း ဖြစ်နိုင်ပါသည်။</i>")
                    del user_states[user_id]
                    return
            else:
                await update.effective_message.reply_html(
                    f"❌ <b>ဖုန်းနံပါတ် ရယူ၍ မရပါ</b>\n\n<i>{balance_res.get('message', 'Token မမှန်ကန်ခြင်း သို့မဟုတ် အခြားအမှားအယွင်း ဖြစ်နိုင်ပါသည်။')}</i>"
                )
                del user_states[user_id]
                return

        await add_account(user_id, phone_number, access_token, account_name)
        await update.effective_message.reply_html(
            f"✅ <b>{account_name} အကောင့်ကို အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ။</b>"
        )
        del user_states[user_id]
        await start(update, context) # Show updated start menu

    else:
        await update.effective_message.reply_html("<i>အမှားအယွင်းတစ်ခုခု ဖြစ်သွားပါပြီ။</i>\n\n<i>ပြန်လည်စတင်ရန် /start ကို နှိပ်ပါ။</i>", parse_mode="HTML")

# --- Callback Query Handlers ---
async def handle_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "add_account":
        message = "🔑 <b>Login Method ရွေးချယ်ပါ</b>\n\n<i>မည်သည့်နည်းလမ်းဖြင့် Login ဝင်လိုပါသနည်း။</i>"
        await query.edit_message_text(message, reply_markup=get_login_options_keyboard(), parse_mode="HTML")

    elif data == "check_balance_menu":
        accounts = await get_user_accounts(user_id)
        if not accounts:
            await query.edit_message_text("⚠️ <b>အကောင့်များ မရှိသေးပါ။</b>\n\n<i>အကောင့်ထည့်ရန် \"➕ အကောင့်ထည့်မည်\" ကို နှိပ်ပါ။</i>", parse_mode="HTML")
            return
        
        keyboard = []
        for acc in accounts:
            keyboard.append([InlineKeyboardButton(f"👤 {acc['name']} ({acc['phone_number'][-4:]})", callback_data=f"select_balance_{acc['phone_number']}")])
        keyboard.append([InlineKeyboardButton("⬅️ နောက်သို့", callback_data="start_menu")])
        
        await query.edit_message_text(
            "📊 <b>လက်ကျန်ကြည့်ရန် အကောင့်ရွေးချယ်ပါ</b> 📊",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    elif data.startswith("select_balance_"):
        phone_number = data.split("_")[2]
        account = await get_account_by_user_id_and_phone(user_id, phone_number)
        if not account:
            await query.edit_message_text("⚠️ <b>အကောင့် မတွေ့ပါ။</b>", parse_mode="HTML")
            return
        
        loading_msg = await send_loading_message(update, context, "📡 <i>လက်ကျန်စစ်ဆေးနေပါသည်...</i>")
        res = await api.get_balance(account["access_token"], phone_number)
        await delete_loading_message(loading_msg)

        if res["status"] == "success" and res["data"] and res["data"].get("result"):
            balance_data = res["data"]["result"]
            main_balance = f"{float(balance_data.get('mainBalance', 0)):,.0f}"
            data_balance = f"{float(balance_data.get('dataBalance', 0)) / (1024*1024):,.2f}" if balance_data.get('dataBalance') else "0"
            loyalty_points = balance_data.get("loyalty_points", "0")

            message = (
                f"💎 <b>{account['name']} ({phone_number})</b>\n\n"
                f"💰 Main: <code>{main_balance}</code> MMK\n"
                f"🌐 Data: <code>{data_balance}</code> MB\n"
                f"🎁 Points: <code>{loyalty_points}</code>"
            )
            await query.edit_message_text(message, reply_markup=get_back_to_balance_list_keyboard(), parse_mode="HTML")
        else:
            error_msg = res.get("message", "API Error")
            if error_msg == "Unauthorized: Token expired or invalid.":
                error_msg = "❌ Token သက်တမ်းကုန်နေပါပြီ။\n\n<i>အကောင့်ကို ဖျက်ပြီး ပြန်ထည့်ပါ။</i>"
            await query.edit_message_text(
                f"❌ <b>လက်ကျန်စစ်ဆေး၍ မရပါ</b>\n\n<i>{error_msg}</i>",
                reply_markup=get_back_to_balance_list_keyboard(),
                parse_mode="HTML"
            )

    elif data == "view_accounts":
        accounts = await get_user_accounts(user_id)
        if not accounts:
            await query.edit_message_text("⚠️ <b>အကောင့်များ မရှိသေးပါ။</b>\n\n<i>အကောင့်ထည့်ရန် \"➕ အကောင့်ထည့်မည်\" ကို နှိပ်ပါ။</i>", parse_mode="HTML")
            return
        
        keyboard = []
        for acc in accounts:
            keyboard.append([InlineKeyboardButton(f"👤 {acc['name']} ({acc['phone_number']})", callback_data=f"manage_{acc['phone_number']}")])
        keyboard.append([InlineKeyboardButton("⬅️ နောက်သို့", callback_data="start_menu")])

        await query.edit_message_text(
            "👥 <b>သင်၏ အကောင့်များ</b> 👥\n\n<i>စီမံရန် အကောင့်တစ်ခုကို ရွေးချယ်ပါ။</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    elif data.startswith("manage_"):
        phone_number = data.split("_")[1]
        account = await get_account_by_user_id_and_phone(user_id, phone_number)
        if not account:
            await query.edit_message_text("⚠️ <b>အကောင့် မတွေ့ပါ။</b>", parse_mode="HTML")
            return
        
        await query.edit_message_text(
            f"👤 <b>{account['name']} ({phone_number})</b>\n\n<i>လုပ်ဆောင်ချက် ရွေးချယ်ပါ။</i>",
            reply_markup=get_account_manage_keyboard(phone_number),
            parse_mode="HTML"
        )

    elif data.startswith("token_"):
        phone_number = data.split("_")[1]
        account = await get_account_by_user_id_and_phone(user_id, phone_number)
        if not account:
            await query.edit_message_text("⚠️ <b>အကောင့် မတွေ့ပါ။</b>", parse_mode="HTML")
            return
        
        token_message = await query.edit_message_text(
            f"🔑 <b>{account['name']} ({phone_number}) Token</b>\n\n<code>{account['access_token']}</code>\n\n<i>(၅ စက္ကန့်အတွင်း အလိုအလျောက် ဖျောက်ပါမည်)</i>",
            parse_mode="HTML"
        )
        await asyncio.sleep(5)
        await token_message.edit_text(
            f"👤 <b>{account['name']} ({phone_number})</b>\n\n<i>လုပ်ဆောင်ချက် ရွေးချယ်ပါ။</i>",
            reply_markup=get_account_manage_keyboard(phone_number),
            parse_mode="HTML"
        )

    elif data.startswith("delete_"):
        phone_number = data.split("_")[1]
        account = await get_account_by_user_id_and_phone(user_id, phone_number)
        if not account:
            await query.edit_message_text("⚠️ <b>အကောင့် မတွေ့ပါ။</b>", parse_mode="HTML")
            return
        
        await delete_account(user_id, phone_number)
        await query.edit_message_text(
            f"🗑️ <b>{account['name']} ({phone_number}) အကောင့်ကို ဖျက်ပြီးပါပြီ။</b>",
            parse_mode="HTML"
        )
        await start(update, context) # Refresh start menu

    elif data == "start_menu":
        await start(update, context)

# --- Main Application ---
async def main():
    await init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))

    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Message Handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot
    logger.info("Bot started polling...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
