# WhatsApp Link Reader & Summarizer Bot 🤖📰

#### Tired of opening all the news articles people send in WhatsApp groups?
This project listens to WhatsApp messages, detects shared links, fetches the linked content, and generates short summaries using a large language model.

The goal is simple:  
**turn link spam into readable summaries.**

---

## 🧠 What It Does

- Listens for incoming WhatsApp messages
- Detects URLs in messages
- Fetches and cleans article content
- Generates concise summaries using an LLM
- Returns or logs the summary instead of the raw link

Think of it as a lightweight **WhatsApp news reader**.

---

## 🏗️ High-Level Architecture

The system runs as two services:

### WhatsApp Listener (Node.js)
- Built on **Baileys** (WhatsApp Web client)
- Handles login and message events

### Summarization Service (Python)
- extracts url in message
- Fetches article content
- Calls an LLM to generate summaries

Both services are orchestrated with **Docker Compose**.

---

## ⚙️ Configuration & Usage

### 1. Clone the Repository
```bash
git clone https://github.com/yedidyatob/WhatsAppLinkReader.git
cd whatsapp-link-reader
```
### 2. Environment variables
This project uses environment variables for secrets and configuration.
An example file is provided:
```bash
cp .env.example .env
```
Edit .env and provide the required values:

- OPENAI_API_KEY – API key for the LLM used for summarization (GPT)
- SETUP_MODE - true/false. On first launch it should be true, this will print out the chat IDs, which you can then put in the next variable. 
- ALLOWED_GROUPS - the groups in which you want the bot to work, separated by commas. get the IDs using the setup mode.
### Running
```bash
docker compose up --build
```
On the first run, the WhatsApp client needs to authenticate.
- A QR code will be printed to the terminal
- Scan it using the WhatsApp mobile app
- Authentication data will be saved locally

If you ran in setup mode, you can send a message in the group you want to run on, and see the group id printed on the screen. copy it and paste in into the .env file under the ALLOWED_GROUPS variable.

Then you can stop the project (CTRL+C), change SETUP_MODE to false, and run again:
```bash
docker compose up -d
```
That's it!

---


## ⚠️ Disclaimer

> **This project is for educational and experimental purposes only.**

- Uses unofficial WhatsApp Web behavior
- Not affiliated with or endorsed by WhatsApp
- May violate WhatsApp’s Terms of Service if misused
- You are responsible for legal and platform compliance

---

## 📄 License

This project is licensed under the **MIT License**.  
See the `LICENSE` file for details.
