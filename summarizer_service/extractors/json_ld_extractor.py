import json
import logging
from bs4 import BeautifulSoup

from extractors.base_extractor import ArticleTextExtractor


ARTICLE_TYPES = {
    "Article",
    "NewsArticle",
    "ReportageNewsArticle",
    "AnalysisNewsArticle",
}

class JsonLDExtractor(ArticleTextExtractor):

    def extract(self, html: str) -> str:
        """
            Returns (title, text) if found, else (None, None)
            """
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")

        logging.info("JSON-LD scripts found: %d", len(scripts))

        for idx, script in enumerate(scripts):
            try:
                data = json.loads(script.string)
            except Exception:
                continue

            # JSON-LD can be a list or a single dict
            candidates = data if isinstance(data, list) else [data]

            for obj in candidates:
                if not isinstance(obj, dict):
                    continue

                obj_type = obj.get("@type")
                if isinstance(obj_type, list):
                    obj_type = obj_type[0]

                if obj_type not in ARTICLE_TYPES:
                    continue

                body = obj.get("articleBody")
                title = obj.get("headline") or obj.get("name")

                if body and len(body) > 500:
                    logging.info(
                        "JSON-LD article found (script %d, %d chars)",
                        idx,
                        len(body),
                    )
                    return title, body

        logging.info("No usable JSON-LD article found")
        return None, None