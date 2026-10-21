class PowerPointComError(RuntimeError):
    """Base error for PowerPoint COM integration."""


class UnsupportedPlatformError(PowerPointComError):
    pass


class PowerPointNotRunningError(PowerPointComError):
    pass


class NoActivePresentationError(PowerPointComError):
    pass


class UnsavedPresentationError(PowerPointComError):
    pass


class UnsafeOutputPathError(PowerPointComError):
    pass


class TextNotFoundError(PowerPointComError):
    pass
