from abc import ABC, abstractmethod
from typing import Tuple

class ArticleTextExtractor(ABC):
    @abstractmethod
    def extract(self, html: str) -> Tuple[str, str]:
        """
        Extracts title and text from HTML.
        
        Returns:
            Tuple[str, str]: A tuple containing (title, text).
        """
        pass
