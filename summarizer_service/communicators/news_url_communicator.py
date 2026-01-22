import logging
import os
import re
from typing import Optional, Dict, Any

import requests

from web_page_fetchers.playwright_web_page_fetcher import PlaywrightFetcher
from extractors.base_extractor import ArticleTextExtractor
from summarizers.base_summarizer import Summarizer
from runtime_config import runtime_config

logger = logging.getLogger(__name__)


class UrlCommunicator:
    URL_REGEX = r"https?://[^\s]+"

    def __init__(self, extractor: ArticleTextExtractor, summarizer: Summarizer):
        self.extractor = extractor
        self.summarizer = summarizer
        self.fetcher = PlaywrightFetcher()
        self.gateway_url = os.getenv("WHATSAPP_GATEWAY_URL", "http://whatsapp_gateway:3000")

    def extract_url(self, text: str) -> Optional[str]:
        match = re.search(self.URL_REGEX, text)
        if match:
            logger.info("Extracted URL: %s", match.group(0))
        return match.group(0) if match else None

    def process_whatsapp_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        chat_id = payload.get("chat_id")
        text = payload.get("text") or ""
        quoted_text = payload.get("quoted_text")
        sender_id = payload.get("sender_id") or ""

        normalized = text.strip().lower()
        if normalized in {"!setup summarizer", "!stop summarizer"}:
            return self._handle_setup_command(chat_id, sender_id, normalized)

        allowed_groups = set(runtime_config.allowed_groups())
        if chat_id not in allowed_groups:
            logger.info("Rejected whatsapp event: unauthorized_group chat_id=%s", chat_id)
            return {"status": "ok", "accepted": False, "reason": "unauthorized_group"}

        if "@bot" not in text.lower():
            logger.info("Ignored whatsapp event: no_bot_tag chat_id=%s", chat_id)
            return {"status": "ok", "accepted": False, "reason": "no_bot_tag"}

        cleaned = re.sub(r"@bot", "", text, flags=re.IGNORECASE).strip()
        input_text = quoted_text.strip() if quoted_text else cleaned
        logger.info(
            "Accepted whatsapp event: chat_id=%s, tagged=true, input_length=%s",
            chat_id,
            len(input_text),
        )

        result = self._summarize_text(input_text)
        if result.get("status") == "ok":
            reply = result.get("summary") or "✅ Done"
            logger.info(
                "Sending summary to gateway: chat_id=%s, preview=%r",
                chat_id,
                reply[:120],
            )
            self._send_whatsapp(chat_id, reply)
            return {"status": "ok", "accepted": True, "reason": None}

        error_msg = result.get("message") or "Could not process request"
        self._send_whatsapp(chat_id, f"⚠️ Error: {error_msg}")
        return {"status": "ok", "accepted": False, "reason": result.get("type") or "error"}

    def _handle_setup_command(self, chat_id: str, sender_id: str, command: str) -> Dict[str, Any]:
        admin_id = runtime_config.admin_sender_id()
        if not admin_id:
            self._send_whatsapp(chat_id, "❌ Admin sender ID not configured.")
            return {"status": "ok", "accepted": False, "reason": "admin_not_configured"}

        if sender_id != admin_id:
            self._send_whatsapp(chat_id, "❌ Unauthorized.")
            return {"status": "ok", "accepted": False, "reason": "unauthorized_admin"}

        if command == "!setup summarizer":
            runtime_config.add_allowed_group(chat_id)
            self._send_whatsapp(chat_id, "✅ Summarizer enabled for this group.")
            return {"status": "ok", "accepted": True, "reason": None}

        runtime_config.remove_allowed_group(chat_id)
        self._send_whatsapp(chat_id, "✅ Summarizer disabled for this group.")
        return {"status": "ok", "accepted": True, "reason": None}

    def _summarize_text(self, text: str) -> Dict[str, Any]:
        url = self.extract_url(text)
        if not url:
            error_msg = "NO_URL"
            logger.error("Error processing request: %s", error_msg)
            return {"status": "error", "message": error_msg}

        # Try extracting page
        try:
            html = self.fetcher.fetch(url)
            page_title, page_text = self.extractor.extract(html)
            logger.info(
                "Extracted page content: title=%r, text_length=%s",
                page_title,
                len(page_text or ""),
            )
        except Exception as e:
            logger.exception("Extraction failed for URL: %s", url)
            return {
                "status": "error",
                "type": "EXTRACTION_ERROR",
                "message": str(e),
                "url": url,
            }

        # Try summarizing page
        try:
            summary = self.summarizer.summarize(page_text)
            logger.info("Summary generated: length=%s", len(summary or ""))
        except Exception as e:
            logger.exception("Summarization failed for URL: %s", url)
            return {
                "status": "error",
                "type": "SUMMARY_ERROR",
                "message": str(e),
                "url": url,
            }

        logger.info("Successfully processed URL: %s", url)
        return {
            "status": "ok",
            "url": url,
            "summary": summary,
        }

    def _send_whatsapp(self, chat_id: str, text: str) -> None:
        if not chat_id or not text:
            return
        try:
            resp = requests.post(
                f"{self.gateway_url}/send",
                json={"to": chat_id, "text": text},
                timeout=5,
            )
            if resp.status_code != 200:
                logger.error("WhatsApp gateway error: %s", resp.text)
        except requests.RequestException as exc:
            logger.error("Failed to reach WhatsApp gateway: %s", exc)
