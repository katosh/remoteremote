"""
Warning Token Service

Generates and validates secure time-limited tokens for TV shutdown warning pages.
"""
import hmac
import hashlib
import time
import json
import base64
from flask import current_app


def generate_warning_token(schedule_id: int, expires_in_seconds: int = 120) -> str:
    """
    Generate a secure token for accessing the shutdown warning page.

    Args:
        schedule_id: The schedule ID that triggered the warning
        expires_in_seconds: Token validity duration (default: 120 seconds)

    Returns:
        URL-safe token string
    """
    secret = current_app.config['SECRET_KEY']
    expires_at = int(time.time()) + expires_in_seconds

    # Create payload
    payload = {
        'schedule_id': schedule_id,
        'expires_at': expires_at,
        'created_at': int(time.time())
    }

    # Encode payload
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

    # Create signature
    signature = hmac.new(
        secret.encode(),
        payload_b64.encode(),
        hashlib.sha256
    ).hexdigest()[:32]  # Use first 32 chars for shorter URL

    # Token format: payload.signature
    return f"{payload_b64}.{signature}"


def validate_warning_token(token: str) -> dict | None:
    """
    Validate a warning token and return payload if valid.

    Args:
        token: The token string to validate

    Returns:
        Payload dict with 'schedule_id', 'expires_at', 'created_at' if valid, None otherwise
    """
    try:
        secret = current_app.config['SECRET_KEY']

        # Split token
        parts = token.split('.')
        if len(parts) != 2:
            return None

        payload_b64, signature = parts

        # Verify signature
        expected_signature = hmac.new(
            secret.encode(),
            payload_b64.encode(),
            hashlib.sha256
        ).hexdigest()[:32]

        if not hmac.compare_digest(signature, expected_signature):
            return None

        # Decode payload
        payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        payload = json.loads(payload_json)

        # Check expiration
        if payload.get('expires_at', 0) < time.time():
            return None

        return payload

    except Exception:
        return None


# Store for cancelled shutdowns (in-memory, keyed by schedule_id)
# Format: {schedule_id: {'cancelled_at': timestamp, 'token': token}}
_cancelled_shutdowns = {}


def cancel_shutdown(schedule_id: int, token: str) -> bool:
    """
    Mark a shutdown as cancelled. Called when user clicks cancel on warning page.

    Args:
        schedule_id: The schedule ID to cancel
        token: The token used to cancel (for verification)

    Returns:
        True if cancellation recorded successfully
    """
    _cancelled_shutdowns[schedule_id] = {
        'cancelled_at': time.time(),
        'token': token
    }
    return True


def is_shutdown_cancelled(schedule_id: int) -> bool:
    """
    Check if a shutdown was recently cancelled.
    Cancellations expire after 5 minutes to avoid stale data.

    Args:
        schedule_id: The schedule ID to check

    Returns:
        True if shutdown was cancelled recently
    """
    cancellation = _cancelled_shutdowns.get(schedule_id)
    if not cancellation:
        return False

    # Cancellations expire after 5 minutes
    if time.time() - cancellation['cancelled_at'] > 300:
        del _cancelled_shutdowns[schedule_id]
        return False

    return True


def clear_cancellation(schedule_id: int) -> None:
    """
    Clear a cancellation record (called after shutdown is executed or skipped).

    Args:
        schedule_id: The schedule ID to clear
    """
    _cancelled_shutdowns.pop(schedule_id, None)
