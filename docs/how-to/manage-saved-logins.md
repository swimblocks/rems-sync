# Manage saved logins

Save, check, change and remove the REMS logins rems-sync uses. All the commands:
[`auth`](../reference/cli.md#auth). Why they work this way: [Saved logins](../explanation/saved-logins.md).

## Save a login

```bash
python -m src.main auth login --team row
```

Enter the REMS username and password (the password shows as `*`), then the six-digit code REMS
emails you. It prints `Logged in to REMS as <username>; saved as 'row'` only if REMS accepted the login;
otherwise nothing is saved, and you can try again.

Choose any alias. Use one per REMS login you hold, such as `row` and `row-referee`.

## See what is saved

```bash
python -m src.main auth status
```

Each alias and its username. If it also says `REMS_USERNAME and REMS_PASSWORD are set`, those
are being used instead; clear them to use the saved logins:

```powershell
Remove-Item Env:REMS_USERNAME, Env:REMS_PASSWORD
```

```bash
unset REMS_USERNAME REMS_PASSWORD
```

## Change a password, or the account for an alias

Run `auth login --team <alias>` again. It offers the saved username; press Enter to keep it, or
type another. The new login replaces the old one once REMS accepts it.

## Remove a login

```bash
python -m src.main auth logout --team row
```

Removes the alias's session, password and username from this machine. It doesn't log out of
REMS anywhere else.

## Run once as another account

Set both `REMS_USERNAME` and `REMS_PASSWORD` in the terminal ([how](../reference/configuration.md#environment-variables));
every REMS command run there uses that account, with its own session, until you clear them.

## If something goes wrong

| Message | What to do |
|---|---|
| `No saved login for team 'row'` | Run `auth login --team row`. |
| `REMS login failed: Login: landed at .../maint.php ...` | REMS rejected the username or password. Check them by signing in to REMS in a browser. |
| `Warning: could not save the REMS session …` | Nothing to do: the next run asks for a code again. |
| `Set both REMS_USERNAME and REMS_PASSWORD, or neither.` | Clear the one that is set, or set the other. |
