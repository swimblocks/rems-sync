
/**
 * Member details found on the following SportLomo pages:
 * - ${baseUrl}/user/membership-management/member-detail/${memberSeasonId}
 * 
 */
class MemberSeasonDetail {

  constructor() {
    /** 
     * The Swimming Canada REMS Member ID which is stable across seasons and is specific to Swimming Canada.
     * Sportlomo never uses these identifiers in URIs or form fields other than searches.
     * 
     * @type {string}
     * @example "SC24176394"
     */  
    this.rems_id = '';

    /** 
     * The Sportlomo Member ID which is stable across seasons.  Usually 6 digits, unclear if this is required.
     * @type {number}
     * @example 217268
     */  
    this.member_id = -1;

    /** 
     * The Sportlomo Member "Season" ID which identifies the member in a particular season.  Usually 6 digits, unclear if this is required.
     * NOTE: this is a term I made up to describe the second last integer identifier in urls like
     *       $baseUrl/user/credentials/add-member-credential/$memberSeasonId/$memberId because that identifier is different
     *       depending on the season and member.
     * @type {number}
     * @example 595775
     */  
    this.member_season_id = -1;

    /**
     * The number which identifies this season for Sportlomo.
     */
    this.season_id = -1;
  }

  /**
   * Get from URL like $baseUrl/user/membership-management/member-detail/${memberSeasonId}
   * @returns {MemberSeasonDetail}
   * @throws {Error} If there's an HTTP error or the details are not found in the HTML.
   */
  static fetchByMemberSeasonId(memberSeasonId, seasonId) {
    let result = new MemberSeasonDetail();
    result.season_id = seasonId;
    result.member_season_id = memberSeasonId;

    // Get the details
    var response = httpRequest(
      `https://swimming.canada.sportsmanager.ie/sportlomo/user/membership-management/member-detail/${memberSeasonId}`, 
      {
        "method": "get",
        "followRedirects": false,
      }
    )
    if (!response) {
      Logger.log("member-detail request error");
      return null;
    } else if (response.getResponseCode() != 200) {
      Logger.log('member-detail not ok: '+response.getResponseCode());
      return null;
    }
    const $ = Cheerio.load(response.getContentText());

    // Find anchor elements which include a reference to the Sportlomo member ID.
    const memberIds = [];
    $('a.smr-button').each(function () {
      const href = $(this).attr('href');
      const matches = href.match(/member-credentials-details\/(\d+)\/(\d+)/);
      if (matches) { memberIds.push(matches[2]); }
    });

    if (memberIds.length == 0) {
      Logger.log(`Failed to find member id for member season id ${memberSeasonId}`);
      return null;
    }
    result.member_id = memberIds[0];

    // Find the Swimming Canada Member ID
    const inputElement = $('#member-member-identifiers-1-member-identifier');
    if (inputElement.length > 0) {
      // Extract the value attribute
      const inputValue = inputElement.attr('value');

      // Validate the value using a regex
      const regex = /^SC\d+$/;
      if (regex.test(inputValue)) {
        result.rems_id = inputValue;
      } else {
        Logger.log("Input element which should contain SC REMS ID not found.");
        return null;
      }
    } else {
      Logger.log('Input element which should contain SC REMS ID not found.');
      return null;
    }

    return result;
  }

  /**
   * Get {MemberSeasonDetail} about the given Swimming Canada REMS Member ID.
   * @returns {MemberSeasonDetail} or null if there was an error.
   */
  static fetchByRemsId(remsId, seasonId) {
    var payload = {
      "FilterForm[primary_identifier]": remsId,
      "FilterForm[season_id]": 232,
      "limit": 15
    };
    var membersResponse = httpRequest(
      "https://swimming.canada.sportsmanager.ie/sportlomo/user/MembershipManagement/members", 
      {
        "method": "post",
        "payload": payload,
        "followRedirects": false,
        "headers": {
          "Referer": "https://swimming.canada.sportsmanager.ie/sportlomo/user/MembershipManagement/members",
          "X-Requested-With": "XMLHttpRequest"
        }
      }
    )
    if (!membersResponse) {
      Logger.log("members search request error");
      return null;
    } else if (membersResponse.getResponseCode() != 200) {
      Logger.log('members search not ok: '+membersResponse.getResponseCode());
      return null;
    }

    var tableData = _parseMembersSearchResult(membersResponse.getContentText());
    for (var i = 0; i < tableData.length; i++) {
      if (tableData[i].REMS_ID === remsId) {
        if (!tableData[i].Actions) {
          Logger.log("No actions for REMS ID "+remsId);
          return null;
        }

        var memberSeasonId = _extractIdFromMemberDetailUrl(tableData[i].Actions);
        Logger.log("Found member season id "+memberSeasonId+" for primary id "+remsId);
        return MemberSeasonDetail.fetchByMemberSeasonId(memberSeasonId, seasonId);
      }
    }
    
    Logger.log("Error: Could not determine member season id for REMS ID "+remsId);
    return null;
  }

  /**
   * Given a data table whose columns correspond to the fields of {MemberSeasonDetail}, return an array of {MemberSeasonDetail} objects.
   * Assumes that the first row is a header row and that the headers include some or all of the following in any order:
   * - REMS Member ID
   * - Member ID
   * - Member Season ID
   * - Season ID
   * 
   * @returns []{MemberSeasonDetail}
   */
  static loadFromDataTable(data) {
    // Extract headers
    const headers = data.shift(); // Remove the first row containing headers

    // Create an array of MemberSeasonDetail objects
    const memberDetailsArray = data.map(row => {
      const detail = new MemberSeasonDetail();
      headers.forEach((header, index) => {
        switch (header) {
          case 'REMS ID':
            detail.rems_id = row[index];
            break;
          case 'Member ID':
            detail.member_id = row[index];
            break;
          case 'Member Season ID':
            detail.member_season_id = row[index];
            break;
          case 'Season ID':
            detail.season_id = row[index];
            break;
          default:
            Logger.log(`Unknown header: ${header}`);
        }
      });
      return detail;
    });

    return memberDetailsArray;
  }
}

  /*
  * Given html assumed to be from POSTing to https://swimming.canada.sportsmanager.ie/sportlomo/user/MembershipManagement/members
  * Returns list of objects with fields:
  * - REMS_ID
  * - First_Name
  * - Last_Name
  * - DOB
  * - Active
  * - Official
  * - Teamsheets
  * - Registration_Date
  * - Start_Date
  * - Expiry
  * - Season
  * - Primary/Dual
  * - Actions
  */
  function _parseMembersSearchResult(html) {
    var $ = Cheerio.load(html);
    var tableRows = $('table tbody tr');
    var tableData = [];

    tableRows.each(function() {
      var rowData = {
        REMS_ID: $(this).find('td:nth-child(2)').text().trim(),
        First_Name: $(this).find('td:nth-child(3)').text().trim(),
        Last_Name: $(this).find('td:nth-child(4)').text().trim(),
        DOB: $(this).find('td:nth-child(5)').text().trim(),
        Active: $(this).find('td:nth-child(6) i').hasClass('smr-green') ? 'Yes' : 'No',
        Official: $(this).find('td:nth-child(7) i').hasClass('smr-green') ? 'Yes' : 'No',
        Teamsheets: $(this).find('td:nth-child(8) i').hasClass('smr-green') ? 'Yes' : 'No',
        Registration_Date: $(this).find('td:nth-child(9)').text().trim(),
        Start_Date: $(this).find('td:nth-child(10)').text().trim(),
        Expiry: $(this).find('td:nth-child(11)').text().trim(),
        Season: $(this).find('td:nth-child(12)').text().trim(),
        Primary_Dual: $(this).find('td:nth-child(13)').text().trim(),
        Actions: $(this).find('td:nth-child(14) a').attr('href')
      };
      tableData.push(rowData);
    });

    return tableData;
  }

  function _extractIdFromMemberDetailUrl(url) {
    var match = url.match(/member-detail\/(\d+)/);
    return match ? match[1] : null;
  }

function testFetch() {
  if (!maybeLoggedIntoREMS() && !loginToREMSAdmin()) {
    Logger.log("testGet failed: Could not get logged in");
  }
  var detail = MemberDetail.getByRemsId("SC24176394", CURRENT_SEASON_ID);
  Logger.log(detail);
}
