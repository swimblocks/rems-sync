import pandas as pd
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from src.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def _positions_df():
    return pd.DataFrame([
        {'Official Name': 'Chris Fletcher', 'Official Position': 'Inspector of Turns',
         'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'Kaoru Yajima',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'Jane Doe', 'Official Position': 'Starter', 'Official Club': 'ROW',
         'Deck Eval Success?': 'FALSE', 'Deck Eval Provider': '',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'Already Done', 'Official Position': 'Starter', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'Someone',
         'Deck Eval Recorded?': 'TRUE', 'Session': '6'},
    ])


def _grid_rows():
    return [
        ['', '', '', 'Some meet title', '', '', '', '', '', '', '', '', ''],
        ['', '', '', '', '', '', '', '', '', '', '', '', ''],
        ['', 'Position', '',
         'Session 1\nFriday, Apr 10\nBriefing',
         'Session 2\nSaturday, Apr 11\nBriefing',
         'Session 3\nSaturday, Apr 11\nBriefing',
         'Session 4\nSaturday, Apr 11\nBriefing',
         'Session 5\nSunday, Apr 12\nBriefing',
         'Session 6\nSunday, Apr 12\nBriefing',
         'Session 7\nSunday, Apr 12\nBriefing',
         '', '', ''],
    ]


def _meet_rows():
    return [
        ['', ''],
        ['Season', '2025-2026'],
        ['Meet Name', 'Cunningham Classic 2026'],
        ['Meet Start Date', '2026-04-10'],
    ]


def _officials_rows():
    return [
        ['', '', 'marker', 'none'],
        ['', '', '', '', '', '', '', '', '', '', '', '', '', '', 'Session 1'],
        ['Form indicates available', 'Form name invalid', 'Email',
         'Name', 'Timestamp', 'REMS ID', 'ROW Acct'],
        ['TRUE', 'FALSE', 'a@b.com', 'Chris Fletcher', 't', 'SC24176410', ''],
        ['TRUE', 'FALSE', 'c@d.com', 'A B', 't', 'SC11112222', ''],
        ['TRUE', 'FALSE', 'e@f.com', 'C D', 't', 'SC33334444', ''],
    ]


def _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=None):
    mock_read_tab.side_effect = lambda sheet_id, tab, client: {
        'Positions': positions_df if positions_df is not None else _positions_df(),
    }[tab]
    mock_read_rows.side_effect = lambda sheet_id, tab, client: {
        'Grid': _grid_rows(),
        'Meet': _meet_rows(),
        'Officials': _officials_rows(),
    }[tab]


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_happy_path(mock_mfa, mock_client_class, mock_get_gs,
                                      mock_read_tab, mock_read_rows, mock_update_cell, runner):
    _patch_sheet_reads(mock_read_tab, mock_read_rows)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '452', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
    ])

    assert result.exit_code == 0, result.output
    assert 'Meet: Cunningham Classic 2026' in result.output
    assert 'Found 1 pending deck eval' in result.output
    assert 'OK row 0' in result.output
    assert 'Done: 1 succeeded, 0 failed' in result.output

    mock_client.add_member_credential.assert_called_once()
    kwargs = mock_client.add_member_credential.call_args.kwargs
    assert kwargs['credential_id'] == '452'
    assert kwargs['provider'] == 'Kaoru Yajima'
    assert kwargs['provider_identifier'] == 'Cunningham Classic 2026'
    assert kwargs['start_date'] == '12/04/2026'  # d/m/Y per REMS form convention
    assert kwargs['description'] == 'Session 6'

    mock_update_cell.assert_called_once_with(
        'fake-id', 'Positions', 0, 'Deck Eval Recorded?', True, mock_get_gs.return_value
    )


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_continues_on_failure(mock_mfa, mock_client_class, mock_get_gs,
                                                mock_read_tab, mock_read_rows, mock_update_cell, runner):
    positions = pd.DataFrame([
        {'Official Name': 'A B', 'Official Position': 'Inspector of Turns', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'C D', 'Official Position': 'Starter', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P2',
         'Deck Eval Recorded?': '', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.side_effect = ["685100", None]
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC1', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '452', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
    ])

    assert result.exit_code == 0, result.output
    assert 'OK row 0' in result.output
    assert 'FAIL row 1' in result.output
    assert 'Done: 1 succeeded, 1 failed' in result.output
    assert mock_update_cell.call_count == 1


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_dry_run(mock_mfa, mock_client_class, mock_get_gs,
                                   mock_read_tab, mock_read_rows, mock_update_cell, runner):
    _patch_sheet_reads(mock_read_tab, mock_read_rows)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '452', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--dry-run',
    ])

    assert result.exit_code == 0, result.output
    assert '[dry-run]' in result.output
    mock_client.login.assert_called_once()
    mock_client.get_member_season_id.assert_called()
    mock_client.get_add_credential_form_options.assert_called()
    mock_client.add_member_credential.assert_not_called()
    mock_update_cell.assert_not_called()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_already_recorded_ticks_cell(mock_mfa, mock_client_class, mock_get_gs,
                                                       mock_read_tab, mock_read_rows, mock_update_cell, runner):
    _patch_sheet_reads(mock_read_tab, mock_read_rows)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    # The pending row is Chris Fletcher / Inspector of Turns at Cunningham Classic 2026 (Apr 12).
    # Pretend he already has #2 recorded on Apr 12 (matches a session date of the meet).
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #1', 'start_date': '15/03/2024'},
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #2', 'start_date': '12/04/2026'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Inspector of Turns Evaluation #2', 'credential_id': '443', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
    ])

    assert result.exit_code == 0, result.output
    assert 'already recorded' in result.output.lower()
    assert 'Done: 1 succeeded, 0 failed' in result.output
    mock_client.add_member_credential.assert_not_called()
    mock_update_cell.assert_called_once_with(
        'fake-id', 'Positions', 0, 'Deck Eval Recorded?', True, mock_get_gs.return_value
    )


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_interactive_yes_posts(mock_mfa, mock_client_class, mock_get_gs,
                                                  mock_read_tab, mock_read_rows, mock_update_cell, runner):
    _patch_sheet_reads(mock_read_tab, mock_read_rows)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--interactive',
    ], input='y\n')

    assert result.exit_code == 0, result.output
    assert 'Submit?' in result.output
    mock_client.add_member_credential.assert_called_once()
    mock_update_cell.assert_called_once()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_interactive_no_skips(mock_mfa, mock_client_class, mock_get_gs,
                                                 mock_read_tab, mock_read_rows, mock_update_cell, runner):
    _patch_sheet_reads(mock_read_tab, mock_read_rows)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--interactive',
    ], input='n\n')

    assert result.exit_code == 0, result.output
    assert 'user declined' in result.output
    mock_client.add_member_credential.assert_not_called()
    mock_update_cell.assert_not_called()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_interactive_quit_aborts_batch(mock_mfa, mock_client_class, mock_get_gs,
                                                          mock_read_tab, mock_read_rows, mock_update_cell, runner):
    # Two pending rows; user quits at the first prompt.
    positions = pd.DataFrame([
        {'Official Name': 'Chris Fletcher', 'Official Position': 'Inspector of Turns', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'Other Person', 'Official Position': 'Starter', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P2',
         'Deck Eval Recorded?': '', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)
    # Officials tab only has Chris; the other is fine for read but won't get reached
    mock_read_rows.side_effect = lambda sheet_id, tab, client: {
        'Grid': _grid_rows(),
        'Meet': _meet_rows(),
        'Officials': [
            ['Form indicates available', 'Form name invalid', 'Email',
             'Name', 'Timestamp', 'REMS ID', 'ROW Acct'],
            ['TRUE', 'FALSE', 'a@b.com', 'Chris Fletcher', 't', 'SC24176410', ''],
            ['TRUE', 'FALSE', 'b@c.com', 'Other Person', 't', 'SC55556666', ''],
        ],
    }[tab]

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Starter Evaluation #1', 'credential_id': '456', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--interactive',
    ], input='q\n')

    assert result.exit_code == 0, result.output
    assert 'Aborting batch' in result.output
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_recheck_verify_only(mock_mfa, mock_client_class, mock_get_gs,
                                               mock_read_tab, mock_read_rows, mock_update_cell, runner):
    """--recheck never POSTs. Already-recorded rows tick the cell, missing rows are reported."""
    positions = pd.DataFrame([
        # Row 0: not in REMS yet -> MISSING in recheck mode
        {'Official Name': 'A B', 'Official Position': 'Inspector of Turns', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': '', 'Session': '6'},
        # Row 1: already in REMS -> OK in recheck mode
        {'Official Name': 'C D', 'Official Position': 'Starter', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P2',
         'Deck Eval Recorded?': 'TRUE', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC11112222', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    # REMS only has the Starter eval (for 'C D') on Apr 12 (matches Session 6 in the grid fixture).
    mock_client.get_member_credentials.side_effect = lambda **kwargs: {
        '178722': [
            {'type': 'Deck Evaluation', 'name': 'Starter Evaluation #1', 'start_date': '12/04/2026'},
        ],
    }.get(str(kwargs['member_id']), [])
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Starter Evaluation #1', 'credential_id': '456', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--recheck',
    ])

    assert result.exit_code == 0, result.output
    assert 'Recheck mode' in result.output
    assert 'Found 2 row(s) to verify' in result.output
    assert 'MISSING row 0' in result.output
    assert 'OK row 1' in result.output
    assert 'already recorded' in result.output.lower()
    # Crucially: never POST in recheck mode.
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_recheck_detects_swapped_dates(mock_mfa, mock_client_class, mock_get_gs,
                                                         mock_read_tab, mock_read_rows, mock_update_cell, runner):
    """In --recheck, an existing eval with a day/month-swapped date (legacy bug)
    is flagged as SWAPPED rather than MISSING."""
    positions = pd.DataFrame([
        {'Official Name': 'A B', 'Official Position': 'Inspector of Turns', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': 'TRUE', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC11112222', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    # Session 6 in the grid fixture is April 12, 2026 (ISO 2026-04-12).
    # The swap of 2026-04-12 is 2026-12-04 (December 4) -> REMS d/m/Y display 04/12/2026.
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #1',
         'start_date': '04/12/2026'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--recheck',
    ])

    assert result.exit_code == 0, result.output
    assert 'SWAPPED row 0' in result.output
    assert '04/12/2026' in result.output
    assert 'MISSING' not in result.output
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_recheck_does_not_prompt_for_missing(mock_mfa, mock_client_class, mock_get_gs,
                                                                mock_read_tab, mock_read_rows, mock_update_cell, runner):
    """--recheck + --interactive: missing rows are reported but NEVER prompt."""
    _patch_sheet_reads(mock_read_tab, mock_read_rows)
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC24176410', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []  # nothing in REMS
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Starter Evaluation #1', 'credential_id': '456', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--recheck', '--interactive',
    ], input='')

    assert result.exit_code == 0, result.output
    assert 'Submit?' not in result.output
    assert 'MISSING' in result.output
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_filters_by_club(mock_mfa, mock_client_class, mock_get_gs,
                                            mock_read_tab, mock_read_rows, mock_update_cell, runner):
    """Only rows whose Official Club matches --rems-club are processed."""
    positions = pd.DataFrame([
        {'Official Name': 'Our Person', 'Official Position': 'Inspector of Turns', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'Visiting Person', 'Official Position': 'Starter', 'Official Club': 'OTHER',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P2',
         'Deck Eval Recorded?': '', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)
    # Officials map needs Our Person but not Visiting Person.
    mock_read_rows.side_effect = lambda sheet_id, tab, client: {
        'Grid': _grid_rows(),
        'Meet': _meet_rows(),
        'Officials': [
            ['Form indicates available', 'Form name invalid', 'Email',
             'Name', 'Timestamp', 'REMS ID', 'ROW Acct'],
            ['TRUE', 'FALSE', 'a@b.com', 'Our Person', 't', 'SC11112222', ''],
        ],
    }[tab]

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC11112222', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
    ])
    assert result.exit_code == 0, result.output
    assert "for club 'ROW'" in result.output
    assert "1 other-club row(s) skipped" in result.output
    mock_client.add_member_credential.assert_called_once()


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_no_match_error_is_short(mock_mfa, mock_client_class, mock_get_gs,
                                                    mock_read_tab, mock_read_rows, mock_update_cell, runner):
    """The 'no credential matching' error is one short sentence; no big Available list."""
    positions = pd.DataFrame([
        {'Official Name': 'Brad Hickey', 'Official Position': 'Standby', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P',
         'Deck Eval Recorded?': '', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)
    mock_read_rows.side_effect = lambda sheet_id, tab, client: {
        'Grid': _grid_rows(),
        'Meet': _meet_rows(),
        'Officials': [
            ['Form indicates available', 'Form name invalid', 'Email',
             'Name', 'Timestamp', 'REMS ID', 'ROW Acct'],
            ['TRUE', 'FALSE', 'a@b.com', 'Brad Hickey', 't', 'SC44445555', ''],
        ],
    }[tab]
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC44445555', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Starter Evaluation #1', 'credential_id': '456', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
    ])
    assert result.exit_code == 0, result.output
    assert "No credential option matching 'Standby Evaluation #1'" in result.output
    # The long Available: ... list is gone.
    assert 'Available:' not in result.output


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_interactive_prompts_for_family_on_no_match(
        mock_mfa, mock_client_class, mock_get_gs,
        mock_read_tab, mock_read_rows, mock_update_cell, runner):
    """In --interactive, on no-match the user picks from a deduped family list."""
    positions = pd.DataFrame([
        {'Official Name': 'Brad Hickey', 'Official Position': 'Standby', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P',
         'Deck Eval Recorded?': '', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)
    mock_read_rows.side_effect = lambda sheet_id, tab, client: {
        'Grid': _grid_rows(),
        'Meet': _meet_rows(),
        'Officials': [
            ['Form indicates available', 'Form name invalid', 'Email',
             'Name', 'Timestamp', 'REMS ID', 'ROW Acct'],
            ['TRUE', 'FALSE', 'a@b.com', 'Brad Hickey', 't', 'SC44445555', ''],
        ],
    }[tab]
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC44445555', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    # Two families: Inspector of Turns and Introduction to Swimming Officiating.
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Inspector of Turns Evaluation #2', 'credential_id': '443', 'type_id': '127'},
        {'label': 'Introduction to Swimming Officiating Evaluation #1', 'credential_id': '441', 'type_id': '127'},
        {'label': 'Introduction to Swimming Officiating Evaluation #2', 'credential_id': '444', 'type_id': '127'},
    ]
    mock_client.add_member_credential.return_value = True

    # Pick option 2 (Introduction to Swimming Officiating) at the family prompt,
    # then 'y' at the Submit? prompt.
    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--interactive',
    ], input='2\ny\n')

    assert result.exit_code == 0, result.output
    assert 'What credential was this evaluation for?' in result.output
    assert 'Inspector of Turns' in result.output
    assert 'Introduction to Swimming Officiating' in result.output
    # The chosen family's #1 should have been POSTed.
    mock_client.add_member_credential.assert_called_once()
    assert mock_client.add_member_credential.call_args.kwargs['credential_id'] == '441'


@patch('src.main.update_cell')
@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
@patch('src.main.REMSClient')
@patch('src.main.get_mfa_code')
def test_upload_deck_evals_interactive_family_skip(
        mock_mfa, mock_client_class, mock_get_gs,
        mock_read_tab, mock_read_rows, mock_update_cell, runner):
    """At the family prompt, 's' (or Enter for default) skips the row."""
    positions = pd.DataFrame([
        {'Official Name': 'Brad Hickey', 'Official Position': 'Standby', 'Official Club': 'ROW',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P',
         'Deck Eval Recorded?': '', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)
    mock_read_rows.side_effect = lambda sheet_id, tab, client: {
        'Grid': _grid_rows(),
        'Meet': _meet_rows(),
        'Officials': [
            ['Form indicates available', 'Form name invalid', 'Email',
             'Name', 'Timestamp', 'REMS ID', 'ROW Acct'],
            ['TRUE', 'FALSE', 'a@b.com', 'Brad Hickey', 't', 'SC44445555', ''],
        ],
    }[tab]
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.get_member_season_id.return_value = "685100"
    mock_client.get_member_details.return_value = {
        'rems_id': 'SC44445555', 'member_id': '178722',
        'member_season_id': '685100', 'season_id': 232,
    }
    mock_client.get_member_credentials.return_value = []
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
    ]

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
        '--interactive',
    ], input='s\n')

    assert result.exit_code == 0, result.output
    assert 'no credential picked' in result.output
    mock_client.add_member_credential.assert_not_called()


@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
def test_upload_deck_evals_no_pending(mock_get_gs, mock_read_tab, mock_read_rows, runner):
    positions = pd.DataFrame([
        {'Official Name': 'A B', 'Official Position': 'Starter', 'Official Club': 'ROW',
         'Deck Eval Success?': 'FALSE', 'Deck Eval Provider': '',
         'Deck Eval Recorded?': '', 'Session': '6'},
    ])
    _patch_sheet_reads(mock_read_tab, mock_read_rows, positions_df=positions)

    result = runner.invoke(cli, [
        'upload-deck-evals',
        '--username', 'u', '--password', 'p',
        '--season', '2025-2026',
        '--sheet-id', 'fake-id',
    ])
    assert result.exit_code == 0, result.output
    assert 'Found 0 pending deck eval' in result.output
