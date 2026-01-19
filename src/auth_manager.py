"""Authentication caching using GCP Secret Manager."""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, cast
import requests
from google.cloud import secretmanager
from google.auth.credentials import Credentials
import click


class AuthManagerError(Exception):
    """Raised when auth management operations fail."""
    pass


def get_secret_manager_client() -> secretmanager.SecretManagerServiceClient:
    """
    Returns an authenticated Secret Manager client using Application Default Credentials.

    Returns:
        SecretManagerServiceClient: Authenticated Secret Manager client.

    Raises:
        AuthManagerError: If authentication fails.
    """
    try:
        from google.auth import default
        creds, _ = default()
        # Cast to Credentials to satisfy type checker
        creds = cast(Credentials, creds)
        client = secretmanager.SecretManagerServiceClient(credentials=creds)
        return client
    except Exception as e:
        raise AuthManagerError(f"Failed to authenticate with Secret Manager: {e}") from e


def store_auth(username: str, password: str, session: requests.Session,
               project_id: str, secret_id: str = "rems-auth") -> None:
    """
    Stores REMS authentication data and session cookies in Secret Manager.

    Creates a new version of the secret with the current auth data.

    Args:
        username: REMS username.
        password: REMS password.
        session: Authenticated requests.Session object.
        project_id: GCP project ID.
        secret_id: Secret ID in Secret Manager (default: "rems-auth").

    Raises:
        AuthManagerError: If storing auth data fails.
    """
    try:
        client = get_secret_manager_client()

        # Serialize session cookies
        session_cookies: dict[str, str] = {}
        for cookie in session.cookies:
            if cookie.value is not None:
                session_cookies[cookie.name] = cookie.value

        # Create auth data structure
        auth_data: dict[str, Any] = {
            "username": username,
            "password": password,
            "session_cookies": session_cookies,
            "last_login": datetime.now(timezone.utc).isoformat(),
            "session_expiry_hours": 8
        }

        # Serialize to JSON
        payload = json.dumps(auth_data).encode('utf-8')

        # Build the secret name
        parent = f"projects/{project_id}/secrets/{secret_id}"

        # Add secret version
        response = client.add_secret_version(
            request={
                "parent": parent,
                "payload": {"data": payload}
            }
        )

        click.echo(f"Auth data stored in Secret Manager: {response.name}")

    except Exception as e:
        raise AuthManagerError(f"Failed to store auth data: {e}")


def load_auth(project_id: str, secret_id: str = "rems-auth") -> Optional[dict[str, Any]]:
    """
    Loads authentication data from Secret Manager.

    Args:
        project_id: GCP project ID.
        secret_id: Secret ID in Secret Manager (default: "rems-auth").

    Returns:
        dict: Auth data with username, password, session_cookies, last_login, or None if not found.

    Raises:
        AuthManagerError: If loading auth data fails (except for not found).
    """
    try:
        client = get_secret_manager_client()

        # Build the secret version name (latest)
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"

        # Access the secret version
        response = client.access_secret_version(request={"name": name})

        # Deserialize payload
        payload = response.payload.data.decode('utf-8')
        auth_data: dict[str, Any] = json.loads(payload)

        return auth_data

    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
            # Secret doesn't exist yet, return None
            return None
        else:
            raise AuthManagerError(f"Failed to load auth data: {e}")


def restore_session(auth_data: dict[str, Any]) -> requests.Session:
    """
    Creates a requests.Session and restores cookies from auth data.

    Args:
        auth_data: Auth data dictionary with session_cookies.

    Returns:
        requests.Session: Session with restored cookies.
    """
    session = requests.Session()

    # Restore cookies
    session_cookies = auth_data.get('session_cookies', {})
    for name, value in session_cookies.items():
        session.cookies.set(name, value)

    return session


def is_session_expired(auth_data: dict[str, Any], expiry_hours: int = 8) -> bool:
    """
    Checks if session has expired based on last_login timestamp.

    Args:
        auth_data: Auth data dictionary with last_login timestamp.
        expiry_hours: Hours until session expires (default: 8).

    Returns:
        bool: True if session is expired, False otherwise.
    """
    try:
        last_login_str = auth_data.get('last_login')
        if not last_login_str:
            return True

        # Parse last login timestamp
        last_login = datetime.fromisoformat(last_login_str)

        # Make timezone-aware if needed
        if last_login.tzinfo is None:
            last_login = last_login.replace(tzinfo=timezone.utc)

        # Check if expired
        now = datetime.now(timezone.utc)
        expiry_time = last_login + timedelta(hours=expiry_hours)

        return now >= expiry_time

    except Exception as e:
        click.echo(f"Error checking session expiry: {e}", err=True)
        # Assume expired on error
        return True
