import requests
import click
import re
from typing import Optional, Callable, Any
from bs4 import BeautifulSoup

class REMSClient:
    BASE_URL = "https://swimming.canada.sportsmanager.ie"

    def __init__(self, username: str, password: str, mfa_callback: Callable[[], Optional[str]],
                 use_cached_auth: bool = True, project_id: Optional[str] = None):
        self.username = username
        self.password = password
        self.mfa_callback = mfa_callback
        self.use_cached_auth = use_cached_auth
        self.project_id = project_id
        self.session = requests.Session()

    def login(self):
        """Logs in to the REMS system."""
        self.session.cookies.clear()
        login_url = f"{self.BASE_URL}/Maint-Login.php"
        login_payload = {"username": self.username, "password": self.password}
        
        response = self.session.post(login_url, data=login_payload, allow_redirects=False)
        response.raise_for_status()

        if response.status_code != 302:
            raise Exception("Login failed: Unexpected status code on login")

        mfa_url = response.headers["Location"]
        response = self.session.get(mfa_url, allow_redirects=False)
        response.raise_for_status()

        if response.status_code != 302:
            raise Exception("Login failed: Unexpected status code on MFA redirect")
        
        return self._do_mfa()

    def _do_mfa(self):
        mfa_code = self.mfa_callback()
        if not mfa_code or len(mfa_code) != 6:
            raise Exception("Invalid MFA code")

        mfa_payload = {
            "digit_1": mfa_code[0],
            "digit_2": mfa_code[1],
            "digit_3": mfa_code[2],
            "digit_4": mfa_code[3],
            "digit_5": mfa_code[4],
            "digit_6": mfa_code[5],
        }
        mfa_verify_url = f"{self.BASE_URL}/sportlomo/users/mfa-verify-otp"
        response = self.session.post(mfa_verify_url, data=mfa_payload, allow_redirects=False)
        response.raise_for_status()

        if response.status_code != 302 or response.headers["Location"] != f"{self.BASE_URL}/logged-in.php":
            raise Exception("MFA verification failed")

        click.echo("Login successful")
        return True

    def logout(self):
        """Logs out of the REMS system."""
        logout_url = f"{self.BASE_URL}/Maint-Logout.php"
        self.session.get(logout_url)
        self.session.cookies.clear()
        click.echo("Logout successful")

    def get_members_csv(self, season_id, group_id=50113):
        """Fetches the members CSV for a given season and group."""
        url = f"{self.BASE_URL}/sportlomo/user/membership-management/member-export?FilterForm%5Bseason_id%5D={season_id}&FilterForm%5Bgroup_id%5D={group_id}"
        response = self.session.get(url, headers={'Accept': 'text/csv'})
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
        response = self.session.post(url, data=payload, headers=headers)
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

    def get_member_details(self, member_season_id, season_id):
        """
        Get from URL like $baseUrl/user/membership-management/member-detail/${memberSeasonId}
        @returns {dict}
        """
        url = f"{self.BASE_URL}/sportlomo/user/membership-management/member-detail/{member_season_id}"
        response = self.session.get(url)
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
            response = self.session.post(url, data=payload)
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
                if len(columns) > 1:
                    actions = [a['href'] for a in columns[6].find_all('a')]
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

    def restore_from_cache(self, auth_data: dict[str, Any]) -> bool:
        """
        Restores session from cached authentication data.

        Args:
            auth_data: Dictionary with session_cookies.

        Returns:
            bool: True if restoration successful, False otherwise.
        """
        try:
            # Restore session cookies
            session_cookies = auth_data.get('session_cookies', {})
            for name, value in session_cookies.items():
                self.session.cookies.set(name, value)

            return True
        except Exception as e:
            click.echo(f"Failed to restore session from cache: {e}", err=True)
            return False

    def is_session_valid(self) -> bool:
        """
        Tests if current session is still valid by making a simple request.

        Returns:
            bool: True if session is valid, False otherwise.
        """
        try:
            # Try to access a protected page (logged-in.php)
            test_url = f"{self.BASE_URL}/logged-in.php"
            response = self.session.get(test_url, allow_redirects=False)

            # If we get a 200 status, session is valid
            # If we get redirected (302), session is invalid
            return response.status_code == 200

        except Exception as e:
            click.echo(f"Error checking session validity: {e}", err=True)
            return False


def get_mfa_code():
    return click.prompt("Please enter the MFA code", type=str)

