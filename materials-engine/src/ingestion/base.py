"""Base class for all material database ingestors."""

import logging
import time
from abc import ABC, abstractmethod
from typing import List, Optional

log = logging.getLogger(__name__)


class IngestionError(Exception):
    """Raised on non-transient ingestion failures."""


class BaseIngestor(ABC):
    """Interface for ingesting materials from external databases.

    All ingestors implement rate limiting, retry with backoff,
    configurable timeout, and structured logging.
    """

    def __init__(self, rate_limit: float = 5.0, timeout: float = 30.0,
                 max_retries: int = 3):
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request = 0.0

    def _throttle(self):
        if self.rate_limit <= 0:
            return
        elapsed = time.time() - self._last_request
        wait = (1.0 / self.rate_limit) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()

    def _retry_request(self, fn, *args, **kwargs):
        """Execute fn with retry + exponential backoff."""
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_err = e
                wait = 2 ** attempt
                log.warning("[%s] Attempt %d/%d failed: %s. Retrying in %ds...",
                            self.source_name, attempt, self.max_retries, e, wait)
                time.sleep(wait)
        log.error("[%s] All %d attempts failed. Last error: %s",
                  self.source_name, self.max_retries, last_err)
        raise IngestionError(f"{self.source_name}: {last_err}") from last_err

    @abstractmethod
    def fetch_materials(self, limit: int = 100, offset: int = 0,
                        filters: Optional[dict] = None) -> List[dict]:
        ...

    @abstractmethod
    def get_material_by_id(self, source_id: str) -> Optional[dict]:
        ...

    @abstractmethod
    def total_count(self) -> int:
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        ...
