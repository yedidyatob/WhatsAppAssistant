import time
import logging
from datetime import timezone

from ..core.service import TimedMessageService
from ..transport.whatsapp import WhatsAppTransport

logger = logging.getLogger(__name__)


class TimedMessageWorker:
    def __init__(
        self,
        service: TimedMessageService,
        transport: WhatsAppTransport,
        poll_interval_seconds: int = 5,
        batch_size: int = 10,
    ):
        """
        send_func(chat_id: str, text: str, message_id: UUID) -> None
        """
        self.service = service
        self.transport = transport
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self._running = False

    def run_forever(self):
        logger.info("TimedMessageWorker started")
        self._running = True

        while self._running:
            try:
                self._run_once()
            except Exception:
                logger.exception("Worker loop error")
                # hard failure protection
                time.sleep(self.poll_interval_seconds)

    def stop(self):
        self._running = False

    def _run_once(self):
        due_messages = self.service.list_due_messages(
            limit=self.batch_size
        )

        if not due_messages:
            logger.debug("No due messages")
            time.sleep(self.poll_interval_seconds)
            return

        logger.info("Found %d due message(s)", len(due_messages))

        for msg in due_messages:
            try:
                logger.info("Sending message %s to %s", msg.id, msg.chat_id)
                self.service.send_message_if_due(
                    msg_id=msg.id,
                    transport=self.transport,
                    quoted_message_id=None
                )
                logger.info("Sent message %s", msg.id)
            except Exception:
                # already recorded as FAILED by service
                logger.exception(
                    "Failed sending message %s", msg.id
                )
