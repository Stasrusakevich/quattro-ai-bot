import json

from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError

from services.logger import logger


async def deliver_notifications(bot, database, item_id=None, limit=20):
    for _ in range(limit):
        notification = database.claim_notification(item_id)
        if notification is None:
            return
        payload = json.loads(notification["payload_json"])
        try:
            result = await getattr(bot, notification["method"])(**payload)
        except RetryAfter as error:
            delay = error.retry_after
            if hasattr(delay, "total_seconds"):
                delay = delay.total_seconds()
            database.notification_result(notification, "pending", error="RetryAfter", delay=float(delay) + 1)
            return
        except (Forbidden, BadRequest) as error:
            database.notification_result(notification, "failed", error=type(error).__name__)
        except NetworkError:
            # Telegram may have delivered it. Avoid an automatic duplicate.
            database.notification_result(notification, "uncertain", error="NetworkError")
        except TelegramError as error:
            database.notification_result(notification, "uncertain", error=type(error).__name__)
        else:
            database.notification_result(notification, "sent", message_id=result.message_id)
        logger.info("Notification processed id=%s", notification["id"])
