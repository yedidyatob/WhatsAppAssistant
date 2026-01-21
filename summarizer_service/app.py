import logging
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from extractors.trafilatura_extractor import TrafilaturaArticleTextExtractor
from summarizers.gpt_summarizer import GPTSummarizer
from communicators.news_url_communicator import UrlCommunicator

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "ERROR").upper(), logging.ERROR),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("werkzeug").setLevel(
    getattr(logging, os.getenv("LOG_LEVEL", "ERROR").upper(), logging.ERROR)
)

app = Flask(__name__)
print("Summarizer commands: !setup summarizer / !stop summarizer")

# Initialize services
extractor = TrafilaturaArticleTextExtractor()
summarizer = GPTSummarizer()
communicator = UrlCommunicator(extractor, summarizer)

@app.route("/process", methods=["POST"])
def process():
    payload = request.get_json()
    if not payload:
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400
        
    result = communicator.process(payload)
    return jsonify(result)

@app.route("/whatsapp/events", methods=["POST"])
def whatsapp_events():
    payload = request.get_json()
    if not payload:
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    result = communicator.process_whatsapp_event(payload)
    return jsonify(result)

@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(port=5001, debug=debug, host="0.0.0.0", use_reloader=debug)
