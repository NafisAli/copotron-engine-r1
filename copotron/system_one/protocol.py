from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from copotron.system_one.types import Question, SystemOneResponse

class SystemOneProvider(ABC):
    """
    Abstract Protocol for System One Decision Providers.
    Decouples engine logic from specific vendors or inference backends.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique identifier for this provider (e.g. 'typesafe', 'fallback', 'mock')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether provider credentials and dependencies are properly configured."""
        pass

    @abstractmethod
    def evaluate(
        self,
        state: Any,
        questions: Dict[str, Question],
        model: Optional[str] = None,
        **kwargs
    ) -> SystemOneResponse:
        """
        Execute parallel System One evaluation over the provided state.
        Must return a standardized SystemOneResponse.
        """
        pass
