"""Application exceptions, mapped to HTTP responses by the handlers registered in main.py."""


class AppError(Exception):
    """Base application error."""

    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ServiceNotConfiguredError(AppError):
    """An external dependency is not configured (e.g. missing Databricks token)."""

    status_code = 503


class ExternalServiceError(AppError):
    """An external service (Kinesis, Databricks...) returned an error."""

    status_code = 502
