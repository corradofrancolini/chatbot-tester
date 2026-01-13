from abc import ABC, abstractmethod

class BaseClient(ABC):
    """
    Abstract base class for external service clients.

    Ensures consistent interface for:
    - Availability checks
    - Initialization (optional)
    """

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the service is reachable/configured.

        Returns:
            True if available
        """
        pass
