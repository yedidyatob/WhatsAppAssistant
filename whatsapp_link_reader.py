# whatsapp_summarizer.py
"""
Simple WhatsApp webhook that:
 - receives incoming WhatsApp messages (Cloud API / Twilio-compatible JSON)
 - detects URLs
 - extracts article text (newspaper3k)
 - summarizes using OpenAI (or a simple fallback)
 - sends reply via provider (example: WhatsApp Cloud API HTTP POST)

Set environment variables:
 - PROVIDER: "cloud" or "twilio"            # controls reply path
 - WHATSAPP_TOKEN: <meta cloud API token>   # for cloud API send (or TWILIO creds)
 - PHONE_NUMBER_ID: <meta phone number id>  # for cloud API
 - OPENAI_API_KEY: <openai key>             # for summarization
 - (if using Twilio) TWILIO_AUTH_TOKEN, TWILIO_AUTH_SID, TWILIO_WHATSAPP_FROM
"""
from typing import Tuple

from flask import Flask, request, jsonify, Response
import os
import re
import requests
# from newspaper import Article
import openai
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from article_text_extractor import fetch_article_text
import time
from dotenv import load_dotenv

load_dotenv()
session = requests.Session()
session.verify = False  # ignore SSL verification

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Config (from env)
PROVIDER = os.getenv("PROVIDER", "cloud")  # 'cloud' or 'twilio'
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")  # meta token
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")  # meta phone number id
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_AUTH_SID = os.getenv("TWILIO_AUTH_SID")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")  # e.g. 'whatsapp:+1415xxxx'

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

# Simple safety / allowed list - optional
ALLOWED_DOMAINS = None  # e.g. {"bbc.co.uk", "nytimes.com"} or None to allow all

def extract_urls(text):
    return URL_RE.findall(text or "")


def summarize_text_openai(text):
    # using the new API interface
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "את עוזרת אדמיניסטרציה שיודעת לסכם כתבות מהעיתון בצורה טובה."},
                {"role": "user", "content": f"סכמי את הכתבה בכמה משפטים קצרים:\n{text}"}
            ],
            temperature=0.3,
            max_tokens=300
        )
        summary = response.choices[0].message.content
        return summary
    except Exception as e:
        import logging
        logging.exception("OpenAI summarization failed: %s", e)
        return None


def send_whatsapp_reply_cloud(to_number, text):
    """Send via WhatsApp Cloud API (Meta)."""
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        logging.error("Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID")
        return False
    url = f"https://graph.facebook.com/v16.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": False, "body": text}
    }
    r = requests.post(url, json=payload, headers=headers)
    logging.info("Cloud send status %s %s", r.status_code, r.text)
    return r.ok

def send_whatsapp_reply_twilio(to_number, text):
    """Send via Twilio API - minimal example."""
    if not TWILIO_AUTH_SID or not TWILIO_AUTH_TOKEN or not TWILIO_WHATSAPP_FROM:
        logging.error("Missing Twilio config")
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_AUTH_SID}/Messages.json"
    data = {
        "To": f"whatsapp:{to_number}",
        "From": TWILIO_WHATSAPP_FROM,
        "Body": text,
    }
    r = requests.post(url, data=data, auth=(TWILIO_AUTH_SID, TWILIO_AUTH_TOKEN))
    logging.info("Twilio send status %s %s", r.status_code, r.text)
    return r.ok

def clean_url(u: str) -> str:
    # Strip ONLY useless trailing punctuation that cannot appear at the end of valid URLs.
    return u.rstrip('.,);:!?"\'<>]')

def handle_link(url: str, phone: str) -> tuple[Response, int]:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
    except Exception:
        domain = None

    if ALLOWED_DOMAINS and domain and domain not in ALLOWED_DOMAINS:
        reply = f"Sorry, content from {domain} is unreadable."
        if PROVIDER == "twilio":
            send_whatsapp_reply_twilio(phone, reply)
        else:
            send_whatsapp_reply_cloud(phone, reply)
        return jsonify(status="blocked_domain"), 200

    title, art_text = fetch_article_text(url)
    if not art_text:
        reply = f"Could not extract article text from the link. Try a news article link (not a paywalled PDF or heavily dynamic page)."
        if PROVIDER == "twilio":
            send_whatsapp_reply_twilio(phone, reply)
        else:
            send_whatsapp_reply_cloud(phone, reply)
        return jsonify(status="extract_fail"), 200

    # limit length for API calls
    if len(art_text) > 8000:
        art_text = art_text[:8000]  # truncate; or do chunked summaries

    summary = summarize_text_openai(art_text)
    if not summary:
        # fallback naive summary: first 3 sentences
        import re
        sents = re.split(r'(?<=[.!?])\s+', art_text)
        summary = " ".join(sents[:3])

    # Compose reply
    reply_lines = []
    if title:
        reply_lines.append(f"*{title}*")
    reply_lines.append(summary)
    reply_lines.append(f"\nSource: {url}")

    reply_message = "\n\n".join(reply_lines)

    # enforce message length for WhatsApp (keep it short)
    if len(reply_message) > 1500:
        reply_message = reply_message[:1490] + "\n… (truncated)"

    # send it back
    ok = False
    if PROVIDER == "twilio":
        ok = send_whatsapp_reply_twilio(phone, reply_message)
    else:
        ok = send_whatsapp_reply_cloud(phone, reply_message)

    return jsonify(status="ok" if ok else "send_failed"), 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        # Simple webhook verification for Meta:
        verify_token = os.getenv("VERIFY_TOKEN", "verify_token_example")
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode and token:
            if mode == "subscribe" and token == verify_token:
                return challenge, 200
            else:
                return "Forbidden", 403
        return "OK", 200

    # Detect Twilio first (form-encoded)
    if request.form and request.form.get("Body"):
        incoming_text = request.form.get("Body")
        phone = request.form.get("From", "")
        if phone.startswith("whatsapp:"):
            phone = phone.split(":", 1)[1]

        # Process Twilio message
        urls = extract_urls(incoming_text)
        if not urls:
            ok =  send_whatsapp_reply_twilio(phone, "I didn't find a link in your message.")
            return jsonify({"sent": ok}), 200

        # process first link (can loop if you want)
        return handle_link(urls[0], phone)




if __name__ == "__main__":
    app.run(debug=True, port=5000)
