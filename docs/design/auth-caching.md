# Implementation Plan: Authentication Caching with Automated MFA

## Overview

Add automated authentication caching using GCP Secret Manager and Gmail API-based MFA code extraction to eliminate manual MFA prompts during regular operations.

## Key Design Decisions

### 1. Secret Manager for Authentication Storage
- **Why**: Purpose-built for secrets with encryption, IAM integration, versioning, and audit logging
- **What we'll store**: Username, password, session cookies, login timestamp
- **Session strategy**: Cache session cookies (8-hour expiry) to minimize re-authentication

### 2. Gmail API for Automated MFA
- **Strategy**: Search for recent MFA emails from REMS, extract 6-digit code via regex
- **Retry logic**: Exponential backoff up to 60 seconds for email delivery delays
- **Email cleanup**: Mark emails as read after successful extraction (maintains audit trail)
- **Fallback**: If Gmail API fails, fall back to interactive prompt

### 3. Command Structure
- **Remove**: `login` command (breaking change for clearer intent)
- **Add**: `setup-auth` command (explicit authentication caching)
- **Default behavior**: Automatically use cached auth when available
- **Override**: Add `--skip-cache` flag to all commands for local testing

### 4. Graceful Fallback Strategy
```
1. Try cached session cookies
2. If expired, re-authenticate with cached username/password + Gmail MFA
3. If Gmail fails, use cached username/password + interactive MFA
4. If no cache, use environment variables/prompts
```

## Implementation Steps

### Phase 1: Infrastructure Setup

**File: `terraform/main.tf`**
- Enable Secret Manager API
- Enable Gmail API
- Grant `roles/secretmanager.admin` to service account
- Create `rems-auth` secret resource with IAM bindings

**File: `requirements.txt`**
- Add `google-cloud-secret-manager==2.22.0`
- Add `google-api-python-client==2.169.0`
- Add `google-auth-httplib2==0.2.1`

### Phase 2: Core Modules

**NEW FILE: `src/gmail_mfa.py`**

Key functions:
```python
def get_gmail_service() -> Resource
def extract_mfa_code_from_email(max_wait_seconds=60) -> Optional[str]
def parse_mfa_code_from_message(message: dict) -> Optional[str]
```

Features:
- Initialize Gmail API client using ADC (user credentials)
- Search for MFA emails: `from:noreply@sportsmanager.ie subject:"verification code" is:unread newer_than:5m`
- Extract 6-digit code using regex
- Retry with exponential backoff (up to 60 seconds)
- Mark email as read after successful extraction
- Return None on failure (triggers fallback)

**NEW FILE: `src/auth_manager.py`**

Key functions:
```python
def get_secret_manager_client() -> SecretManagerServiceClient
def store_auth(username, password, session, project_id, secret_id="rems-auth") -> None
def load_auth(project_id, secret_id="rems-auth") -> Optional[dict]
def restore_session(auth_data: dict) -> requests.Session
def is_session_expired(auth_data: dict, expiry_hours=8) -> bool
```

Auth data structure (JSON):
```json
{
  "username": "user@example.com",
  "password": "encrypted_password",
  "session_cookies": {"cookie_name": "cookie_value", ...},
  "last_login": "2026-01-19T10:30:00Z",
  "session_expiry_hours": 8
}
```

### Phase 3: Update REMSClient

**File: `src/rems_client.py`**

Add methods:
```python
def restore_from_cache(self, auth_data: dict) -> bool
def is_session_valid(self) -> bool
def login_with_gmail_mfa(self, gmail_mfa_extractor) -> bool
```

Update `__init__`:
- Add `use_cached_auth` parameter
- Add `project_id` parameter

### Phase 4: Update CLI Commands

**File: `src/main.py`**

Changes:
1. Remove `login` command completely, add `setup-auth` command
2. Add helper function `get_authenticated_client()` for auth loading logic
3. Add to all REMS commands:
   - `--skip-cache` flag
   - `--use-gmail-mfa` flag
   - `--project-id` parameter (optional, can use `GCP_PROJECT_ID` env var)
4. Make username/password optional (can come from cache)

New `setup-auth` command:
```python
@cli.command()
@click.option('--username', envvar='REMS_USERNAME', required=True)
@click.option('--password', envvar='REMS_PASSWORD', hide_input=True, required=True)
@click.option('--project-id', envvar='GCP_PROJECT_ID')
@click.option('--use-gmail-mfa/--no-gmail-mfa', default=False)
def setup_auth(username, password, project_id, use_gmail_mfa):
    """Sets up and caches REMS authentication in GCP Secret Manager."""
```

Updated command pattern (example: `refresh-members`):
- Add `--skip-cache`, `--use-gmail-mfa`, `--project-id` options
- Make `--username` and `--password` optional (not required if cache available)
- Call `get_authenticated_client()` helper instead of creating REMSClient directly

### Phase 5: Testing

**NEW FILE: `tests/test_gmail_mfa.py`**
- Test MFA code extraction (mock Gmail API)
- Test email not found (should return None)
- Test timeout scenario
- Test various email formats (regex validation)
- Test Gmail API auth failure

**NEW FILE: `tests/test_auth_manager.py`**
- Test store/load auth (mock Secret Manager)
- Test secret not found (should return None)
- Test session restoration
- Test expiry checking
- Test corrupted JSON handling

**UPDATE: `tests/test_rems_client.py`**
- Test `restore_from_cache()`
- Test `is_session_valid()`
- Test Gmail MFA integration
- Test fallback to interactive MFA

**UPDATE: `tests/test_main.py`**
- Test `setup-auth` command
- Test commands with cache hit/miss
- Test `--skip-cache` flag
- Test expired session handling

### Phase 6: Documentation

**File: `README.md`**

Add sections:
1. **Gmail API Setup** (new section before "Usage")
   - Enable Gmail API steps
   - OAuth consent screen setup
   - Service account vs user authentication
   - Two options: user credentials (recommended) or service account with domain-wide delegation

2. **Authentication Caching** (new section in "Usage")
   - How to set up: `setup-auth` command
   - How caching works
   - How to skip cache: `--skip-cache` flag
   - How to use Gmail MFA: `--use-gmail-mfa` flag
   - Session expiry (8 hours)
   - Migration note: `login` command has been removed, use `setup-auth` instead

3. **Environment Variables** (update existing or add new)
   - `GCP_PROJECT_ID`: GCP project ID for Secret Manager

Example usage patterns:
```bash
# Initial setup with Gmail MFA
python -m src.main setup-auth --username <user> --password <pass> --project-id <project> --use-gmail-mfa

# Use cached auth (no MFA prompt)
python -m src.main refresh-members --season 2025 --output csv --output-file members.csv --project-id <project>

# Skip cache for testing
python -m src.main refresh-members --skip-cache --username <user> --password <pass> --season 2025 --output csv --output-file members.csv
```

**File: `CONTRIBUTING.md`**

Add note about testing with external services:
- Use mocks for GCP services
- Never use real credentials in tests
- Test both success and failure scenarios
- Test fallback behavior

## Critical Files

Files that will be created or modified:
- `terraform/main.tf` - Add Secret Manager, Gmail API, IAM roles
- `requirements.txt` - Add GCP dependencies
- `src/gmail_mfa.py` - NEW: Gmail MFA extraction
- `src/auth_manager.py` - NEW: Secret Manager integration
- `src/rems_client.py` - Add cache restoration methods
- `src/main.py` - Remove login command, add setup-auth, add cache support to all commands
- `tests/test_gmail_mfa.py` - NEW: Test Gmail MFA
- `tests/test_auth_manager.py` - NEW: Test auth manager
- `tests/test_rems_client.py` - UPDATE: Test cache methods
- `tests/test_main.py` - UPDATE: Test CLI with cache
- `README.md` - Document Gmail setup and caching

## Security Considerations

1. **Never log auth data or session cookies**
2. **Use Secret Manager's automatic encryption**
3. **Limit IAM access to service account only**
4. **Use least-privilege OAuth scopes** (gmail.readonly)
5. **Implement session validation before use**
6. **8-hour session expiry (balances security and UX)**
7. **Generic error messages** (no auth details)

## Verification

End-to-end test scenarios:
1. Run `setup-auth` with interactive MFA → auth stored
2. Run `setup-auth` with Gmail MFA → auth stored
3. Run command with cached auth → no MFA prompt (cache hit)
4. Run command with `--skip-cache` → MFA prompt required
5. Run command with expired session → auto re-auth with cached auth
6. Run command with invalid cache → graceful failure with helpful error
7. Gmail API fails → falls back to interactive MFA prompt
8. All unit tests pass
9. Code coverage >80% on new modules

## User Preferences (Confirmed)

1. **Gmail API Authentication**: Use user credentials via `gcloud auth application-default login`
   - Simpler setup without requiring G Suite admin permissions
   - Document this approach in README

2. **MFA Email Handling**: Mark emails as read after extracting code
   - Maintains audit trail in mailbox
   - User can verify which codes were used
   - Keeps inbox organized (unread = unused codes)

3. **Session Expiry**: 8 hours (user preference)
   - Balance between security and user experience
   - Use as default in `is_session_expired()` function

4. **Command Changes**: Remove `login` command completely
   - Breaking change but clearer intent
   - Only use `setup-auth` going forward
   - Document migration in README

5. **Error Handling**: When cached auth fails, provide clear error message directing user to run `setup-auth`
