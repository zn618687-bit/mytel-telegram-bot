import aiohttp
import json
import logging
import asyncio
import gzip
from config import MYTEL_OTP_REQUEST_URL, MYTEL_OTP_VALIDATE_URL, MYTEL_BALANCE_URL

logger = logging.getLogger(__name__)

class MytelProAPI:
    def __init__(self):
        # Professional Mobile User-Agent
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 7.1.2; Pixel 4 Build/RQ3A.211001.001)",
            "Accept-Encoding": "gzip",
            "Connection": "keep-alive"
        }
        self.timeout = aiohttp.ClientTimeout(total=20)
        self.loyalty_url = "https://apis.mytel.com.mm/loyalty/v2.0/api/pack/j4u?phoneNo={phone}"
        self.game_profile_url = "https://pubapi-mygov2.mtgmm.co/v1/engine/user/profile"
        self.game_claim_url = "https://pubapi-mygov2.mtgmm.co/v1/engine/user/claim-daily-reward"

    async def _make_request(self, method, url, headers=None, **kwargs):
        """Standardized async request handler with robust Gzip and JSON handling."""
        req_headers = headers if headers else self.headers
        try:
            async with aiohttp.ClientSession(headers=req_headers, timeout=self.timeout) as session:
                async with session.request(method, url, **kwargs) as response:
                    status = response.status
                    content = await response.read()
                    
                    # Manually decompress Gzip if Content-Encoding is gzip
                    if response.headers.get("Content-Encoding") == "gzip":
                        try:
                            content = gzip.decompress(content)
                        except Exception as e:
                            logger.error(f"Gzip decompression failed for {url}: {e}")

                    try:
                        data = json.loads(content.decode("utf-8"))
                    except json.JSONDecodeError:
                        try:
                            data = json.loads(content.decode("latin-1"))
                        except json.JSONDecodeError:
                            data = {"raw_response": content.decode("utf-8", errors="ignore"), "message": "Non-JSON response"}
                    except Exception as e:
                        data = {"raw_response": content.decode("utf-8", errors="ignore"), "message": f"Decode error: {e}"}

                    if status == 200:
                        # Mytel uses errorCode, code, or status
                        err_code = data.get("errorCode") if data.get("errorCode") is not None else data.get("code")
                        if err_code in [0, 200, "0", "200"] or (err_code is None and data.get("result") is not None) or data.get("status") == "success":
                            return {"status": "success", "message": "OK", "data": data}
                        return {"status": "error", "message": data.get("message") or data.get("desc") or "API Error", "data": data}
                    elif status == 401:
                        return {"status": "error", "message": "Unauthorized/Expired", "data": None}
                    else:
                        return {"status": "error", "message": f"Server Error ({status})", "data": data}
        except Exception as e:
            logger.error(f"API Exception at {url}: {e}")
            return {"status": "error", "message": "Connection Failed", "data": str(e)}

    async def send_otp(self, phone):
        """⚡ Request OTP."""
        return await self._make_request("GET", MYTEL_OTP_REQUEST_URL.format(phone=phone))

    async def validate_otp(self, phone, otp):
        """🛡️ Validate OTP and get Token."""
        payload = {
            "phoneNumber": phone, "password": otp, "appVersion": "1.0.93",
            "buildVersionApp": "217", "deviceId": "0", "imei": "0",
            "os": "Android", "osAp": "android", "version": "1.2"
        }
        return await self._make_request("POST", MYTEL_OTP_VALIDATE_URL, json=payload)

    async def get_balance(self, token, phone):
        """💰 Get Balance, Data, and Loyalty Points."""
        headers = {**self.headers, "Authorization": f"Bearer {token}"}
        balance_res = await self._make_request("GET", MYTEL_BALANCE_URL.format(isdn=phone), headers=headers)
        points = "0"
        points_res = await self._make_request("GET", self.loyalty_url.format(phone=phone), headers=headers)
        if points_res["status"] == "success":
            try: points = points_res["data"]["result"]["loyalty_point"]
            except: pass
        if balance_res["status"] == "success":
            balance_res["points"] = points
            return balance_res
        return balance_res

    async def get_game_profile(self, token):
        """🎮 Get Game Profile Information."""
        headers = {**self.headers, "Authorization": f"Bearer {token}"}
        return await self._make_request("GET", self.game_profile_url, headers=headers)

    async def claim_daily_reward(self, token):
        """🎁 Claim Daily Game Reward."""
        headers = {**self.headers, "Authorization": f"Bearer {token}"}
        return await self._make_request("POST", self.game_claim_url, headers=headers)
