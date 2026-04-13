import aiohttp
import json
import logging
from config import MYTEL_OTP_REQUEST_URL, MYTEL_OTP_VALIDATE_URL, MYTEL_BALANCE_URL

logger = logging.getLogger(__name__)

async def send_otp(phone_number):
    """Send OTP to the provided phone number."""
    url = MYTEL_OTP_REQUEST_URL.format(phone=phone_number)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response_data = await response.json()
                logger.info(f"OTP Request Response for {phone_number}: {response.status} - {response_data}")
                
                if response.status == 200:
                    return response_data
                else:
                    logger.error(f"OTP Request failed with status {response.status}: {response_data}")
                    return {"errorCode": response.status, "message": "OTP request failed"}
    except asyncio.TimeoutError:
        logger.error(f"OTP Request timeout for {phone_number}")
        return {"errorCode": 408, "message": "Request timeout"}
    except Exception as e:
        logger.error(f"Error sending OTP for {phone_number}: {str(e)}")
        return {"errorCode": 500, "message": str(e)}

async def validate_otp(phone_number, otp):
    """Validate OTP code and return access token."""
    url = MYTEL_OTP_VALIDATE_URL
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "MytelApp/1.0.93"
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
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=json.dumps(payload), timeout=aiohttp.ClientTimeout(total=10)) as response:
                response_data = await response.json()
                logger.info(f"OTP Validation Response for {phone_number}: {response.status}")
                logger.debug(f"Response Data: {response_data}")
                
                if response.status == 200:
                    # Check if errorCode in response is 200 (success)
                    if response_data.get("errorCode") == 200 and "result" in response_data:
                        return response_data
                    elif response_data.get("errorCode") == 200:
                        # Sometimes API returns errorCode 200 but no result
                        logger.warning(f"OTP validation returned 200 but no token in result for {phone_number}")
                        return response_data
                    else:
                        logger.error(f"OTP validation failed: errorCode {response_data.get('errorCode')}")
                        return response_data
                else:
                    logger.error(f"OTP Validation failed with HTTP status {response.status}: {response_data}")
                    return {"errorCode": response.status, "message": "OTP validation failed"}
    except asyncio.TimeoutError:
        logger.error(f"OTP Validation timeout for {phone_number}")
        return {"errorCode": 408, "message": "Request timeout"}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OTP validation response for {phone_number}: {str(e)}")
        return {"errorCode": 500, "message": "Invalid response format"}
    except Exception as e:
        logger.error(f"Error validating OTP for {phone_number}: {str(e)}")
        return {"errorCode": 500, "message": str(e)}

async def get_balance(token, isdn):
    """Get account balance using access token."""
    url = MYTEL_BALANCE_URL.format(isdn=isdn)
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "MytelApp/1.0.93"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                logger.info(f"Balance Request for {isdn}: {response.status}")
                
                if response.status == 200:
                    response_data = await response.json()
                    return response_data
                elif response.status == 401:
                    logger.warning(f"Token expired for {isdn}")
                    return {"errorCode": 401, "message": "Unauthorized: Token expired or invalid"}
                else:
                    logger.error(f"Balance request failed with status {response.status}")
                    return {"errorCode": response.status, "message": "Balance request failed"}
    except asyncio.TimeoutError:
        logger.error(f"Balance request timeout for {isdn}")
        return {"errorCode": 408, "message": "Request timeout"}
    except Exception as e:
        logger.error(f"Error getting balance for {isdn}: {str(e)}")
        return {"errorCode": 500, "message": str(e)}
