import aiohttp
import json
from config import MYTEL_OTP_REQUEST_URL, MYTEL_OTP_VALIDATE_URL, MYTEL_BALANCE_URL

async def send_otp(phone_number):
    url = MYTEL_OTP_REQUEST_URL.format(phone=phone_number)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                response.raise_for_status()

async def validate_otp(phone_number, otp):
    url = MYTEL_OTP_VALIDATE_URL
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "phoneNumber": phone_number,
        "password": otp,
        "appVersion": "1.0.93",
        "buildVersionApp": "217",
        "deviceId": "0",
        "imei": "0",
        "os": "Android",
        "osAp": "android",
        "version": "1.2"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=json.dumps(payload)) as response:
            if response.status == 200:
                return await response.json()
            else:
                response.raise_for_status()

async def get_balance(token, isdn):
    url = MYTEL_BALANCE_URL.format(isdn=isdn)
    headers = {
        "Authorization": f"Bearer {token}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 401:
                return {"errorCode": 401, "message": "Unauthorized: Token expired or invalid"}
            else:
                response.raise_for_status()
