import json
import re
from pathlib import Path
from urllib.parse import urljoin

import click
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Transport-level retry for transient errors: timeouts, rate-limits, and
# 5xx upstream errors. urllib3's Retry honours Retry-After automatically and
# implements exponential backoff so we don't have to.
_RETRY_STATUS_FORCELIST = frozenset((408, 425, 429, 500, 502, 503, 504, 509, 522, 524))


def _build_retry():
    return Retry(
        total=4,
        backoff_factor=1,  # urllib3 default 0; bumps gaps to 0s, 2s, 4s, 8s
        status_forcelist=_RETRY_STATUS_FORCELIST,
        # allowed_methods=None means "retry all methods including POST". REMS's
        # transient errors (502 from a busy backend) typically mean the request
        # never reached the app, so POST retries are safe in practice.
        allowed_methods=None,
        respect_retry_after_header=True,
        raise_on_status=False,
    )


def _default_cookie_cache_path():
    return Path.home() / ".rems-sync" / "cookies.json"


class REMSClient:
    BASE_URL = "https://swimming.canada.sportsmanager.ie"

    def __init__(self, username, password, mfa_callback, cookie_cache_path=None):
        self.username = username
        self.password = password
        self.mfa_callback = mfa_callback
        self.session = requests.Session()
        adapter = HTTPAdapter(max_retries=_build_retry())
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.cookie_cache_path = (
            Path(cookie_cache_path) if cookie_cache_path is not None
            else _default_cookie_cache_path()
        )

    def _save_cookies(self):
        try:
            self.cookie_cache_path.parent.mkdir(parents=True, exist_ok=True)
            cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
            self.cookie_cache_path.write_text(json.dumps(cookies))
            click.echo(f"Cached {len(cookies)} cookies to {self.cookie_cache_path}", err=True)
        except OSError as e:
            click.echo(f"Warning: could not save cookie cache: {e}", err=True)

    def _load_cookies(self):
        if not self.cookie_cache_path.exists():
            return False
        try:
            cookies = json.loads(self.cookie_cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        if not cookies:
            return False
        self.session.cookies.update(cookies)
        return True

    def _clear_cookie_cache(self):
        try:
            self.cookie_cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _keep_only_mfa_cookies(self):
        """Drop session-y cookies but preserve REMS 'remember-me' MFA cookies.

        REMS recognises a known device via the mfa_token / mfa_tokens / mfa_uuid
        cookies and skips the OTP step on subsequent logins. A stale PHPSESSID
        in the same request confuses the server into bouncing us back to the
        login page, so we keep ONLY the mfa_* cookies and let it issue a fresh
        PHPSESSID.
        """
        names_to_drop = [n for n in list(self.session.cookies.keys())
                         if not n.lower().startswith("mfa_")]
        for name in names_to_drop:
            try:
                del self.session.cookies[name]
            except KeyError:
                pass

    def _request(self, method, url, **kwargs):
        """Authenticated HTTP request with a 403 → re-auth safety net.

        Transient 5xx / rate-limit retries happen at the transport layer
        (urllib3 Retry, configured in __init__). This method only handles
        the REMS-specific 403 case: the Authentication-JWT cookie has a
        1h Max-Age and can lapse mid-batch, in which case we run a full
        MFA re-login and retry the call once.
        """
        if getattr(self, '_in_login_flow', False):
            return self.session.request(method, url, **kwargs)

        response = self.session.request(method, url, **kwargs)
        if response.status_code != 403:
            return response

        click.echo("Session expired mid-call (HTTP 403); re-authenticating...", err=True)
        self.session.cookies.clear()
        self._clear_cookie_cache()
        self._in_login_flow = True
        try:
            self.login(use_cache=False)
        finally:
            self._in_login_flow = False
        return self.session.request(method, url, **kwargs)

    def _probe_session(self):
        """Return True if the current session cookies authenticate against REMS.

        Uses a POST that mirrors the real auth-requiring calls (get_member_season_id),
        because a GET to /MembershipManagement/members returns 200 even with a
        stale Authentication-JWT — it just serves the search form HTML. The POST
        actually requires the JWT and returns 403 when it has lapsed (the JWT
        has a 1-hour Max-Age, independent of the longer-lived PHPSESSID/mfa cookies).
        """
        probe_url = f"{self.BASE_URL}/sportlomo/user/MembershipManagement/members"
        payload = {"FilterForm[primary_identifier]": "", "limit": 1}
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": probe_url,
        }
        try:
            response = self.session.post(probe_url, data=payload, headers=headers, allow_redirects=False)
        except requests.RequestException:
            return False
        if response.status_code == 200:
            return True
        if response.status_code in (301, 302):
            location = response.headers.get("Location", "")
            return "Maint-Login" not in location and "mfa" not in location.lower()
        return False

    def login(self, use_cache=True):
        """Logs in to the REMS system.

        Browser flow (per inspection in Chrome incognito):
          GET /maint.php (200, login form)
          POST /Maint-Login.php (302 to /sportlomo/users/mfa-login/, sets PHPSESSID)
          GET /sportlomo/users/mfa-login/ (302 to /sportlomo/users/mfa-verify-otp,
              sets mfa_token + mfa_tokens AND triggers the OTP email)
          GET /sportlomo/users/mfa-verify-otp (200, OTP form)
          POST /sportlomo/users/mfa-verify-otp with digits + form CSRF token
              (302 to /logged-in.php, sets mfa_token + mfa_tokens + mfa_uuid)
          GET /logged-in.php (302 to /club_home.php)
          GET /club_home.php (200)

        Walk one hop at a time so we don't make spurious GETs on /mfa-login that
        send extra OTP emails.
        """
        if use_cache and self._load_cookies() and self._probe_session():
            click.echo("Using cached REMS session (MFA skipped)")
            return True

        # Start clean — stale mfa_* cookies from a previous device-session can
        # make REMS bounce mfa-login/ <-> mfa-verify-otp instead of rendering
        # the OTP form.
        self.session.cookies.clear()

        # 1. GET the login form page to seed the session.
        self.session.get(f"{self.BASE_URL}/maint.php", allow_redirects=False)

        # 2. POST credentials.
        response = self.session.post(
            f"{self.BASE_URL}/Maint-Login.php",
            data={"username": self.username, "password": self.password},
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 302:
            raise Exception(
                f"Login failed: expected 302 from Maint-Login, got {response.status_code}"
            )

        next_url = urljoin(f"{self.BASE_URL}/Maint-Login.php", response.headers["Location"])
        last_url = f"{self.BASE_URL}/Maint-Login.php"

        # 3. Walk the chain one hop at a time. Stop at either the OTP form
        # (mfa-verify-otp, returns 200 with the form HTML) or a logged-in
        # landing page (any other 200).
        for _ in range(8):
            response = self.session.get(next_url, allow_redirects=False)
            response.raise_for_status()
            last_url = next_url
            if response.status_code != 302:
                break
            next_url = urljoin(last_url, response.headers["Location"])
        else:
            raise Exception("Login: too many redirects without reaching a final page")

        # 4. If we landed on the OTP form page, prompt + submit.
        if "/sportlomo/users/mfa-verify-otp" in last_url:
            return self._do_mfa(otp_form_url=last_url, otp_form_html=response.text)

        # 5. Otherwise the session should already be live — probe to confirm.
        if self._probe_session():
            click.echo("Login successful (cached MFA token honored, OTP skipped)")
            self._save_cookies()
            return True
        raise Exception(
            f"Login: landed at {last_url} (status {response.status_code}) but probe says not authenticated"
        )

    def _do_mfa(self, otp_form_url, otp_form_html):
        """Prompt for an OTP and submit it. Reads the form HTML for any hidden
        inputs (e.g. CSRF token) and includes them in the POST so REMS treats
        it the same as a browser-submitted form."""
        soup = BeautifulSoup(otp_form_html, 'lxml')
        # Carry forward all hidden inputs from the form (catches CSRF tokens,
        # YII_CSRF_TOKEN, etc., without needing to know their exact name).
        hidden_fields = {}
        for inp in soup.select('form input[type="hidden"]'):
            name = inp.get('name')
            if name:
                hidden_fields[name] = inp.get('value', '')

        mfa_code = self.mfa_callback()
        if not mfa_code or len(mfa_code) != 6:
            raise Exception("Invalid MFA code")

        mfa_payload = dict(hidden_fields)
        mfa_payload.update({
            "digit_1": mfa_code[0],
            "digit_2": mfa_code[1],
            "digit_3": mfa_code[2],
            "digit_4": mfa_code[3],
            "digit_5": mfa_code[4],
            "digit_6": mfa_code[5],
        })
        mfa_verify_url = f"{self.BASE_URL}/sportlomo/users/mfa-verify-otp"
        response = self.session.post(
            mfa_verify_url, data=mfa_payload,
            headers={"Referer": otp_form_url},
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 302:
            raise Exception(
                f"MFA verification failed: expected 302, got {response.status_code} (OTP rejected?)"
            )
        location = response.headers.get("Location", "")
        if "mfa-login" in location or "Maint-Login" in location or "mfa-verify-otp" in location:
            raise Exception(f"MFA verification failed: OTP rejected ({location!r})")

        # Browser flow continues: 302 -> /logged-in.php -> /club_home.php. Walk it.
        last_url = mfa_verify_url
        next_url = urljoin(last_url, location)
        for _ in range(8):
            response = self.session.get(next_url, allow_redirects=False)
            response.raise_for_status()
            last_url = next_url
            if response.status_code != 302:
                break
            next_url = urljoin(last_url, response.headers["Location"])

        if self._probe_session():
            click.echo("Login successful")
            self._save_cookies()
            return True
        raise Exception(
            f"MFA verification failed: landed at {last_url} but probe says not authenticated"
        )

    def logout(self):
        """Logs out of the REMS system."""
        logout_url = f"{self.BASE_URL}/Maint-Logout.php"
        self.session.get(logout_url)
        self.session.cookies.clear()
        self._clear_cookie_cache()
        click.echo("Logout successful")

    def get_members_csv(self, season_id, group_id=50113):
        """Fetches the members CSV for a given season and group."""
        url = f"{self.BASE_URL}/sportlomo/user/membership-management/member-export?FilterForm%5Bseason_id%5D={season_id}&FilterForm%5Bgroup_id%5D={group_id}"
        response = self._request('GET', url, headers={'Accept': 'text/csv'})
        response.raise_for_status()
        return response.text

    def get_member_season_id(self, rems_id, season_id):
        """
        Get the MemberSeasonDetail for a given Swimming Canada REMS Member ID.
        Returns the memberSeasonId.
        """
        url = f"{self.BASE_URL}/sportlomo/user/MembershipManagement/members"
        payload = {
            "FilterForm[primary_identifier]": rems_id,
            "FilterForm[season_id]": season_id,
            "limit": 15
        }
        headers = {
            "Referer": url,
            "X-Requested-With": "XMLHttpRequest"
        }
        response = self._request('POST', url, data=payload, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        table_rows = soup.select('table tbody tr')

        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) > 1 and columns[1].text.strip() == rems_id:
                actions_cell = columns[13]
                action_link = actions_cell.find('a')
                if action_link:
                    href = action_link['href']
                    match = re.search(r'member-detail/(\d+)', href)
                    if match:
                        return match.group(1)
        return None

    def search_member_by_name(self, name, season_id):
        """
        Search for a member by full name (e.g. "Chris Fletcher") in the given season.
        Returns the member_season_id of the unique match, or None if not found.
        Raises an exception if multiple members match.
        """
        parts = name.strip().split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"Expected 'First Last' name, got: {name!r}")
        first_name, last_name = parts

        url = f"{self.BASE_URL}/sportlomo/user/MembershipManagement/members"
        payload = {
            "FilterForm[first_name]": first_name,
            "FilterForm[last_name]": last_name,
            "FilterForm[season_id]": season_id,
            "limit": 15,
        }
        headers = {
            "Referer": url,
            "X-Requested-With": "XMLHttpRequest",
        }
        response = self._request('POST', url, data=payload, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        table_rows = soup.select('table tbody tr')

        matches = []
        for row in table_rows:
            columns = row.find_all('td')
            if len(columns) <= 13:
                continue
            actions_cell = columns[13]
            action_link = actions_cell.find('a')
            if not action_link:
                continue
            href = action_link.get('href', '')
            match = re.search(r'member-detail/(\d+)', href)
            if match:
                matches.append(match.group(1))

        if not matches:
            return None
        if len(matches) > 1:
            raise Exception(
                f"Found {len(matches)} members named {name!r} in season {season_id}; "
                f"name search is ambiguous."
            )
        return matches[0]

    def get_member_details(self, member_season_id, season_id):
        """
        Get from URL like $baseUrl/user/membership-management/member-detail/${memberSeasonId}
        @returns {dict}
        """
        url = f"{self.BASE_URL}/sportlomo/user/membership-management/member-detail/{member_season_id}"
        response = self._request('GET', url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        member_id = None
        for a in soup.select('a.smr-button'):
            href = a.get('href', '')
            match = re.search(r'member-credentials-details/(\d+)/(\d+)', href)
            if match:
                member_id = match.group(2)
                break

        rems_id_input = soup.select_one('#member-member-identifiers-0-member-identifier')
        rems_id = rems_id_input.get('value') if rems_id_input else None

        return {
            'rems_id': rems_id,
            'member_id': member_id,
            'member_season_id': member_season_id,
            'season_id': season_id,
        }

    def get_member_credential_details(self, member_season_id, member_id, credential_id):
        """
        Fetch the full record for a single existing member credential.

        Returns a dict with: provider, provider_identifier (meet name),
        description (session), start_date, expiry_date, state, name, type, status.
        """
        url = (f"{self.BASE_URL}/sportlomo/user/credentials/"
               f"view-from-member-profile/{member_season_id}/{member_id}/{credential_id}")
        response = self._request('GET', url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        def _val(field_id):
            el = soup.find(id=field_id)
            if el is None:
                return ''
            if el.name == 'input':
                return (el.get('value') or '').strip()
            return el.get_text(strip=True)

        def _selected_value(name):
            select = soup.find('select', {'name': name})
            if select is None:
                return ''
            opt = select.find('option', selected=True)
            return (opt.get('value') if opt else '') or ''

        return {
            'credential_id': str(credential_id),
            'name': _val('name'),
            'type': _val('type'),
            'short_name': _val('short-name'),
            'status': _val('current-status'),
            'state': _selected_value('state') or _val('state'),
            'start_date': _val('start-date'),
            'expiry_date': _val('expiry-date'),
            'description': _val('description'),
            'provider': _val('provider'),
            'provider_identifier': _val('provider-identifier'),
        }

    def update_member_credential(self, member_season_id, member_id, credential_id, field_overrides):
        """Edit an existing member credential.

        GETs the view-from-member-profile page, scrapes ALL form fields
        (inputs, selects, textareas — including hidden CSRF tokens), applies
        `field_overrides` (e.g. {"start_date": "11/04/2025"}), and POSTs the
        same URL. Sending the full form back preserves fields we don't intend
        to change.

        Success is a 302 redirect (Yii post-save behavior).
        """
        url = (f"{self.BASE_URL}/sportlomo/user/credentials/"
               f"view-from-member-profile/{member_season_id}/{member_id}/{credential_id}")
        response = self._request('GET', url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        form = soup.find('form')
        if form is None:
            raise Exception(f"Could not find edit form at {url}")

        payload = []
        for inp in form.find_all('input'):
            name = inp.get('name')
            if not name or inp.get('type') == 'file':
                continue
            payload.append((name, inp.get('value', '') or ''))
        for sel in form.find_all('select'):
            name = sel.get('name')
            if not name:
                continue
            selected = sel.find('option', selected=True)
            payload.append((name, (selected.get('value') if selected else '') or ''))
        for ta in form.find_all('textarea'):
            name = ta.get('name')
            if name:
                payload.append((name, ta.get_text() or ''))

        # Apply overrides — replace existing entries by name, append any new ones.
        override_names = set(field_overrides.keys())
        payload = [(n, v) for (n, v) in payload if n not in override_names]
        payload.extend(field_overrides.items())

        response = self._request(
            'POST', url, data=payload,
            headers={"Referer": url},
            allow_redirects=False,
        )
        if response.status_code != 302:
            raise Exception(
                f"update_member_credential failed: expected 302, got {response.status_code}"
            )
        return True

    def get_add_credential_form_options(self, member_season_id, member_id, type_label="Deck Evaluation"):
        """
        Return credential options available for the given credential type.

        The add-credential form is multi-step. The page itself only renders a
        "Type" dropdown (e.g. "Deck Evaluation"); the actual credential list
        is populated by an AJAX POST to /sportlomo/user/credentials/update-credential-form
        once a type is selected. This method reproduces that flow.

        Returns a list of dicts: {label, credential_id, type_id}.
        """
        form_url = f"{self.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}"
        form_response = self._request('GET', form_url)
        form_response.raise_for_status()

        soup = BeautifulSoup(form_response.text, 'lxml')
        type_select = soup.find('select', {'name': 'type'})
        if type_select is None:
            raise Exception("Could not find 'type' select on add-credential form")

        type_id = None
        for opt in type_select.find_all('option'):
            if opt.get_text(strip=True).lower() == type_label.lower():
                type_id = (opt.get('value') or '').strip()
                break
        if not type_id:
            available = ", ".join(o.get_text(strip=True) for o in type_select.find_all('option'))
            raise Exception(f"Type {type_label!r} not found in form type dropdown. Available: {available}")

        ajax_url = f"{self.BASE_URL}/sportlomo/user/credentials/update-credential-form"
        payload = [
            ("_method", "POST"),
            ("purchased_credential_id", ""),
            ("type", type_id),
            ("credential_id", ""),
            ("provider", ""),
            ("provider_identifier", ""),
            ("start_date", ""),
            ("member_id", str(member_id)),
            ("expiry_date", ""),
            ("description", ""),
            ("state", ""),
            ("nextStep", "credential-name"),
            ("credential_upload_1", ""),
            ("temp_credential_upload_1", ""),
        ]
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": form_url,
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        ajax_response = self._request('POST', ajax_url, data=payload, headers=headers)
        ajax_response.raise_for_status()

        try:
            data = ajax_response.json()
        except ValueError:
            raise Exception(f"update-credential-form returned non-JSON: {ajax_response.text[:200]!r}")

        if not data or not isinstance(data, dict) or 'credentials' not in data:
            raise Exception(f"update-credential-form returned no credentials: {data!r}")

        credentials = data['credentials']
        if isinstance(credentials, dict):
            credentials = list(credentials.values())

        return [
            {'label': c.get('name', ''), 'credential_id': str(c.get('id', '')), 'type_id': type_id}
            for c in credentials
        ]

    def add_member_credential(self, member_season_id, member_id, credential_id, type_id,
                              provider, provider_identifier, start_date, description,
                              state=80):
        """
        POST a new member credential. Returns True on success.

        Success is indicated by a 302 redirect to the member-credentials-details page.
        Any other response raises an Exception.

        Args:
            member_season_id: Sportlomo member season id (in the URL)
            member_id: Sportlomo member id (in the URL and form)
            credential_id: id of the credential to add (e.g. 452 for "IT Eval #1")
            type_id: credential type category id (e.g. 127 for "Deck Evaluation")
            provider: name of the official who provided/signed the credential
            provider_identifier: meet name or other identifier of where it was granted
            start_date: date string in MM/DD/YYYY format
            description: free-form description (e.g. "Session 6")
            state: state code; defaults to 80 ("Active" / "Approved")
        """
        url = f"{self.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}"
        expected_redirect_prefix = (
            f"{self.BASE_URL}/sportlomo/user/credentials/member-credentials-details/"
        )

        payload = [
            ("_method", "POST"),
            ("purchased_credential_id", ""),
            ("type", str(type_id)),
            ("credential_id", str(credential_id)),
            ("provider", provider),
            ("provider_identifier", provider_identifier),
            ("start_date", start_date),
            ("member_id", str(member_id)),
            ("expiry_date", ""),
            ("description", description),
            ("state", str(state)),
            ("nextStep", "credential-date"),
            ("credential_upload_1", ""),
            ("temp_credential_upload_1", ""),
        ]
        files = {
            "credential_upload": ("", b"", "application/octet-stream"),
            "temp_credential_upload": ("", b"", "application/octet-stream"),
        }

        response = self._request('POST', url, data=payload, files=files, allow_redirects=False)

        if response.status_code != 302:
            raise Exception(
                f"add_member_credential failed: expected 302, got {response.status_code}"
            )
        location = response.headers.get("Location", "")
        if not location.startswith(expected_redirect_prefix):
            raise Exception(
                f"add_member_credential failed: unexpected redirect target {location!r}"
            )
        return True

    def get_member_credentials(self, rems_id, member_id, member_season_id, page_size=100):
        """
        Get a table of Member Credentials Details for a member who was active in some season.
        """
        credentials = []
        page_number = 1
        total_pages = 1

        while page_number <= total_pages:
            url = f"{self.BASE_URL}/sportlomo/user/credentials/member-credentials-details/{member_season_id}/{member_id}?page={page_number}"
            payload = {'limit': page_size}
            response = self._request('POST', url, data=payload)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')

            if page_number == 1:
                pagination_text_element = soup.select_one('.ssm-pagination .no-of-records')
                if pagination_text_element:
                    pagination_text = pagination_text_element.text.strip()
                    matches = re.search(r'(\d+) of (\d+)', pagination_text)
                    if matches:
                        total_pages = int(matches[2])
                else:
                    total_pages = 1


            table_rows = soup.select('table tbody tr')
            for row in table_rows:
                columns = row.find_all('td')
                if len(columns) <= 7:
                    continue
                actions = [a['href'] for a in columns[7].find_all('a')]
                credentials.append({
                    'rems_id': rems_id,
                    'member_id': member_id,
                    'member_season_id': member_season_id,
                    'name': columns[0].text.strip(),
                    'type': columns[1].text.strip(),
                    'first_name': columns[2].text.strip(),
                    'last_name': columns[3].text.strip(),
                    'status': columns[4].text.strip(),
                    'start_date': columns[5].text.strip(),
                    'expiry_date': columns[6].text.strip(),
                    'actions': ", ".join(actions),
                })

            page_number += 1

        return credentials

def get_mfa_code():
    return click.prompt("Please enter the MFA code", type=str)

