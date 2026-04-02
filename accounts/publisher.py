import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)


class EventPublisher(ABC):
    """Abstract base class for event publishers."""

    @abstractmethod
    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Publish an event.

        Args:
            event_type: A string identifying the type of event (e.g., 'user_created').
            payload: The event data as a dictionary.
        """
        pass
