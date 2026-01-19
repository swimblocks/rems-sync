"""Tests for authentication manager."""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
import requests
from src.auth_manager import (
    get_secret_manager_client,
    store_auth,
    load_auth,
    restore_session,
    is_session_expired,
    AuthManagerError
)


@pytest.fixture
def mock_secret_manager_client():
    """Fixture for mocked Secret Manager client."""
    client = Mock()
    return client


@pytest.fixture
def sample_auth_data():
    """Fixture for sample auth data."""
    return {
        "username": "test@example.com",
        "password": "test_password",
        "session_cookies": {
            "session_id": "abc123",
            "token": "xyz789"
        },
        "last_login": datetime.now(timezone.utc).isoformat(),
        "session_expiry_hours": 8
    }


@pytest.fixture
def expired_auth_data():
    """Fixture for expired auth data."""
    expired_time = datetime.now(timezone.utc) - timedelta(hours=10)
    return {
        "username": "test@example.com",
        "password": "test_password",
        "session_cookies": {},
        "last_login": expired_time.isoformat(),
        "session_expiry_hours": 8
    }


@pytest.fixture
def mock_session():
    """Fixture for mocked requests.Session."""
    session = requests.Session()
    session.cookies.set("session_id", "abc123")
    session.cookies.set("token", "xyz789")
    return session


def test_get_secret_manager_client_success():
    """Test successful Secret Manager client creation."""
    with patch('google.auth.default') as mock_default, \
         patch('src.auth_manager.secretmanager.SecretManagerServiceClient') as mock_client_class:
        mock_creds = Mock()
        mock_default.return_value = (mock_creds, 'project')
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        client = get_secret_manager_client()

        assert client == mock_client
        mock_client_class.assert_called_once_with(credentials=mock_creds)


def test_get_secret_manager_client_failure():
    """Test Secret Manager client creation failure."""
    with patch('google.auth.default', side_effect=Exception("Auth failed")):
        with pytest.raises(AuthManagerError, match="Failed to authenticate with Secret Manager"):
            get_secret_manager_client()


def test_store_auth_success(mock_secret_manager_client, mock_session):
    """Test successful auth data storage."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_response = Mock()
        mock_response.name = "projects/test/secrets/rems-auth/versions/1"
        mock_secret_manager_client.add_secret_version.return_value = mock_response

        store_auth("test_user", "test_pass", mock_session, "test_project")

        # Verify add_secret_version was called
        mock_secret_manager_client.add_secret_version.assert_called_once()

        # Verify the payload structure
        call_args = mock_secret_manager_client.add_secret_version.call_args
        payload = json.loads(call_args[1]['request']['payload']['data'])

        assert payload['username'] == "test_user"
        assert payload['password'] == "test_pass"
        assert 'session_cookies' in payload
        assert payload['session_cookies']['session_id'] == "abc123"
        assert payload['session_cookies']['token'] == "xyz789"
        assert 'last_login' in payload
        assert payload['session_expiry_hours'] == 8


def test_store_auth_failure(mock_secret_manager_client, mock_session):
    """Test auth data storage failure."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_secret_manager_client.add_secret_version.side_effect = Exception("Storage failed")

        with pytest.raises(AuthManagerError, match="Failed to store auth data"):
            store_auth("test_user", "test_pass", mock_session, "test_project")


def test_load_auth_success(mock_secret_manager_client, sample_auth_data):
    """Test successful auth data loading."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        # Mock response with encoded payload
        mock_response = Mock()
        mock_response.payload.data = json.dumps(sample_auth_data).encode('utf-8')
        mock_secret_manager_client.access_secret_version.return_value = mock_response

        auth_data = load_auth("test_project")

        assert auth_data['username'] == sample_auth_data['username']
        assert auth_data['password'] == sample_auth_data['password']
        assert auth_data['session_cookies'] == sample_auth_data['session_cookies']
        assert auth_data['last_login'] == sample_auth_data['last_login']


def test_load_auth_not_found(mock_secret_manager_client):
    """Test loading auth when secret doesn't exist."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_secret_manager_client.access_secret_version.side_effect = Exception("Secret not found")

        auth_data = load_auth("test_project")

        assert auth_data is None


def test_load_auth_does_not_exist(mock_secret_manager_client):
    """Test loading auth when secret does not exist."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_secret_manager_client.access_secret_version.side_effect = Exception("Resource does not exist")

        auth_data = load_auth("test_project")

        assert auth_data is None


def test_load_auth_other_error(mock_secret_manager_client):
    """Test loading auth with non-not-found error."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_secret_manager_client.access_secret_version.side_effect = Exception("Permission denied")

        with pytest.raises(AuthManagerError, match="Failed to load auth data"):
            load_auth("test_project")


def test_load_auth_corrupted_json(mock_secret_manager_client):
    """Test loading auth with corrupted JSON data."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_response = Mock()
        mock_response.payload.data = b'not valid json'
        mock_secret_manager_client.access_secret_version.return_value = mock_response

        with pytest.raises(AuthManagerError, match="Failed to load auth data"):
            load_auth("test_project")


def test_restore_session(sample_auth_data):
    """Test session restoration from auth data."""
    session = restore_session(sample_auth_data)

    assert isinstance(session, requests.Session)
    assert session.cookies.get('session_id') == "abc123"
    assert session.cookies.get('token') == "xyz789"


def test_restore_session_empty_cookies():
    """Test session restoration with no cookies."""
    auth_data = {
        "session_cookies": {}
    }

    session = restore_session(auth_data)

    assert isinstance(session, requests.Session)
    assert len(session.cookies) == 0


def test_restore_session_missing_cookies_key():
    """Test session restoration when session_cookies key is missing."""
    auth_data = {}

    session = restore_session(auth_data)

    assert isinstance(session, requests.Session)
    assert len(session.cookies) == 0


def test_is_session_expired_false(sample_auth_data):
    """Test session expiry check for valid session."""
    expired = is_session_expired(sample_auth_data, expiry_hours=8)

    assert expired is False


def test_is_session_expired_true(expired_auth_data):
    """Test session expiry check for expired session."""
    expired = is_session_expired(expired_auth_data, expiry_hours=8)

    assert expired is True


def test_is_session_expired_exact_boundary():
    """Test session expiry at exact boundary."""
    # Session created exactly 8 hours ago
    exact_time = datetime.now(timezone.utc) - timedelta(hours=8)
    auth_data = {
        "last_login": exact_time.isoformat()
    }

    expired = is_session_expired(auth_data, expiry_hours=8)

    assert expired is True


def test_is_session_expired_no_last_login():
    """Test session expiry when last_login is missing."""
    auth_data = {}

    expired = is_session_expired(auth_data)

    assert expired is True


def test_is_session_expired_invalid_timestamp():
    """Test session expiry with invalid timestamp."""
    auth_data = {
        "last_login": "invalid timestamp"
    }

    expired = is_session_expired(auth_data)

    assert expired is True


def test_is_session_expired_custom_expiry_hours():
    """Test session expiry with custom expiry hours."""
    # Session created 6 hours ago
    recent_time = datetime.now(timezone.utc) - timedelta(hours=6)
    auth_data = {
        "last_login": recent_time.isoformat()
    }

    # Should not be expired with 8 hour expiry
    assert is_session_expired(auth_data, expiry_hours=8) is False

    # Should be expired with 4 hour expiry
    assert is_session_expired(auth_data, expiry_hours=4) is True


def test_is_session_expired_naive_datetime():
    """Test session expiry with naive datetime (no timezone)."""
    # Create naive datetime
    naive_time = datetime.now() - timedelta(hours=10)
    auth_data = {
        "last_login": naive_time.isoformat()
    }

    # Should handle naive datetime and assume it's expired
    expired = is_session_expired(auth_data, expiry_hours=8)

    assert expired is True


def test_store_auth_custom_secret_id(mock_secret_manager_client, mock_session):
    """Test storing auth with custom secret ID."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_response = Mock()
        mock_response.name = "projects/test/secrets/custom-secret/versions/1"
        mock_secret_manager_client.add_secret_version.return_value = mock_response

        store_auth("test_user", "test_pass", mock_session, "test_project", secret_id="custom-secret")

        # Verify the parent path includes custom secret ID
        call_args = mock_secret_manager_client.add_secret_version.call_args
        parent = call_args[1]['request']['parent']
        assert "custom-secret" in parent


def test_load_auth_custom_secret_id(mock_secret_manager_client, sample_auth_data):
    """Test loading auth with custom secret ID."""
    with patch('src.auth_manager.get_secret_manager_client', return_value=mock_secret_manager_client):
        mock_response = Mock()
        mock_response.payload.data = json.dumps(sample_auth_data).encode('utf-8')
        mock_secret_manager_client.access_secret_version.return_value = mock_response

        auth_data = load_auth("test_project", secret_id="custom-secret")

        # Verify the secret name includes custom secret ID
        call_args = mock_secret_manager_client.access_secret_version.call_args
        name = call_args[1]['request']['name']
        assert "custom-secret" in name
