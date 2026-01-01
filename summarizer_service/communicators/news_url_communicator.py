import logging
import re
from typing import Optional, Dict, Any

from web_page_fetchers.playwright_web_page_fetcher import PlaywrightFetcher
from extractors.base_extractor import ArticleTextExtractor
from summarizers.base_summarizer import Summarizer

class UrlCommunicator:
    URL_REGEX = r"https?://[^\s]+"

    def __init__(self, extractor: ArticleTextExtractor, summarizer: Summarizer):
        self.extractor = extractor
        self.summarizer = summarizer
        self.fetcher = PlaywrightFetcher()

    def extract_url(self, text: str) -> Optional[str]:
        match = re.search(self.URL_REGEX, text)
        return match.group(0) if match else None

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        text = payload.get("text", "")

        url = self.extract_url(text)
        if not url:
            error_msg = "NO_URL"
            logging.error(f"Error processing request: {error_msg}")
            return {"status": "error", "message": error_msg}

        # Try extracting page
        try:
            html = self.fetcher.fetch(url)
            page_title, page_text = self.extractor.extract(html)
        except Exception as e:
            logging.exception(f"Extraction failed for URL: {url}")
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
            logging.exception(f"Summarization failed for URL: {url}")
            return {
                "status": "error",
                "type": "SUMMARY_ERROR",
                "message": str(e),
                "url": url
            }
            
        logging.info(f"Successfully processed URL: {url}")
        return {
            "status": "ok",
            "url": url,
            "summary": summary
        }
