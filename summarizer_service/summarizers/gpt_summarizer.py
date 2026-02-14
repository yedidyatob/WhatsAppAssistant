import logging

from openai import OpenAI, OpenAIError

from summarizers.base_summarizer import Summarizer
from runtime_config import runtime_config

logger = logging.getLogger(__name__)


class GPTSummarizer(Summarizer):

    def __init__(self) -> None:
        self.client = OpenAI()

    def summarize(self, text: str) -> str:
        if not text:
            raise ValueError("Text cannot be empty")

        max_completion_tokens = runtime_config.openai_max_completion_tokens()
        estimated_prompt_tokens = self._estimate_prompt_tokens(text)
        reserved_tokens = estimated_prompt_tokens + max_completion_tokens
        allowed, used, budget = runtime_config.reserve_openai_tokens(reserved_tokens)
        if not allowed:
            raise ValueError(
                "Daily OpenAI token budget reached "
                f"({used}/{budget}). Try again tomorrow or raise OPENAI_DAILY_TOKEN_BUDGET."
            )
            
        logger.debug("Input length: %s", len(text))
        actual_tokens = 0
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an assistant that summarizes news articles. "
                            "Write the summary in the same language as the original article. "
                            "Do not translate the text and do not mention the article's language."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Summarize the following article in a few short sentences:\n{text}"
                    }
                ],
                max_completion_tokens=max_completion_tokens
            )

            logger.debug("OpenAI response received")

            usage = getattr(response, "usage", None)
            if usage is not None:
                actual_tokens = int(getattr(usage, "total_tokens", 0) or 0)

            if not response.choices or not response.choices[0].message.content:
                raise ValueError("OpenAI returned an empty response")
                
            summary = response.choices[0].message.content
            logger.debug("Summary length: %s", len(summary))
            logger.debug("Summary text: %s", summary)
            return summary
            
        except OpenAIError as e:
            logger.exception("OpenAI API error: %s", e)
            raise  # Re-raise to be caught by the communicator
        except Exception as e:
            logger.exception("Unexpected error in GPTSummarizer: %s", e)
            raise
        finally:
            runtime_config.reconcile_openai_tokens(
                reserved=reserved_tokens,
                actual=actual_tokens,
            )

    def _estimate_prompt_tokens(self, text: str) -> int:
        # Quick conservative estimate without extra dependencies.
        return max(1, int(len(text) / 3.5) + 120)
