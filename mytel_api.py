import aiohttp
import asyncio
import json
import logging
import zlib
import brotli

# Configure logging
logging.basicConfig(level=logging.INFO, format=\'%(asctime)s - %(levelname)s - %(message)s\')
logger = logging.getLogger(__name__)

# Assuming these are defined in config.py
# from config import MYTEL_OTP_REQUEST_URL, MYTEL_OTP_VALIDATE_URL, MYTEL_BALANCE_URL
# For now, using placeholders if config.py is not provided
MYTEL_OTP_REQUEST_URL = "https://apis.mytel.com.mm/api/v1/auth/otp?msisdn={phone}"
MYTEL_OTP_VALIDATE_URL = "https://apis.mytel.com.mm/api/v1/auth/login"
MYTEL_BALANCE_URL = "https://apis.mytel.com.mm/api/v1/user/balance?isdn={isdn}"

class MytelProAPI:
    BASE_URL = "https://apis.mytel.com.mm"
    LOYALTY_API_HOST = "apis.mytel.com.mm"

    COMMON_HEADERS = {
        \'User-Agent\': \'Dalvik/2.1.0 (Linux; U; Android 7.1.2; Pixel 4 Build/RQ3A.211001.001)\',
        \'Connection\': \'keep-alive\',
        \'Accept-Encoding\': \'gzip, deflate, br\' # Request all common compressions
    }

    def __init__(self):
        self.session = None
        self.timeout = aiohttp.ClientTimeout(total=15) # 15 seconds timeout for all requests

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _decompress_response(self, content, content_encoding):
        try:
            if content_encoding == \'gzip\':
                return zlib.decompress(content, 16 + zlib.MAX_WBITS)
            elif content_encoding == \'deflate\':
                return zlib.decompress(content, -zlib.MAX_WBITS)
            elif content_encoding == \'br\':
                return brotli.decompress(content)
            else:
                return content # No compression or unknown
        except (zlib.error, brotli.error) as e:
            logger.error(f"Decompression failed for {content_encoding}: {e}")
            return content # Return original content if decompression fails

    async def _make_request(self, method, url, token=None, json_data=None, api_type=\'general\'):
        await self._get_session()
        _headers = self.COMMON_HEADERS.copy()

        if api_type == \'loyalty\':
            _headers[\'Host\'] = self.LOYALTY_API_HOST
            _headers[\'Accept\'] = \'application/json\'
            _headers[\'Content-Type\'] = \'application/json\'
        else: # general Mytel APIs
            _headers[\'Host\'] = self.BASE_URL.split(\'//\')[1].split(\'/\')[0]
            _headers[\'Accept\'] = \'application/json\'
            _headers[\'Content-Type\'] = \'application/json\'

        if token:
            _headers[\'Authorization\'] = f\'Bearer {token}\' # Ensure \'Bearer\' is capitalized

        try:
            async with self.session.request(method, url, json=json_data, headers=_headers) as response:
                status = response.status
                content_encoding = response.headers.get(\'Content-Encoding\')
                raw_content = await response.read()

                # Decompress content if needed
                decompressed_content = await self._decompress_response(raw_content, content_encoding)

                try:
                    # Attempt to decode as UTF-8 first, then fall back to latin-1 or ignore errors
                    decoded_content = decompressed_content.decode(\'utf-8\')
                    json_response = json.loads(decoded_content)
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to decode/parse JSON (UTF-8) from {url}: {e}. Trying latin-1 or raw.")
                    try:
                        decoded_content = decompressed_content.decode(\'latin-1\')
                        json_response = json.loads(decoded_content)
                    except (UnicodeDecodeError, json.JSONDecodeError) as e_fallback:
                        logger.error(f"Failed to decode/parse JSON (latin-1) from {url}: {e_fallback}. Returning raw content.")
                        json_response = {"raw_response": decompressed_content.decode(\'utf-8\', errors=\'ignore\'), "message": "Non-JSON or malformed response"}
                except Exception as e:
                    logger.error(f"Unexpected error during JSON processing from {url}: {e}")
                    json_response = {"raw_response": decompressed_content.decode(\'utf-8\', errors=\'ignore\'), "message": f"Unexpected processing error: {e}"}

                # Standardize response format
                if status == 200:
                    # Check for Mytel specific error codes within the JSON response
                    api_error_code = json_response.get(\'errorCode\') or json_response.get(\'code\')
                    if api_error_code in [0, \'0\', 200, \'200\'] or (api_error_code is None and json_response.get(\'result\') is not None) or json_response.get(\'status\') == \'success\':
                        return {"status": "success", "message": "Request successful", "data": json_response}
                    else:
                        error_message = json_response.get(\'message\') or json_response.get(\'desc\') or \'API reported an error\'
                        return {"status": "error", "message": error_message, "data": json_response}
                elif status == 401:
                    return {"status": "error", "message": "Unauthorized: Token expired or invalid.", "data": json_response}
                else:
                    error_message = json_response.get(\'message\') or json_response.get(\'desc\') or f"Server error with status {status}"
                    return {"status": "error", "message": error_message, "data": json_response}
        except asyncio.TimeoutError:
            logger.error(f"API request to {url} timed out after {self.timeout.total} seconds.")
            return {"status": "error", "message": "API request timed out.", "data": None}
        except aiohttp.ClientError as e:
            logger.error(f"Client error during API request to {url}: {e}")
            return {"status": "error", "message": f"Network error: {e}", "data": None}
        except Exception as e:
            logger.error(f"An unexpected error occurred during API request to {url}: {e}")
            return {"status": "error", "message": f"An unexpected error occurred: {e}", "data": None}

    async def get_otp(self, phone_number):
        url = MYTEL_OTP_REQUEST_URL.format(phone=phone_number)
        return await self._make_request("GET", url)

    async def verify_otp(self, phone_number, otp_code):
        url = MYTEL_OTP_VALIDATE_URL
        json_data = {
            "phoneNumber": phone_number, "password": otp_code, "appVersion": "1.0.93",
            "buildVersionApp": "217", "deviceId": "0", "imei": "0",
            "os": "Android", "osAp": "android", "version": "1.2"
        }
        return await self._make_request("POST", url, json_data=json_data)

    async def get_balance(self, token, phone):
        url = MYTEL_BALANCE_URL.format(isdn=phone)
        balance_res = await self._make_request("GET", url, token=token)
        
        points = "0"
        loyalty_url = f"https://{self.LOYALTY_API_HOST}/loyalty/v2.0/api/pack/j4u?phoneNo={phone}"
        points_res = await self._make_request("GET", loyalty_url, token=token, api_type=\'loyalty\')
        
        if points_res["status"] == "success" and points_res["data"] and points_res["data"].get("result"):
            try:
                points = str(points_res["data"]["result"]["loyalty_point"])
            except KeyError:
                logger.warning(f"Loyalty point key not found for phone {phone}")
        
        if balance_res["status"] == "success":
            balance_res["data"]["loyalty_points"] = points # Add points to balance data
            return balance_res
        return balance_res

# Example Usage (for testing purposes)
async def main():
    api = MytelProAPI()
    # Replace with a valid token for testing
    test_token = "YOUR_VALID_MYTEL_TOKEN"
    test_phone = "YOUR_PHONE_NUMBER"
    
    if test_token != "YOUR_VALID_MYTEL_TOKEN":
        print("\n--- Testing Balance with Loyalty ---")
        balance_res = await api.get_balance(test_token, test_phone)
        logger.info(f"Balance Result: {balance_res}")

    else:
        logger.info("Please set a valid MYTEL_TOKEN and MYTEL_PHONE in mytel_api.py for testing.")

    await api._close_session()

if __name__ == \'__main__\':
    asyncio.run(main()))
