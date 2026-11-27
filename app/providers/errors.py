class ProviderError(Exception):
    """Adapter-level failure; messages may contain sensitive vendor details."""

    def __init__(self, *args: object, upstream_status_code: int | None = None) -> None:
        super().__init__(*args)
        self.upstream_status_code = (
            upstream_status_code
            if type(upstream_status_code) is int and 100 <= upstream_status_code <= 599
            else None
        )


class ProviderUnavailable(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    pass


class ProviderQuotaExceeded(ProviderError):
    pass


class ProviderTimedOut(ProviderError):
    pass


class ProviderInvalidResponse(ProviderError):
    pass


class ProviderUnsupportedLanguage(ProviderError):
    pass
