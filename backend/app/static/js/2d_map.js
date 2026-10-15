/**
 * 2D Live Campus Spatial Map Engine
 * Manages real-time telemetry polling, stable room-anchored student markers,
 * spatial inspection, zoom controls, and instant student search.
 */

const mapApp = (function() {
    // State
    let studentMarkers = {};     // student_id -> { element, currentZoneId, data }
    let roomCards = {};          // zone_id -> DOM element
    let fetchInterval = null;
    let currentSelectedStudentId = null;
    let latestData = null;
    let currentZoom = 1.0;
    let sidePanelOpen = true;
    let currentSearchTerm = "";

    // DOM references
    const roomsGrid = document.getElementById('rooms-grid-container');
    const transitCanvasArea = document.getElementById('transit-canvas-area');
    const transitCountLabel = document.getElementById('transit-count-label');
    const lastUpdatedText = document.getElementById('last-updated-text');
    
    // KPI Badges
    const kpiTotalStudents = document.getElementById('kpi-total-students');
    const kpiTotalZones = document.getElementById('kpi-total-zones');
    const kpiAttentionCount = document.getElementById('kpi-attention-count');
    
    // Panels
    const mapSidePanel = document.getElementById('map-side-panel');
    const generalOverviewView = document.getElementById('general-overview-view');
    const studentInspectorView = document.getElementById('student-inspector-view');
    const overviewZonesList = document.getElementById('overview-zones-list');
    const overviewZoneCount = document.getElementById('overview-zone-count');

    // Student Inspector Fields
    const spAvatar = document.getElementById('sp-avatar');
    const spName = document.getElementById('sp-name');
    const spClass = document.getElementById('sp-class');
    const spStatusBadge = document.getElementById('sp-status-badge');
    const spZone = document.getElementById('sp-zone');
    const spDistance = document.getElementById('sp-distance');
    const spBattery = document.getElementById('sp-battery');
    const spDevice = document.getElementById('sp-device');
    const spLink = document.getElementById('sp-link');

    /**
     * Compute a deterministic angle from student ID for stable positioning
     */
    function getSeededAngle(uuidStr) {
        if (!uuidStr) return 0;
        let sum = 0;
        for (let i = 0; i < Math.min(8, uuidStr.length); i++) {
            sum += uuidStr.charCodeAt(i);
        }
        return (sum * 137.5) * (Math.PI / 180);
    }

    /**
     * Calculate room percentage coordinates for a student
     * Uses distance factor (1 - confidence) with stable angular spread
     */
    function calculateRoomPosition(studentId, confidence) {
        const angle = getSeededAngle(studentId);
        // Distance factor: confidence 1.0 (very close to center AP) -> factor 0.12
        // confidence 0.2 (edge of room) -> factor 0.38
        const clampedConf = Math.max(0.1, Math.min(1.0, confidence || 0.5));
        const distanceFactor = 0.10 + (1.0 - clampedConf) * 0.28;

        // Spread in percentage from center (50%, 50%)
        const xPercent = 50 + Math.cos(angle) * (distanceFactor * 100);
        const yPercent = 50 + Math.sin(angle) * (distanceFactor * 100);

        return {
            x: Math.max(12, Math.min(88, xPercent)),
            y: Math.max(15, Math.min(85, yPercent))
        };
    }

    /**
     * Fetch latest live occupancy from backend API
     */
    async function fetchMapData() {
        try {
            if (lastUpdatedText) {
                lastUpdatedText.textContent = "Syncing radar...";
            }
            const response = await fetch('/api/v1/dashboard/live', {
                headers: { 'Accept': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`API response status: ${response.status}`);
            }

            const data = await response.json();
            latestData = data;
            renderMap(data);

            const now = new Date();
            if (lastUpdatedText) {
                lastUpdatedText.textContent = `Live • ${now.toLocaleTimeString()}`;
            }
        } catch (error) {
            console.warn("Map telemetry sync warning:", error);
            if (lastUpdatedText) {
                lastUpdatedText.textContent = "Sync paused. Retrying...";
            }
        }
    }

    /**
     * Render entire map state: rooms, transit area, and student markers
     */
    function renderMap(data) {
        const zones = data.zones || [];
        const roamingZone = data.roaming_zone || { occupants: [] };
        const metrics = data.metrics || {};

        // Update KPI counters
        if (kpiTotalStudents) kpiTotalStudents.textContent = metrics.trackable_students ?? 0;
        if (kpiTotalZones) kpiTotalZones.textContent = zones.length;
        if (kpiAttentionCount) kpiAttentionCount.textContent = metrics.attention_students ?? 0;
        if (overviewZoneCount) overviewZoneCount.textContent = `${zones.length} Rooms`;

        // 1. Render / Update Room Cards in Grid
        let overviewHTML = '';
        const activeZoneIds = new Set();

        zones.forEach(zone => {
            if (!zone.zone_id) return;
            activeZoneIds.add(zone.zone_id);

            // Side panel overview item
            overviewHTML += `
                <div style="background: var(--color-bg); padding: 12px; border-radius: var(--radius-md); margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; border-left: 3px solid ${zone.has_restricted_student ? 'var(--color-status-red)' : 'var(--color-primary)'};">
                    <div>
                        <div style="font-weight: 600; font-size: 0.85rem; color: var(--color-text-primary);">${escapeHtml(zone.zone_name)}</div>
                        <div style="font-size: 11px; color: var(--color-text-muted);">${zone.building ? escapeHtml(zone.building) : 'Main Building'}${zone.floor ? ' • ' + escapeHtml(zone.floor) : ''}</div>
                    </div>
                    <span class="room-occupancy-badge ${zone.has_restricted_student ? 'danger' : ''}">
                        ${zone.occupant_count} ${zone.occupant_count === 1 ? 'Student' : 'Students'}
                    </span>
                </div>
            `;

            let card = roomCards[zone.zone_id];
            if (!card) {
                card = document.createElement('div');
                card.className = 'map-room-card';
                card.id = `room-card-${zone.zone_id}`;

                card.innerHTML = `
                    <div class="room-header">
                        <div class="room-title-area">
                            <div class="room-name-text">
                                <svg style="width: 16px; height: 16px; color: var(--color-primary);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
                                </svg>
                                <span>${escapeHtml(zone.zone_name)}</span>
                            </div>
                            <div class="room-meta-text">
                                ${zone.building ? escapeHtml(zone.building) : 'Zone'} ${zone.floor ? '• ' + escapeHtml(zone.floor) : ''}
                            </div>
                        </div>
                        <div class="room-occupancy-badge" id="badge-${zone.zone_id}">
                            0 Students
                        </div>
                    </div>
                    <div class="room-area" id="room-area-${zone.zone_id}">
                        <div class="room-watermark">${escapeHtml(zone.zone_name)}</div>
                        <div class="radar-ring ring-outer"></div>
                        <div class="radar-ring ring-middle"></div>
                        <div class="radar-ring ring-inner"></div>
                        <div class="ap-node" title="Master AP Scanner Antenna">
                            <span class="ap-pulse"></span>
                            <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"></path>
                            </svg>
                        </div>
                        <div class="room-empty-state" id="empty-state-${zone.zone_id}">No active occupants</div>
                    </div>
                `;

                roomsGrid.appendChild(card);
                roomCards[zone.zone_id] = card;
            }

            // Update room badge & alert border
            const badge = card.querySelector(`#badge-${zone.zone_id}`);
            if (badge) {
                badge.textContent = `${zone.occupant_count} ${zone.occupant_count === 1 ? 'Student' : 'Students'}`;
                if (zone.has_restricted_student) {
                    badge.className = 'room-occupancy-badge danger';
                    card.classList.add('has-alert');
                } else {
                    badge.className = 'room-occupancy-badge';
                    card.classList.remove('has-alert');
                }
            }

            // Toggle empty state label
            const emptyLabel = card.querySelector(`#empty-state-${zone.zone_id}`);
            if (emptyLabel) {
                emptyLabel.style.display = zone.occupant_count === 0 ? 'block' : 'none';
            }
        });

        // Remove obsolete room cards
        Object.keys(roomCards).forEach(zid => {
            if (!activeZoneIds.has(zid)) {
                roomCards[zid].remove();
                delete roomCards[zid];
            }
        });

        if (overviewZonesList) {
            overviewZonesList.innerHTML = overviewHTML || '<div style="color: var(--color-text-muted); font-size: var(--font-size-xs); text-align: center; padding: 20px;">No active physical zones detected.</div>';
        }

        // 2. Position Student Markers inside Rooms
        const seenStudentIds = new Set();

        zones.forEach(zone => {
            if (!zone.zone_id) return;
            const roomArea = document.getElementById(`room-area-${zone.zone_id}`);
            if (!roomArea) return;

            (zone.occupants || []).forEach(student => {
                seenStudentIds.add(student.student_id);
                const pos = calculateRoomPosition(student.student_id, student.confidence);
                const estimatedMeters = (1.0 - Math.min(1.0, student.confidence || 0.5)) * 8.5;

                let markerObj = studentMarkers[student.student_id];
                if (!markerObj) {
                    // Create marker element
                    const marker = document.createElement('div');
                    marker.className = 'student-marker';
                    marker.id = `marker-${student.student_id}`;

                    const initialLetter = (student.full_name || 'S').trim().charAt(0).toUpperCase();
                    marker.innerHTML = `
                        <span>${initialLetter}</span>
                        <div class="marker-tooltip" id="tooltip-${student.student_id}">
                            ${escapeHtml(student.full_name)}
                        </div>
                    `;

                    marker.onclick = (e) => {
                        e.stopPropagation();
                        selectStudent(student, zone.zone_name, estimatedMeters);
                    };

                    roomArea.appendChild(marker);

                    markerObj = {
                        element: marker,
                        currentZoneId: zone.zone_id,
                        data: student
                    };
                    studentMarkers[student.student_id] = markerObj;
                } else {
                    // If student changed rooms, move DOM element into the new room area
                    if (markerObj.currentZoneId !== zone.zone_id) {
                        roomArea.appendChild(markerObj.element);
                        markerObj.currentZoneId = zone.zone_id;
                    }
                    markerObj.data = student;
                    markerObj.element.onclick = (e) => {
                        e.stopPropagation();
                        selectStudent(student, zone.zone_name, estimatedMeters);
                    };
                }

                // Smoothly update marker coordinates (percentages relative to this room)
                markerObj.element.style.left = `${pos.x}%`;
                markerObj.element.style.top = `${pos.y}%`;

                // Update styling
                if (student.is_restricted) {
                    markerObj.element.classList.add('restricted');
                } else {
                    markerObj.element.classList.remove('restricted');
                }

                if (student.battery_percent !== null && student.battery_percent < 20) {
                    markerObj.element.classList.add('low-battery');
                } else {
                    markerObj.element.classList.remove('low-battery');
                }

                if (currentSelectedStudentId === student.student_id) {
                    markerObj.element.classList.add('selected');
                    updateInspectorLive(student, zone.zone_name, estimatedMeters);
                } else {
                    markerObj.element.classList.remove('selected');
                }

                // Update tooltip text
                const tooltip = markerObj.element.querySelector(`#tooltip-${student.student_id}`);
                if (tooltip) {
                    tooltip.textContent = `${student.full_name} (~${estimatedMeters.toFixed(1)}m)`;
                }
            });
        });

        // 3. Render Transit Corridor (Roaming students)
        const roamingOccupants = roamingZone.occupants || [];
        if (transitCountLabel) {
            transitCountLabel.textContent = `${roamingOccupants.length} ${roamingOccupants.length === 1 ? 'Student' : 'Students'} in Transit`;
        }

        if (roamingOccupants.length === 0) {
            if (transitCanvasArea) {
                transitCanvasArea.innerHTML = `
                    <span style="font-size: var(--font-size-xs); color: var(--color-text-muted); font-style: italic;">
                        All students are currently located inside active classrooms.
                    </span>
                `;
            }
        } else {
            let transitHTML = '';
            roamingOccupants.forEach(student => {
                seenStudentIds.add(student.student_id);
                const initialLetter = (student.full_name || 'S').trim().charAt(0).toUpperCase();

                transitHTML += `
                    <div class="transit-pill" onclick="mapApp.selectRoamingStudent('${student.student_id}')">
                        <span class="status-dot" style="background: var(--color-status-yellow);"></span>
                        <div style="width: 22px; height: 22px; border-radius: 50%; background: var(--color-primary); color: white; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold;">
                            ${initialLetter}
                        </div>
                        <span>${escapeHtml(student.full_name)}</span>
                        <span style="font-size: 10px; color: var(--color-text-muted);">Transit</span>
                    </div>
                `;
            });
            if (transitCanvasArea) {
                transitCanvasArea.innerHTML = transitHTML;
            }
        }

        // 4. Clean up markers for offline/unassigned students
        Object.keys(studentMarkers).forEach(id => {
            if (!seenStudentIds.has(id)) {
                studentMarkers[id].element.remove();
                delete studentMarkers[id];
            }
        });

        // Apply any active search filter
        if (currentSearchTerm) {
            applySearchFilter(currentSearchTerm);
        }
    }

    /**
     * Inspect a student on dot click
     */
    function selectStudent(student, zoneName, estimatedMeters) {
        currentSelectedStudentId = student.student_id;

        // Ensure inspector panel is visible
        if (!sidePanelOpen) {
            toggleSidePanel();
        }

        if (generalOverviewView) generalOverviewView.style.display = 'none';
        if (studentInspectorView) studentInspectorView.style.display = 'flex';

        updateInspectorLive(student, zoneName, estimatedMeters);

        // Highlight selected marker visually
        Object.values(studentMarkers).forEach(obj => {
            if (obj.data && obj.data.student_id === student.student_id) {
                obj.element.classList.add('selected');
                obj.element.style.opacity = '1';
            } else {
                obj.element.classList.remove('selected');
                obj.element.style.opacity = currentSearchTerm ? '0.2' : '0.7';
            }
        });
    }

    /**
     * Live refresh inspector card fields
     */
    function updateInspectorLive(student, zoneName, estimatedMeters) {
        if (!student) return;

        if (spName) spName.textContent = student.full_name;
        if (spClass) spClass.textContent = `Class: ${student.class_name || 'N/A'}`;
        if (spAvatar) spAvatar.textContent = (student.full_name || 'S').trim().charAt(0).toUpperCase();

        if (spZone) spZone.textContent = zoneName || 'Roaming / Transit';
        if (spDistance) spDistance.textContent = `~${(estimatedMeters || 1.5).toFixed(1)} meters`;

        if (spBattery) {
            if (student.battery_percent !== null && student.battery_percent !== undefined) {
                spBattery.textContent = `${student.battery_percent}%`;
                spBattery.style.color = student.battery_percent < 20 ? 'var(--color-status-red)' : 'var(--color-status-green)';
            } else {
                spBattery.textContent = '100%';
                spBattery.style.color = 'var(--color-status-green)';
            }
        }

        if (spDevice) {
            spDevice.textContent = student.device_code || 'WB-001';
        }

        if (spStatusBadge) {
            if (student.is_restricted) {
                spStatusBadge.innerHTML = `
                    <span class="status-pill offline"><span class="status-dot"></span> Restricted Zone Breach</span>
                `;
            } else {
                spStatusBadge.innerHTML = `
                    <span class="status-pill online"><span class="status-dot"></span> Authorized In Zone</span>
                `;
            }
        }

        if (spLink) {
            spLink.href = `/students/${student.student_id}`;
        }
    }

    /**
     * Clear student focus and return to general overview
     */
    function clearSelection() {
        currentSelectedStudentId = null;

        if (generalOverviewView) generalOverviewView.style.display = 'flex';
        if (studentInspectorView) studentInspectorView.style.display = 'none';

        // Reset all marker opacities
        Object.values(studentMarkers).forEach(obj => {
            obj.element.classList.remove('selected');
            obj.element.style.opacity = '1';
        });
    }

    /**
     * Instant search & highlight
     */
    function handleSearch(term) {
        currentSearchTerm = (term || '').trim().toLowerCase();
        applySearchFilter(currentSearchTerm);
    }

    function applySearchFilter(term) {
        if (!term) {
            Object.values(studentMarkers).forEach(obj => {
                obj.element.style.opacity = '1';
            });
            return;
        }

        let firstMatch = null;
        Object.values(studentMarkers).forEach(obj => {
            const name = (obj.data?.full_name || '').toLowerCase();
            const code = (obj.data?.student_code || '').toLowerCase();
            const matches = name.includes(term) || code.includes(term);

            if (matches) {
                obj.element.style.opacity = '1';
                obj.element.style.transform = 'translate(-50%, -50%) scale(1.3)';
                if (!firstMatch) firstMatch = obj;
            } else {
                obj.element.style.opacity = '0.15';
                obj.element.style.transform = 'translate(-50%, -50%) scale(1)';
            }
        });
    }

    /**
     * Zoom In / Out / Reset
     */
    function zoomIn() {
        currentZoom = Math.min(1.5, currentZoom + 0.12);
        applyZoom();
    }

    function zoomOut() {
        currentZoom = Math.max(0.75, currentZoom - 0.12);
        applyZoom();
    }

    function resetZoom() {
        currentZoom = 1.0;
        applyZoom();
    }

    function applyZoom() {
        if (roomsGrid) {
            roomsGrid.style.transform = `scale(${currentZoom})`;
        }
    }

    /**
     * Toggle Side Panel Collapse for maximum screen width
     */
    function toggleSidePanel() {
        sidePanelOpen = !sidePanelOpen;
        const panel = document.getElementById('map-side-panel');
        const label = document.getElementById('panel-toggle-label');

        if (panel) {
            if (sidePanelOpen) {
                panel.classList.remove('collapsed');
                if (label) label.textContent = 'Hide Inspector';
            } else {
                panel.classList.add('collapsed');
                if (label) label.textContent = 'Show Inspector';
            }
        }
    }

    /**
     * Toggle Fullscreen Mode
     */
    function toggleFullscreen() {
        const appEl = document.getElementById('main-map-app');
        if (!document.fullscreenElement) {
            if (appEl?.requestFullscreen) {
                appEl.requestFullscreen().catch(err => console.warn(err));
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen().catch(err => console.warn(err));
            }
        }
    }

    /**
     * Utility: HTML escape string to prevent XSS
     */
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function selectRoamingStudent(studentId) {
        if (!latestData || !latestData.roaming_zone) return;
        const st = (latestData.roaming_zone.occupants || []).find(s => s.student_id === studentId);
        if (st) {
            selectStudent(st, "Transit / Roaming Corridor", 8.0);
        }
    }

    /**
     * Engine startup
     */
    function startEngine() {
        fetchMapData();
        // Poll every 3 seconds for smooth real-time safety telemetry
        fetchInterval = setInterval(fetchMapData, 3000);
    }

    return {
        start: startEngine,
        fetchMapData: fetchMapData,
        clearSelection: clearSelection,
        handleSearch: handleSearch,
        zoomIn: zoomIn,
        zoomOut: zoomOut,
        resetZoom: resetZoom,
        toggleSidePanel: toggleSidePanel,
        toggleFullscreen: toggleFullscreen,
        selectRoamingStudent: selectRoamingStudent
    };
})();

// Initialize when DOM content is loaded
document.addEventListener('DOMContentLoaded', () => {
    mapApp.start();
});
