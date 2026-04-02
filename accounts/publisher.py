import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class EventPublisher():

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        print(event_type, payload)
        pass
