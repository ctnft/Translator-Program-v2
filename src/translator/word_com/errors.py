class WordComError(RuntimeError):
    pass


class UnsupportedPlatformError(WordComError):
    pass


class WordNotRunningError(WordComError):
    pass


class NoActiveDocumentError(WordComError):
    pass


class UnsavedDocumentError(WordComError):
    pass


class UnsafeOutputPathError(WordComError):
    pass
