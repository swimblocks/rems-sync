// Function to store cookies in Properties Service
function storeCookies(cookies) {
  var cache = CacheService.getUserCache();
  cache.put('rems_cookies', JSON.stringify(cookies), 43200);  // Expires in 12 hours
}

/**
 * Remove any REMS cookies from the current user's cache.
 */
function clearCookies() {
  var cache = CacheService.getUserCache();
  cache.remove('rems_cookies');
}

// Function to retrieve cookies from Properties Service
function retrieveCookies() {
  var cache = CacheService.getUserCache();
  var cookiesString = cache.get('rems_cookies');
  return cookiesString ? JSON.parse(cookiesString) : {};
}

// Function to update cookies from response headers
function updateCookies(response) {
  var setCookieHeaders = response.getAllHeaders()['Set-Cookie'];
  var cookies = retrieveCookies();

  if (setCookieHeaders) {
    // Convert single cookie string to array if necessary
    if (!Array.isArray(setCookieHeaders)) {
      setCookieHeaders = [setCookieHeaders];
    }

    setCookieHeaders.forEach(function(cookieString) {
      var cookieParts = cookieString.split(';')[0].split('=');
      var name = cookieParts[0].trim();
      var value = cookieParts[1].trim();
      cookies[name] = value;
    });

    storeCookies(cookies);
  }
}

// Function to get cookies as a header string
function getCookiesHeader() {
  var cookies = retrieveCookies();
  if (!cookies) { return null; }

  var cookieArray = [];
  for (var name in cookies) {
    cookieArray.push(name + '=' + cookies[name]);
  }
  return cookieArray.join('; ');
}

/**
 * @returns {HTTPResponse}
 */
function httpRequest(url, options) {
  try {
    var reqHeaders = options["headers"];
    if (!reqHeaders) { reqHeaders = {}; }

    let cookiesHeader = getCookiesHeader();
    if (cookiesHeader) { reqHeaders["Cookie"] = cookiesHeader; } 

    options["headers"] = reqHeaders;
    options["muteHttpExceptions"] = true;

    var response = UrlFetchApp.fetch(url, options);
    var respCode = response.getResponseCode();
    var respHeaders = response.getAllHeaders();
    var respContent = response.getContentText();

    if (response.getResponseCode() == 500) {
      Logger.log(response.getContentText());
      return null;
    }

    updateCookies(response);
    return response;
  } catch (e) {
    Logger.log('Error: ' + e.message);
  }
  return null;
}


/**
 * Parse table data and append to the provided data array
 * @param {CheerioAPI} $
 * @param {Array} data - An array of rows, each containing an array of columns of data.
 * @param {Array} specifiedHeaders - An array of all header names, including constantColumns and table columns.
 * @param {Array} [constantColumns=[]] - An optional nested array where each inner array contains a pair: [header, value].
  */
function appendTableData($, data, specifiedHeaders, constantColumns = []) {
  // Extract table headers
  const tableHeaders = [];
  $('table thead th').each(function () {
    const headerText = $(this).text().trim();
    tableHeaders.push(headerText);
  });

  // Ensure all specified headers are present in the table headers
  const missingHeaders = specifiedHeaders.filter(header => !tableHeaders.includes(header) && !constantColumns.some(constant => constant[0] === header));
  if (missingHeaders.length > 0) {
    Logger.log('Error: Missing expected headers - ' + missingHeaders.join(', '));
    return;
  }

  // Extract constant headers and values
  const constantHeaders = constantColumns.map(constant => constant[0]);

  // Include constant headers in the headers if they exist
  const headers = [...constantHeaders, ...tableHeaders];
  if (data.length == 0) {
    data.push(headers);
  }

  // Extract table data and map to specified headers
  $('table tbody tr').each(function () {
    const row = new Array(specifiedHeaders.length).fill(''); // Start with empty values

    // Add constant values to the correct positions
    constantColumns.forEach((constant, index) => {
      const headerIndex = specifiedHeaders.indexOf(constant[0]);
      row[headerIndex] = constant[1];
    });

    // Add table data values to the correct positions
    $(this).find('td').each(function (index) {
      const header = tableHeaders[index];
      const columnIndex = specifiedHeaders.indexOf(header);

      if (header === 'Actions') {
        const urls = [];
        $(this).find('a').each(function () {
          const url = $(this).attr('href');
          if (url) {
            urls.push(url.trim());
          }
        });
        row[columnIndex] = urls.join(', ');
      } else {
        row[columnIndex] = $(this).text().trim();
      }
    });

    data.push(row);
  });
}

function parseTotalPages($) {
  // Extract pagination info from the initial HTML
  const paginationText = $('.ssm-pagination .no-of-records').text().trim();
  const matches = paginationText.match(/(\d+) of (\d+)/);
  if (matches) {
    return parseInt(matches[2], 10);
  }
  return -1;
}


/**
 * Without trying to login we cannot be sure whether we are, but this will tell you whether
 * we have valid cached cookies which make being logged in possible.
 * 
 * @returns {boolean}
 */
function maybeLoggedIntoREMS() {
  return (isEmptyObject(retrieveCookies())) ? false : true;
}

/** 
 * Returns true if the given object is equivalent to {}
 */
function isEmptyObject(obj) {
  return Object.keys(obj).length === 0 && obj.constructor === Object;
}

/**
 * Log into REMS as an Admin using the provided username and password.  
 * Calls back to the provided callback function to get the user's MFA token. 
 */
function loginToREMSAdmin(username, password, mfaCodeCallback) {
  clearCookies();
  var loginResponse = httpRequest(
    "https://swimming.canada.sportsmanager.ie/Maint-Login.php",
    {
      "method": "post",
      "payload": { "username": username, "password": password },
      "followRedirects": false
    }
  )
  if (!loginResponse) {
    Logger.log("Maint-login.php request error");
    return false;
  } else if (loginResponse.getResponseCode() == 200) {
    Logger.log('Login successful no redirect.');
    return true;
  } else if (loginResponse.getResponseCode() != 302) {
    Logger.log('Login failed: ' + loginResponse.getResponseCode());
    return false;''
  }

  // Follow redirects to mfa-login
  var mfaUrl = loginResponse.getAllHeaders()['Location'];
  var mfaResponse = httpRequest(
    mfaUrl,
    {
      "method": "get",
      "followRedirects": false
    }
  )
  if (!mfaResponse) {
    Logger.log("Error getting MFA url "+mfaUrl);
    return false;
  } else if (mfaResponse.getResponseCode() != 302) {
    Logger.log("Login failed: "+mfaResponse.getResponseCode());
  }

  return doMFA(mfaCodeCallback);
}

function doMFA(mfaCodeCallback) {
  var mfaCode = mfaCodeCallback();

  if (!mfaCode || mfaCode.length != 6) {
    Logger.log("Invalid MFA Code: "+mfaCode);
    return false;
  }
  var payload = {
    "digit_1": mfaCode.charAt(0),
    "digit_2": mfaCode.charAt(1),
    "digit_3": mfaCode.charAt(2),
    "digit_4": mfaCode.charAt(3),
    "digit_5": mfaCode.charAt(4),
    "digit_6": mfaCode.charAt(5)
  }
  var mfaCodeResponse = httpRequest(
    "https://swimming.canada.sportsmanager.ie/sportlomo/users/mfa-verify-otp",
    {
      "method": "post",
      "payload": payload,
      "followRedirects": false
    }
  )
  if (!mfaCodeResponse || mfaCodeResponse.getResponseCode() != 302) {
    Logger.log("MFA Verify Error, response code: "+mfaCodeResponse.getResponseCode());
    return false;
  } else if (mfaCodeResponse.getAllHeaders()['Location'] != "https://swimming.canada.sportsmanager.ie/logged-in.php") {
    Logger.log("MFA Verify not redirected to logged in: "+mfaCodeResponse.getAllHeaders()['Location']);
    return false;
  }
  Logger.log("MFA success");
  return true;
}

function performLoggedInGet(url) {
  var options = {
    "method": "get",
    "headers": {
      "Cookie": getCookiesHeader(),
    },
    "followRedirects": true
  };

  try {
    var response = UrlFetchApp.fetch(url, options);
    if (response.getResponseCode() != 200) {
      Logger.log('Action failed: ' + response.getResponseCode());
      return "";
    }

    Logger.log('Action performed successfully');
    return response;
  } catch (e) {
    Logger.log('Error: ' + e.message);
    return "";
  }    
}

function submitForm(url, payload) {
  var options = {
    "method": "post",
    "payload": payload,
    "headers": {
      "Cookie": getCookiesHeader(),
    },
    "followRedirects": false
  };

  try {
    var response = UrlFetchApp.fetch(url, options);
    if (response.getResponseCode() === 200) {
      Logger.log('Form submitted successfully');
      return response;
    } else {
      Logger.log('Form submission failed: ' + response.getResponseCode());
      return "";
    }
  } catch (e) {
    Logger.log('Error: ' + e.message);
    return "";
  }
}
