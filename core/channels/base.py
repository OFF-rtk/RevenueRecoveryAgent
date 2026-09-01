"""
core/channels/base.py
────────────────────
Base interface for recovery channels.
"""
import abc

class BaseChannel(abc.ABC):
    @abc.abstractmethod
    async def send(self, to: str, message: str) -> dict:
        """
        Send a text message to the specified destination.
        Returns a dictionary containing provider response details.
        """
        pass

    @abc.abstractmethod
    async def send_template(self, to: str, template_name: str, parameters: list[str]) -> dict:
        """
        Send a pre-approved template message with parameters.
        Returns a dictionary containing provider response details.
        """
        pass
