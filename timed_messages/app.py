from fastapi import FastAPI
from .transport.whatsapp import router as whatsapp_router

app = FastAPI()
app.include_router(whatsapp_router)