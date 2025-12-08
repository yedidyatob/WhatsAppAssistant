from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time


class PlaywrightFetcher:
    @staticmethod
    def fetch(url: str, timeout: int = 40000) -> str:
        """
        Fetch the fully rendered HTML of a page using Playwright (sync version).

        Args:
            url (str): The URL to fetch.
            timeout (int): Timeout in milliseconds (default 40s).

        Returns:
            str: HTML content of the page.
        """
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )

            page = context.new_page()

            # Disable heavy resources (images, fonts, media)
            def block_heavy(route):
                if route.request.resource_type in ["image", "font", "media"]:
                    route.abort()
                else:
                    route.continue_()

            context.route("**/*", block_heavy)

            try:
                # Try full network idle first
            #     page.goto(url, timeout=timeout, wait_until="networkidle")
            # except PlaywrightTimeoutError:
                # Fallback to DOMContentLoaded if networkidle fails
                page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            except Exception as e:
                browser.close()
                raise e
            time.sleep(2)
            html = page.content()
            browser.close()
            return html

# test
# html = asyncio.run(fetch_page("https://www.calcalist.co.il/..."))
