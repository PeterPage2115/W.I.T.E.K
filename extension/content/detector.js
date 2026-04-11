/**
 * W.I.T.E.K Extension — Page Detector
 * Detects which Travian page we're on and adds a "Send to W.I.T.E.K" button.
 */

(function () {
  'use strict';

  const url = window.location.href;
  const origin = window.location.origin;

  // Detect page type from URL patterns
  let pageType = 'unknown';
  if (/\/report\b/.test(url) && /id=/.test(url)) {
    // Check if it's a spy report (subject/header contains spy indicators)
    const subject = document.querySelector('#reportWrapper .header .headline .subject');
    const subjectText = subject ? subject.textContent.toLowerCase() : '';
    if (subjectText.includes('szpieg') || subjectText.includes('spy') || subjectText.includes('zwiad')) {
      pageType = 'spy_report';
    } else {
      pageType = 'report';
    }
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
   * Inject "Send to W.I.T.E.K" button on the page
   */
  function injectButton(type) {
    const btn = document.createElement('button');
    btn.id = 'witek-send-btn';
    btn.innerHTML = '⚔️ Wyślij do W.I.T.E.K';
    btn.style.cssText= `
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
        case 'spy_report':
          payload = parseSpyReport();
          action = 'send_spy_report';
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
      btn.innerHTML = '⚔️ Wyślij do W.I.T.E.K';
      btn.style.borderColor= '#d4a017';
      btn.disabled = false;
    }, 3000);
  }

  // ─── Helpers ──────────────────────────────────────────

  /**
   * Extract coords from an element containing .coordinateX / .coordinateY spans.
   * Travian embeds parens in the text: "(76" and "43)"
   */
  function extractCoordsFrom(el) {
    const xEl = el.querySelector('.coordinateX');
    const yEl = el.querySelector('.coordinateY');
    if (xEl && yEl) {
      const x = parseInt(xEl.textContent.replace(/[()]/g, '').trim());
      const y = parseInt(yEl.textContent.replace(/[()]/g, '').trim());
      if (!isNaN(x) && !isNaN(y)) return { x, y };
    }
    return null;
  }

  /**
   * Get current village coords from sidebar (works on dorf1.php, build.php, etc.)
   */
  function getVillageCoords() {
    // Sidebar: active village entry contains "(x|y)" as text
    const active = document.querySelector('.listEntry.village.active');
    if (active) {
      const match = active.textContent.match(/\(\s*(-?\d+)\s*\|\s*(-?\d+)\s*\)/);
      if (match) return { x: parseInt(match[1]), y: parseInt(match[2]) };
    }
    // Fallback: page title
    const titleMatch = document.title.match(/\((-?\d+)\|(-?\d+)\)/);
    if (titleMatch) return { x: parseInt(titleMatch[1]), y: parseInt(titleMatch[2]) };
    return { x: null, y: null };
  }

  /**
   * Extract unit ID string from an img.unit element.
   * Returns "hero" for uhero, or numeric string like "21" for u21.
   */
  function getUnitId(img) {
    if (img.classList.contains('uhero')) return 'hero';
    const match = img.className.match(/\bu(\d+)\b/);
    return match ? match[1] : null;
  }

  /**
   * Parse a role section (.role.attacker or .role.defender) from a report.
   * Returns { player, village, alliance, troops, losses, bounty? }
   */
  function parseRoleSection(roleEl) {
    const data = { troops: {}, losses: {} };

    // Player / village / alliance from headline
    const headline = roleEl.querySelector('.troopHeadline');
    if (headline) {
      data.player = headline.querySelector('a.player')?.textContent?.trim() || '';
      data.village = headline.querySelector('a.village')?.textContent?.trim() || '';
      const allyEl = headline.querySelector('span.inline-block');
      data.alliance = allyEl ? allyEl.textContent.trim().replace(/[\[\]]/g, '') : '';
    }

    // Unit table has multiple tbody.units:
    //   1st = icon row (unit IDs), 2nd = counts, 3rd = losses
    const tbodies = roleEl.querySelectorAll('tbody.units');
    if (tbodies.length < 2) return data;

    // 1st tbody: extract unit IDs from icon images
    const unitIds = [];
    tbodies[0].querySelectorAll('td.uniticon img.unit').forEach((img) => {
      unitIds.push(getUnitId(img));
    });

    // 2nd tbody: troop counts
    tbodies[1].querySelectorAll('td.unit').forEach((cell, i) => {
      if (i < unitIds.length && unitIds[i]) {
        const count = parseInt(cell.textContent.trim()) || 0;
        if (count > 0) data.troops[unitIds[i]] = count;
      }
    });

    // 3rd tbody: losses
    if (tbodies.length >= 3) {
      tbodies[2].querySelectorAll('td.unit').forEach((cell, i) => {
        if (i < unitIds.length && unitIds[i]) {
          const loss = parseInt(cell.textContent.trim()) || 0;
          if (loss > 0) data.losses[unitIds[i]] = loss;
        }
      });
    }

    // Bounty (attacker only — tbody.infos)
    const infosTbody = roleEl.querySelector('tbody.infos');
    if (infosTbody) {
      const bounty = {};
      const resDiv = infosTbody.querySelector('.res');
      if (resDiv) {
        ['lumber', 'clay', 'iron', 'crop'].forEach((res) => {
          const icon = resDiv.querySelector(`i.${res}`);
          if (icon) {
            const valEl = icon.closest('.inlineIcon')?.querySelector('.value');
            if (valEl) bounty[res] = parseInt(valEl.textContent.trim()) || 0;
          }
        });
      }
      const carryMatch = infosTbody.textContent.match(/(\d+)\s*\/\s*(\d+)/);
      if (carryMatch) {
        bounty.carry_used = parseInt(carryMatch[1]);
        bounty.carry_max = parseInt(carryMatch[2]);
      }
      if (Object.keys(bounty).length > 0) data.bounty = bounty;
    }

    return data;
  }

  // ─── Parsers ───────────────────────────────────────────

  /**
   * Parse combat statistics section (battle power, kill cost)
   * Travian HTML: div.combatStatistics > table.combatStatistic
   * Labels in <th>, values in <td> > span.value (numbers may have spaces like "1 755")
   */
  function parseStatistics(reportEl) {
    const stats = {};
    const table = reportEl.querySelector('table.combatStatistic');
    if (!table) return stats;

    const rows = table.querySelectorAll('tbody tr');
    for (const row of rows) {
      const label = row.querySelector('th')?.textContent?.trim().toLowerCase() || '';
      const valueCells = row.querySelectorAll('td');
      if (valueCells.length < 2) continue;

      const atkText = valueCells[0]?.querySelector('.value')?.textContent?.replace(/\D/g, '') || '';
      const defText = valueCells[1]?.querySelector('.value')?.textContent?.replace(/\D/g, '') || '';
      const atkVal = parseInt(atkText, 10);
      const defVal = parseInt(defText, 10);

      if (label.includes('siła') || label.includes('power') || label.includes('strength')) {
        if (!isNaN(atkVal)) stats.battle_power_atk = atkVal;
        if (!isNaN(defVal)) stats.battle_power_def = defVal;
      } else if (label.includes('koszt') || label.includes('cost')) {
        if (!isNaN(atkVal)) stats.kill_cost_atk = atkVal;
        if (!isNaN(defVal)) stats.kill_cost_def = defVal;
      }
    }
    return stats;
  }

  /**
   * Parse battle report page (#reportWrapper)
   */
  function parseReport() {
    const reportEl = document.getElementById('reportWrapper');
    if (!reportEl) return null;

    // Report ID from URL (may contain non-numeric chars like "8230762|311aedc1")
    const idMatch = url.match(/id=([^&\s]+)/);
    const reportId = idMatch ? idMatch[1] : null;

    // Report header: subject and time
    const subject = reportEl.querySelector('.header .headline .subject')?.textContent?.trim() || '';
    const time = reportEl.querySelector('.header .time .text')?.textContent?.trim() || '';

    // Attacker and defender sections
    const attackerEl = reportEl.querySelector('.role.attacker');
    const defenderEl = reportEl.querySelector('.role.defender');

    // Combat statistics (battle power, kill cost)
    const statistics = parseStatistics(reportEl);

    const result = {
      report_id: reportId,
      subject,
      time,
      attacker: attackerEl ? parseRoleSection(attackerEl) : { troops: {}, losses: {} },
      defender: defenderEl ? parseRoleSection(defenderEl) : { troops: {}, losses: {} },
      ...statistics,
    };

    return result;
  }

  /**
   * Parse village troop overview (dorf1.php — #troops table)
   */
  function parseTroops() {
    const coords = getVillageCoords();
    const troops = {};

    const troopTable = document.getElementById('troops');
    if (troopTable) {
      troopTable.querySelectorAll('tbody tr').forEach((row) => {
        const img = row.querySelector('td.ico img.unit');
        const numCell = row.querySelector('td.num');
        if (!img || !numCell) return;

        const unitId = getUnitId(img);
        if (!unitId) return;

        // Filter out Nature units (u31-u40) — they appear on oases
        const numericId = parseInt(unitId);
        if (!isNaN(numericId) && numericId >= 31 && numericId <= 40) return;

        const count = parseInt(numCell.textContent.trim()) || 0;
        if (count > 0) troops[unitId] = count;
      });
    }

    const villageName = document.querySelector('input.villageNameInput')?.value || '';

    return { x: coords.x, y: coords.y, village_name: villageName, troops };
  }

  /**
   * Parse rally point incoming attacks (build.php?gid=16)
   */
  function parseIncoming() {
    const coords = getVillageCoords();
    const incoming = [];

    // Each movement is a separate table.troop_details; inAttack = incoming attack
    document.querySelectorAll('table.troop_details.inAttack').forEach((table) => {
      const entry = {};

      // Source coords from th.coords inside the units tbody
      const coordsTh = table.querySelector('th.coords');
      if (coordsTh) {
        const src = extractCoordsFrom(coordsTh);
        if (src) {
          entry.from_x = src.x;
          entry.from_y = src.y;
        }
      }

      // Movement headline (player/village info)
      const headlineCell = table.querySelector('td.troopHeadline');
      if (headlineCell) {
        entry.description = headlineCell.textContent.trim();
        const link = headlineCell.querySelector('a');
        if (link) entry.player_name = link.textContent.trim();
      }

      // Timer — seconds remaining
      const timerEl = table.querySelector('.timer[counting="down"]');
      if (timerEl) {
        const seconds = parseInt(timerEl.getAttribute('value'));
        if (!isNaN(seconds)) {
          // Convert remaining seconds to arrival unix timestamp
          entry.arrival_unix = Math.floor(Date.now() / 1000) + seconds;
          entry.seconds_remaining = seconds;
        }
      }

      // Troop details: extract unit IDs and counts (if visible)
      const tbodies = table.querySelectorAll('tbody.units');
      if (tbodies.length >= 2) {
        const unitIds = [];
        tbodies[0].querySelectorAll('td.uniticon img.unit').forEach((img) => {
          unitIds.push(getUnitId(img));
        });
        const troops = {};
        tbodies[1].querySelectorAll('td.unit').forEach((cell, i) => {
          if (i < unitIds.length && unitIds[i]) {
            const count = parseInt(cell.textContent.trim()) || 0;
            if (count > 0) troops[unitIds[i]] = count;
          }
        });
        if (Object.keys(troops).length > 0) entry.troops = troops;
      }

      if (entry.from_x != null || entry.arrival_unix) {
        incoming.push(entry);
      }
    });

    return { x: coords.x, y: coords.y, incoming };
  }

  /**
   * Parse spy report page.
   * Extracts target info, resources, troops, and defense buildings.
   */
  function parseSpyReport() {
    const reportEl = document.getElementById('reportWrapper');
    if (!reportEl) return null;

    const result = {
      spy_type: 'resources',
      resources: {},
      troops: {},
      defense_buildings: {},
    };

    // Target info from defender section headline
    const defenderEl = reportEl.querySelector('.role.defender');
    if (defenderEl) {
      const headline = defenderEl.querySelector('.troopHeadline');
      if (headline) {
        result.target_player = headline.querySelector('a.player')?.textContent?.trim() || '';
        result.target_village = headline.querySelector('a.village')?.textContent?.trim() || '';
      }
      // Coordinates from defender section
      const coordEl = defenderEl.querySelector('.coordinateX');
      if (coordEl) {
        const coords = extractCoordsFrom(coordEl.closest('.coordinateContainer') || defenderEl);
        if (coords) {
          result.x = coords.x;
          result.y = coords.y;
        }
      }
    }

    // Fallback: coordinates from any coordinate container in the report
    if (result.x == null) {
      const containers = reportEl.querySelectorAll('.coordinateContainer, [class*="coordinate"]');
      for (const container of containers) {
        const coords = extractCoordsFrom(container);
        if (coords) {
          result.x = coords.x;
          result.y = coords.y;
          break;
        }
      }
    }

    // Resources — look for resource icons (lumber/clay/iron/crop) with values
    const resSection = reportEl.querySelector('.res, .resources, .resourceReport');
    const resContainer = resSection || reportEl;
    ['lumber', 'clay', 'iron', 'crop'].forEach((res) => {
      // Try icon-based: <i class="lumber"> near <span class="value">
      const icon = resContainer.querySelector(`i.${res}, .${res} i, img[class*="${res}"]`);
      if (icon) {
        const parent = icon.closest('.inlineIcon, .resourceWrapper, td, div');
        if (parent) {
          const valEl = parent.querySelector('.value, span, .num');
          if (valEl) {
            const val = parseInt(valEl.textContent.replace(/\D/g, ''));
            if (!isNaN(val)) result.resources[res] = val;
          }
        }
      }
    });

    // Fallback: look for resource cells in table rows
    if (Object.keys(result.resources).length === 0) {
      const resCells = reportEl.querySelectorAll('td .res, td.res');
      const resNames = ['lumber', 'clay', 'iron', 'crop'];
      resCells.forEach((cell, i) => {
        if (i < 4) {
          const val = parseInt(cell.textContent.replace(/\D/g, ''));
          if (!isNaN(val)) result.resources[resNames[i]] = val;
        }
      });
    }

    // Troops — reuse the same pattern as battle reports
    let hasTroops = false;
    const troopSections = reportEl.querySelectorAll('.role.defender tbody.units, table.troop_details tbody.units');
    if (troopSections.length >= 2) {
      const unitIds = [];
      troopSections[0].querySelectorAll('td.uniticon img.unit').forEach((img) => {
        unitIds.push(getUnitId(img));
      });
      troopSections[1].querySelectorAll('td.unit').forEach((cell, i) => {
        if (i < unitIds.length && unitIds[i]) {
          const count = parseInt(cell.textContent.trim()) || 0;
          if (count > 0) {
            result.troops[unitIds[i]] = count;
            hasTroops = true;
          }
        }
      });
    }

    // Defense buildings — look for building info (wall, palace, etc.)
    const buildingKeywords = {
      'mur': 'wall', 'wall': 'wall', 'palisada': 'wall', 'palisade': 'wall',
      'mury': 'wall', 'earth wall': 'wall',
      'pałac': 'palace', 'palace': 'palace',
      'rezydencja': 'residence', 'residence': 'residence',
    };
    const infoRows = reportEl.querySelectorAll('.buildingInfo tr, .defenseInfo tr, tbody.infos tr');
    infoRows.forEach((row) => {
      const label = row.querySelector('td:first-child, th')?.textContent?.trim().toLowerCase() || '';
      const value = row.querySelector('td:last-child, td .value')?.textContent?.trim() || '';
      for (const [keyword, key] of Object.entries(buildingKeywords)) {
        if (label.includes(keyword)) {
          const level = parseInt(value.replace(/\D/g, ''));
          if (!isNaN(level) && level > 0) result.defense_buildings[key] = level;
          break;
        }
      }
    });

    // Determine spy_type
    const hasResources = Object.keys(result.resources).length > 0;
    if (hasResources && hasTroops) {
      result.spy_type = 'both';
    } else if (hasTroops) {
      result.spy_type = 'troops';
    } else {
      result.spy_type = 'resources';
    }

    return result;
  }
})();
