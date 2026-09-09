"""Domain errors raised by services and mapped to HTTP at the edge."""

from __future__ import annotations


class DomainError(Exception):
    """Business failure. The request session commits these so audit rows persist."""

    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
