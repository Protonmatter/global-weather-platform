from abc import ABC, abstractmethod

from weather_platform.domain.models import Observation


class ObservationAdapter(ABC):
    """Contract for source-specific decoders."""

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Stable decoder identity including a semantic version."""

    @abstractmethod
    def decode(self, payload: bytes) -> list[Observation]:
        """Decode one immutable source record into zero or more canonical observations."""
