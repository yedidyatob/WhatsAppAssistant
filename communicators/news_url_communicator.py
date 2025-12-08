import logging
import re

from web_page_fetchers.playwright_web_page_fetcher import PlaywrightFetcher


class UrlCommunicator:
    URL_REGEX = r"https?://[^\s]+"

    def __init__(self, extractor, summarizer):
        self.extractor = extractor
        self.summarizer = summarizer
        self.fetcher = PlaywrightFetcher()

    def extract_url(self, text: str) -> str | None:
        match = re.search(self.URL_REGEX, text)
        return match.group(0) if match else None

    def process(self, payload: dict) -> dict:
        text = payload.get("text", "")

        url = self.extract_url(text)
        if not url:
            logging.error(str({"status": "error", "message": "NO_URL"}))
            return {"status": "error", "message": "NO_URL"}

        # Try extracting page
        try:
            html = self.fetcher.fetch(url)
            page_title, page_text = self.extractor.extract(html)
        except Exception as e:
            logging.error(e)
            return {
                "status": "error",
                "type": "EXTRACTION_ERROR",
                "message": str(e),
                "url": url
            }

        # Try summarizing page
        try:
            summary = self.summarizer.summarize(page_text)
        except Exception as e:
            logging.error(e)

            return {
                "status": "error",
                "type": "SUMMARY_ERROR",
                "message": str(e),
                "url": url
            }
        logging.info({"status": "ok", "url": url})
        return {
            "status": "ok",
            "url": url,
            "summary": summary
        }
