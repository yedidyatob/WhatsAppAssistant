# Personal WhatsApp Assistant 🤖📰⏱️

#### A self-hosted, modular AI concierge for message automation and intelligent link summarization.
Turn WhatsApp into a proactive assistant with message scheduling, link summaries, and a modular microservice architecture.

- ⏱️ **Message Scheduler:** Never miss a "Happy Birthday" or a deadline again. Schedule messages to individuals or groups with a simple chat-based interface.
- 📰 **Smart Summarizer:** Save hours of reading. Get instant, AI-generated TL;DRs of shared articles directly in the chat.
- 🏗️ **Modular Design:** Built on a broadcast architecture — easily add your own custom features without touching the core connection logic.

## ✅ Choose Your Gateway

| Option | Best For | Setup Effort | Notes |
| --- | --- | --- | --- |
| **Hosted Official Bot (beta)** | Fastest way to try the official bot | None | **Reach out to me if you want to join as a tester.** |
| **Official Cloud API (self-hosted)** | Production-grade + assistant mode | High | Requires Meta app + webhook + tokens |
| **Baileys (WhatsApp Web)** | Most full-featured assistant | Low | Unofficial, QR login, sends from your number, can be used in groups |

### Demo

| Link Summarizer | Message Scheduler |
| :---: | :---: |
| <img src="./WhatappLinkReaderDemo.jpeg" width="280" alt="Summarizer Demo"> | <img src="./TimedMessagesDemo.jpeg" width="280" alt="Timed Messages Demo"> |
---

## 🚀 Quickstart (Self-Hosted)
### 1. Prerequisites
- **Docker & Docker Compose** installed.
- An **OpenAI API Key** (for the summarizer; not necessary for just the scheduler).
- If using **Baileys (WhatsApp Web)**: a WhatsApp account to link (a secondary account is recommended).
- If using **Official Cloud API**: a Meta WhatsApp Cloud API setup (app, webhook, access token) and a Cloud API phone number/`WHATSAPP_PHONE_NUMBER_ID`.

### 2. Installation & Configuration
1. **Clone the repository:**
```bash
git clone https://github.com/yedidyatob/WhatsAppLinkReader.git
cd WhatsAppLinkReader
```

2. **Prepare environment variables:**
```bash
cp .env.example .env
```
Edit `.env`:
- Set `OPENAI_API_KEY` and `DEFAULT_TIMEZONE` (e.g., `Asia/Jerusalem`).
- Optional cost guardrails:
  - `OPENAI_DAILY_TOKEN_BUDGET` for free-tier limits.
  - `OPENAI_MAX_COMPLETION_TOKENS` for per-summary caps.


### 3A. Official Cloud API (self-hosted)
Use this if you want **assistant mode** and a fully official gateway.

1. Set `WHATSAPP_ASSISTANT_MODE=true`.
2. Set Cloud API env vars:
   - `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
   - `WHATSAPP_APP_SECRET`
   - `WHATSAPP_CLOUD_TOKEN`
   - `WHATSAPP_PHONE_NUMBER_ID`
   - (optional) `WHATSAPP_GRAPH_VERSION`
3. Webhook URL: point your WhatsApp Cloud API webhook to:
   `https://<your-domain>/` (path is `/`).
> Note: When assistant mode is enabled, services use the official gateway by default. The Baileys gateway remains available.

**Assistant mode auth flow:** a dedicated Auth service handles `!auth` and `!whoami`. Each user must DM `!auth` to generate a personal auth code (printed in logs and sent to admin via WhatsApp). The admin shares that code, and the user completes auth by replying with the 6-digit code. Approved numbers are stored in `config/common_runtime.json` under `approved_numbers`.

**Scheduling window:** in assistant mode, outbound messages are constrained by Meta's 24-hour free-service window. Use `WHATSAPP_ASSISTANT_MAX_SCHEDULE_HOURS` to control the limit.

### 3B. Baileys (WhatsApp Web)
Use this if you want the fastest local setup (unofficial).

1. **Launch the suite:**
```bash
docker compose up --build
```

2. **Link your account**: Watch the gateway logs (`whatsapp-gateway`) and scan the QR code with your WhatsApp app.

3. **Claim Admin rights:** Find the `admin_setup_code` in the `auth_service` logs. In WhatsApp, send the bot a private message: `!whoami <your_code>`.

4. **Activate in groups:** To enable features in a specific group, send:
- `!setup timed messages`
- `!setup summarizer`

## 📱 How to Use

| Feature | Usage |
| --- | --- |
| **Schedule Message** | Type `add`. The bot will guide you through an interactive flow to set the content and time. |
| **Manage Schedule** | Use `list` to see pending messages. To delete one, simply **Reply** to the bot's "Scheduled..." confirmation message with the word `cancel`. |
| **Summarize Link** | Standard mode: tag the bot with `@bot` in a message with a link, or **Reply** to any link with `@bot`. Assistant mode: any message with a URL from an approved sender is summarized automatically. |

---

## ⚙️ Technical Deep Dive

### Asynchronous Microservices Architecture
This suite operates on a **decoupled push-pull model**, ensuring the WhatsApp connection remains stable even during heavy processing or long wait times.

1. **The Broadcast:** When a message arrives, the **Gateway (Node.js)** sends an HTTP POST (Webhook) to all service URLs in `WHATSAPP_EVENT_TARGETS`.
2. **The Processing:** Services (Python) process the data independently.
   - **Auth Service:** Handles `!auth` / `!whoami` commands and updates shared runtime config for approved users/admin state.
   - **Timed Messages Service:** Monitors a **PostgreSQL** database. A dedicated worker "sleeps and polls" the DB to trigger message delivery with high reliability.
   - **Summarizer Service:** Uses **Playwright** to render JS-heavy sites and **Trafilatura** for text extraction before calling the OpenAI API.
3. **The Callback:** When a service is ready to reply, it calls the Gateway's `/send` endpoint with `{ "to": "<chat_id>", "text": "..." }`. This allows tasks to take as long as they need without blocking the Gateway.

### Persistence Layers
- **Relational Data:** PostgreSQL stores the message queue for the scheduler, ensuring your tasks survive a container restart.
- **Contextual Commands:** The Timed Messages service tracks the Message IDs of its confirmations. When a user replies `cancel` to a specific confirmation, the service retrieves the linked task from PostgreSQL and removes it, allowing for precise management.
- **Hot-Reloading Config:** Group permissions and Admin settings are stored in shared `/config` JSON files allowing updates without restarts.
- **Session State:** Saved in the `/auth` volume to persist the WhatsApp Web login.

### 🛠️ Extending the Suite (Add Your Own Service)
The architecture is designed for growth. You can add a new service (e.g., "Weather Alerts" or "Stock Tracker") in minutes.

1. **Create your worker**
Your service just needs to listen for a POST request, and call the Gateway's `/send` endpoint when it wants to talk back.

```python
# Quick Python Example
import requests
from fastapi import FastAPI, Request

app = FastAPI()
GATEWAY_URL = "http://whatsapp-gateway:3000/send"

@app.post("/whatsapp/events")
async def handle_event(request: Request):
    data = await request.json()
    if (data.get("text") or "").strip().lower() == "!ping":
        requests.post(GATEWAY_URL, json={"to": data.get("chat_id"), "text": "Pong! 🏓"})
    return {"status": "ok"}
```

2. **Update Environment**
Append your new service URL to `WHATSAPP_EVENT_TARGETS` in your `.env`.

## 🩺 Troubleshooting
If you are logged out of WhatsApp or get a connection error loop (when ASSISTANT_MODE=false),
remove the auth folder and reconnect:
```bash
rm -rf auth
```

---

## ⚠️ Disclaimer & License
**MIT License.** The official Cloud API gateway is fully supported by Meta. The Baileys (WhatsApp Web) gateway is unofficial and may risk account flagging. Use responsibly and comply with WhatsApp policies.
