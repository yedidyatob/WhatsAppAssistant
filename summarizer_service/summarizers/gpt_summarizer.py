import logging

import openai

from summarizers.base_summarizer import Summarizer


class GPTSummarizer(Summarizer):

    def summarize(self, text):
        # using the new API interface
        if not text:
            raise ValueError("text cannot be empty")
        logging.debug("🔥 INPUT:", text)
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
        logging.debug("OPENAI RAW:", response)
        summary = response.choices[0].message.content
        logging.debug("SUMMARY TEXT:", summary)
        return summary