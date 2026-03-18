"""Common package exports: pagination helpers, exceptions and constants.

This module re-exports selected names from submodules so other parts
of the application can import from `app.common`.
"""

from .database import pagination_utils
from .exceptions import (
        BaseError,
        ValidationError,
        ResourceNotFoundError,
        PermissionError,
        AuthenticationError,
        DatabaseError,
        RateLimitError,
)
from .constants import (
        PAGE_SIZE,
        MAX_PAGE_SIZE,
        NOTIFICATION_TYPES,
        RESOURCE_TYPES,
        USER_ROLES,
        REGEX_PHONE,
        REGEX_EMAIL,
        REGEX_USERNAME,
        REGEX_PASSWORD,
        CONTENT_MIN_LENGTH,
        CONTENT_MAX_LENGTH,
        USERNAME_MIN_LENGTH,
        USERNAME_MAX_LENGTH,
        PASSWORD_MIN_LENGTH,
        PASSWORD_MAX_LENGTH,
        JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
        JWT_REFRESH_TOKEN_EXPIRES_DAYS,
        CACHE_KEY_USER,
        CACHE_KEY_POST,
        CACHE_KEY_NOTIFICATION_UNREAD_COUNT,
        STATUS_SUCCESS,
        STATUS_ERROR,
        STATUS_VALIDATION_ERROR,
        STATUS_NOT_FOUND,
        STATUS_PERMISSION_DENIED,
        STATUS_UNAUTHORIZED,
)

__all__ = [
        # pagination
        "pagination_utils",
        # exceptions
        "BaseError",
        "ValidationError",
        "ResourceNotFoundError",
        "PermissionError",
        "AuthenticationError",
        "DatabaseError",
        "RateLimitError",
        # constants
        "PAGE_SIZE",
        "MAX_PAGE_SIZE",
        "NOTIFICATION_TYPES",
        "RESOURCE_TYPES",
        "USER_ROLES",
        "REGEX_PHONE",
        "REGEX_EMAIL",
        "REGEX_USERNAME",
        "REGEX_PASSWORD",
        "CONTENT_MIN_LENGTH",
        "CONTENT_MAX_LENGTH",
        "USERNAME_MIN_LENGTH",
        "USERNAME_MAX_LENGTH",
        "PASSWORD_MIN_LENGTH",
        "PASSWORD_MAX_LENGTH",
        "JWT_ACCESS_TOKEN_EXPIRES_MINUTES",
        "JWT_REFRESH_TOKEN_EXPIRES_DAYS",
        "CACHE_KEY_USER",
        "CACHE_KEY_POST",
        "CACHE_KEY_NOTIFICATION_UNREAD_COUNT",
        "STATUS_SUCCESS",
        "STATUS_ERROR",
        "STATUS_VALIDATION_ERROR",
        "STATUS_NOT_FOUND",
        "STATUS_PERMISSION_DENIED",
        "STATUS_UNAUTHORIZED",
]

