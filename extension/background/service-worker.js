/**
 * W.I.T.E.K Extension — Service Worker (Manifest V3 background)
 * Relays data from content scripts to W.I.T.E.K webhook API.
 */

// Default config
const DEFAULT_CONFIG = {
  serverUrl: '',
  token: '',
  enabled: false,
};

/**
 * Get config from chrome.storage.sync
 */
function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(['witek_config'], (result) => {
      resolve(result.witek_config || DEFAULT_CONFIG);
    });
  });
}

/**
 * Save config to chrome.storage.sync
 */
function saveConfig(config) {
  return new Promise((resolve) => {
    chrome.storage.sync.set({ witek_config: config }, resolve);
  });
}

/**
 * Send data to W.I.T.E.K API
 */
async function sendToApi(endpoint, payload) {
  const config = await getConfig();

  if (!config.enabled) {
    return { success: false, error: 'Extension disabled' };
  }
  if (!config.serverUrl || !config.token) {
    return { success: false, error: 'Server URL or token not configured' };
  }

  const url = `${config.serverUrl.replace(/\/$/, '')}${endpoint}`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Witek-Token': config.token,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text();
      return { success: false, error: `HTTP ${response.status}: ${text}` };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

/**
 * Test connection to W.I.T.E.K server
 */
async function testConnection(serverUrl, token) {
  const url = `${serverUrl.replace(/\/$/, '')}/api/ext/troops`;
  try {
    const response = await fetch(url, {
      method: 'OPTIONS',
      headers: { 'X-Witek-Token': token },
    });
    return { success: response.ok || response.status === 204 };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Message handler
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'send_report') {
    sendToApi('/api/ext/report', request.payload)
      .then(sendResponse);
    return true;
  }

  if (request.action === 'send_spy_report') {
    sendToApi('/api/ext/spy-report', request.payload)
      .then(sendResponse);
    return true;
  }

  if (request.action === 'send_troops') {
    sendToApi('/api/ext/troops', request.payload)
      .then(sendResponse);
    return true;
  }

  if (request.action === 'send_incoming') {
    sendToApi('/api/ext/incoming', request.payload)
      .then(sendResponse);
    return true;
  }

  if (request.action === 'get_config') {
    getConfig().then(sendResponse);
    return true;
  }

  if (request.action === 'save_config') {
    saveConfig(request.config).then(() => {
      sendResponse({ success: true });
    });
    return true;
  }

  if (request.action === 'test_connection') {
    testConnection(request.serverUrl, request.token)
      .then(sendResponse);
    return true;
  }
});

console.log('[W.I.T.E.K] Service worker started');
