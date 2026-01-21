from fastapi import FastAPI
from .transport.whatsapp import router as whatsapp_router
from .transport.scheduled_messages import router as scheduled_messages_router
from timed_messages.runtime_config import runtime_config

app = FastAPI()
app.include_router(whatsapp_router)
app.include_router(scheduled_messages_router)

@app.on_event("startup")
def log_admin_setup() -> None:
    print("Timed messages commands: !setup timed messages / !stop timed messages")
    if runtime_config.admin_sender_id():
        return
    setup_code = runtime_config.admin_setup_code()
    print("=== Admin Setup Required ===")
    print(f"Setup code: {setup_code}")
    print("Send this message from your WhatsApp account:")
    print(f"!whoami {setup_code}")
    print("============================")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
