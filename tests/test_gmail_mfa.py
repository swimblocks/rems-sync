"""Tests for Gmail MFA code extraction."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import base64
from src.gmail_mfa import (
    get_gmail_service,
    parse_mfa_code_from_message,
    extract_mfa_code_from_email,
    get_mfa_code_gmail,
    GmailMFAError
)


@pytest.fixture
def mock_gmail_service():
    """Fixture for mocked Gmail API service."""
    service = Mock()
    return service


@pytest.fixture
def sample_message_with_code():
    """Fixture for sample email message with MFA code."""
    body = "Your verification code is: 123456. Please enter this code to continue."
    encoded_body = base64.urlsafe_b64encode(body.encode('utf-8')).decode('utf-8')
    return {
        'id': 'msg_123',
        'payload': {
            'body': {
                'data': encoded_body
            }
        }
    }


@pytest.fixture
def sample_message_multipart():
    """Fixture for multipart email message with MFA code."""
    body = "Your REMS verification code: 987654"
    encoded_body = base64.urlsafe_b64encode(body.encode('utf-8')).decode('utf-8')
    return {
        'id': 'msg_456',
        'payload': {
            'parts': [
                {
                    'mimeType': 'text/plain',
                    'body': {
                        'data': encoded_body
                    }
                }
            ]
        }
    }


def test_get_gmail_service_success():
    """Test successful Gmail service authentication."""
    with patch('google.auth.default') as mock_default, \
         patch('src.gmail_mfa.build') as mock_build:
        mock_creds = Mock()
        mock_default.return_value = (mock_creds, 'project')
        mock_service = Mock()
        mock_build.return_value = mock_service

        service = get_gmail_service()

        assert service == mock_service
        mock_default.assert_called_once()
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)


def test_get_gmail_service_failure():
    """Test Gmail service authentication failure."""
    with patch('google.auth.default', side_effect=Exception("Auth failed")):
        with pytest.raises(GmailMFAError, match="Failed to authenticate with Gmail API"):
            get_gmail_service()


def test_parse_mfa_code_simple_format(sample_message_with_code):
    """Test parsing MFA code from simple email format."""
    code = parse_mfa_code_from_message(sample_message_with_code)
    assert code == '123456'


def test_parse_mfa_code_multipart(sample_message_multipart):
    """Test parsing MFA code from multipart email."""
    code = parse_mfa_code_from_message(sample_message_multipart)
    assert code == '987654'


def test_parse_mfa_code_various_formats():
    """Test parsing MFA codes from various email formats."""
    test_cases = [
        ("Your code is 111222", "111222"),
        ("Verification code: 333444", "333444"),
        ("Use this code 555666 to log in", "555666"),
        ("777888", "777888"),
        ("Code 999000 expires in 5 minutes", "999000"),
    ]

    for body_text, expected_code in test_cases:
        encoded_body = base64.urlsafe_b64encode(body_text.encode('utf-8')).decode('utf-8')
        message = {
            'payload': {
                'body': {'data': encoded_body}
            }
        }
        code = parse_mfa_code_from_message(message)
        assert code == expected_code, f"Failed to parse '{body_text}', expected {expected_code}, got {code}"


def test_parse_mfa_code_not_found():
    """Test parsing when no MFA code is present."""
    body = "This is a regular email with no code"
    encoded_body = base64.urlsafe_b64encode(body.encode('utf-8')).decode('utf-8')
    message = {
        'payload': {
            'body': {'data': encoded_body}
        }
    }
    code = parse_mfa_code_from_message(message)
    assert code is None


def test_parse_mfa_code_html_fallback():
    """Test parsing MFA code from HTML email when no plain text."""
    html_body = '<p>Your code: <strong>246810</strong></p>'
    encoded_body = base64.urlsafe_b64encode(html_body.encode('utf-8')).decode('utf-8')
    message = {
        'payload': {
            'parts': [
                {
                    'mimeType': 'text/html',
                    'body': {'data': encoded_body}
                }
            ]
        }
    }
    code = parse_mfa_code_from_message(message)
    assert code == '246810'


def test_extract_mfa_code_success(mock_gmail_service, sample_message_with_code):
    """Test successful MFA code extraction."""
    with patch('src.gmail_mfa.get_gmail_service', return_value=mock_gmail_service):
        # Mock messages list
        mock_gmail_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg_123'}]
        }

        # Mock message get
        mock_gmail_service.users().messages().get().execute.return_value = sample_message_with_code

        # Mock message modify (mark as read)
        mock_modify = MagicMock()
        mock_gmail_service.users().messages().modify.return_value = mock_modify

        code = extract_mfa_code_from_email(max_wait_seconds=5)

        assert code == '123456'
        # Verify email was marked as read
        mock_gmail_service.users().messages().modify.assert_called_once()


def test_extract_mfa_code_not_found(mock_gmail_service):
    """Test MFA code extraction when no email found."""
    with patch('src.gmail_mfa.get_gmail_service', return_value=mock_gmail_service):
        # Mock empty messages list
        mock_gmail_service.users().messages().list().execute.return_value = {
            'messages': []
        }

        code = extract_mfa_code_from_email(max_wait_seconds=2)

        assert code is None


def test_extract_mfa_code_timeout(mock_gmail_service):
    """Test MFA code extraction timeout scenario."""
    with patch('src.gmail_mfa.get_gmail_service', return_value=mock_gmail_service), \
         patch('src.gmail_mfa.time.sleep'):  # Mock sleep to speed up test
        # Always return empty messages
        mock_gmail_service.users().messages().list().execute.return_value = {
            'messages': []
        }

        code = extract_mfa_code_from_email(max_wait_seconds=3)

        assert code is None


def test_extract_mfa_code_gmail_api_error(mock_gmail_service):
    """Test MFA code extraction when Gmail API fails."""
    with patch('src.gmail_mfa.get_gmail_service', side_effect=GmailMFAError("API unavailable")):
        with pytest.raises(GmailMFAError, match="API unavailable"):
            extract_mfa_code_from_email()


def test_extract_mfa_code_search_error(mock_gmail_service):
    """Test MFA code extraction when message search fails."""
    with patch('src.gmail_mfa.get_gmail_service', return_value=mock_gmail_service):
        # Mock search failure
        mock_gmail_service.users().messages().list().execute.side_effect = Exception("Search failed")

        code = extract_mfa_code_from_email(max_wait_seconds=2)

        assert code is None


def test_get_mfa_code_gmail_success():
    """Test convenience function for successful MFA code retrieval."""
    with patch('src.gmail_mfa.extract_mfa_code_from_email', return_value='123456'):
        code = get_mfa_code_gmail()
        assert code == '123456'


def test_get_mfa_code_gmail_failure():
    """Test convenience function when extraction fails."""
    with patch('src.gmail_mfa.extract_mfa_code_from_email', return_value=None):
        code = get_mfa_code_gmail()
        assert code is None


def test_get_mfa_code_gmail_exception():
    """Test convenience function when Gmail API raises exception."""
    with patch('src.gmail_mfa.extract_mfa_code_from_email', side_effect=GmailMFAError("API error")):
        code = get_mfa_code_gmail()
        assert code is None


def test_parse_mfa_code_malformed_message():
    """Test parsing MFA code from malformed message."""
    # Empty payload
    code = parse_mfa_code_from_message({})
    assert code is None

    # Missing data
    code = parse_mfa_code_from_message({'payload': {'body': {}}})
    assert code is None
