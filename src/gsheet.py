import gspread
import click
import google.auth
import pandas as pd
import re
from datetime import datetime
from gspread.utils import rowcol_to_a1

def get_gspread_client():
    """
    Returns an authenticated gspread client using Application Default Credentials.
    """
    creds, project = _get_credentials()
    client = gspread.authorize(creds)
    return client


def _get_credentials():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    return google.auth.default(scopes=scopes)


def get_drive_session():
    """Return a `requests.Session`-like object authenticated to call the Google
    Drive v3 REST API directly. Used for folder/sheet discovery that gspread
    doesn't natively support."""
    from google.auth.transport.requests import AuthorizedSession
    creds, _ = _get_credentials()
    return AuthorizedSession(creds)


def get_credentials_identity():
    """Best-effort: return the email/principal currently used by ADC, or None.
    Useful in error messages when a Drive API call returns empty results due
    to a missing share."""
    try:
        creds, _ = _get_credentials()
    except Exception:
        return None
    for attr in ('service_account_email', '_target_principal', 'signer_email'):
        value = getattr(creds, attr, None)
        if value:
            return value
    return None


_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
_DRIVE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"


def list_drive_subfolders(drive_session, parent_folder_id, drive_id=None):
    """List all sub-folders directly inside `parent_folder_id`. Returns a list
    of {'id': ..., 'name': ...} dicts. `drive_id` is the shared-drive id when
    the parent lives in a shared drive (required by the Drive API for listing
    shared-drive contents)."""
    return _drive_query(
        drive_session,
        q=f"'{parent_folder_id}' in parents and mimeType = '{_DRIVE_FOLDER_MIME}' and trashed = false",
        drive_id=drive_id,
    )


def find_drive_sheet_in_folder(drive_session, folder_id, name_substring, drive_id=None):
    """Return the first spreadsheet inside `folder_id` whose name contains
    `name_substring` (case-insensitive). Returns {'id', 'name'} or None."""
    files = _drive_query(
        drive_session,
        q=f"'{folder_id}' in parents and mimeType = '{_DRIVE_SHEET_MIME}' and trashed = false",
        drive_id=drive_id,
    )
    needle = name_substring.casefold()
    for f in files:
        if needle in (f.get('name') or '').casefold():
            return f
    return None


def _drive_query(drive_session, q, drive_id=None):
    """Run a Drive v3 files.list query, returning the full file list across
    pages. Each file is a dict with at least 'id' and 'name'.

    When `drive_id` is set the query is scoped to that specific shared drive
    (corpora=drive + driveId). Otherwise the query runs across all corpora
    the caller has access to."""
    out = []
    page_token = None
    while True:
        params = {
            "q": q,
            "fields": "nextPageToken, files(id, name, mimeType)",
            "pageSize": 200,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if drive_id:
            params["corpora"] = "drive"
            params["driveId"] = drive_id
        else:
            params["corpora"] = "allDrives"
        if page_token:
            params["pageToken"] = page_token
        response = drive_session.get(_DRIVE_FILES_URL, params=params)
        response.raise_for_status()
        body = response.json()
        out.extend(body.get('files', []))
        page_token = body.get('nextPageToken')
        if not page_token:
            return out

def write_df_to_sheet(df, sheet_id, sheet_name, client):
    """
    Writes a pandas DataFrame to a Google Sheet.
    """
    spreadsheet = client.open_by_key(sheet_id)
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="100", cols="20")
    
    worksheet.clear()
    # Replace NaN with empty string to avoid JSON compliance issues
    df_filled = df.fillna('')
    # Filter out columns that are "Unnamed" (Pandas adds these for trailing commas)
    cols_to_include = [c for c in df_filled.columns if not str(c).startswith('Unnamed:')]
    df_final = df_filled[cols_to_include]
    worksheet.update([df_final.columns.values.tolist()] + df_final.values.tolist())
    click.echo(f"Successfully wrote data to sheet: {sheet_name}")

def _open_worksheet(client, sheet_id, sheet_name):
    """Open a worksheet by tab name, raising a click.ClickException with a
    clear message if the tab doesn't exist (instead of gspread's raw
    WorksheetNotFound)."""
    spreadsheet = client.open_by_key(sheet_id)
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        raise click.ClickException(
            f"Tab {sheet_name!r} not found in sheet {sheet_id}."
        )


def read_sheet_tab(sheet_id, sheet_name, client):
    """
    Read a named tab from a Google Sheet and return it as a pandas DataFrame.
    Treats the first row as the header. Empty cells become empty strings.
    """
    worksheet = _open_worksheet(client, sheet_id, sheet_name)
    rows = worksheet.get_all_values()
    if not rows:
        return pd.DataFrame()
    header, *data_rows = rows
    return pd.DataFrame(data_rows, columns=header)

def read_sheet_rows(sheet_id, sheet_name, client):
    """Return raw rows (list of lists of strings) from the named tab. No header inference."""
    worksheet = _open_worksheet(client, sheet_id, sheet_name)
    return worksheet.get_all_values()


def parse_meet_tab(rows):
    """
    Parse the Meet tab into a dict keyed on the column-A label.

    The Meet tab is a flat key/value layout where the first row may be blank
    and each subsequent row is `(label, value)`. Blank or partial rows are skipped.
    Example: [('', ''), ('Season', '2025-2026'), ('Meet Name', 'Cunningham Classic 2026'), ...]
    """
    out = {}
    for row in rows:
        if len(row) < 2:
            continue
        key = (row[0] or '').strip()
        value = (row[1] or '').strip()
        if not key:
            continue
        out[key] = value
    return out


_SESSION_HEADER_RE = re.compile(r'^\s*Session\s+(\d+)', re.IGNORECASE)
_DATE_LINE_RE = re.compile(
    r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+'
    r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})',
    re.IGNORECASE,
)


def parse_grid_session_dates(rows, year):
    """
    Parse Grid tab raw rows into a {session_id: "YYYY-MM-DD"} mapping.

    The Grid tab is a 2D layout where each session is a column. The header
    row (the first row containing any "Session N" cell) has multi-line cells
    such as:

        Session 1
        Friday, Apr 10
        Senior Briefing: 3:55 pm
        ...

    The session id is the integer after "Session", and the date is the
    "<DayOfWeek>, <Mon> <Day>" line. The year is supplied externally
    (typically from the Meet tab's "Meet Start Date").
    """
    out = {}
    for row in rows:
        if not any(_SESSION_HEADER_RE.match(cell or '') for cell in row):
            continue
        for cell in row:
            if not cell:
                continue
            m = _SESSION_HEADER_RE.match(cell)
            if not m:
                continue
            session_id = m.group(1)
            date_match = _DATE_LINE_RE.search(cell)
            if not date_match:
                continue
            month = datetime.strptime(date_match.group(1)[:3].title(), "%b").month
            day = int(date_match.group(2))
            out[session_id] = f"{int(year):04d}-{month:02d}-{day:02d}"
        return out
    return out


def parse_officials_name_to_rems_id(rows):
    """
    Parse the Officials tab into a {Name: REMS ID} mapping.

    Locates the header row by finding the first row that contains both
    a "Name" and a "REMS ID" cell. Subsequent rows are data. Rows with
    a blank Name or blank REMS ID are skipped.
    """
    header_idx = None
    name_col = rems_col = None
    for i, row in enumerate(rows):
        stripped = [(c or '').strip() for c in row]
        if 'Name' in stripped and 'REMS ID' in stripped:
            header_idx = i
            name_col = stripped.index('Name')
            rems_col = stripped.index('REMS ID')
            break
    if header_idx is None:
        raise ValueError("Could not find a header row with both 'Name' and 'REMS ID' in Officials tab.")

    out = {}
    for row in rows[header_idx + 1:]:
        if len(row) <= max(name_col, rems_col):
            continue
        name = (row[name_col] or '').strip()
        rems_id = (row[rems_col] or '').strip()
        if not name or not rems_id:
            continue
        out[name] = rems_id
    return out


def update_cell(sheet_id, sheet_name, row_index, col_name, value, client):
    """
    Write `value` to a single cell in the given tab.

    `row_index` is the 0-based index of the data row (i.e. row 0 is the first
    row after the header). `col_name` is the column header name as it appears
    in the first row of the tab.
    """
    worksheet = _open_worksheet(client, sheet_id, sheet_name)
    header = worksheet.row_values(1)
    if col_name not in header:
        raise ValueError(f"Column {col_name!r} not found in tab {sheet_name!r}. Headers: {header}")
    col_idx_1 = header.index(col_name) + 1
    row_idx_1 = row_index + 2
    a1 = rowcol_to_a1(row_idx_1, col_idx_1)
    worksheet.update_acell(a1, value)
