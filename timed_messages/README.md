# Timed Messages (DB Setup)

## Alembic migrations

Set the database URL and run migrations from the repository root:

```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/timed_messages"
alembic -c timed_messages/alembic.ini upgrade head
```

If you run from inside `timed_messages/`, use:

```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/timed_messages"
alembic -c alembic.ini upgrade head
```

To generate a new revision:

```bash
alembic -c timed_messages/alembic.ini revision -m "describe change"
```

## API quick test (curl)

Start the API from the repo root:

```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/timed_messages"
uvicorn timed_messages.app:app --reload
```

Schedule a message:

```bash
curl -X POST http://127.0.0.1:8000/messages/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": "12345@c.us",
    "text": "Hello from the scheduler",
    "send_at": "2030-01-01T12:00:00Z",
    "idempotency_key": "demo-1",
    "source": "api",
    "reason": "readme-test"
  }'
```

Cancel a message:

```bash
curl -X POST http://127.0.0.1:8000/messages/{MESSAGE_ID}/cancel
```

List due messages:

```bash
curl "http://127.0.0.1:8000/messages/due?limit=10"
```

Test the WhatsApp inbound endpoint (simulates Baileys):

```bash
curl -X POST http://127.0.0.1:8000/whatsapp/events \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "whatsapp-msg-1",
    "timestamp": 1893456000,
    "chat_id": "12345@c.us",
    "sender_id": "12345@c.us",
    "is_group": false,
    "text": "schedule 2030-01-01T12:00:00Z Hello from WhatsApp",
    "raw": {"source": "test"}
  }'
```

## End-to-end test (API + worker + mock gateway)

1) Start Postgres:

```bash
docker compose up -d postgres
```

2) Start the mock WhatsApp gateway:

```bash
python timed_messages/tools/mock_gateway.py
```

3) Start the API (new terminal):

```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/timed_messages"
uvicorn timed_messages.app:app --reload
```

4) Start the worker (new terminal):

```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/timed_messages"
python -m timed_messages.worker.worker
```

5) Schedule a message due in ~30 seconds:

```bash
SEND_AT="$(date -u -d "+30 seconds" +"%Y-%m-%dT%H:%M:%SZ")"
curl -X POST http://127.0.0.1:8000/messages/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": "12345@c.us",
    "text": "Hello from the worker",
    "send_at": "'"$SEND_AT"'",
    "idempotency_key": "demo-2",
    "source": "api",
    "reason": "end-to-end"
  }'
```

You should see the worker pick it up and the mock gateway receive `/send`.
