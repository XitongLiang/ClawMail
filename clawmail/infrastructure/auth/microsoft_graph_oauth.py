"""
Microsoft Graph OAuth 2.0 Device Code Flow
用于 Outlook.com / Microsoft 365 的 Graph API 认证。
使用 Graph 权限（Mail.Read / Mail.Send），替代旧的 IMAP/SMTP 权限。
"""

import asyncio
import time

import httpx

MS_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
MS_SCOPES = (
    "https://graph.microsoft.com/Mail.Read "
    "https://graph.microsoft.com/Mail.Send "
    "https://graph.microsoft.com/User.Read "
    "offline_access openid profile email"
)
MS_DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


def _post_sync(url: str, data: dict) -> dict:
    with httpx.Client(timeout=30, trust_env=False) as client:
        resp = client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()


def _post_sync_noraise(url: str, data: dict) -> dict:
    with httpx.Client(timeout=30, trust_env=False) as client:
        resp = client.post(url, data=data)
        return resp.json()


async def start_device_code_flow() -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _post_sync,
        MS_DEVICE_CODE_URL,
        {"client_id": MS_CLIENT_ID, "scope": MS_SCOPES},
    )


async def poll_for_token(device_code: str, interval: int, expires_in: int) -> dict:
    loop = asyncio.get_event_loop()
    deadline = time.monotonic() + expires_in
    poll_interval = interval

    while time.monotonic() < deadline:
        await asyncio.sleep(poll_interval)
        data = await loop.run_in_executor(
            None,
            _post_sync_noraise,
            MS_TOKEN_URL,
            {
                "client_id": MS_CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
        )
        if "access_token" in data:
            return data
        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            poll_interval += 5
            continue
        elif error == "expired_token":
            raise TimeoutError("设备码已过期，请重新开始")
        else:
            raise Exception(f"OAuth 错误 {error}: {data.get('error_description')}")

    raise TimeoutError("设备码流程超时，请重新开始")


async def refresh_access_token(refresh_token: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _post_sync,
        MS_TOKEN_URL,
        {
            "client_id": MS_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
