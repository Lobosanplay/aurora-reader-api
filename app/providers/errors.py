class ProviderError(Exception):
    """Adapter-level failure; messages may contain sensitive vendor details."""


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
