import logging
import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from extractors.trafilatura_extractor import TrafilaturaArticleTextExtractor
from summarizers.gpt_summarizer import GPTSummarizer
from communicators.news_url_communicator import UrlCommunicator
from runtime_config import runtime_config
from shared.logging_utils import configure_logging

load_dotenv()

log_level = configure_logging()
logging.getLogger("werkzeug").setLevel(log_level)
logger = logging.getLogger(__name__)

app = Flask(__name__)
logger.info("Summarizer commands: !setup summarizer / !stop summarizer")

SUMMARIZER_INSTRUCTION = (
    "Summarizer: send any news article link to the assistant and get the summary back as a reply."
)
runtime_config.set_instruction("summarizer", SUMMARIZER_INSTRUCTION)
logger.info("Instructions:")
for _, instruction in runtime_config.instructions().items():
    logger.info("- %s", instruction)

# Initialize services
extractor = TrafilaturaArticleTextExtractor()
summarizer = GPTSummarizer()
communicator = UrlCommunicator(extractor, summarizer)

@app.route("/whatsapp/events", methods=["POST"])
def whatsapp_events():
    payload = request.get_json(silent=True)
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
