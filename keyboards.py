from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from messages import MESSAGES

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton(MESSAGES["add_account_button"], callback_data="add_account")],
        [InlineKeyboardButton(MESSAGES["check_balance_button"], callback_data="check_balance")],
        [InlineKeyboardButton(MESSAGES["manage_accounts_button"], callback_data="manage_accounts")]
    ]
    return InlineKeyboardMarkup(keyboard)

def login_method_keyboard():
    keyboard = [
        [InlineKeyboardButton(MESSAGES["login_with_otp_button"], callback_data="login_otp")],
        [InlineKeyboardButton(MESSAGES["login_with_token_button"], callback_data="login_token")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton(MESSAGES["back_to_main_menu_button"], callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def account_list_keyboard(accounts):
    keyboard = []
    for acc_id, phone, alias, _ in accounts:
        display_name = alias if alias else phone
        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"select_account_{acc_id}")])
    keyboard.append([InlineKeyboardButton(MESSAGES["add_new_account_button"], callback_data="add_account")])
    keyboard.append([InlineKeyboardButton(MESSAGES["back_to_main_menu_button"], callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def account_management_keyboard(account_id):
    keyboard = [
        [InlineKeyboardButton(MESSAGES["check_balance_single_button"], callback_data=f"check_balance_single_{account_id}")],
        [InlineKeyboardButton(MESSAGES["view_token_button"], callback_data=f"view_token_{account_id}")],
        [InlineKeyboardButton(MESSAGES["delete_account_button"], callback_data=f"delete_account_{account_id}")]
    ]
    keyboard.append([InlineKeyboardButton(MESSAGES["back_to_manage_accounts_button"], callback_data="manage_accounts")])
    return InlineKeyboardMarkup(keyboard)

def cancel_keyboard():
    keyboard = [
        [InlineKeyboardButton(MESSAGES["cancel_button"], callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)
