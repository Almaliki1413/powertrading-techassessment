"""Typed domain errors. The API maps these; application code must not swallow them."""

from __future__ import annotations


class DomainError(Exception):
    code: str = "DOMAIN_ERROR"
    http_status: int = 400

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.blocking = True


class InvalidDateRange(DomainError):
    code = "INVALID_DATE_RANGE"
    http_status = 400


class ArchiveNotFound(DomainError):
    code = "ARCHIVE_NOT_FOUND"
    http_status = 404


class HashMismatch(DomainError):
    code = "HASH_MISMATCH"
    http_status = 409


class UnsafeArchive(DomainError):
    code = "UNSAFE_ARCHIVE"
    http_status = 422


class UnsupportedSchema(DomainError):
    code = "UNSUPPORTED_SCHEMA"
    http_status = 422


class InvalidRrp(DomainError):
    code = "INVALID_RRP"
    http_status = 422


class AmbiguousRevision(DomainError):
    code = "AMBIGUOUS_REVISION"
    http_status = 409


class IncompleteIntervalSet(DomainError):
    code = "INCOMPLETE_INTERVAL_SET"
    http_status = 409


class MarketDataNotFirm(DomainError):
    code = "MARKET_DATA_NOT_FIRM"
    http_status = 409


class InvalidConfiguration(DomainError):
    code = "INVALID_CONFIGURATION"
    http_status = 400


class SolverBusy(DomainError):
    code = "SOLVER_BUSY"
    http_status = 503


class SolverUnavailable(DomainError):
    code = "SOLVER_UNAVAILABLE"
    http_status = 503


class SolverFailed(DomainError):
    code = "SOLVER_FAILED"
    http_status = 503


class PostSolveVerificationFailed(DomainError):
    code = "POST_SOLVE_VERIFICATION_FAILED"
    http_status = 500
