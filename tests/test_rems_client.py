import pytest
import responses
import json
from src.rems_client import REMSClient

@pytest.fixture
def rems_client(tmp_path):
    return REMSClient("test_user", "test_password", lambda: "123456",
                      cookie_cache_path=tmp_path / "cookies.json")

def _mock_login_form(client):
    """Mock the GET /maint.php login form fetch the new login flow makes first."""
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/maint.php",
        status=200,
        body="<html>login form</html>",
    )


def _mock_otp_form_get(client, url=None):
    """Mock the GET on the OTP-form page. By default the real form lives at
    /sportlomo/users/mfa-login/ and returns 200 with the form HTML."""
    responses.add(
        responses.GET,
        url or f"{client.BASE_URL}/sportlomo/users/mfa-login/",
        status=200,
        body="<html>OTP form</html>",
    )


def _mock_post_mfa_redirect_chain(client):
    """Common mocks for the post-OTP chain: mfa-login -> logged-in.php -> /club_home.php -> probe."""
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/logged-in.php",
        status=302,
        headers={"Location": "/club_home.php"},
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/club_home.php",
        status=200,
        body="<html>Home</html>",
    )
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=200,
    )


@responses.activate
def test_login_success(rems_client):
    _mock_login_form(rems_client)
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-login"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-login",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=200,
        body="<html><form><input type='hidden' name='_csrf' value='tok'/></form></html>",
    )
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/logged-in.php"},
    )
    _mock_post_mfa_redirect_chain(rems_client)

    assert rems_client.login() is True

@responses.activate
def test_login_persists_cookies_on_success(rems_client):
    _mock_login_form(rems_client)
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-login",
                 "Set-Cookie": "sess=abc123; Path=/"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-login",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=200,
        body="<html><form><input type='hidden' name='_csrf' value='tok'/></form></html>",
    )
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/logged-in.php"},
    )
    _mock_post_mfa_redirect_chain(rems_client)
    assert rems_client.login() is True
    assert rems_client.cookie_cache_path.exists()
    cached = json.loads(rems_client.cookie_cache_path.read_text())
    assert cached.get("sess") == "abc123"


@responses.activate
def test_login_uses_cached_cookies_when_probe_returns_200(tmp_path):
    cache = tmp_path / "cookies.json"
    cache.write_text(json.dumps({"sess": "cached-token"}))
    mfa_calls = []
    client = REMSClient("u", "p", lambda: (mfa_calls.append(1), "111111")[1],
                        cookie_cache_path=cache)
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=200,
    )
    assert client.login() is True
    assert mfa_calls == []


@responses.activate
def test_login_falls_back_when_probe_returns_403(tmp_path):
    """Stale JWT: PHPSESSID/mfa cookies present but Authentication-JWT expired."""
    cache = tmp_path / "cookies.json"
    cache.write_text(json.dumps({"sess": "stale-jwt"}))
    client = REMSClient("u", "p", lambda: "123456", cookie_cache_path=cache)
    # First the cache-probe POST returns 403 (stale JWT) -> fall back to full login.
    # Then after the OTP, the chain probe POST returns 200.
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=403,
    )
    _mock_login_form(client)
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{client.BASE_URL}/sportlomo/users/mfa-login"},
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/sportlomo/users/mfa-login",
        status=302,
        headers={"Location": f"{client.BASE_URL}/sportlomo/users/mfa-verify-otp"},
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=200,
        body="<html><form><input type='hidden' name='_csrf' value='tok'/></form></html>",
    )
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=302,
        headers={"Location": f"{client.BASE_URL}/logged-in.php"},
    )
    _mock_post_mfa_redirect_chain(client)
    assert client.login() is True


@responses.activate
def test_login_skips_mfa_real_chain(tmp_path):
    """The real successful no-MFA chain: Maint-Login -> mfa-login/ -> logged-in.php -> /club_home.php."""
    cache = tmp_path / "cookies.json"
    cache.write_text(json.dumps({
        "PHPSESSID": "stale", "mfa_token": "x", "mfa_tokens": "y", "mfa_uuid": "z",
    }))
    mfa_calls = []
    client = REMSClient("u", "p", lambda: (mfa_calls.append(1), "111111")[1],
                        cookie_cache_path=cache)
    # Probe with stale PHPSESSID fails (so we go to full login).
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=403,
    )
    _mock_login_form(client)
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{client.BASE_URL}/sportlomo/users/mfa-login/"},
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/sportlomo/users/mfa-login/",
        status=302,
        headers={"Location": f"{client.BASE_URL}/logged-in.php"},
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/logged-in.php",
        status=302,
        headers={"Location": "/club_home.php"},  # relative on purpose
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/club_home.php",
        status=200,
        body="<html>Home</html>",
    )
    # Second probe (after redirect chain) succeeds.
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=200,
    )
    assert client.login() is True
    assert mfa_calls == []


@responses.activate
def test_login_keeps_only_mfa_cookies_before_post(tmp_path):
    """Stale PHPSESSID is dropped, mfa_* preserved, before POST Maint-Login."""
    cache = tmp_path / "cookies.json"
    cache.write_text(json.dumps({
        "PHPSESSID": "stale-and-rejected",
        "mfa_token": "keep-me",
        "mfa_tokens": "keep-me-2",
        "mfa_uuid": "keep-me-3",
    }))
    client = REMSClient("u", "p", lambda: "111111", cookie_cache_path=cache)

    # Probe fails so we go to full login.
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=403,
    )
    _mock_login_form(client)
    # POST Maint-Login — capture what cookies are sent.
    captured_cookies = {}
    def login_callback(req):
        captured_cookies.update({c.split("=", 1)[0].strip(): c.split("=", 1)[1]
                                  for c in (req.headers.get("Cookie") or "").split(";") if "=" in c})
        return (302, {"Location": f"{client.BASE_URL}/logged-in.php"}, "")
    responses.add_callback(
        responses.POST,
        f"{client.BASE_URL}/Maint-Login.php",
        callback=login_callback,
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/logged-in.php",
        status=200,
    )
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=200,
    )

    client.login()
    assert "PHPSESSID" not in captured_cookies


@responses.activate
def test_request_auto_reauth_on_403(tmp_path):
    """A 403 mid-call triggers a full MFA re-login and retries the original request."""
    cache = tmp_path / "cookies.json"
    cache.write_text(json.dumps({"sess": "stale"}))
    mfa_calls = []
    client = REMSClient("u", "p", lambda: (mfa_calls.append(1), "123456")[1],
                        cookie_cache_path=cache)

    # Initial probe succeeds (200 POST) so we go straight to using the cache.
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=200,
    )
    assert client.login() is True
    assert mfa_calls == []  # cache used, no MFA so far

    # Now simulate a real authenticated call where the JWT has lapsed:
    # the first POST returns 403, the re-login flow runs (Maint-Login -> mfa-login -> mfa-verify-otp),
    # and the retried POST returns 200.
    target_url = f"{client.BASE_URL}/sportlomo/user/credentials/member-credentials-details/789/456"
    responses.add(responses.POST, target_url, status=403)
    _mock_login_form(client)
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{client.BASE_URL}/sportlomo/users/mfa-login"},
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/sportlomo/users/mfa-login",
        status=302,
        headers={"Location": f"{client.BASE_URL}/sportlomo/users/mfa-verify-otp"},
    )
    responses.add(
        responses.GET,
        f"{client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=200,
        body="<html><form><input type='hidden' name='_csrf' value='tok'/></form></html>",
    )
    responses.add(
        responses.POST,
        f"{client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=302,
        headers={"Location": f"{client.BASE_URL}/logged-in.php"},
    )
    _mock_post_mfa_redirect_chain(client)
    responses.add(responses.POST, target_url, body="<table><tbody></tbody></table>", status=200)

    creds = client.get_member_credentials("SC123", "456", "789")
    assert mfa_calls == [1]  # re-login was triggered exactly once
    assert creds == []  # successful retry returned an empty table


@responses.activate
def test_login_failure_bad_credentials(rems_client):
    """Bad creds: POST Maint-Login returns 200 (login form re-rendered). The
    probe then fails since we're not authenticated."""
    _mock_login_form(rems_client)
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/Maint-Login.php",
        status=200,
    )
    # Probe will fail
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        status=403,
    )
    with pytest.raises(Exception, match="Login failed: expected 302 from Maint-Login"):
        rems_client.login()

@responses.activate
def test_login_failure_bad_mfa(rems_client):
    _mock_login_form(rems_client)
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-login"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-login",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=200,
        body="<html><form><input type='hidden' name='_csrf' value='tok'/></form></html>",
    )
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=200,
    )

    with pytest.raises(Exception, match="OTP rejected"):
        rems_client.login()

@responses.activate
def test_get_members_csv(rems_client):
    season_id = 123
    expected_csv = "header1,header2\nvalue1,value2"
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/user/membership-management/member-export?FilterForm%5Bseason_id%5D={season_id}&FilterForm%5Bgroup_id%5D=50113",
        body=expected_csv,
        status=200,
        content_type="text/csv",
    )

    csv_data = rems_client.get_members_csv(season_id)
    assert csv_data == expected_csv

@responses.activate
def test_get_member_season_id(rems_client):
    rems_id = "SC123456"
    season_id = 123
    html_response = f"""
    <table>
        <tbody>
            <tr>
                <td></td>
                <td>{rems_id}</td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td></td>
                <td><a href="/sportlomo/user/membership-management/member-detail/789/456">Details</a></td>
            </tr>
        </tbody>
    </table>
    """
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        body=html_response,
        status=200,
    )

    member_season_id = rems_client.get_member_season_id(rems_id, season_id)
    assert member_season_id == "789"

@responses.activate
def test_search_member_by_name_unique(rems_client):
    season_id = 123
    html_response = """
    <table>
        <tbody>
            <tr>
                <td></td><td>SC123456</td><td></td><td></td><td></td><td></td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td>
                <td><a href="/sportlomo/user/membership-management/member-detail/789/456">Details</a></td>
            </tr>
        </tbody>
    </table>
    """
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        body=html_response,
        status=200,
    )

    member_season_id = rems_client.search_member_by_name("Chris Fletcher", season_id)
    assert member_season_id == "789"

@responses.activate
def test_search_member_by_name_not_found(rems_client):
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        body="<table><tbody></tbody></table>",
        status=200,
    )
    assert rems_client.search_member_by_name("Nobody Here", 123) is None

@responses.activate
def test_search_member_by_name_ambiguous(rems_client):
    html_response = """
    <table>
        <tbody>
            <tr>
                <td></td><td>SC1</td><td></td><td></td><td></td><td></td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td>
                <td><a href="/sportlomo/user/membership-management/member-detail/111/100">A</a></td>
            </tr>
            <tr>
                <td></td><td>SC2</td><td></td><td></td><td></td><td></td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td>
                <td><a href="/sportlomo/user/membership-management/member-detail/222/200">B</a></td>
            </tr>
        </tbody>
    </table>
    """
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/MembershipManagement/members",
        body=html_response,
        status=200,
    )
    with pytest.raises(Exception, match="ambiguous"):
        rems_client.search_member_by_name("Common Name", 123)

def test_search_member_by_name_requires_two_parts(rems_client):
    with pytest.raises(ValueError, match="First Last"):
        rems_client.search_member_by_name("OnlyOne", 123)

@responses.activate
def test_get_member_details(rems_client):
    member_season_id = 789
    season_id = 123
    html_response = f"""
    <input id="member-member-identifiers-0-member-identifier" value="SC12345678" />
    <a class="smr-button" href="/sportlomo/user/credentials/member-credentials-details/{member_season_id}/456">View Credentials</a>
    """
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/user/membership-management/member-detail/{member_season_id}",
        body=html_response,
        status=200,
    )

    details = rems_client.get_member_details(member_season_id, season_id)
    assert details == {
        'rems_id': 'SC12345678',
        'member_id': '456',
        'member_season_id': member_season_id,
        'season_id': season_id,
    }

@responses.activate
def test_get_member_credential_details(rems_client):
    member_season_id = 685100
    member_id = 178722
    credential_id = 452
    html = """
    <form>
      <input id="type" value="Deck Evaluation" />
      <input id="name" value="Chief Timekeeper Evaluation #2" />
      <input id="short-name" value="CT Eval #2" />
      <input id="current-status" value="Approved" />
      <select name="state"><option value="80" selected>Active</option></select>
      <input id="start-date" value="12/04/2026" />
      <input id="expiry-date" value="" />
      <input id="description" value="Session 6" />
      <input id="provider" value="Kaoru Yajima" />
      <input id="provider-identifier" value="Cunningham Classic 2026" />
    </form>
    """
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/view-from-member-profile/{member_season_id}/{member_id}/{credential_id}",
        body=html,
        status=200,
    )
    details = rems_client.get_member_credential_details(member_season_id, member_id, credential_id)
    assert details['name'] == 'Chief Timekeeper Evaluation #2'
    assert details['provider'] == 'Kaoru Yajima'
    assert details['provider_identifier'] == 'Cunningham Classic 2026'
    assert details['description'] == 'Session 6'
    assert details['start_date'] == '12/04/2026'
    assert details['state'] == '80'


@responses.activate
def test_get_add_credential_form_options_via_ajax(rems_client):
    member_season_id = 685100
    member_id = 178722
    form_html = """
    <form>
      <select name="type" id="cred-type-select">
        <option value="">Select Credential Type</option>
        <option value="127">Deck Evaluation</option>
        <option value="128">Officials Level Certification</option>
      </select>
      <select name="credential_id" id="cred-name-select">
        <option value="">Select Credential</option>
      </select>
    </form>
    """
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}",
        body=form_html,
        status=200,
    )
    ajax_payload = {
        "credentials": [
            {"id": 442, "name": "Inspector of Turns Evaluation #1", "survey": None, "expiry": None, "description": ""},
            {"id": 443, "name": "Inspector of Turns Evaluation #2", "survey": None, "expiry": None, "description": ""},
        ],
        "loadCredList": True,
    }
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/update-credential-form",
        json=ajax_payload,
        status=200,
    )

    options = rems_client.get_add_credential_form_options(member_season_id, member_id)
    assert options == [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Inspector of Turns Evaluation #2', 'credential_id': '443', 'type_id': '127'},
    ]

@responses.activate
def test_get_add_credential_form_options_type_label_not_found(rems_client):
    member_season_id = 685100
    member_id = 178722
    form_html = """
    <form>
      <select name="type">
        <option value="128">Officials Level Certification</option>
      </select>
    </form>
    """
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}",
        body=form_html,
        status=200,
    )
    with pytest.raises(Exception, match="Deck Evaluation"):
        rems_client.get_add_credential_form_options(member_season_id, member_id)

@responses.activate
def test_get_add_credential_form_options_missing_type_select(rems_client):
    member_season_id = 685100
    member_id = 178722
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}",
        body="<html><body>nope</body></html>",
        status=200,
    )
    with pytest.raises(Exception, match="'type' select"):
        rems_client.get_add_credential_form_options(member_season_id, member_id)

@responses.activate
def test_add_member_credential_success(rems_client):
    member_season_id = 685100
    member_id = 178722
    redirect_location = (
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/member-credentials-details/"
        f"{member_season_id}/{member_id}"
    )
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}",
        status=302,
        headers={"Location": redirect_location},
    )

    assert rems_client.add_member_credential(
        member_season_id=member_season_id,
        member_id=member_id,
        credential_id=452,
        type_id=127,
        provider="Kaoru Yajima",
        provider_identifier="Cunningham Classic 2026",
        start_date="04/12/2026",
        description="Session 6",
    ) is True

@responses.activate
def test_add_member_credential_failure_non_302(rems_client):
    member_season_id = 685100
    member_id = 178722
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}",
        status=200,
    )
    with pytest.raises(Exception, match="expected 302"):
        rems_client.add_member_credential(
            member_season_id=member_season_id,
            member_id=member_id,
            credential_id=452, type_id=127, provider="x",
            provider_identifier="y", start_date="04/12/2026", description="Session 1",
        )

@responses.activate
def test_add_member_credential_failure_wrong_redirect(rems_client):
    member_season_id = 685100
    member_id = 178722
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/add-member-credential/{member_season_id}/{member_id}",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/some-error-page"},
    )
    with pytest.raises(Exception, match="unexpected redirect"):
        rems_client.add_member_credential(
            member_season_id=member_season_id,
            member_id=member_id,
            credential_id=452, type_id=127, provider="x",
            provider_identifier="y", start_date="04/12/2026", description="Session 1",
        )

@responses.activate
def test_get_member_credentials(rems_client):
    rems_id = "SC123456"
    member_id = "456"
    member_season_id = "789"
    html_response_page1 = """
    <table>
        <tbody>
            <tr>
                <td>Cred Name 1</td>
                <td>Type 1</td>
                <td>First 1</td>
                <td>Last 1</td>
                <td>Status 1</td>
                <td>Start 1</td>
                <td>Expiry 1</td>
                <td><a href="/action1">Action 1</a></td>
            </tr>
        </tbody>
    </table>
    <div class="ssm-pagination"><span class="no-of-records">1 to 1 of 2</span></div>
    """
    html_response_page2 = """
    <table>
        <tbody>
            <tr>
                <td>Cred Name 2</td>
                <td>Type 2</td>
                <td>First 2</td>
                <td>Last 2</td>
                <td>Status 2</td>
                <td>Start 2</td>
                <td>Expiry 2</td>
                <td><a href="/action2">Action 2</a></td>
            </tr>
        </tbody>
    </table>
    <div class="ssm-pagination"><span class="no-of-records">2 to 2 of 2</span></div>
    """
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/member-credentials-details/{member_season_id}/{member_id}?page=1",
        body=html_response_page1,
        status=200,
    )
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/user/credentials/member-credentials-details/{member_season_id}/{member_id}?page=2",
        body=html_response_page2,
        status=200,
    )

    credentials = rems_client.get_member_credentials(rems_id, member_id, member_season_id)
    assert len(credentials) == 2
    assert credentials[0]['name'] == 'Cred Name 1'
    assert credentials[0]['actions'] == '/action1'
    assert credentials[1]['name'] == 'Cred Name 2'
    assert credentials[1]['actions'] == '/action2'
