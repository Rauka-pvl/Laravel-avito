"""Custom exceptions for Trast Parser V2"""


class TrastParserException(Exception):
    """Base exception for all parser errors"""
    pass


class ProxyException(TrastParserException):
    """Exception related to proxy operations"""
    pass


class ProxyValidationError(ProxyException):
    """Proxy validation failed"""
    pass


class ProxyConnectionError(ProxyException):
    """Failed to connect through proxy"""
    pass


class BrowserException(TrastParserException):
    """Exception related to browser/driver operations"""
    pass


class DriverCreationError(BrowserException):
    """Failed to create browser driver"""
    pass


class TabCrashedError(BrowserException):
    """Browser tab crashed"""
    pass


class PageException(TrastParserException):
    """Exception related to page operations"""
    pass


class PageBlockedError(PageException):
    """Page is blocked (Cloudflare, etc.)"""
    pass


class PageEmptyError(PageException):
    """Page is empty (no products)"""
    pass


class PageLoadError(PageException):
    """Failed to load page"""
    pass


class ParsingException(TrastParserException):
    """Exception during parsing"""
    pass


class StorageException(TrastParserException):
    """Exception during data storage"""
    pass

