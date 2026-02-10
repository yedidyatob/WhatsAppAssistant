import logging
import os

from fastapi import FastAPI

from shared.logging_utils import configure_logging
from .transport.whatsapp import router as whatsapp_router
from .transport.scheduled_messages import router as scheduled_messages_router
from timed_messages.runtime_config import runtime_config

log_level = configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()
app.include_router(whatsapp_router)
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
