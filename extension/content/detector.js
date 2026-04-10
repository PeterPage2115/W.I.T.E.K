/**
 * WITEK Extension — Page Detector
 * Detects which Travian page we're on and adds a "Send to WITEK" button.
 */

(function () {
  'use strict';

  const url = window.location.href;
  const origin = window.location.origin;

  // Detect page type
  let pageType = 'unknown';
  if (/berichte\.php/.test(url) && /id=\d+/.test(url)) {
    pageType = 'report';
  } else if (/build\.php/.test(url) && /gid=16/.test(url)) {
    pageType = 'rally_point';
  } else if (/dorf1\.php/.test(url)) {
    pageType = 'village';
  }

  if (pageType === 'unknown') return;

  // Check if extension is enabled
  chrome.runtime.sendMessage({ action: 'get_config' }, (config) => {
    if (!config || !config.enabled) return;
    injectButton(pageType);
  });

  /**
   * Inject "Send to WITEK" button on the page
   */
  function injectButton(type) {
    const btn = document.createElement('button');
    btn.id = 'witek-send-btn';
    btn.innerHTML = '⚔️ Wyślij do WITEK';
    btn.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 99999;
      padding: 10px 20px;
      background: linear-gradient(135deg, #5a3a1a 0%, #8b6914 100%);
      color: #f0e6d0;
      border: 2px solid #d4a017;
      border-radius: 6px;
      font-family: 'Georgia', serif;
      font-size: 14px;
      font-weight: bold;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5);
      transition: all 0.2s;
    `;
    btn.addEventListener('mouseenter', () => {
      btn.style.background = 'linear-gradient(135deg, #8b6914 0%, #c9a227 100%)';
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.background = 'linear-gradient(135deg, #5a3a1a 0%, #8b6914 100%)';
    });

    btn.addEventListener('click', () => handleSend(type, btn));
    document.body.appendChild(btn);
  }

  /**
   * Handle send button click
   */
  async function handleSend(type, btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Wysyłanie...';

    let payload = null;
    let action = null;

    try {
      switch (type) {
        case 'report':
          payload = parseReport();
          action = 'send_report';
          break;
        case 'village':
          payload = parseTroops();
          action = 'send_troops';
          break;
        case 'rally_point':
          payload = parseIncoming();
          action = 'send_incoming';
          break;
      }

      if (!payload) {
        showStatus(btn, '❌ Nie udało się odczytać danych', false);
        return;
      }

      payload.server_url = origin;

      chrome.runtime.sendMessage({ action, payload }, (response) => {
        if (response && response.success) {
          showStatus(btn, '✅ Wysłano!', true);
        } else {
          showStatus(btn, `❌ ${response?.error || 'Błąd'}`, false);
        }
      });
    } catch (error) {
      showStatus(btn, `❌ ${error.message}`, false);
    }
  }

  /**
   * Show status on button, then reset
   */
  function showStatus(btn, text, success) {
    btn.innerHTML = text;
    btn.style.borderColor = success ? '#2ecc71' : '#e74c3c';
    setTimeout(() => {
      btn.innerHTML = '⚔️ Wyślij do WITEK';
      btn.style.borderColor = '#d4a017';
      btn.disabled = false;
    }, 3000);
  }

  // ─── Parsers ───────────────────────────────────────────

  /**
   * Parse battle report page
   */
  function parseReport() {
    // Find report container
    const reportEl = document.getElementById('report') ||
                     document.querySelector('.reportWrapper') ||
                     document.querySelector('#reportWrapper');
    if (!reportEl) return null;

    // Extract report ID from URL
    const idMatch = url.match(/id=(\d+)/);
    const reportId = idMatch ? parseInt(idMatch[1]) : null;

    // Find troop tables (attacker and defender sections)
    const tables = reportEl.querySelectorAll('table');
    
    const result = {
      report_id: reportId,
      attacker: { troops: {}, losses: {} },
      defender: { troops: {}, losses: {} },
    };

    // Look for player names in report header
    const headers = reportEl.querySelectorAll('.troopHeadline, .role_att, .role_def');
    headers.forEach((h) => {
      const link = h.querySelector('a');
      if (link) {
        const name = link.textContent.trim();
        if (h.classList.contains('role_att') || h.closest('.att')) {
          result.attacker.name = name;
        } else if (h.classList.contains('role_def') || h.closest('.def')) {
          result.defender.name = name;
        }
      }
    });

    // Parse troop tables
    // Travian reports have unit images with class like "unit u1", "unit u2" etc
    const unitSections = reportEl.querySelectorAll('.troops');
    unitSections.forEach((section) => {
      const isAttacker = section.closest('.att') !== null || 
                         section.previousElementSibling?.classList?.contains('role_att');
      const side = isAttacker ? result.attacker : result.defender;
      
      const unitCells = section.querySelectorAll('td.unit');
      const countCells = section.querySelectorAll('td.num, td.count');
      
      unitCells.forEach((cell, i) => {
        const img = cell.querySelector('img');
        if (img) {
          // Extract unit ID from class like "unit u1" or image src
          const unitMatch = img.className.match(/u(\d+)/) || 
                           img.src.match(/u(\d+)/);
          if (unitMatch && countCells[i]) {
            const unitId = unitMatch[1];
            const count = parseInt(countCells[i].textContent.replace(/\D/g, '')) || 0;
            side.troops[unitId] = count;
          }
        }
      });
    });

    // Wall level
    const wallEl = reportEl.querySelector('.wall, .building');
    if (wallEl) {
      const levelMatch = wallEl.textContent.match(/(\d+)/);
      if (levelMatch) {
        result.wall_level_after = parseInt(levelMatch[1]);
      }
    }

    return result;
  }

  /**
   * Parse village troop overview
   */
  function parseTroops() {
    // Get village coordinates from page
    const coordsEl = document.querySelector('.coordinateX, .coords, #side_navi .villageList .active');
    let x = null, y = null;

    // Try getting coords from the village coordinates display
    const xEl = document.querySelector('.coordinateX');
    const yEl = document.querySelector('.coordinateY');
    if (xEl && yEl) {
      x = parseInt(xEl.textContent.replace(/[()]/g, '').trim());
      y = parseInt(yEl.textContent.replace(/[()]/g, '').trim());
    }

    // Alternative: parse from URL or page title
    if (x === null) {
      const coordMatch = document.title.match(/\((-?\d+)\|(-?\d+)\)/);
      if (coordMatch) {
        x = parseInt(coordMatch[1]);
        y = parseInt(coordMatch[2]);
      }
    }

    const troops = {};

    // Find troop display area
    const troopEl = document.querySelector('#troops, .troop_details, .villTroops');
    if (troopEl) {
      const unitEls = troopEl.querySelectorAll('.unit, [class*="unitSmall"]');
      unitEls.forEach((el) => {
        const unitMatch = el.className.match(/u(\d+)/);
        const countEl = el.nextElementSibling || el.parentElement?.querySelector('.num');
        if (unitMatch && countEl) {
          const count = parseInt(countEl.textContent.replace(/\D/g, '')) || 0;
          if (count > 0) {
            troops[unitMatch[1]] = count;
          }
        }
      });
    }

    const villageName = document.querySelector('.villageNameInput, #villageNameField')?.value ||
                        document.querySelector('.village_name, .villageName')?.textContent?.trim() || 
                        '';

    return { x, y, village_name: villageName, troops };
  }

  /**
   * Parse rally point incoming attacks
   */
  function parseIncoming() {
    // Get village coordinates
    const xEl = document.querySelector('.coordinateX');
    const yEl = document.querySelector('.coordinateY');
    let x = null, y = null;
    if (xEl && yEl) {
      x = parseInt(xEl.textContent.replace(/[()]/g, '').trim());
      y = parseInt(yEl.textContent.replace(/[()]/g, '').trim());
    }

    const incoming = [];

    // Find incoming attack rows
    const rows = document.querySelectorAll('#overview tr, .troop_details tr, .movements tr');
    rows.forEach((row) => {
      // Check if it's an incoming attack (not outgoing)
      const typeEl = row.querySelector('.att1, .att2, .att3, img[class*="att"]');
      if (!typeEl) return;

      // Determine attack type from icon
      let type = 'attack';
      if (typeEl.classList.contains('att1') || typeEl.src?.includes('att1')) type = 'raid';
      if (typeEl.classList.contains('att3') || typeEl.src?.includes('att3')) type = 'spy';

      // Source coordinates
      let fromX = null, fromY = null;
      const coordLink = row.querySelector('a[href*="position"]');
      if (coordLink) {
        const coordMatch = coordLink.textContent.match(/\((-?\d+)\|(-?\d+)\)/);
        if (coordMatch) {
          fromX = parseInt(coordMatch[1]);
          fromY = parseInt(coordMatch[2]);
        }
      }

      // Arrival time
      let arrivalUnix = null;
      const timerEl = row.querySelector('.timer, [id*="timer"]');
      if (timerEl) {
        const val = timerEl.getAttribute('value') || timerEl.dataset?.endat;
        if (val) {
          arrivalUnix = parseInt(val);
        }
      }

      // Player name
      const playerEl = row.querySelector('.player a, .playerName');
      const playerName = playerEl?.textContent?.trim() || '';

      if (fromX !== null || arrivalUnix) {
        incoming.push({
          type,
          from_x: fromX,
          from_y: fromY,
          arrival_unix: arrivalUnix,
          player_name: playerName,
        });
      }
    });

    return { x, y, incoming };
  }
})();
