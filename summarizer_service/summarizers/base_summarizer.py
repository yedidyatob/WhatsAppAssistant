from abc import ABC, abstractmethod

class Summarizer(ABC):
    @abstractmethod
    def summarize(self, text: str) -> str:
        """
        Summarizes the given text.
        
        Args:
            text (str): The text to summarize.
            
        Returns:
            str: The summary.
        """
        pass
