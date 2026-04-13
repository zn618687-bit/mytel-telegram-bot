import aiohttp
import json
import logging
import asyncio
from config import MYTEL_OTP_REQUEST_URL, MYTEL_OTP_VALIDATE_URL, MYTEL_BALANCE_URL

logger = logging.getLogger(__name__)

class MytelProAPI:
    def __init__(self):
        self.headers = {
            "User-Agent": "MytelApp/1.0.93 (Android; 13; Build/TP1A.220624.014; en_US)",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "keep-alive"
        }
        self.timeout = aiohttp.ClientTimeout(total=15)

    async def _make_request(self, method, url, **kwargs):
        """Internal helper for standardized API requests."""
        try:
            async with aiohttp.ClientSession(headers=self.headers, timeout=self.timeout) as session:
                async with session.request(method, url, **kwargs) as response:
                    status_code = response.status
                    try:
                        data = await response.json()
                    except:
                        data = await response.text()

                    if status_code == 200:
                        # Mytel specific logic: check errorCode inside JSON
                        if isinstance(data, dict) and data.get("errorCode") in [0, 200]:
                            return {"status": "success", "message": "Operation successful", "data": data}
                        else:
                            msg = data.get("message") if isinstance(data, dict) else "API error"
                            return {"status": "error", "message": msg, "data": data}
                    elif status_code == 401:
                        return {"status": "error", "message": "Unauthorized: Token expired", "data": None}
                    else:
                        return {"status": "error", "message": f"Server error ({status_code})", "data": data}
        except asyncio.TimeoutError:
            return {"status": "error", "message": "Network timeout. Please try again.", "data": None}
        except Exception as e:
            logger.error(f"API Request Exception: {str(e)}")
            return {"status": "error", "message": "Connection failed.", "data": str(e)}

    async def send_otp(self, phone_number):
        """⚡ Request OTP from Mytel server."""
        url = MYTEL_OTP_REQUEST_URL.format(phone=phone_number)
        return await self._make_request("GET", url)

    async def validate_otp(self, phone_number, otp):
        """🛡️ Validate OTP and retrieve access token."""
        url = MYTEL_OTP_VALIDATE_URL
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
        return await self._make_request("POST", url, json=payload)

    async def get_balance(self, token, isdn):
        """💰 Fetch balance details for the given ISDN."""
        url = MYTEL_BALANCE_URL.format(isdn=isdn)
        headers = {**self.headers, "Authorization": f"Bearer {token}"}
        
        # Override headers locally for this request to include Bearer token
        try:
            async with aiohttp.ClientSession(headers=headers, timeout=self.timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("errorCode") == 0:
                            return {"status": "success", "message": "Balance retrieved", "data": data}
                        return {"status": "error", "message": data.get("message", "Balance error"), "data": data}
                    elif response.status == 401:
                        return {"status": "error", "message": "Token expired", "data": None}
                    return {"status": "error", "message": f"Server error ({response.status})", "data": None}
        except Exception as e:
            return {"status": "error", "message": "Connection failed", "data": str(e)}
