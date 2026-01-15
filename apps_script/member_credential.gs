/**
 * Matches the form field names used by SportLomo on the following member credentials pages:
 * - $baseUrl/user/credentials/view-from-member-profile/$memberSeasonId/$memberId/$memberCredentialId
 * - $baseUrl/user/credentials/add-member-credential/$memberSeasonId/$memberId
 * 
 * Notably the "memberSeasonId" component appears to just need to be the member's current season ID.  So,
 * unlike one might expect in a restful API, any given member credential has many possible URIs as long as
 * the "memberSeasonId" is one of the season ids for the "memberId" and the "memberCredentialId" is for the
 * given memberId.  Why not just have the memberId or memberCredentialIds in the URL?  To spite us. 
 * 
 * WARNING: No etags here. Data race if there are multiple writers to the same member credential.
 */
class MemberCredential {

  constructor() {
    /**
     * The overall category of credential, usually "Deck Evaluation" in this codebase.
     * @type {string}
     * @example "Deck Evaluation"
     */
    this.type = '';

    /** 
     * The name of the credential type.
     * @type {string}
     * @example "Inspector of Turns Evaluation #2"
     */  
    this.name = '';

    /**
     * The short name of the credential type.
     * @type {string}
     * @example "IT Eval #2"
     */
    this.short_name = '';
  
    /**
     * The state of this member credential when it was retrieved from Sportlomo.  This is a number here but of course
     * is some sort of Enum on the Sportlomo side which we should document here. 
     * @type {number}
     * @example 80
     */
    this.original_state = '';

    /**
     * The state that this member credential should be set to when POSTed to Sportlomo.
     * @type {number}
     * @example 80
     */
    this.state = '';

    /**
     * A human readable version of the state, but slightly different since 80 is "Active" in dropdowns but corresponds
     * to "Approved" in the current_status so there's probably some subtle difference between the fields that are 
     * currently opaque to me.
     * 
     * @type {string}
     * @example "Approved"
     */
    this.current_status = '';

    /**
     * The "dd/mm/yyyy" date on which this member "started" having this credential.
     * @type {string}
     * @example "25/12/1978"
     */
    this.start_date = '';

    /**
     * The "dd/mm/yyyy" date on which this member "stops" having this credential.
     * @type {string}
     * @example "25/12/1978"
     */
    this.expiry_date = '';

    /**
     * Additional information related to this member's receipt of this credential, e.g. which session at the meet
     * referenced by the "provider_identifier".
     * @type {string}
     * @example "Session 1, Lane 1/2"
     */
    this.description = '';

    /**
     * The full name of the official who signed the deck evaluation, conducted the clinic, or similar.
     * @type {string}
     * @example "Gavin Bee"
     */
    this.provider = '';

    /** The name of the meet or other string which identifies where the credential was granted. 
     * @type {string}
     * @example "ROW Dean Boles 2025"
     */
    this.provider_identifier = '';
  }

  /**
   * Get from URL like $baseUrl/user/credentials/view-from-member-profile/$memberSeasonId/$memberId/$credentialId
   * @returns {MemberCredential}
   * @throws {Error} If there's an HTTP error or the credential details are not found in the HTML.
   */
  static fetch(memberId, memberSeasonId, credentialId) {
    // Get the member credential data from Sportlomo
    var httpResponse = httpRequest(
      "https://swimming.canada.sportsmanager.ie/sportlomo/user/credentials/view-from-member-profile/"+memberSeasonId+"/"+memberId+"/"+credentialId,
      {
        "method": "get",
        "followRedirects": false
      }
    );
    if (httpResponse.getResponseCode() != 200) {
      throw new Error("Error GETing MemberCredential: "+httpResponse.getResponseCode());
    }

    // Parse the HTML
    var $ = Cheerio.load(httpResponse.getContentText());

    // Navigate to the form section
    var formSection = $('#view-from-member-profile .form-holder form .panel-shadow-box:has(#type)');
    if (!formSection.length) {
      throw new Error("Form section containing member credential details not found.");
    }

    // Create an instance of MemberCredential
    var credential = new MemberCredential();

    // Extract values from the relevant section
    credential.type = formSection.find('#type').val();
    credential.name = formSection.find('#name').val();
    credential.short_name = formSection.find('#short-name').val();
    credential.original_state = formSection.find('input[name="original_state"]').val();
    credential.current_status = formSection.find('#current-status').val();
    credential.start_date = formSection.find('#start-date').val();
    credential.expiry_date = formSection.find('#expiry-date').val();
    credential.description = formSection.find('#description').val();
    credential.provider = formSection.find('#provider').val();
    credential.provider_identifier = formSection.find('#provider-identifier').val();
    credential.state = formSection.find('#state').val();

    return credential;    
  }
}

function testFetch() {
  if (!maybeLoggedIntoREMS() && !loginToREMSAdmin()) {
    Logger.log("testGet failed: Could not get logged in");
  }
  var cred = MemberCredential.fetch(178705, 570939, 191807);
  Logger.log(cred);
}
