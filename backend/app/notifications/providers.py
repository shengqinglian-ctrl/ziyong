import hashlib

import httpx


def mask_webhook(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"masked-{digest}"


class NotificationProvider:
    async def send(self, webhook_url: str, title: str, message: str) -> tuple[bool, str | None]:
        raise NotImplementedError


class FeishuProvider(NotificationProvider):
    async def send(self, webhook_url: str, title: str, message: str) -> tuple[bool, str | None]:
        payload = {"msg_type": "text", "content": {"text": f"{title}\n{message}"}}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
        return response.is_success, None if response.is_success else response.text


class WeComProvider(NotificationProvider):
    async def send(self, webhook_url: str, title: str, message: str) -> tuple[bool, str | None]:
        payload = {"msgtype": "markdown", "markdown": {"content": f"**{title}**\n\n{message}"}}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(webhook_url, json=payload)
        return response.is_success, None if response.is_success else response.text
