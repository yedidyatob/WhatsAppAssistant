import logging
import openai
from openai import OpenAIError

from summarizers.base_summarizer import Summarizer

class GPTSummarizer(Summarizer):

    def summarize(self, text: str) -> str:
        if not text:
            raise ValueError("Text cannot be empty")
            
        logging.debug(f"🔥 INPUT length: {len(text)}")
        
        try:
            response = openai.chat.completions.create(
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
            
            logging.debug(f"OPENAI RAW: {response}")
            
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("OpenAI returned an empty response")
                
            summary = response.choices[0].message.content
            logging.debug(f"SUMMARY TEXT: {summary}")
            return summary
            
        except OpenAIError as e:
            logging.error(f"OpenAI API error: {e}")
            raise  # Re-raise to be caught by the communicator
        except Exception as e:
            logging.error(f"Unexpected error in GPTSummarizer: {e}")
            raise