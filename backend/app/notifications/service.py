from datetime import datetime

from sqlalchemy.orm import Session

from app.models.domain import AlertEvent, NotificationChannel, NotificationDelivery
from app.notifications.providers import FeishuProvider, WeComProvider


SEVERITY_RANK = {"normal": 1, "important": 2, "urgent": 3}
PROVIDERS = {
    "feishu": FeishuProvider,
    "wecom": WeComProvider,
    "wechat": WeComProvider,
}


def should_send(channel: NotificationChannel, event: AlertEvent) -> bool:
    event_rank = SEVERITY_RANK.get(event.severity, 1)
    channel_rank = SEVERITY_RANK.get(channel.min_severity, 1)
    return channel.enabled and event_rank >= channel_rank and bool(channel.webhook_url)


def delivery_dedupe_key(event: AlertEvent) -> str:
    payload = event.payload or {}
    category = payload.get("category") or f"rule:{event.rule_id or 'manual'}"
    stock_code = event.stock_code or "global"
    return f"{stock_code}:{category}:{event.severity}"


def already_delivered(db: Session, channel: NotificationChannel, event: AlertEvent) -> bool:
    if event.id is None:
        return False
    row = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.channel_id == channel.id,
            NotificationDelivery.alert_event_id == event.id,
            NotificationDelivery.status == "sent",
        )
        .first()
    )
    return row is not None


async def send_event_notifications(db: Session, events: list[AlertEvent]) -> None:
    if not events:
        return
    channels = db.query(NotificationChannel).filter(NotificationChannel.enabled.is_(True)).all()
    if not channels:
        for event in events:
            event.send_status = "no_channel"
        return

    for event in events:
        sent = 0
        skipped = 0
        failures = []
        for channel in channels:
            if not should_send(channel, event):
                continue
            dedupe_key = delivery_dedupe_key(event)
            if already_delivered(db, channel, event):
                skipped += 1
                continue
            provider_cls = PROVIDERS.get(channel.provider)
            if provider_cls is None:
                failures.append(f"{channel.name}: unsupported provider")
                continue
            try:
                ok, error = await provider_cls().send(channel.webhook_url or "", event.title, event.message)
            except Exception as exc:
                ok, error = False, str(exc)
            if ok:
                sent += 1
                db.add(
                    NotificationDelivery(
                        channel_id=channel.id,
                        alert_event_id=event.id,
                        dedupe_key=dedupe_key,
                        status="sent",
                        sent_at=datetime.utcnow(),
                    )
                )
            else:
                failures.append(f"{channel.name}: {error or 'send failed'}")
                db.add(
                    NotificationDelivery(
                        channel_id=channel.id,
                        alert_event_id=event.id,
                        dedupe_key=dedupe_key,
                        status="failed",
                        error=error or "send failed",
                    )
                )
        if sent:
            event.send_status = "sent"
        elif failures:
            event.send_status = "failed"
            event.payload = {**(event.payload or {}), "notification_errors": failures[:3]}
        elif skipped:
            event.send_status = "deduped"
        else:
            event.send_status = "filtered"
