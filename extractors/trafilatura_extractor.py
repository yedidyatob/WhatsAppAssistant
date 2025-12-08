import trafilatura

from bs4 import BeautifulSoup
import logging

from extractors.base_extractor import ArticleTextExtractor

class TrafilaturaArticleTextExtractor(ArticleTextExtractor):

    def extract(self, html):


        title = ""

        # # 1️⃣ Fetch HTML with requests
        # try:
        #     response = requests.get(url, timeout=10, headers={
        #         "User-Agent": "Mozilla/5.0"
        #     })
        #     response.raise_for_status()
        #     html = response.text
        #     logging.info(f"Fetched {len(html)} characters of HTML")
        # except Exception as e:
        #     logging.error(f"Failed to fetch page: {e}")
        #     return ("", "")   # ALWAYS return 2 values

        # 2️⃣ Extract <title> tag
        try:
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception as e:
            logging.error(f"Failed to extract <title>: {e}")

        # 3️⃣ Extract main article text via Trafilatura
        try:
            text = trafilatura.extract(html)
            if text:
                logging.info(f"Trafilatura extracted {len(text)} characters")
                return (title, text)
        except Exception as e:
            logging.error(f"Trafilatura extraction failed: {e}")



        # 5️⃣ Final fallback: return title only (or empty)
        logging.warning("No text could be extracted")
        return (title, "")