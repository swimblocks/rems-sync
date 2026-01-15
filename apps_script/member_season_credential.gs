/**
 * Member credentials found on the following SportLomo pages:
 * - ${BASE_URL}/user/credentials/member-credentials-details/${memberSeasonId}/${memberId}
 */
class MemberSeasonCredential {
  /**
   * Constructor to initialize the MemberSeasonCredentials instance with individual data fields.
   * @param {string} remsId - REMS ID
   * @param {string} memberId - REMS Member ID
   * @param {string} memberSeasonId - Sportlomo Member Season ID 
   * @param {string} name - Name
   * @param {string} type - Type
   * @param {string} firstName - First Name
   * @param {string} lastName - Last Name
   * @param {string} status - Status
   * @param {string} startDate - Start Date
   * @param {string} expiryDate - Expiry Date
   * @param {string} actions - Actions
   */
  constructor(remsId, memberId, memberSeasonId, name, type, firstName, lastName, status, startDate, expiryDate, actions) {
    /** 
     * The Swimming Canada REMS Member ID which is stable across seasons and is specific to Swimming Canada.
     * Sportlomo never uses these identifiers in URIs or form fields other than searches.
     * 
     * @type {string}
     * @example "SC24176394"
     */  
    this.rems_id = remsId;

    /** 
     * The Sportlomo Member ID which is stable across seasons.  Usually 6 digits, unclear if this is required.
     * @type {number}
     * @example 217268
     */  
    this.member_id = memberId;

    /** 
     * The Sportlomo Member "Season" ID which identifies the member in a particular season.  Usually 6 digits, unclear if this is required.
     * NOTE: this is a term I made up to describe the second last integer identifier in urls like
     *       $baseUrl/user/credentials/add-member-credential/$memberSeasonId/$memberId because that identifier is different
     *       depending on the season and member.
     * @type {number}
     * @example 595775
     */      
    this.member_season_id = memberSeasonId;

    /** 
     * The name of the credential type.
     * @type {string}
     * @example "Inspector of Turns Evaluation #2"
     */  
    this.name = name;

    /**
     * The overall category of credential, usually "Deck Evaluation" in this codebase.
     * @type {string}
     * @example "Deck Evaluation"
     */
    this.type = type;

    /**
     * @type {string}
     */
    this.first_name = firstName;

    /**
     * @type {string}
     */
    this.last_name = lastName;

    /**
     * A human readable version of the state, but slightly different since 80 is "Active" in dropdowns but corresponds
     * to "Approved" in the current_status so there's probably some subtle difference between the fields that are 
     * currently opaque to me.
     * 
     * @type {string}
     * @example "Approved"
     */
    this.status = status;

    /**
     * The "dd/mm/yyyy" date on which this member "started" having this credential.
     * @type {string}
     * @example "25/12/1978"
     */
    this.start_date = startDate;

    /**
     * The "dd/mm/yyyy" date on which this member "stops" having this credential.
     * @type {string}
     * @example "25/12/1978"
     */
    this.expiry_date = expiryDate;

    /**
     * Any array of URLs representing actions that can be taken on this MemberSeasonCredential.
     * 
     * @type []{string}
     */
    this.actions = actions;
  }


  /**
   * Get a table of Member Credentials Details for a current season member.
   * 
   * @param {MemberSeasonDetail} memberSeasonDetails A {MemberSeasonDetail} which includes all the ids for this member.
   * @returns []{MemberSeasonCredentials} Rows of data containing the member's credentials, starts with a header row.
   */
  static fetch(memberSeasonDetails, pageSize = 100) {
    return MemberSeasonCredential.fetchById(memberSeasonDetails.rems_id,
                     memberSeasonDetails.member_id,
                     memberSeasonDetails.member_season_id,
                     pageSize);
  }

  /**
   * Get a table of Member Credentials Details for a member who was active in some season.
   * 
   * @param {number} remsId The Swimming Canada REMS identifier of the member.
   * @param {number} memberId The season-agnostic Sportlomo identifier of the member.
   * @param {number} memberSeasonId The Sportlomo identifier of the member for a season. 
   * @returns [][]string Rows of data containing the member's credentials, starts with a header row.
   */
  static fetchById(remsId, memberId, memberSeasonId, pageSize = 100) {
    const data = [];
    let pageNumber = 1;
    let totalPages = 1;

    do {
      // Yes logic says memberSeasonId and memberId are backwards in this URL but Sportlomo's
      // website follows rules that we mortals were not intended to understand.
      let credsUrl = `${BASE_URL}/user/credentials/member-credentials-details/${memberSeasonId}/${memberId}?page=${pageNumber}`;

      const response = httpRequest(
        credsUrl, 
        {
          method: "post",
          payload: { limit: pageSize },
          followRedirects: false,
        }
      );

      if (!response) {
        Logger.log("member-credentials-details request error");
        return data;
      } else if (response.getResponseCode() != 200) {
        Logger.log('member-credentials-details not ok: ' + response.getResponseCode());
        return data;
      }

      const $ = Cheerio.load(response.getContentText());
      const tableHeaders = [ 
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
      // Append table data for the current page
      appendTableData(
        $, 
        data, 
        tableHeaders,
        [
          ["REMS ID", remsId],
          ["Member ID", memberId],
          ["Member Season ID", memberSeasonId]
        ]
      );

      // Check if more data is available
      totalPages = parseTotalPages($);
      pageNumber++;
    } while (pageNumber <= totalPages);

    return data.slice(1).map(row => new MemberSeasonCredential(...row));
  }
}
