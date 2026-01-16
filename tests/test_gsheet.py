import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from src.gsheet import write_df_to_sheet

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
