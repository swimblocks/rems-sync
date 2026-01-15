function getSeasonIdFromSheetName() {
  const sheetName = SpreadsheetApp.getActiveSpreadsheet().getName(); // e.g. "2025-2026"
  const match = sheetName.match(/(\d{4})-\d{4}/);

  if (!match) {
    throw new Error('Sheet name must be in format "YYYY-YYYY"');
  }

  const startYear = parseInt(match[1], 10);

  var baseYear = 2017;
  var baseSeasonId = 226;
  if (startYear == 2022 || startYear == 2023) {
    baseYear = 2022;
    baseSeasonId = 224;
  } else if (startYear >= 2024) {
    baseYear = 2024;
    baseSeasonId = 231;
  }

  const seasonId = baseSeasonId + (startYear - baseYear);
  return seasonId;
}

