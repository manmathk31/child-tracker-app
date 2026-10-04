/**
 * 2D Live Campus Map Application
 * Handles real-time polling, smooth student movement, and zone analytics.
 */

const mapApp = (function() {
    let studentNodes = {};
    let roomNodes = {};
    let fetchInterval = null;
    let currentSelectedStudentId = null;

    // DOM Elements
    const roomsLayer = document.getElementById('rooms-layer');
    const studentsLayer = document.getElementById('students-layer');
    const lastUpdatedText = document.getElementById('last-updated-text');
    
    // Analytics Panel
    const globalAnalytics = document.getElementById('global-analytics');
    const analyticsBody = document.getElementById('analytics-body');
    
    // Profile Panel
    const selectedProfile = document.getElementById('selected-profile');
    const spAvatar = document.getElementById('sp-avatar');
    const spName = document.getElementById('sp-name');
    const spClass = document.getElementById('sp-class');
    const spZone = document.getElementById('sp-zone');
    const spDistance = document.getElementById('sp-distance');
    const spBattery = document.getElementById('sp-battery');
    const spLink = document.getElementById('sp-link');

    // Utility: simple pseudo-random based on UUID
    function getSeededAngle(uuidStr) {
        if (!uuidStr) return 0;
        let sum = 0;
        for (let i = 0; i < Math.min(8, uuidStr.length); i++) {
            sum += uuidStr.charCodeAt(i);
        }
        // Golden angle distribution
        return (sum * 137.5) * (Math.PI / 180);
    }

    async function fetchMapData() {
        try {
            lastUpdatedText.textContent = "Updating...";
            const response = await fetch('/api/v1/dashboard/live');
            if (!response.ok) throw new Error("API Network Error");
            const data = await response.json();
            
            renderMap(data);
            
            const now = new Date();
            lastUpdatedText.textContent = `Live • ${now.toLocaleTimeString()}`;
        } catch (error) {
            console.error("Map fetch error:", error);
            lastUpdatedText.textContent = "Connection lost. Retrying...";
        }
    }

    function renderMap(data) {
        const zones = data.zones || [];
        
        // Add the roaming zone to the list so it gets rendered as a "Hallway/Outside" area
        if (data.roaming_zone) {
            // Give it a pseudo-ID so the logic treats it like a normal room
            data.roaming_zone.zone_id = 'roaming';
            zones.push(data.roaming_zone);
        }
        
        // 1. Render/Update Rooms
        let analyticsHTML = '';
        
        zones.forEach(zone => {
            if (!zone.zone_id) return; // Skip if no zone ID
            
            // Generate analytics HTML for this zone
            analyticsHTML += `
                <div style="background: var(--color-bg); padding: 12px; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; border-left: 3px solid var(--color-primary);">
                    <span style="font-weight: 600; font-size: 0.9rem;">${zone.zone_name}</span>
                    <span class="room-occupancy-badge" style="background: ${zone.has_restricted_student ? 'var(--color-status-red)' : 'var(--color-primary)'}">
                        ${zone.occupant_count} Students
                    </span>
                </div>
            `;

            let roomDiv = roomNodes[zone.zone_id];
            if (!roomDiv) {
                // Create room DOM
                roomDiv = document.createElement('div');
                roomDiv.className = 'map-room';
                roomDiv.id = `room-${zone.zone_id}`;
                
                roomDiv.innerHTML = `
                    <div class="room-label">${zone.zone_id === 'roaming' ? 'HALLWAY' : zone.zone_name}</div>
                    <div class="room-header" style="${zone.zone_id === 'roaming' ? 'background: #f8fafc;' : ''}">
                        <span style="font-weight: 600; font-size: 0.85rem; color: var(--color-text-primary);">${zone.zone_name}</span>
                        <span class="room-occupancy-badge" id="badge-${zone.zone_id}">0</span>
                    </div>
                    <div class="room-area" id="area-${zone.zone_id}">
                        ${zone.zone_id === 'roaming' ? '' : `
                        <div class="ap-node" title="Master Scanner (AP)">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"></path></svg>
                        </div>
                        `}
                    </div>
                `;
                
                if (zone.zone_id === 'roaming') {
                    roomDiv.style.borderStyle = 'dashed';
                    roomDiv.style.backgroundColor = 'rgba(255, 255, 255, 0.5)';
                }
                
                roomsLayer.appendChild(roomDiv);
                roomNodes[zone.zone_id] = roomDiv;
            }
            
            // Update badge
            const badge = roomDiv.querySelector(`#badge-${zone.zone_id}`);
            if (badge) {
                badge.textContent = zone.occupant_count;
                if (zone.has_restricted_student) {
                    badge.style.background = 'var(--color-status-red)';
                } else {
                    badge.style.background = 'var(--color-primary)';
                }
            }
        });
        
        analyticsBody.innerHTML = analyticsHTML || '<div style="color: var(--color-text-muted); font-size: 0.85rem;">No active zones detected.</div>';

        // 2. Track which students were seen in this tick to remove old ones
        const seenStudentIds = new Set();
        
        // Ensure DOM has layout calculated before positioning dots
        requestAnimationFrame(() => {
            const containerRect = studentsLayer.getBoundingClientRect();

            zones.forEach(zone => {
                if (!zone.zone_id) return;
                const roomArea = document.getElementById(`area-${zone.zone_id}`);
                if (!roomArea) return;
                
                const roomRect = roomArea.getBoundingClientRect();
                
                // Calculate Room Center relative to the absolute students-layer
                const cx = (roomRect.left - containerRect.left) + (roomRect.width / 2);
                const cy = (roomRect.top - containerRect.top) + (roomRect.height / 2);
                
                // Max radius for students to roam in this room
                const maxRadius = Math.min(roomRect.width, roomRect.height) / 2 - 25;

                zone.occupants.forEach(student => {
                    seenStudentIds.add(student.student_id);
                    
                    // Estimate distance visually (Confidence 1.0 = center, Confidence 0.0 = edge)
                    // If confidence is low, push them outwards
                    const distanceFactor = Math.max(0, 1.0 - student.confidence);
                    const radius = distanceFactor * maxRadius;
                    const angle = getSeededAngle(student.student_id);
                    
                    const tx = cx + Math.cos(angle) * radius;
                    const ty = cy + Math.sin(angle) * radius;
                    
                    // Estimated physical distance in meters (mock mapping: 1.0 conf = 0m, 0.0 conf = 15m)
                    const estimatedMeters = (1.0 - student.confidence) * 15;

                    let dot = studentNodes[student.student_id];
                    if (!dot) {
                        dot = document.createElement('div');
                        dot.className = 'student-dot';
                        dot.style.pointerEvents = 'auto'; // allow clicking
                        dot.onclick = () => selectStudent(student, zone.zone_name, estimatedMeters);
                        studentsLayer.appendChild(dot);
                        
                        // Initial placement without animation
                        dot.style.transition = 'none';
                        dot.style.left = tx + 'px';
                        dot.style.top = ty + 'px';
                        
                        // Force reflow to enable transition for future moves
                        void dot.offsetWidth;
                        dot.style.transition = '';
                        
                        studentNodes[student.student_id] = dot;
                    }
                    
                    // Update visuals
                    dot.dataset.name = student.full_name;
                    dot.style.left = tx + 'px';
                    dot.style.top = ty + 'px';
                    
                    if (student.is_restricted) {
                        dot.classList.add('restricted');
                    } else {
                        dot.classList.remove('restricted');
                    }
                    
                    if (student.battery_percent !== null && student.battery_percent < 20) {
                        dot.classList.add('low-battery');
                    } else {
                        dot.classList.remove('low-battery');
                    }
                    
                    // If this student is currently selected in the side panel, update the panel live
                    if (currentSelectedStudentId === student.student_id) {
                        updateSidePanelLive(student, zone.zone_name, estimatedMeters);
                    }
                });
            });
            
            // 3. Remove disappeared students
            Object.keys(studentNodes).forEach(id => {
                if (!seenStudentIds.has(id)) {
                    studentNodes[id].remove();
                    delete studentNodes[id];
                }
            });
        });
    }

    function selectStudent(student, zoneName, estimatedMeters) {
        currentSelectedStudentId = student.student_id;
        
        // UI Switching
        globalAnalytics.style.display = 'none';
        selectedProfile.style.display = 'block';
        
        // Populate
        updateSidePanelLive(student, zoneName, estimatedMeters);
        
        // Provide link to full history
        spLink.href = `/students/${student.student_id}/history`;
        
        // Highlight logic (optional visual)
        Object.values(studentNodes).forEach(node => {
            node.style.opacity = '0.3';
            node.style.transform = 'translate(-50%, -50%) scale(0.8)';
            node.style.zIndex = '10';
        });
        
        const activeDot = studentNodes[student.student_id];
        if (activeDot) {
            activeDot.style.opacity = '1';
            activeDot.style.transform = 'translate(-50%, -50%) scale(1.5)';
            activeDot.style.zIndex = '30';
            activeDot.style.border = '2px solid var(--color-surface)';
            activeDot.style.boxShadow = '0 0 0 4px rgba(37,99,235,0.4)';
        }
    }
    
    function updateSidePanelLive(student, zoneName, estimatedMeters) {
        spName.textContent = student.full_name;
        spClass.textContent = `Class: ${student.class_name || 'N/A'}`;
        spAvatar.textContent = student.full_name.charAt(0).toUpperCase();
        
        spZone.textContent = zoneName;
        spDistance.textContent = `~${estimatedMeters.toFixed(1)} meters`;
        
        if (student.battery_percent !== null) {
            spBattery.textContent = `${student.battery_percent}%`;
            spBattery.style.color = student.battery_percent < 20 ? 'var(--color-status-red)' : 'inherit';
        } else {
            spBattery.textContent = 'Unknown';
            spBattery.style.color = 'inherit';
        }
    }

    function clearSelection() {
        currentSelectedStudentId = null;
        globalAnalytics.style.display = 'block';
        selectedProfile.style.display = 'none';
        
        // Reset dot styles
        Object.values(studentNodes).forEach(node => {
            node.style.opacity = '1';
            node.style.transform = 'translate(-50%, -50%)';
            node.style.zIndex = '10';
            node.style.border = '2px solid white';
            node.style.boxShadow = '0 2px 5px rgba(0,0,0,0.2)';
        });
    }

    function startEngine() {
        fetchMapData(); // Initial load
        fetchInterval = setInterval(fetchMapData, 3000); // refresh every 3 seconds
    }

    // Expose public API
    return {
        start: startEngine,
        fetchMapData: fetchMapData,
        clearSelection: clearSelection
    };
})();

// Start when document is ready
document.addEventListener('DOMContentLoaded', () => {
    mapApp.start();
});
