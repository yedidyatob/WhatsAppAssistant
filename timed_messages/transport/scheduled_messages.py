from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.models import ScheduledMessage
from ..core.service import TimedMessageService
from ..infra.db import get_connection
from ..infra.repo_sql import PostgresScheduledMessageRepository

'''
Another way to access the scheduler, not through whatsapp.
Mainly for testing.
'''
router = APIRouter(prefix="/messages", tags=["messages"])


class ScheduleMessageRequest(BaseModel):
    chat_id: str
    text: str
    send_at: datetime = Field(..., description="ISO-8601 timestamp (UTC)")
    idempotency_key: str
    source: str
    reason: Optional[str] = None


class CancelMessageResponse(BaseModel):
    status: str = "ok"


def get_service():
    conn = get_connection()
    try:
        repo = PostgresScheduledMessageRepository(conn)
        yield TimedMessageService(repo)
    finally:
        conn.close()


@router.post("/schedule", response_model=ScheduledMessage)
def schedule_message(
    payload: ScheduleMessageRequest,
    service: TimedMessageService = Depends(get_service),
):
    try:
        return service.schedule_message(
            chat_id=payload.chat_id,
            text=payload.text,
            send_at=payload.send_at,
            idempotency_key=payload.idempotency_key,
            source=payload.source,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{msg_id}/cancel", response_model=CancelMessageResponse)
def cancel_message(
    msg_id: UUID,
    service: TimedMessageService = Depends(get_service),
):
    try:
        service.cancel_message(msg_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CancelMessageResponse()


@router.get("/due", response_model=list[ScheduledMessage])
def list_due_messages(
    limit: int = 10,
    service: TimedMessageService = Depends(get_service),
):
    return service.list_due_messages(limit=limit)
