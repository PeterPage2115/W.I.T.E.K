/**
 * WITEK Extension Popup — Settings management
 */

const serverUrlEl = document.getElementById('server-url');
const tokenEl = document.getElementById('token');
const enabledEl = document.getElementById('enabled');
const saveBtn = document.getElementById('save-btn');
const testBtn = document.getElementById('test-btn');
const statusEl = document.getElementById('status');

// Load settings on open
document.addEventListener('DOMContentLoaded', () => {
  chrome.runtime.sendMessage({ action: 'get_config' }, (config) => {
    if (config) {
      serverUrlEl.value = config.serverUrl || '';
      tokenEl.value = config.token || '';
      enabledEl.checked = config.enabled || false;
    }
  });
});

// Save settings
saveBtn.addEventListener('click', () => {
  const config = {
    serverUrl: serverUrlEl.value.trim(),
    token: tokenEl.value.trim(),
    enabled: enabledEl.checked,
  };

  if (config.enabled && (!config.serverUrl || !config.token)) {
    showStatus('⚠️ Podaj URL serwera i token przed włączeniem', 'error');
    return;
  }

  chrome.runtime.sendMessage({ action: 'save_config', config }, (response) => {
    if (response && response.success) {
      showStatus('✅ Ustawienia zapisane!', 'success');
    } else {
      showStatus('❌ Błąd zapisu', 'error');
    }
  });
});

// Test connection
testBtn.addEventListener('click', () => {
  const serverUrl = serverUrlEl.value.trim();
  const token = tokenEl.value.trim();

  if (!serverUrl || !token) {
    showStatus('⚠️ Podaj URL serwera i token', 'error');
    return;
  }

  testBtn.disabled = true;
  testBtn.textContent = '⏳ Testowanie...';

  chrome.runtime.sendMessage(
    { action: 'test_connection', serverUrl, token },
    (response) => {
      testBtn.disabled = false;
      testBtn.textContent = '🔗 Testuj połączenie';

      if (response && response.success) {
        showStatus('✅ Połączenie OK!', 'success');
      } else {
        showStatus(`❌ ${response?.error || 'Brak połączenia'}`, 'error');
      }
    }
  );
});

function showStatus(text, type) {
  statusEl.textContent = text;
  statusEl.className = `status ${type}`;
  setTimeout(() => {
    statusEl.textContent = '';
    statusEl.className = 'status';
  }, 4000);
}
