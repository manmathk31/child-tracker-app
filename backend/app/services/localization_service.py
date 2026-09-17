"""Indoor Localization Engine for Wi-Fi RSSI Fingerprinting.

Implements high-performance, low-cost probabilistic positioning:
1. In-memory fingerprint profile cache with TTL and explicit invalidation to avoid DB overhead.
2. Variance-weighted Euclidean signal distance matching with missing-AP penalty.
3. Continuous confidence scoring (0.0 to 1.0) and configurable low-confidence thresholding.
4. Bounded temporal hysteresis filter (sliding window per wearable) to eliminate room fluttering.
"""

import asyncio
import logging
import math
import time
import uuid
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.device import Device, DeviceStatus
from app.models.fingerprint import Fingerprint, FingerprintAPStat, FingerprintStatus
from app.models.location_record import LocationRecord
from app.models.student import Student
from app.schemas.location import (
    LocationEstimate,
    LocationRecordResponse,
    StudentLiveLocationResponse,
    TelemetryIngestIn,
    TelemetryIngestResponse,
)
from app.services.settings_service import get_or_create_alert_settings

logger = logging.getLogger("childtrack.localization")

# Cache configuration
CACHE_TTL_SECONDS: float = 30.0
HYSTERESIS_WINDOW_SIZE: int = 5
HYSTERESIS_DEVICE_EXPIRY_SECONDS: float = 3600.0


@dataclass
class CachedAPStat:
    bssid: str
    median_rssi: float
    stddev_rssi: float
    sample_count: int


@dataclass
class CachedZoneProfile:
    zone_id: uuid.UUID
    zone_name: str
    fingerprint_id: uuid.UUID
    ap_stats: dict[str, CachedAPStat]  # BSSID -> Stat


# In-memory global state
_fingerprint_cache: dict[uuid.UUID, CachedZoneProfile] = {}
_cache_last_loaded: float = 0.0
_cache_lock = asyncio.Lock()

# Device temporal history: device_id -> deque of (zone_id, confidence, timestamp)
_device_history: dict[uuid.UUID, deque[tuple[uuid.UUID | None, str | None, float, float]]] = {}


def invalidate_fingerprint_cache() -> None:
    """Explicitly invalidate in-memory fingerprint cache."""
    global _cache_last_loaded
    _cache_last_loaded = 0.0
    logger.debug("Localization fingerprint cache invalidated.")


def clear_hysteresis_state() -> None:
    """Clear all device hysteresis buffers (primarily used in testing)."""
    global _device_history
    _device_history.clear()


async def get_cached_active_fingerprints(db: AsyncSession) -> dict[uuid.UUID, CachedZoneProfile]:
    """Retrieve active zone fingerprint profiles, using cached memory if fresh."""
    global _fingerprint_cache, _cache_last_loaded

    now = time.monotonic()
    if _fingerprint_cache and (now - _cache_last_loaded < CACHE_TTL_SECONDS):
        return _fingerprint_cache

    async with _cache_lock:
        # Re-check after lock acquisition
        if _fingerprint_cache and (time.monotonic() - _cache_last_loaded < CACHE_TTL_SECONDS):
            return _fingerprint_cache

        stmt = (
            select(Fingerprint)
            .where(Fingerprint.status == FingerprintStatus.ACTIVE)
            .options(
                selectinload(Fingerprint.zone),
                selectinload(Fingerprint.ap_stats).selectinload(FingerprintAPStat.access_point),
            )
        )
        res = await db.execute(stmt)
        active_fps = res.scalars().all()

        new_cache: dict[uuid.UUID, CachedZoneProfile] = {}
        for fp in active_fps:
            if not fp.zone or not fp.zone.is_active:
                continue

            ap_map: dict[str, CachedAPStat] = {}
            for stat in fp.ap_stats:
                if stat.access_point and stat.access_point.is_active:
                    bssid = stat.access_point.bssid.upper()
                    ap_map[bssid] = CachedAPStat(
                        bssid=bssid,
                        median_rssi=float(stat.median_rssi),
                        stddev_rssi=float(stat.stddev_rssi),
                        sample_count=stat.sample_count,
                    )

            if ap_map:
                new_cache[fp.zone_id] = CachedZoneProfile(
                    zone_id=fp.zone_id,
                    zone_name=fp.zone.name,
                    fingerprint_id=fp.id,
                    ap_stats=ap_map,
                )

        _fingerprint_cache = new_cache
        _cache_last_loaded = time.monotonic()
        logger.info(
            "Reloaded active fingerprint cache: %d zones indexed.",
            len(_fingerprint_cache),
        )
        return _fingerprint_cache


def compute_zone_distance(
    scan_map: dict[str, int],
    zone_profile: CachedZoneProfile,
) -> tuple[float, int]:
    """Compute variance-weighted Euclidean signal distance between scan and fingerprint.

    Args:
        scan_map: Dict of BSSID -> observed RSSI (dBm).
        zone_profile: Pre-computed statistical fingerprint for a zone.

    Returns:
        Tuple of (weighted_distance, matched_ap_count).
    """
    matched_aps = 0
    weighted_sq_err = 0.0
    total_weights = 0.0

    for bssid, stat in zone_profile.ap_stats.items():
        if bssid in scan_map:
            matched_aps += 1
            diff = scan_map[bssid] - stat.median_rssi
            # Weight by inverse standard deviation: stable APs have higher weight
            weight = 1.0 / (max(stat.stddev_rssi, 1.0) + 1.0)
            weighted_sq_err += weight * (diff**2)
            total_weights += weight
        else:
            # Missing AP penalty: if AP is strong in fingerprint but missing from scan
            if stat.median_rssi >= -75.0:
                # Assume signal fell below receiver sensitivity (-95 dBm)
                diff = stat.median_rssi - (-95.0)
                penalty_weight = 0.4
                weighted_sq_err += penalty_weight * (diff**2)
                total_weights += penalty_weight

    # Penalize strong APs seen in scan that do not exist in this zone
    for bssid, rssi in scan_map.items():
        if bssid not in zone_profile.ap_stats:
            if rssi >= -65:
                diff = rssi - (-95.0)
                penalty_weight = 0.3
                weighted_sq_err += penalty_weight * (diff**2)
                total_weights += penalty_weight

    if total_weights <= 0.0 or matched_aps == 0:
        return float("inf"), 0

    distance = math.sqrt(weighted_sq_err / total_weights)
    return distance, matched_aps


def estimate_position_from_profiles(
    scan_map: dict[str, int],
    profiles: dict[uuid.UUID, CachedZoneProfile],
    min_confidence_threshold: float,
) -> LocationEstimate:
    """Calculate the best matching zone and continuous confidence score from active profiles."""
    if not profiles or not scan_map:
        return LocationEstimate(
            zone_id=None,
            zone_name=None,
            confidence=0.0,
            is_low_confidence=True,
            distance_metrics={},
        )

    distance_metrics: dict[str, float] = {}
    valid_candidates: list[tuple[float, CachedZoneProfile]] = []

    for _zone_id, profile in profiles.items():
        dist, matched_count = compute_zone_distance(scan_map, profile)
        if matched_count > 0 and not math.isinf(dist):
            distance_metrics[profile.zone_name] = round(dist, 2)
            valid_candidates.append((dist, profile))

    if not valid_candidates:
        return LocationEstimate(
            zone_id=None,
            zone_name=None,
            confidence=0.0,
            is_low_confidence=True,
            distance_metrics=distance_metrics,
        )

    # Sort candidates by distance ascending
    valid_candidates.sort(key=lambda x: x[0])
    best_dist, best_profile = valid_candidates[0]

    # Probabilistic Softmin calculation: S(z) = exp(-D(z) / tau)
    tau = 12.0  # Temperature scaling in dBm
    exp_scores = [math.exp(-cand[0] / tau) for cand in valid_candidates]
    total_score = sum(exp_scores)

    if total_score > 0:
        p_best = exp_scores[0] / total_score
    else:
        p_best = 0.0

    # Attenuation based on absolute distance quality
    # Signals with best_dist <= 5 dBm receive 1.0; at 35 dBm drops to 0.0
    quality_factor = max(0.0, min(1.0, 1.0 - (max(0.0, best_dist - 5.0) / 30.0)))
    raw_confidence = p_best * quality_factor
    confidence = round(max(0.0, min(1.0, raw_confidence)), 4)

    is_low_conf = confidence < min_confidence_threshold or best_dist > 35.0

    return LocationEstimate(
        zone_id=best_profile.zone_id if not is_low_conf else None,
        zone_name=best_profile.zone_name if not is_low_conf else None,
        confidence=confidence,
        is_low_confidence=is_low_conf,
        distance_metrics=distance_metrics,
    )


def apply_temporal_hysteresis(
    device_id: uuid.UUID,
    raw_estimate: LocationEstimate,
) -> LocationEstimate:
    """Apply bounded sliding-window hysteresis smoothing to prevent room fluttering.

    Rules:
    1. If buffer has previous stable observations and current reading is a single transient
       flutter with confidence < 0.85, the previous stable room is preserved.
    2. Sustained room transitions (2+ consecutive matching readings) or high-confidence
       readings (>= 0.85) immediately update the location.
    """
    global _device_history

    now = time.monotonic()
    history = _device_history.setdefault(device_id, deque(maxlen=HYSTERESIS_WINDOW_SIZE))

    # Prune outdated observations (> 10 minutes)
    while history and (now - history[0][3] > 600.0):
        history.popleft()

    curr_zone_id = raw_estimate.zone_id
    curr_zone_name = raw_estimate.zone_name
    curr_conf = raw_estimate.confidence

    if raw_estimate.is_low_confidence or curr_zone_id is None:
        history.append((None, None, curr_conf, now))
        return raw_estimate

    # Immediate confirmation if confidence is very high
    if curr_conf >= 0.85 or len(history) == 0:
        history.append((curr_zone_id, curr_zone_name, curr_conf, now))
        return raw_estimate

    # Check previous readings in buffer
    prev_readings = [item for item in history if item[0] is not None]

    if prev_readings:
        last_zone_id, last_zone_name, last_conf, _ = prev_readings[-1]

        # If current reading matches previous stable zone, accept and reinforce
        if curr_zone_id == last_zone_id:
            history.append((curr_zone_id, curr_zone_name, curr_conf, now))
            return raw_estimate

        # If current reading is different from previous:
        # Check if this is the 2nd consecutive time we see the new zone
        matching_new_zone = sum(1 for item in history if item[0] == curr_zone_id)
        if matching_new_zone >= 1:
            # Sustained transition confirmed
            history.append((curr_zone_id, curr_zone_name, curr_conf, now))
            return raw_estimate

        # Single transient flutter: smooth by retaining previous stable zone
        # with slightly damped confidence
        smoothed_conf = round(max(0.40, (last_conf * 0.7) + (curr_conf * 0.3)), 4)
        history.append((curr_zone_id, curr_zone_name, curr_conf, now))
        logger.debug(
            "Hysteresis filter smoothed flutter for device %s: %s -> %s (retained %s)",
            device_id,
            last_zone_name,
            curr_zone_name,
            last_zone_name,
        )
        return LocationEstimate(
            zone_id=last_zone_id,
            zone_name=last_zone_name,
            confidence=smoothed_conf,
            is_low_confidence=False,
            distance_metrics=raw_estimate.distance_metrics,
        )

    # First observation in history
    history.append((curr_zone_id, curr_zone_name, curr_conf, now))
    return raw_estimate


async def process_telemetry_scan(
    db: AsyncSession,
    payload: TelemetryIngestIn,
) -> TelemetryIngestResponse:
    """Process incoming hardware telemetry transmission from an ESP32 wearable.

    Performs:
    1. Device lookup & verification.
    2. Device online status & battery state update.
    3. Multi-zone probabilistic RSSI vector localization.
    4. Temporal hysteresis smoothing.
    5. Location audit record persistence for paired students.
    """
    # 1. Lookup device
    normalized_mac = payload.mac_address.upper()
    device_stmt = (
        select(Device)
        .where(
            or_(
                Device.device_code == payload.device_id,
                Device.mac_address == normalized_mac,
            )
        )
        .options(selectinload(Device.student))
    )
    device_res = await db.execute(device_stmt)
    device = device_res.scalar_one_or_none()

    if not device:
        logger.warning(
            "Telemetry rejected: Unrecognized device identifier '%s' (MAC: %s)",
            payload.device_id,
            payload.mac_address,
        )
        raise NotFoundError("Device", payload.device_id)

    # 2. Update device status
    now_utc = datetime.now(UTC)
    device.last_seen_at = now_utc
    device.status = DeviceStatus.ONLINE
    device.battery_percent = payload.battery_percent
    if payload.firmware_version:
        device.firmware_version = payload.firmware_version

    # 3. Load active fingerprints & alert settings
    profiles = await get_cached_active_fingerprints(db)
    alert_settings = await get_or_create_alert_settings(db)
    min_conf_threshold = alert_settings.min_localization_confidence

    # 4. Compute localization estimate
    scan_map = {item.bssid.upper(): item.rssi for item in payload.scan}
    raw_estimate = estimate_position_from_profiles(
        scan_map=scan_map,
        profiles=profiles,
        min_confidence_threshold=min_conf_threshold,
    )

    # 5. Apply temporal hysteresis
    final_estimate = apply_temporal_hysteresis(device.id, raw_estimate)

    # 6. If device is assigned to an enrolled student, persist LocationRecord
    if device.student_id:
        record = LocationRecord(
            student_id=device.student_id,
            device_id=device.id,
            zone_id=final_estimate.zone_id if not final_estimate.is_low_confidence else None,
            confidence=final_estimate.confidence,
            raw_scan={
                "scan": [item.model_dump() for item in payload.scan],
                "events": payload.events or {},
                "battery_percent": payload.battery_percent,
            },
            recorded_at=now_utc,
        )
        db.add(record)

    await db.commit()

    assigned_zone = final_estimate.zone_name if not final_estimate.is_low_confidence else None
    return TelemetryIngestResponse(
        status="ack",
        device_id=payload.device_id,
        assigned_zone=assigned_zone,
        confidence=round(final_estimate.confidence, 2),
        server_time=now_utc,
    )


async def get_student_location_history(
    db: AsyncSession,
    student_id: uuid.UUID,
    limit: int = 50,
) -> Sequence[LocationRecord]:
    """Retrieve historical location breadcrumbs for a student."""
    stmt = (
        select(LocationRecord)
        .where(LocationRecord.student_id == student_id)
        .order_by(LocationRecord.recorded_at.desc())
        .limit(limit)
        .options(
            selectinload(LocationRecord.zone),
            selectinload(LocationRecord.student),
            selectinload(LocationRecord.device),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_student_live_location(
    db: AsyncSession,
    student_id: uuid.UUID,
) -> StudentLiveLocationResponse:
    """Retrieve current live position and recent breadcrumbs for a student."""
    student_stmt = (
        select(Student)
        .where(Student.id == student_id)
        .options(selectinload(Student.device))
    )
    student_res = await db.execute(student_stmt)
    student = student_res.scalar_one_or_none()

    if not student:
        raise NotFoundError("Student", student_id)

    # Fetch last 10 location breadcrumbs
    history = await get_student_location_history(db, student_id, limit=10)

    device = student.device
    device_status = device.status.value if device else "unassigned"
    battery = device.battery_percent if device else None
    last_seen = device.last_seen_at if device else None

    latest_record = history[0] if history else None
    current_zone_id = latest_record.zone_id if latest_record else None
    current_zone_name = latest_record.zone_name if latest_record else None
    confidence = latest_record.confidence if latest_record else 0.0
    is_low_conf = current_zone_id is None

    breadcrumbs = [LocationRecordResponse.model_validate(r) for r in history]

    return StudentLiveLocationResponse(
        student_id=student.id,
        student_name=student.full_name,
        student_code=student.student_code,
        device_id=device.id if device else None,
        device_code=device.device_code if device else None,
        device_status=device_status,
        battery_percent=battery,
        last_seen_at=last_seen,
        current_zone_id=current_zone_id,
        current_zone_name=current_zone_name,
        confidence=confidence,
        is_low_confidence=is_low_conf,
        recent_breadcrumbs=breadcrumbs,
    )
