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

@app.on_event("startup")
def log_admin_setup() -> None:
    logger.info("Timed messages commands: !setup timed messages / !stop timed messages")
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
