import logging

from openai import OpenAI, OpenAIError

from summarizers.base_summarizer import Summarizer

logger = logging.getLogger(__name__)


class GPTSummarizer(Summarizer):

    def __init__(self) -> None:
        self.client = OpenAI()

    def summarize(self, text: str) -> str:
        if not text:
            raise ValueError("Text cannot be empty")
            
        logger.debug("Input length: %s", len(text))
        
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
                max_completion_tokens=1000
            )
            
            logger.debug("OpenAI response received")
            
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
