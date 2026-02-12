import logging
import os

from fastapi import FastAPI

from shared.auth import InMemoryPendingAuthStore
from shared.logging_utils import configure_logging
from timed_messages.runtime_config import runtime_config

from .core.flow_store import InMemoryFlowStore
from .core.whatsapp_event_service import WhatsAppEventService
from .transport.scheduled_messages import router as scheduled_messages_router
from .transport.whatsapp import create_router as create_whatsapp_router

log_level = configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()
app.include_router(
    create_whatsapp_router(
        flow_store=InMemoryFlowStore(ttl=WhatsAppEventService._flow_ttl),
        pending_auth_store=InMemoryPendingAuthStore(ttl=WhatsAppEventService._auth_ttl),
    )
)
if os.getenv("TIMED_MESSAGES_ENABLE_DEBUG_API", "").lower() == "true":
    app.include_router(scheduled_messages_router)


TIMED_MESSAGES_INSTRUCTION = (
    "Timed Messages: use *add* to schedule, *list* to view pending messages, "
    "and cancel by replying *cancel* to a scheduled confirmation."
)


@app.on_event("startup")
def log_admin_setup() -> None:
    runtime_config.set_instruction("timed_messages", TIMED_MESSAGES_INSTRUCTION)
    logger.info("Timed messages commands: !setup timed messages / !stop timed messages")
    logger.info("Instructions:")
    for _, instruction in runtime_config.instructions().items():
        logger.info("- %s", instruction)
    if runtime_config.admin_sender_id():
        return
    setup_code = runtime_config.admin_setup_code()
    logger.warning("=== Admin Setup Required ===")
    logger.warning("Setup code: %s", setup_code)
    logger.warning("Send this message from your WhatsApp account:")
    logger.warning("!whoami %s", setup_code)
    logger.warning("============================")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
