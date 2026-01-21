# Personal WhatsApp Assistant 🤖📰⏱️

#### Tired of digging through WhatsApp noise?
This project is a personal WhatsApp assistant that summarizes shared links and lets you schedule messages to be sent later.

The goal is simple:  
**Turn link spam into readable summaries and send messages on your schedule.**

---

## 🧠 What It Does

- Summarizes links posted in chats
- Schedules messages for a future time
- Lets you manage scheduled messages via chat commands
- Runs fully via Docker Compose

Think of it as a lightweight **WhatsApp assistant** that helps you keep up and stay on top of reminders.
More features are on the way.

### Demo

<img src="./WhatappLinkReaderDemo.jpeg" width="240" alt="Summarizer Demo Image">
<img src="./TimedMessagesDemo.jpeg" width="240" alt="Timed Messages Demo Image">

---

## 🏗️ High-Level Architecture

The system runs as multiple services:

### 1. WhatsApp Gateway (Node.js)
- Built on **Baileys** (WhatsApp Web client)
- Handles login, message events, and replies
- Automatically reconnects if the connection drops

### 2. Summarization Service (Python)
- Extracts URLs from text
- Fetches article content using **Playwright** (handles dynamic JS sites)
- Extracts clean text using **Trafilatura** (with JSON-LD fallback)
- Calls **OpenAI GPT** to generate summaries

### 3. Timed Messages Service (Python + Postgres)
- Accepts add/list/cancel commands
- Stores schedules in Postgres DB
- A worker delivers messages at the right time

All services are orchestrated with **Docker Compose**.

---

## ⚙️ Configuration & Usage

### 1. Clone the Repository
```bash
git clone https://github.com/yedidyatob/WhatsAppLinkReader.git
cd WhatsAppLinkReader
```

### 2. Environment Variables
This project uses environment variables for secrets and configuration. An example file is provided:
```bash
cp .env.example .env
```
Edit `.env` and provide the required values:

- `OPENAI_API_KEY` – API key for the LLM used for summarization (GPT)
- `WHATSAPP_GATEWAY_URL` - Base URL used by services to send replies via the gateway.
- `WHATSAPP_EVENT_TARGETS` - Comma-separated list of service endpoints (default is already set). 
- `DATABASE_URL` - Postgres DSN for the timed messages service.
- `DEFAULT_TIMEZONE` - IANA timezone for scheduling (e.g. `UTC`, `America/New_York`).

Runtime settings live in `config/`:
- `config/summarizer_runtime.json` – allowed group IDs for summarization.
- `config/common_runtime.json` – admin sender ID for timed messages.
- `config/timed_messages_runtime.json` – scheduling group + admin setup code.

### 3. Running
```bash
docker compose up --build
```
On the first run, the WhatsApp client needs to authenticate.
- A QR code will be printed to the terminal.
- Scan it using the WhatsApp mobile app (Linked Devices).
- Authentication data will be saved locally in the `auth/` folder.
- Set an admin once: check terminal output for `admin_setup_code`, then send `!whoami <code>` in WhatsApp.

You're set up!

### 4. Usage
**Summarizer**
- Enable the Summarizer in a group with `!setup summarizer`.
- Use the key phrase **"@bot"** - anyone in the group can use it.
- **Direct Message:** Send a message containing a link and `@bot`.
- **Reply:** Reply to a message containing a link with `@bot`.

**Timed Messages**
- Enable scheduling in a group with `!setup timed messages`.
- Commands: `add` (interactive), `list`, `cancel`, `instructions`.

#### Troubleshooting
If you are logged out of WhatsApp or get a connection error loop,
remove the auth folder and reconnect:
```bash
rm -rf auth
```

---

## ⚠️ Disclaimer

> **This project is for educational and experimental purposes only.**

- Uses unofficial WhatsApp Web behavior.
- Not affiliated with or endorsed by WhatsApp.
- May violate WhatsApp’s Terms of Service if misused.
- You are responsible for legal and platform compliance.

---

## 📄 License

This project is licensed under the **MIT License**.  
See the `LICENSE` file for details.
