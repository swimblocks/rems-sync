"""An in-memory keyring backend, so tests never touch the OS keychain.

Copied from swimblocks/semotion-sync.
"""

from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.passwords: dict[tuple[str, str], str] = {}
        self.refuse_deletes = False  # True: deletes fail and the entry stays, as when access is denied

    def get_password(self, service, username):
        return self.passwords.get((service, username))

    def set_password(self, service, username, password):
        self.passwords[(service, username)] = password

    def delete_password(self, service, username):
        if self.refuse_deletes:
            raise PasswordDeleteError("access denied")
        if self.passwords.pop((service, username), None) is None:
            raise PasswordDeleteError(f"no password for {username} in {service}")
