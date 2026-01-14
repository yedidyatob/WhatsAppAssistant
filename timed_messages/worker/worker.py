import logging
from ..infra.db import get_connection
from ..infra.repo_sql import PostgresScheduledMessageRepository
from ..core.service import TimedMessageService
from .scheduler import TimedMessageWorker
from ..transport.whatsapp import WhatsAppTransport


logging.basicConfig(level=logging.INFO)

conn = get_connection()
repo = PostgresScheduledMessageRepository(conn)
service = TimedMessageService(repo)
transport = WhatsAppTransport()

worker = TimedMessageWorker(
    service=service,
    transport=transport,
)

worker.run_forever()
