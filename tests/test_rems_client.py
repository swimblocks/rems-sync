import pytest
import responses
from src.rems_client import REMSClient

@pytest.fixture
def rems_client():
    return REMSClient("test_user", "test_password", lambda: "123456")

@responses.activate
def test_login_success(rems_client):
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/mfa-login"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/mfa-login",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp"},
    )
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/logged-in.php"},
    )

    assert rems_client.login() is True

@responses.activate
def test_login_failure_bad_credentials(rems_client):
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/Maint-Login.php",
        status=200,
    )

    with pytest.raises(Exception, match="Login failed: Unexpected status code on login"):
        rems_client.login()

@responses.activate
def test_login_failure_bad_mfa(rems_client):
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/Maint-Login.php",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/mfa-login"},
    )
    responses.add(
        responses.GET,
        f"{rems_client.BASE_URL}/mfa-login",
        status=302,
        headers={"Location": f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp"},
    )
    responses.add(
        responses.POST,
        f"{rems_client.BASE_URL}/sportlomo/users/mfa-verify-otp",
        status=200,
    )

    with pytest.raises(Exception, match="MFA verification failed"):
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
    assert credentials[1]['name'] == 'Cred Name 2'
