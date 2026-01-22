import logging
import os

from shared.logging_utils import configure_logging
from ..infra.db import get_connection
from ..infra.repo_sql import PostgresScheduledMessageRepository
from ..core.service import TimedMessageService
from .scheduler import TimedMessageWorker
from ..transport.whatsapp import WhatsAppTransport


configure_logging()

conn = get_connection()
repo = PostgresScheduledMessageRepository(conn)
service = TimedMessageService(repo)
transport = WhatsAppTransport()

worker = TimedMessageWorker(
    service=service,
    transport=transport,
)

worker.run_forever()
