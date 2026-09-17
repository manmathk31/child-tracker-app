/**
 * ChildTrack Live Safety Monitoring Dashboard Engine
 * 
 * Manages periodic auto-polling (/api/v1/dashboard/live), DOM hydration,
 * client-side search/filter, and real-time room occupancy grid updates.
 */

(function () {
  'use strict';

  let pollIntervalId = null;
  let isAutoRefreshActive = true;
  let currentClassFilter = '';
  let currentSearchQuery = '';
  let isFetching = false;

  // DOM Elements
  const totalStudentsEl = document.getElementById('metric-total-students');
  const trackableStudentsEl = document.getElementById('metric-trackable-students');
  const attentionStudentsEl = document.getElementById('metric-attention-students');
  const activeAlertsEl = document.getElementById('metric-active-alerts');
  const occupancyGridEl = document.getElementById('occupancy-grid');
  const roamingZoneCardEl = document.getElementById('roaming-zone-card');
  const studentsListEl = document.getElementById('students-grid');
  const alertsFeedEl = document.getElementById('alerts-feed-list');
  const searchInputEl = document.getElementById('student-search-input');
  const classFilterSelectEl = document.getElementById('class-filter-select');
  const toggleAutoBtn = document.getElementById('toggle-auto-refresh-btn');
  const statusIndicatorEl = document.getElementById('live-status-indicator');
  const lastUpdatedEl = document.getElementById('live-last-updated');

  function updateStatus(state, text) {
    if (!statusIndicatorEl) return;
    statusIndicatorEl.className = 'status-pill ' + state;
    const dot = statusIndicatorEl.querySelector('.status-dot');
    const label = statusIndicatorEl.querySelector('.status-label');
    if (label) label.textContent = text;
  }

  function getInitials(name) {
    if (!name) return '??';
    const parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }

  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  async function fetchLiveDashboard() {
    if (isFetching) return;
    isFetching = true;

    try {
      updateStatus('attention', 'Updating...');
      const url = new URL('/api/v1/dashboard/live', window.location.origin);
      if (currentClassFilter) {
        url.searchParams.set('class_name', currentClassFilter);
      }

      const res = await fetch(url.toString(), {
        headers: {
          'Accept': 'application/json'
        }
      });

      if (!res.ok) {
        throw new Error('HTTP ' + res.status);
      }

      const data = await res.json();
      renderDashboard(data);

      updateStatus('online', 'Live');
      if (lastUpdatedEl) {
        const d = new Date();
        lastUpdatedEl.textContent = 'Updated ' + d.toLocaleTimeString();
      }
    } catch (err) {
      console.warn('[ChildTrack Live Dashboard] Polling error:', err);
      updateStatus('offline', 'Offline');
    } finally {
      isFetching = false;
    }
  }

  function renderDashboard(data) {
    if (!data) return;

    // 1. Update Metrics
    if (data.metrics) {
      if (totalStudentsEl) totalStudentsEl.textContent = data.metrics.total_students;
      if (trackableStudentsEl) trackableStudentsEl.textContent = data.metrics.trackable_students;
      if (attentionStudentsEl) attentionStudentsEl.textContent = data.metrics.attention_students;
      if (activeAlertsEl) activeAlertsEl.textContent = data.metrics.active_alerts_count;
    }

    // 2. Render Room Occupancy Grid
    if (occupancyGridEl && Array.isArray(data.zones)) {
      renderOccupancyGrid(data.zones, data.roaming_zone);
    }

    // 3. Render Student Cards Grid
    if (studentsListEl && Array.isArray(data.students)) {
      renderStudentsGrid(data.students);
    }

    // 4. Render Active Alerts Feed
    if (alertsFeedEl) {
      renderAlertsFeed(data.active_alerts || []);
    }
  }

  function renderOccupancyGrid(zones, roamingZone) {
    if (zones.length === 0 && (!roamingZone || roamingZone.occupant_count === 0)) {
      return; // Keep existing empty state if no zones exist
    }

    let html = '';

    // Physical Rooms
    zones.forEach(zone => {
      const hasRestricted = zone.has_restricted_student;
      const cardBorder = hasRestricted ? 'border: 2px solid var(--color-danger); background: #fff5f5;' : 'border: 1px solid var(--color-border);';
      const badgeClass = zone.occupant_count > 0 ? 'online' : 'offline';

      html += `
        <div class="card room-card" style="${cardBorder} margin-bottom: 0; display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--space-2);">
              <div>
                <h3 style="font-size: var(--font-size-base); font-weight: var(--font-weight-bold); color: var(--color-text-primary); margin: 0;">
                  <a href="/zones/${zone.zone_id}" style="color: inherit; text-decoration: none;">📍 ${escapeHtml(zone.zone_name)}</a>
                </h3>
                ${zone.building || zone.floor ? `
                  <div style="font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: 2px;">
                    ${escapeHtml(zone.building || '')} ${zone.floor ? '• ' + escapeHtml(zone.floor) : ''}
                  </div>
                ` : ''}
              </div>
              <span class="status-pill ${badgeClass}" style="font-size: 11px; padding: 2px 8px; min-height: 24px;">
                ${zone.occupant_count} ${zone.occupant_count === 1 ? 'Student' : 'Students'}
              </span>
            </div>

            ${hasRestricted ? `
              <div style="display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: var(--font-weight-bold); color: var(--color-danger); margin-bottom: var(--space-2);">
                <span>⚠️</span> Restricted Zone Violation
              </div>
            ` : ''}

            <!-- Occupant Avatar Chips -->
            <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-top: var(--space-2);">
              ${zone.occupants && zone.occupants.length > 0 ? zone.occupants.map(occ => `
                <a href="/students/${occ.student_id}" 
                   title="${escapeHtml(occ.full_name)} (${escapeHtml(occ.class_name)}) ${occ.is_restricted ? '— RESTRICTED' : ''}" 
                   style="text-decoration: none;">
                  <div style="display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: var(--radius-full); font-size: 11px; font-weight: var(--font-weight-medium); ${occ.is_restricted ? 'background: var(--color-danger); color: white;' : 'background: var(--color-bg-subtle); color: var(--color-text-primary); border: 1px solid var(--color-border);'}">
                    <span style="font-weight: var(--font-weight-bold);">${getInitials(occ.full_name)}</span>
                    <span>${escapeHtml(occ.full_name.split(' ')[0])}</span>
                    ${occ.battery_percent !== null && occ.battery_percent !== undefined ? `<span style="opacity: 0.8; font-size: 10px;">🔋${occ.battery_percent}%</span>` : ''}
                  </div>
                </a>
              `).join('') : `
                <span style="font-size: var(--font-size-xs); color: var(--color-text-muted); font-style: italic;">
                  No students currently detected in room
                </span>
              `}
            </div>
          </div>
        </div>
      `;
    });

    occupancyGridEl.innerHTML = html;

    // Roaming / Low Confidence Zone
    if (roamingZoneCardEl && roamingZone) {
      const roamingCount = roamingZone.occupant_count || 0;
      const countBadge = roamingZoneCardEl.querySelector('.roaming-count');
      const listContainer = roamingZoneCardEl.querySelector('.roaming-occupants-list');

      if (countBadge) {
        countBadge.textContent = roamingCount + ' ' + (roamingCount === 1 ? 'Student' : 'Students');
      }

      if (listContainer) {
        if (roamingZone.occupants && roamingZone.occupants.length > 0) {
          listContainer.innerHTML = roamingZone.occupants.map(occ => `
            <a href="/students/${occ.student_id}" title="${escapeHtml(occ.full_name)}" style="text-decoration: none;">
              <div style="display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: var(--radius-full); font-size: 11px; background: #fff3cd; color: #856404; border: 1px solid #ffeeba;">
                <span>⚠️</span>
                <span>${escapeHtml(occ.full_name)}</span>
                <span style="font-size: 10px; opacity: 0.8;">(${escapeHtml(occ.class_name)})</span>
              </div>
            </a>
          `).join('');
        } else {
          listContainer.innerHTML = `
            <span style="font-size: var(--font-size-xs); color: var(--color-text-muted); font-style: italic;">
              None (All active wearables are localized in registered rooms)
            </span>
          `;
        }
      }
    }
  }

  function renderStudentsGrid(students) {
    const q = currentSearchQuery.trim().toLowerCase();

    // Client-side search filtering
    const filtered = students.filter(s => {
      if (!q) return true;
      const name = (s.full_name || '').toLowerCase();
      const code = (s.student_code || '').toLowerCase();
      const tag = (s.device_code || '').toLowerCase();
      const zone = (s.current_zone_name || '').toLowerCase();
      const className = (s.class_name || '').toLowerCase();
      return name.includes(q) || code.includes(q) || tag.includes(q) || zone.includes(q) || className.includes(q);
    });

    if (filtered.length === 0) {
      studentsListEl.innerHTML = `
        <div style="grid-column: 1 / -1; padding: var(--space-6); text-align: center; color: var(--color-text-muted);">
          No students match the active search or class filter.
        </div>
      `;
      return;
    }

    studentsListEl.innerHTML = filtered.map(s => {
      const isRestricted = s.is_restricted;
      const statusLevel = s.status_level || 'offline';
      const cardBorder = isRestricted ? 'border: 2px solid var(--color-danger); background: #fffdfd;' : 'border: 1px solid var(--color-border);';

      return `
        <div class="card student-card" style="${cardBorder} margin-bottom: 0; display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-3);">
              <div style="display: flex; align-items: center; gap: var(--space-3);">
                <div style="width: 42px; height: 42px; border-radius: var(--radius-full); background: var(--color-primary-light); color: var(--color-primary); font-size: var(--font-size-sm); font-weight: var(--font-weight-bold); display: flex; align-items: center; justify-content: center;">
                  ${getInitials(s.full_name)}
                </div>
                <div>
                  <div style="font-weight: var(--font-weight-bold); font-size: var(--font-size-base); color: var(--color-text-primary);">
                    <a href="/students/${s.student_id}" style="color: inherit; text-decoration: none;">${escapeHtml(s.full_name)}</a>
                  </div>
                  <div style="font-size: var(--font-size-xs); color: var(--color-text-secondary);">
                    ${escapeHtml(s.student_code)} • ${escapeHtml(s.class_name)}
                  </div>
                </div>
              </div>

              <span class="status-pill ${statusLevel}" style="font-size: 11px; padding: 2px 8px; min-height: 24px;">
                <span class="status-dot"></span>
                <span>${statusLevel.toUpperCase()}</span>
              </span>
            </div>

            <!-- Current Room -->
            <div style="background: var(--color-bg-subtle); border-radius: var(--radius-md); padding: var(--space-2) var(--space-3); margin-bottom: var(--space-3);">
              <div style="font-size: 11px; color: var(--color-text-secondary); text-transform: uppercase; font-weight: var(--font-weight-semibold);">
                Estimated Location
              </div>
              <div style="font-size: var(--font-size-sm); font-weight: var(--font-weight-bold); margin-top: 2px; display: flex; align-items: center; justify-content: space-between;">
                ${s.current_zone_name ? `
                  <span style="color: ${isRestricted ? 'var(--color-danger)' : 'var(--color-success)'};">
                    📍 ${escapeHtml(s.current_zone_name)}
                  </span>
                  <span style="font-size: 11px; font-weight: normal; color: var(--color-text-muted);">
                    ${Math.round(s.confidence * 100)}% conf
                  </span>
                ` : `
                  <span style="color: var(--color-warning);">
                    ⚠️ Unknown / Roaming
                  </span>
                `}
              </div>
              ${isRestricted ? `
                <div style="margin-top: 4px; font-size: 11px; color: var(--color-danger); font-weight: var(--font-weight-bold);">
                  🚫 Outside permitted safe zones!
                </div>
              ` : ''}
            </div>

            <!-- Hardware Tag Info -->
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: var(--font-size-xs); color: var(--color-text-secondary);">
              <div>
                Tag: <strong style="font-family: monospace;">${escapeHtml(s.device_code || 'Unpaired')}</strong>
              </div>
              <div>
                ${s.battery_percent !== null && s.battery_percent !== undefined ? `
                  <span style="font-weight: var(--font-weight-semibold); color: ${s.battery_percent <= 20 ? 'var(--color-danger)' : 'var(--color-text-primary)'};">
                    🔋 ${s.battery_percent}%
                  </span>
                ` : '—'}
              </div>
            </div>
          </div>

          <div style="margin-top: var(--space-3); padding-top: var(--space-2); border-top: 1px solid var(--color-border-subtle); display: flex; justify-content: space-between; align-items: center;">
            <a href="/students/${s.student_id}/history" style="font-size: var(--font-size-xs); color: var(--color-primary); font-weight: var(--font-weight-medium);">
              Movement Timeline &rarr;
            </a>
            <a href="/students/${s.student_id}" style="font-size: var(--font-size-xs); color: var(--color-text-secondary);">
              Profile
            </a>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderAlertsFeed(alerts) {
    if (!alertsFeedEl) return;

    if (alerts.length === 0) {
      alertsFeedEl.innerHTML = `
        <div style="padding: var(--space-4); text-align: center; color: var(--color-success); font-size: var(--font-size-sm); background: var(--color-status-green-bg); border-radius: var(--radius-md); border: 1px solid var(--color-status-green-border);">
          ✓ All clear — No active safety alerts. All monitored students are in authorized safe zones.
        </div>
      `;
      return;
    }

    alertsFeedEl.innerHTML = alerts.map(a => {
      const severityColor = a.severity === 'critical' ? 'var(--color-danger)' : (a.severity === 'warning' ? 'var(--color-warning)' : 'var(--color-primary)');
      const dateStr = a.created_at ? new Date(a.created_at).toLocaleTimeString() : '—';

      return `
        <li style="display: flex; justify-content: space-between; align-items: center; padding: var(--space-3); border-bottom: 1px solid var(--color-border-subtle); gap: var(--space-3); flex-wrap: wrap;">
          <div style="display: flex; align-items: center; gap: var(--space-3);">
            <span style="display: inline-block; width: 10px; height: 10px; border-radius: var(--radius-full); background: ${severityColor};"></span>
            <div>
              <div style="font-weight: var(--font-weight-bold); font-size: var(--font-size-sm); color: var(--color-text-primary);">
                ${escapeHtml(a.message)}
              </div>
              <div style="font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: 2px;">
                Type: <strong>${escapeHtml(a.type)}</strong> • ${dateStr}
              </div>
            </div>
          </div>
          <div>
            <button onclick="window.acknowledgeAlert('${a.id}')" class="btn btn-secondary" style="font-size: var(--font-size-xs); min-height: 28px; padding: 2px 10px;">
              Acknowledge
            </button>
          </div>
        </li>
      `;
    }).join('');
  }

  // Global acknowledge action
  window.acknowledgeAlert = async function (alertId) {
    try {
      const res = await fetch(`/api/v1/alerts/${alertId}/acknowledge`, {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      if (res.ok) {
        fetchLiveDashboard();
      }
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  };

  function startPolling() {
    if (pollIntervalId) clearInterval(pollIntervalId);
    pollIntervalId = setInterval(fetchLiveDashboard, 5000);
    isAutoRefreshActive = true;
    if (toggleAutoBtn) {
      toggleAutoBtn.innerHTML = '⏸️ Pause Auto-Refresh';
      toggleAutoBtn.classList.remove('btn-secondary');
      toggleAutoBtn.classList.add('btn-secondary');
    }
    updateStatus('online', 'Live');
  }

  function stopPolling() {
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
    isAutoRefreshActive = false;
    if (toggleAutoBtn) {
      toggleAutoBtn.innerHTML = '▶️ Resume Auto-Refresh';
    }
    updateStatus('attention', 'Paused');
  }

  // Initialize
  document.addEventListener('DOMContentLoaded', () => {
    // Initial fetch to sync real-time DOM
    fetchLiveDashboard();

    // Start 5-second polling
    startPolling();

    // Toggle button
    if (toggleAutoBtn) {
      toggleAutoBtn.addEventListener('click', () => {
        if (isAutoRefreshActive) {
          stopPolling();
        } else {
          startPolling();
          fetchLiveDashboard();
        }
      });
    }

    // Search filter input
    if (searchInputEl) {
      searchInputEl.addEventListener('input', (e) => {
        currentSearchQuery = e.target.value;
        // Re-filter immediately using cached DOM data
        fetchLiveDashboard();
      });
    }

    // Class filter select
    if (classFilterSelectEl) {
      classFilterSelectEl.addEventListener('change', (e) => {
        currentClassFilter = e.target.value;
        fetchLiveDashboard();
      });
    }
  });

})();
