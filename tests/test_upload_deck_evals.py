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
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'Kaoru Yajima',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'Jane Doe', 'Official Position': 'Starter',
         'Deck Eval Success?': 'FALSE', 'Deck Eval Provider': '',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'Already Done', 'Official Position': 'Starter',
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
    assert kwargs['start_date'] == '04/12/2026'
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
        {'Official Name': 'A B', 'Official Position': 'Inspector of Turns',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'C D', 'Official Position': 'Starter',
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
    # The pending row is Chris Fletcher / Inspector of Turns at Cunningham Classic 2026, Session 6.
    # Pretend he already has #2 recorded for that exact meet+session.
    mock_client.get_member_credentials.return_value = [
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #1',
         'actions': '/sportlomo/user/credentials/view-from-member-profile/685100/178722/442'},
        {'type': 'Deck Evaluation', 'name': 'Inspector of Turns Evaluation #2',
         'actions': '/sportlomo/user/credentials/view-from-member-profile/685100/178722/443'},
    ]
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Inspector of Turns Evaluation #2', 'credential_id': '443', 'type_id': '127'},
    ]
    mock_client.get_member_credential_details.side_effect = lambda msid, mid, cid: {
        '442': {'name': 'Inspector of Turns Evaluation #1',
                'provider_identifier': 'Old Meet 2024', 'description': 'Session 2'},
        '443': {'name': 'Inspector of Turns Evaluation #2',
                'provider_identifier': 'Cunningham Classic 2026', 'description': 'Session 6'},
    }[str(cid)]

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
        {'Official Name': 'Chris Fletcher', 'Official Position': 'Inspector of Turns',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': '', 'Session': '6'},
        {'Official Name': 'Other Person', 'Official Position': 'Starter',
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
        {'Official Name': 'A B', 'Official Position': 'Inspector of Turns',
         'Deck Eval Success?': 'TRUE', 'Deck Eval Provider': 'P1',
         'Deck Eval Recorded?': '', 'Session': '6'},
        # Row 1: already in REMS -> OK in recheck mode
        {'Official Name': 'C D', 'Official Position': 'Starter',
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
    # REMS only has the Starter eval (for 'C D'); not the Inspector of Turns.
    mock_client.get_member_credentials.side_effect = lambda **kwargs: {
        '178722': [
            {'type': 'Deck Evaluation', 'name': 'Starter Evaluation #1',
             'actions': '/sportlomo/user/credentials/view-from-member-profile/685100/178722/456'},
        ],
    }.get(str(kwargs['member_id']), [])
    mock_client.get_add_credential_form_options.return_value = [
        {'label': 'Inspector of Turns Evaluation #1', 'credential_id': '442', 'type_id': '127'},
        {'label': 'Starter Evaluation #1', 'credential_id': '456', 'type_id': '127'},
    ]
    mock_client.get_member_credential_details.side_effect = lambda msid, mid, cid: {
        '456': {'name': 'Starter Evaluation #1',
                'provider_identifier': 'Cunningham Classic 2026', 'description': 'Session 6'},
    }[str(cid)]

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


@patch('src.main.read_sheet_rows')
@patch('src.main.read_sheet_tab')
@patch('src.main.get_gspread_client')
def test_upload_deck_evals_no_pending(mock_get_gs, mock_read_tab, mock_read_rows, runner):
    positions = pd.DataFrame([
        {'Official Name': 'A B', 'Official Position': 'Starter',
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
