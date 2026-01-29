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

logger = logging.getLogger(__name__)


class JsonLDExtractor(ArticleTextExtractor):

    def extract(self, html: str) -> tuple[str, str]:
        """
        Returns (title, text) if found, else ("", "").
        """
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", type="application/ld+json")

        logger.info("JSON-LD scripts found: %d", len(scripts))

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
                    logger.info(
                        "JSON-LD article found (script %d, %d chars)",
                        idx,
                        len(body),
                    )
                    return title, body

        logger.info("No usable JSON-LD article found")
        return "", ""
