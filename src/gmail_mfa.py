"""Gmail API integration for automated MFA code extraction."""
import re
import time
import base64
from typing import Optional, Any, Tuple
from googleapiclient.discovery import build, Resource
from google.auth.credentials import Credentials
import click


class GmailMFAError(Exception):
    """Raised when Gmail MFA extraction fails."""
    pass


def get_gmail_service() -> Resource:
    """
    Returns an authenticated Gmail API service using Application Default Credentials.

    Returns:
        Resource: Authenticated Gmail API service.

    Raises:
        GmailMFAError: If authentication fails.
    """
    try:
        from google.auth import default
        scopes = ['https://www.googleapis.com/auth/gmail.readonly',
                  'https://www.googleapis.com/auth/gmail.modify']
        creds, _ = default(scopes=scopes)
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        raise GmailMFAError(f"Failed to authenticate with Gmail API: {e}") from e


def parse_mfa_code_from_message(message: dict[str, Any]) -> Optional[str]:
    """
    Extracts 6-digit MFA code from email message using regex.

    Args:
        message: Gmail API message object.

    Returns:
        str: 6-digit MFA code if found, None otherwise.
    """
    try:
        # Get message payload
        payload = message.get('payload', {})

        # Try to get body from different possible locations
        body = ''
        if 'body' in payload and 'data' in payload['body']:
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
                elif part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                    # Fallback to HTML if no plain text
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')

        # Extract 6-digit code using regex
        # Look for patterns like "123456", "code: 123456", "verification code: 123456"
        patterns = [
            r'\b(\d{6})\b',  # Simple 6-digit number
            r'code[:\s]+(\d{6})',  # "code: 123456" or "code 123456"
            r'verification[:\s]+code[:\s]+(\d{6})',  # "verification code: 123456"
        ]

        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1) if 'verification' in pattern or 'code' in pattern else match.group(0)

        return None
    except Exception as e:
        click.echo(f"Error parsing MFA code from message: {e}", err=True)
        return None


def extract_mfa_code_from_email(max_wait_seconds: int = 60) -> Optional[str]:
    """
    Searches Gmail for recent MFA code email from REMS.

    Implements retry with exponential backoff up to max_wait_seconds.
    Marks email as read after successful extraction.

    Args:
        max_wait_seconds: Maximum seconds to wait for email (default: 60).

    Returns:
        str: 6-digit MFA code if found, None otherwise.

    Raises:
        GmailMFAError: If Gmail API is not accessible.
    """
    try:
        service = get_gmail_service()
    except GmailMFAError:
        raise

    # Query for MFA emails
    query = 'from:noreply@sportsmanager.ie subject:"verification code" is:unread newer_than:5m'

    start_time = time.time()
    wait_time = 2  # Start with 2 seconds

    while time.time() - start_time < max_wait_seconds:
        try:
            # Search for messages
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=1
            ).execute()

            messages = results.get('messages', [])

            if messages:
                # Get the full message
                message = service.users().messages().get(
                    userId='me',
                    id=messages[0]['id'],
                    format='full'
                ).execute()

                # Extract MFA code
                mfa_code = parse_mfa_code_from_message(message)

                if mfa_code:
                    # Mark email as read
                    service.users().messages().modify(
                        userId='me',
                        id=messages[0]['id'],
                        body={'removeLabelIds': ['UNREAD']}
                    ).execute()

                    return mfa_code

            # Wait before retrying (exponential backoff)
            if time.time() - start_time + wait_time < max_wait_seconds:
                click.echo(f"Waiting for MFA email... ({int(time.time() - start_time)}s elapsed)")
                time.sleep(wait_time)
                wait_time = min(wait_time * 1.5, 10)  # Max 10 seconds between retries
            else:
                break

        except Exception as e:
            click.echo(f"Error searching for MFA email: {e}", err=True)
            break

    # Timeout or error
    return None


def get_mfa_code_gmail() -> Optional[str]:
    """
    Convenience function to extract MFA code from Gmail.
    Falls back to None if extraction fails (caller should handle fallback).

    Returns:
        str: 6-digit MFA code if found, None otherwise.
    """
    try:
        code = extract_mfa_code_from_email()
        if code:
            click.echo("MFA code extracted from Gmail")
            return code
        else:
            click.echo("Failed to extract MFA code from Gmail", err=True)
            return None
    except GmailMFAError as e:
        click.echo(f"Gmail MFA error: {e}", err=True)
        return None
