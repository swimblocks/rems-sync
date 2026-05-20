import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock
from src.gsheet import (
    write_df_to_sheet, read_sheet_tab, update_cell,
    parse_meet_tab, parse_grid_session_dates, parse_officials_name_to_rems_id,
)

def test_write_df_to_sheet_cleans_data():
    # Setup mock client and spreadsheet
    mock_client = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    
    mock_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    
    # Create a DataFrame with NaN and an Unnamed column
    data = {
        'ColA': [1.0, np.nan, 3.0],
        'ColB': ['foo', 'bar', None],
        'Unnamed: 103': [4, 5, 6]
    }
    df = pd.DataFrame(data)
    
    write_df_to_sheet(df, 'fake-id', 'fake-sheet', mock_client)
    
    # Verify worksheet.update was called with cleaned data
    # It should have:
    # 1. Dropped 'Unnamed: 103'
    # 2. Replaced NaN/None with ''
    expected_data = [
        ['ColA', 'ColB'],
        [1.0, 'foo'],
        ['', 'bar'],
        [3.0, '']
    ]
    
    # Get the actual call arguments
    args, kwargs = mock_worksheet.update.call_args
    actual_data = args[0]
    
    assert actual_data == expected_data
    mock_worksheet.clear.assert_called_once()


def _mock_client_with_worksheet(mock_worksheet):
    mock_client = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    return mock_client


def test_read_sheet_tab_returns_dataframe():
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = [
        ['Official Name', 'Official Position', 'Deck Eval Success?'],
        ['Chris Fletcher', 'Inspector of Turns', 'TRUE'],
        ['Jane Doe', 'Starter', 'FALSE'],
    ]
    client = _mock_client_with_worksheet(mock_worksheet)

    df = read_sheet_tab('fake-id', 'positions', client)

    assert list(df.columns) == ['Official Name', 'Official Position', 'Deck Eval Success?']
    assert len(df) == 2
    assert df.iloc[0]['Official Name'] == 'Chris Fletcher'


def test_read_sheet_tab_empty():
    mock_worksheet = MagicMock()
    mock_worksheet.get_all_values.return_value = []
    client = _mock_client_with_worksheet(mock_worksheet)

    df = read_sheet_tab('fake-id', 'positions', client)
    assert df.empty


def test_update_cell_writes_to_correct_a1():
    mock_worksheet = MagicMock()
    mock_worksheet.row_values.return_value = [
        'Official Name', 'Official Position', 'Deck Eval Success?', 'Deck Eval Recorded?'
    ]
    client = _mock_client_with_worksheet(mock_worksheet)

    # row_index=2 (third data row → spreadsheet row 4) + col "Deck Eval Recorded?" (4th col) → D4
    update_cell('fake-id', 'positions', 2, 'Deck Eval Recorded?', True, client)

    mock_worksheet.update_acell.assert_called_once_with('D4', True)


def test_update_cell_unknown_column_raises():
    mock_worksheet = MagicMock()
    mock_worksheet.row_values.return_value = ['A', 'B']
    client = _mock_client_with_worksheet(mock_worksheet)

    with pytest.raises(ValueError, match="not found"):
        update_cell('fake-id', 'positions', 0, 'Missing', True, client)


def test_parse_meet_tab_handles_blank_header_row():
    rows = [
        ['', ''],
        ['Season', '2025-2026'],
        ['Meet Name', 'Cunningham Classic 2026'],
        ['Meet Sanction Number', '61794'],
        ['Meet Start Date', '2026-04-10'],
        ['', ''],
    ]
    meta = parse_meet_tab(rows)
    assert meta == {
        'Season': '2025-2026',
        'Meet Name': 'Cunningham Classic 2026',
        'Meet Sanction Number': '61794',
        'Meet Start Date': '2026-04-10',
    }


def test_parse_grid_session_dates_extracts_from_multiline_headers():
    rows = [
        ['', '', '', 'Cunningham Classic 2026 - April 10-12, 2026', '', '', ''],
        ['', '', '', '', '', '', ''],
        ['', 'Position', '',
         'Session 1\nFriday, Apr 10\nSenior Briefing: 3:55 pm',
         'Session 2\nSaturday, Apr 11\nSenior Briefing: 6:55 am',
         'Session 6\nSunday, Apr 12\nSenior Briefing: 9:25 am',
         ''],
        ['', 'Meet Manager', '', 'Mike Hui', 'Mike Hui', 'Mike Hui (DE)', ''],
    ]
    dates = parse_grid_session_dates(rows, year=2026)
    assert dates == {
        '1': '2026-04-10',
        '2': '2026-04-11',
        '6': '2026-04-12',
    }


def test_parse_grid_session_dates_no_session_row_returns_empty():
    rows = [['just', 'a', 'plain', 'sheet']]
    assert parse_grid_session_dates(rows, year=2026) == {}


def test_parse_officials_name_to_rems_id():
    rows = [
        ['', '', 'some marker', 'none'],
        ['', '', '', '', '', '', '', '', '', '', '', '', '', '', 'Session 1'],
        ['Form indicates available', 'Form name invalid', 'Email from Form',
         'Name', 'Form Resp. Timestamp', 'REMS ID', 'ROW Acct'],
        ['TRUE', 'FALSE', 'a@b.com', 'Gavin Bee', '2026-03-23 22:58:56', 'SC24176394', ''],
        ['TRUE', 'FALSE', 'c@d.com', 'Janpreet', '2026-03-24 08:00:00', 'SC11112222', ''],
        ['TRUE', 'FALSE', 'e@f.com', '', '2026-03-25 08:00:00', 'SC99998888', ''],   # no name → skip
        ['TRUE', 'FALSE', 'g@h.com', 'Missing REMS', '2026-03-26 08:00:00', '', ''],  # no rems → skip
    ]
    m = parse_officials_name_to_rems_id(rows)
    assert m == {'Gavin Bee': 'SC24176394', 'Janpreet': 'SC11112222'}


def test_parse_officials_name_to_rems_id_no_header_raises():
    rows = [['just', 'a', 'plain', 'sheet']]
    with pytest.raises(ValueError, match="header row"):
        parse_officials_name_to_rems_id(rows)
