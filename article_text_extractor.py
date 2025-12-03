import time

from playwright.sync_api import sync_playwright
import logging


def fetch_article_text(url):
    """
    Fetch article text from Hebrew news sites with site-specific selectors.
    Includes logging for debugging extraction.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            logging.info("Navigating to URL: %s", url)
            page.goto(url, timeout=30000, wait_until="domcontentloaded")

            text = None

            # --- Israel Hayom ---
            paragraphs = page.locator("#text-content p.pf0")
            logging.info("Israel Hayom article__body count: %d", paragraphs.count())
            if paragraphs.count() > 0:
                time.sleep(1)
                text = "\n".join([paragraphs.nth(i).inner_text() for i in range(paragraphs.count())])
                logging.info("Extracted %d characters from Israel Hayom article__body", len(text))
                logging.info("Preview: %s", text[:300].replace("\n", " "))

            # --- Ynet ---
            if not text:
                content = page.locator("div#articleText")
                logging.info("Ynet content count: %d", content.count())
                if content.count() > 0:
                    text = content.inner_text()
                    logging.info("Extracted %d characters from Ynet content", len(text))
                    logging.info("Preview: %s", text[:300].replace("\n", " "))

            # --- Generic fallback ---
            if not text:
                paragraphs = page.locator("article p")
                logging.info("Fallback paragraphs count: %d", paragraphs.count())
                if paragraphs.count() > 0:
                    text = "\n".join([paragraphs.nth(i).inner_text() for i in range(paragraphs.count())])
                    logging.info("Extracted %d characters from fallback paragraphs", len(text))
                    logging.info("Preview: %s", text[:300].replace("\n", " "))
                else:
                    logging.info("No content found in fallback paragraphs.")
                    text = None

            title = page.title()
            logging.info("Page title: %s", title)

            browser.close()
            return title, text

    except Exception as e:
        logging.exception("Playwright failed for URL %s: %s", url, e)
        return None, None
