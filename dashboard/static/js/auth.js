/**
 * Same-origin browser auth helper for deployment API-key mode.
 *
 * The backend can require FOURD_API_KEY. Browser fetch requests can attach the
 * key as X-API-Key, while iframe previews and file downloads rely on the same
 * key mirrored into a same-origin cookie.
 */
(function () {
  var STORAGE_KEY = "4dpapers_api_key";
  var COOKIE_NAME = "fourd_api_key";
  var nativeFetch = window.fetch.bind(window);
  var promptInFlight = null;

  function readStoredKey() {
    try {
      return localStorage.getItem(STORAGE_KEY) || "";
    } catch (err) {
      return "";
    }
  }

  function readCookieKey() {
    var prefix = COOKIE_NAME + "=";
    var parts = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < parts.length; i++) {
      var item = parts[i].trim();
      if (item.indexOf(prefix) === 0) {
        return decodeURIComponent(item.slice(prefix.length));
      }
    }
    return "";
  }

  function getApiKey() {
    return readStoredKey() || readCookieKey() || "";
  }

  function writeCookie(value) {
    var cookie = COOKIE_NAME + "=" + encodeURIComponent(value) + "; Path=/; SameSite=Lax";
    if (window.location.protocol === "https:") {
      cookie += "; Secure";
    }
    document.cookie = cookie;
  }

  function clearCookie() {
    document.cookie = COOKIE_NAME + "=; Path=/; Max-Age=0; SameSite=Lax";
  }

  function emitChange(reason) {
    document.dispatchEvent(new CustomEvent("fourd-auth-changed", {
      detail: {
        configured: !!getApiKey(),
        reason: reason || "update",
      },
    }));
  }

  function setApiKey(value, reason) {
    var trimmed = String(value || "").trim();
    if (!trimmed) {
      clearApiKey(reason || "empty");
      return "";
    }
    try {
      localStorage.setItem(STORAGE_KEY, trimmed);
    } catch (err) {
      // Ignore storage failures and fall back to the cookie path.
    }
    writeCookie(trimmed);
    emitChange(reason || "saved");
    return trimmed;
  }

  function clearApiKey(reason) {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (err) {
      // Ignore storage failures.
    }
    clearCookie();
    emitChange(reason || "cleared");
  }

  function syncStoredKeyToCookie() {
    var value = readStoredKey();
    if (value && value !== readCookieKey()) {
      writeCookie(value);
    }
  }

  function isSameOriginRequest(input) {
    try {
      var raw = input instanceof Request ? input.url : String(input);
      var url = new URL(raw, window.location.href);
      return url.origin === window.location.origin;
    } catch (err) {
      return false;
    }
  }

  function buildHeaders(input, init, apiKey) {
    var headers = new Headers(input instanceof Request ? input.headers : undefined);
    if (init && init.headers) {
      var extra = new Headers(init.headers);
      extra.forEach(function (value, key) {
        headers.set(key, value);
      });
    }
    if (apiKey) {
      headers.set("X-API-Key", apiKey);
    }
    return headers;
  }

  function cloneInit(init) {
    var next = Object.assign({}, init || {});
    delete next.__fourdAuthRetried;
    return next;
  }

  function promptForApiKey(reason) {
    var current = getApiKey();
    var message = reason === "invalid"
      ? "This 4Dpapers deployment rejected the saved API key. Enter the current deployment API key:"
      : "This 4Dpapers deployment requires an API key. Enter it to continue:";
    var entered = window.prompt(message, current);
    if (entered === null) {
      return "";
    }
    return setApiKey(entered, reason === "invalid" ? "replaced" : "prompted");
  }

  async function ensureApiKey(reason) {
    if (promptInFlight) {
      return promptInFlight;
    }
    promptInFlight = Promise.resolve().then(function () {
      return promptForApiKey(reason);
    }).finally(function () {
      promptInFlight = null;
    });
    return promptInFlight;
  }

  async function authorizedFetch(input, init) {
    if (!isSameOriginRequest(input)) {
      return nativeFetch(input, init);
    }

    var apiKey = getApiKey();
    var requestInit = cloneInit(init);
    requestInit.headers = buildHeaders(input, requestInit, apiKey);

    var response = await nativeFetch(input, requestInit);
    if (response.status !== 401 || (init && init.__fourdAuthRetried)) {
      return response;
    }

    var replacementKey = await ensureApiKey(apiKey ? "invalid" : "missing");
    if (!replacementKey) {
      return response;
    }

    var retryInit = Object.assign({}, init || {}, { __fourdAuthRetried: true });
    return authorizedFetch(input, retryInit);
  }

  function updateSettingsUi() {
    var input = document.getElementById("deploymentApiKey");
    var status = document.getElementById("deploymentApiKeyStatus");
    var key = getApiKey();

    if (input && document.activeElement !== input) {
      input.value = key;
    }
    if (status) {
      status.textContent = key ? "Saved in this browser" : "Not configured";
      status.style.color = key ? "#22c55e" : "#f59e0b";
    }
  }

  function bindSettingsUi() {
    var input = document.getElementById("deploymentApiKey");
    var save = document.getElementById("deploymentApiKeySave");
    var clear = document.getElementById("deploymentApiKeyClear");
    if (!input || !save || !clear) {
      return;
    }

    save.addEventListener("click", function () {
      setApiKey(input.value, "saved");
      updateSettingsUi();
    });

    clear.addEventListener("click", function () {
      clearApiKey("cleared");
      input.value = "";
      updateSettingsUi();
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        save.click();
      }
    });

    updateSettingsUi();
  }

  syncStoredKeyToCookie();
  window.fetch = authorizedFetch;
  window.FOURD_AUTH = {
    getApiKey: getApiKey,
    setApiKey: setApiKey,
    clearApiKey: clearApiKey,
    ensureApiKey: ensureApiKey,
  };

  document.addEventListener("DOMContentLoaded", bindSettingsUi);
  document.addEventListener("fourd-auth-changed", updateSettingsUi);
})();
