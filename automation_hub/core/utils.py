"""Utility functions for request handling and common operations."""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Get client IP address."""
    return request.client.host if request.client else ""


def get_user_agent(request: Request) -> str:
    """Get user agent string."""
    return (request.headers.get("user-agent") or "")[:500]
