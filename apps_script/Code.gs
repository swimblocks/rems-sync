

function onOpen() {
  updateMenu();
}

function updateMenu() {
  const ui = SpreadsheetApp.getUi();
  const menu = ui.createMenu('REMS Menu')
    .addItem('Login to REMS', 'onLoginToREMS')
    .addItem('Refresh REMS Members', 'onRefreshREMSMembers')
    .addItem('Refresh REMS Member Details', 'onRefreshREMSMemberDetails')
    .addItem('Refresh REMS Member Credentials', 'onRefreshREMSMemberCredentials');  

  menu.addToUi();
}

function showErrorDialog(message) {
  const ui = SpreadsheetApp.getUi();
  ui.alert('Error', message, ui.ButtonSet.OK);
}

/**
 * Called when "Login to REMS" clicked in our menu.
 */
function onLoginToREMS() {
  const html = HtmlService.createHtmlOutputFromFile('LoginDialog')
    .setWidth(300)
    .setHeight(200);
  SpreadsheetApp.getUi().showModalDialog(html, 'Login to REMS');
}

function onLoginDialogSubmit(username, password) {
  Logger.log("LoginDialogSubmit");
  
  // Show error dialog if login failed
  if (!loginToREMSAdmin(username, password, getCodeFromUser)) {
    showErrorDialog('Failed to login to REMS. Please check your credentials and try again.');
  }

  // After login, refresh the menu
  updateMenu();
}

function onRefreshREMSMembers() {
  if (!maybeLoggedIntoREMS()) {
    SpreadsheetApp.getActiveSpreadsheet().toast("Not signed in, cannot refresh REMS members.");
    return;
  }

  refreshMembers();
}

function onRefreshREMSMemberDetails() {
  if (!maybeLoggedIntoREMS()) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Not signed in, cannot refresh REMS member details.");
    return;
  }
  refreshAllMemberDetails();
}

function onRefreshREMSMemberCredentials() {
  if (!maybeLoggedIntoREMS()) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Not signed in, cannot refresh REMS member credentials.");
    return;
  }
  refreshAllMemberCredentials();
}


function getCodeFromUser() {
  var ui = SpreadsheetApp.getUi();
  var result = ui.prompt("Please enter the MFA code");
  Logger.log(result.getResponseText());
  return result.getResponseText();
}

/**
 * Iterates over the named range "OfficialsREMSMemberIds" and calls the specified callback function for each ID.
 * 
 * @param {function(string): void} fn - The callback function to call for each REMS ID.
 */
function processRegisteredOfficialREMSIDs(fn) {
  // Get the named range "OfficialsREMSMemberIds"
  const sheet = SpreadsheetApp.getActiveSpreadsheet();
  const range = sheet.getRangeByName('OfficialsREMSMemberIds');
  
  if (!range) {
    Logger.log('Named range "OfficialsREMSMemberIds" not found.');
    return;
  }

  // Get the values from the named range
  const values = range.getValues();
  
  // Iterate over the values and call the callback function for each ID
  for (let i = 0; i < values.length; i++) {
    const remsId = values[i][0];
    if (remsId.length == 0) { continue; }
    fn(remsId);
    Logger.log(`Processed ${remsId}. Sleeping for a second.`);
    Utilities.sleep(1000);
  }
}

/**
 * Update the contents of the 'REMS Members' sheet by downloading all officials for the current season.
 */
function refreshMembers() {
  try {
    const seasonId = getSeasonIdFromSheetName();
    const groupId = 50113; // Officials
    const url = `https://swimming.canada.sportsmanager.ie/sportlomo/user/membership-management/member-export?FilterForm%5Bseason_id%5D=${seasonId}&FilterForm%5Bgroup_id%5D=${groupId}`;

    Logger.log(url);

    const response = httpRequest(url, {
      method: 'get',
      followRedirects: false,
      headers: {
        'Accept': 'text/csv'
      }
    });

    if (!response || response.getResponseCode() !== 200) {
      showErrorDialog('Failed to fetch REMS Members CSV. Response code: ' + (response ? response.getResponseCode() : 'null'));
      return;
    }

    const csvText = response.getContentText();
    const csvData = Utilities.parseCsv(csvText);

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('REMS Members');
    if (!sheet) {
      showErrorDialog('Sheet "REMS Members" not found.');
      return;
    }

    sheet.clear();
    sheet.getRange(1, 1, csvData.length, csvData[0].length).setValues(csvData);
    SpreadsheetApp.getActiveSpreadsheet().toast("REMS Members refreshed successfully.");
  } catch (e) {
    showErrorDialog('Error refreshing REMS Members: ' + e.message);
  }
}

/**
 * Update the contents of the 'REMS Member Credentials' sheet to include the most recent creds
 * for all members in 'REMS Member Details'
 */
function refreshAllMemberCredentials() {
  // Get the {MemberSeasonDetail} objects for all registered members from the reference sheet we use for that data.
  let memberDetailsArray = loadMemberDetailsFromSheet();
  if (memberDetailsArray.length == 0) {
    Logger.log("Could not find any Member Season Details");
    return;
  }

  // @type []{MemberSeasonCredential}
  let data = [];
  memberDetailsArray.forEach((memberSeasonDetails, index) => {
    if (memberSeasonDetails.rems_id.length == 0) {
      Logger.log('Empty member season details while refreshing all member credentials, skipping.');
      return;
    }
    
    memberCreds = MemberSeasonCredential.fetch(memberSeasonDetails);
    if (!memberCreds) {
      Logger.log(`Failed to fetch member season credentials for REMS id ${memberSeasonDetails.rems_id}`);
    } else {
      Logger.log(`Fetched MemberSeasonCredentials for ${memberSeasonDetails.rems_id}, creds are:\n${JSON.stringify(memberCreds)}`);
      data.push(...memberCreds);
    }
  });

  // Update the Google Sheet
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('REMS Member Credentials');
  
  // Prepare the header row
  const headers = [ 
    'REMS ID',
    'Member ID',
    'Member Season ID',
    'Name',
    'Type',
    'First Name',
    'Last Name',
    'Status',
    'Start Date',
    'Expiry Date',
    'Actions'
  ];
  
  // Prepare the data rows
  const dataRows = data.map(detail => [
    detail.rems_id,
    detail.member_id,
    detail.member_season_id,
    detail.name,
    detail.type,
    detail.first_name,
    detail.last_name,
    detail.status,
    detail.start_date,
    detail.expiry_date,
    detail.actions
  ]);

  // Add the headers and data to the sheet
  sheet.clear(); // Clear any existing content
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]); // Set header row
  sheet.getRange(2, 1, dataRows.length, headers.length).setValues(dataRows); // Set data rows
}

/**
 * Get the {MemberSeasonDetail} for all registered officials.  Write the results to the REMS MemberDetails tab.
 */
function refreshAllMemberDetails() {
  let data = [];
  processRegisteredOfficialREMSIDs(function(remsId) {
    // Get the MemberSeasonDetail for this person
    let md = MemberSeasonDetail.fetchByRemsId(remsId, CURRENT_SEASON_ID);

    // Add the MemberSeasonDetail to the result;
    if (md != null) { data.push(md) };
  });
  if (data.length == 0) {
    Logger.log("Did not find any member details.");
    return;
  }

  // Update the Google Sheet
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('REMS Member Details');
  
  // Prepare the header row
  const headers = ['REMS ID', 'Member ID', 'Season ID', 'Member Season ID'];
  
  // Prepare the data rows
  const dataRows = data.map(detail => [
    detail.rems_id,
    detail.member_id,
    detail.member_season_id,
    detail.season_id
  ]);

  // Add the headers and data to the sheet
  sheet.clear(); // Clear any existing content
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]); // Set header row
  sheet.getRange(2, 1, dataRows.length, headers.length).setValues(dataRows); // Set data rows
}

/**
 * Refresh All REMS Data that we support fetching via the web.
 * Goes in the most reasonable order and may pause between refreshes if needed to avoid throttling.
 */
function refreshAllREMSData() {
  refreshAllMemberDetails();
  refreshAllMemberCredentials();
}

/**
 * Load all cached {MemberSeasonDetail} instances from the 'REMS Member Details' tab.
 * 
 * @returns []{MemberSeasonDetail}
 */
function loadMemberDetailsFromSheet() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = spreadsheet.getSheetByName('REMS Member Details');
  if (!sheet) {
    Logger.log('Sheet not found');
    return [];
  }
  return MemberSeasonDetail.loadFromDataTable(sheet.getDataRange().getValues());
}



