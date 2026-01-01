import trafilatura
from bs4 import BeautifulSoup
import logging

from extractors.base_extractor import ArticleTextExtractor
from extractors.json_ld_extractor import JsonLDExtractor

class TrafilaturaArticleTextExtractor(ArticleTextExtractor):

    def extract(self, html):
        title = ""

        # 1️⃣ Extract <title> tag
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception as e:
            logging.error(f"Failed to extract <title>: {e}")

        # 2️⃣ Extract main article text via Trafilatura
        try:
            text = trafilatura.extract(html)
            if text:
                logging.info(f"Trafilatura extracted {len(text)} characters")
                if len(text) > 800:
                    return title, text
        except Exception as e:
            logging.error(f"Trafilatura extraction failed: {e}")
            
        logging.warning("Very short text or extraction failed, attempting JSON-LD fallback")
        
        # 3️⃣ Fallback to JSON-LD
        try:
            json_ld_title, json_ld_text = JsonLDExtractor().extract(html)
            if json_ld_text:
                # Use JSON-LD title if we didn't find one earlier
                final_title = title if title else json_ld_title
                return final_title, json_ld_text
        except Exception as e:
            logging.error(f"JSON-LD extraction failed: {e}")

        # 4️⃣ Final fallback: return title only (or empty)
        logging.warning("No text could be extracted")
        return title, ""
