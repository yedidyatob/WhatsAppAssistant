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
                {"role": "system", "content": "את עוזרת אדמיניסטרציה שיודעת לסכם כתבות מהעיתון בצורה טובה."},
                {"role": "user", "content": f"סכמי את הכתבה בכמה משפטים קצרים:\n{text}"}
            ],
            max_completion_tokens=1000
        )
        logging.debug("OPENAI RAW:", response)
        summary = response.choices[0].message.content
        logging.debug("SUMMARY TEXT:", summary)
        return summary