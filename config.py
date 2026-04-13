import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8425866664:AAELO6CYz0Feb-ZEELceCGpkd-s0dHQUr2M")

MYTEL_OTP_REQUEST_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/get-otp?phoneNumber={phone}"
MYTEL_OTP_VALIDATE_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/validate-otp"
MYTEL_BALANCE_URL = "https://apis.mytel.com.mm/account-detail/api/v1.2/individual/account-main?isdn={isdn}&language=en"
