import logging

import trafilatura
from bs4 import BeautifulSoup

from extractors.base_extractor import ArticleTextExtractor
from extractors.json_ld_extractor import JsonLDExtractor

logger = logging.getLogger(__name__)

class TrafilaturaArticleTextExtractor(ArticleTextExtractor):

    def extract(self, html):
        title = ""

        # 1️⃣ Extract <title> tag
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception as e:
            logger.warning("Failed to extract <title>: %s", e)

        # 2️⃣ Extract main article text via Trafilatura
        try:
            text = trafilatura.extract(html)
            if text:
                logger.info("Trafilatura extracted %s characters", len(text))
                if len(text) > 800:
                    return title, text
        except Exception as e:
            logger.warning("Trafilatura extraction failed: %s", e)
            
        logger.warning("Very short text or extraction failed, attempting JSON-LD fallback")
        
        # 3️⃣ Fallback to JSON-LD
        try:
            json_ld_title, json_ld_text = JsonLDExtractor().extract(html)
            if json_ld_text:
                # Use JSON-LD title if we didn't find one earlier
                final_title = title if title else json_ld_title
                return final_title, json_ld_text
        except Exception as e:
            logger.warning("JSON-LD extraction failed: %s", e)

        # 4️⃣ Final fallback: return title only (or empty)
        logger.warning("No text could be extracted")
        return title, ""
