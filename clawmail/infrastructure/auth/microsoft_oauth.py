"""
Microsoft OAuth 2.0 Device Code Flow
用于 Outlook.com / Microsoft 365 的 IMAP/SMTP OAuth 认证。

注：使用同步 httpx.Client + run_in_executor，避免 sniffio 在 qasync 事件循环下
无法识别异步后端的问题（"unknown async library, or not in async context"）。
"""

import asyncio
import time

import httpx

MS_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
MS_SCOPES = (
    "https://outlook.office.com/IMAP.AccessAsUser.All "
    "https://outlook.office.com/SMTP.Send "
    "offline_access openid profile email"
)
MS_DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


def _post_sync(url: str, data: dict) -> dict:
    """同步 HTTP POST，在线程池中运行以兼容 qasync。"""
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()


def _post_sync_noraise(url: str, data: dict) -> dict:
    """同步 HTTP POST，不抛出 HTTP 错误（由调用方检查 error 字段）。"""
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, data=data)
        return resp.json()


async def start_device_code_flow() -> dict:
    """
    向 Microsoft 设备码端点发起请求。
    返回包含 device_code, user_code, verification_uri, expires_in, interval 的字典。
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _post_sync,
        MS_DEVICE_CODE_URL,
        {"client_id": MS_CLIENT_ID, "scope": MS_SCOPES},
    )


async def poll_for_token(device_code: str, interval: int, expires_in: int) -> dict:
    """
    轮询令牌端点直到用户完成认证或超时。
    返回包含 access_token, refresh_token, expires_in 的字典。
    超时抛出 TimeoutError，其他错误抛出 Exception。
    """
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
            desc = data.get("error_description", "")
            raise Exception(f"OAuth 错误 {error}: {desc}")

    raise TimeoutError("设备码流程超时，请重新开始")


async def refresh_access_token(refresh_token: str) -> dict:
    """
    使用 refresh_token 获取新的 access_token。
    返回包含 access_token, expires_in（可能含 refresh_token）的字典。
    """
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
