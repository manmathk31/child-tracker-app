"""Business logic for Wi-Fi RSSI fingerprint collection, AP filtering, and calibration."""

import json
import logging
import re
import statistics
import uuid
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.access_point import AccessPoint
from app.models.fingerprint import (
    Fingerprint,
    FingerprintAPStat,
    FingerprintSample,
    FingerprintStatus,
)
from app.models.zone import Zone
from app.schemas.fingerprint import CalibrationBatchIn, FingerprintCreate, FingerprintUpdate

logger = logging.getLogger("childtrack.fingerprint_service")

WHITELIST_TAG_PREFIX = "[WHITELIST:"
WHITELIST_TAG_REGEX = r"\[WHITELIST:([^\]]*)\]"


def _encode_notes(notes: Optional[str], target_ap_ids: Optional[List[uuid.UUID]]) -> Optional[str]:
    """Encode optional target AP whitelist metadata into notes."""
    base_notes = notes.strip() if notes else ""
    if not target_ap_ids:
        return base_notes if base_notes else None

    whitelist_str = ",".join(str(ap_id) for ap_id in target_ap_ids)
    tag = f"{WHITELIST_TAG_PREFIX}{whitelist_str}]"
    return f"{tag}\n{base_notes}".strip()


def parse_whitelisted_ap_ids(notes: Optional[str]) -> Optional[List[uuid.UUID]]:
    """Extract whitelisted AP IDs from notes tag if present."""
    if not notes:
        return None
    match = re.search(WHITELIST_TAG_REGEX, notes)
    if not match:
        return None
    raw_ids = match.group(1).split(",")
    result: List[uuid.UUID] = []
    for raw in raw_ids:
        raw_clean = raw.strip()
        if raw_clean:
            try:
                result.append(uuid.UUID(raw_clean))
            except ValueError:
                pass
    return result if result else None


async def create_fingerprint(
    db: AsyncSession,
    user_id: uuid.UUID,
    fingerprint_in: FingerprintCreate,
) -> Fingerprint:
    """Initialize a new draft fingerprint survey session for a zone."""
    # Verify zone exists
    zone_stmt = select(Zone).where(Zone.id == fingerprint_in.zone_id)
    zone_res = await db.execute(zone_stmt)
    if not zone_res.scalar_one_or_none():
        raise NotFoundError("Zone", fingerprint_in.zone_id)

    # If target APs specified, verify they exist
    if fingerprint_in.target_ap_ids:
        ap_stmt = select(AccessPoint).where(AccessPoint.id.in_(fingerprint_in.target_ap_ids))
        ap_res = await db.execute(ap_stmt)
        found_aps = ap_res.scalars().all()
        if len(found_aps) != len(set(fingerprint_in.target_ap_ids)):
            raise NotFoundError("AccessPoint", "One or more target APs not found")

    combined_notes = _encode_notes(fingerprint_in.notes, fingerprint_in.target_ap_ids)

    fingerprint = Fingerprint(
        zone_id=fingerprint_in.zone_id,
        created_by=user_id,
        sample_count=0,
        quality_score=None,
        min_rssi_cutoff=fingerprint_in.min_rssi_cutoff,
        status=FingerprintStatus.DRAFT,
        notes=combined_notes,
    )
    db.add(fingerprint)
    await db.commit()
    await db.refresh(fingerprint)

    logger.info("Initialized draft fingerprint survey: id=%s zone_id=%s", fingerprint.id, fingerprint.zone_id)
    return await get_fingerprint_by_id(db, fingerprint.id)


async def get_fingerprint_by_id(db: AsyncSession, fingerprint_id: uuid.UUID) -> Fingerprint:
    """Retrieve fingerprint survey with preloaded zone, creator, and AP statistical breakdown."""
    stmt = (
        select(Fingerprint)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Fingerprint.zone),
            selectinload(Fingerprint.creator),
            selectinload(Fingerprint.ap_stats).selectinload(FingerprintAPStat.access_point),
        )
        .where(Fingerprint.id == fingerprint_id)
    )
    result = await db.execute(stmt)
    fingerprint = result.scalar_one_or_none()
    if not fingerprint:
        raise NotFoundError("Fingerprint", fingerprint_id)
    return fingerprint



async def list_fingerprints(
    db: AsyncSession,
    zone_id: Optional[uuid.UUID] = None,
    status: Optional[FingerprintStatus] = None,
) -> Sequence[Fingerprint]:
    """List all fingerprint surveys with preloaded metadata."""
    stmt = (
        select(Fingerprint)
        .options(
            selectinload(Fingerprint.zone),
            selectinload(Fingerprint.creator),
            selectinload(Fingerprint.ap_stats).selectinload(FingerprintAPStat.access_point),
        )
    )
    if zone_id:
        stmt = stmt.where(Fingerprint.zone_id == zone_id)
    if status:
        stmt = stmt.where(Fingerprint.status == status)
    stmt = stmt.order_by(Fingerprint.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def ingest_samples_batch(
    db: AsyncSession,
    fingerprint_id: uuid.UUID,
    batch: CalibrationBatchIn,
) -> int:
    """Ingest a batch of raw Wi-Fi scan readings, applying AP filtering and RSSI cutoff thresholds."""
    fingerprint = await get_fingerprint_by_id(db, fingerprint_id)
    if fingerprint.status != FingerprintStatus.DRAFT:
        raise ConflictError(f"Cannot ingest samples into survey with status '{fingerprint.status.value}'.")

    whitelist_ap_ids = parse_whitelisted_ap_ids(fingerprint.notes)

    # 1. Gather and normalize observed BSSIDs
    observed_bssids = {s.bssid for s in batch.scan}
    if not observed_bssids:
        return 0

    # 2. Query registered, active Access Points matching observed BSSIDs
    ap_stmt = select(AccessPoint).where(
        AccessPoint.bssid.in_(observed_bssids),
        AccessPoint.is_active == True,  # noqa: E712
    )
    ap_res = await db.execute(ap_stmt)
    ap_map: Dict[str, AccessPoint] = {ap.bssid: ap for ap in ap_res.scalars().all()}

    # 3. Filter readings
    accepted_samples: List[FingerprintSample] = []
    for scan_item in batch.scan:
        ap = ap_map.get(scan_item.bssid)
        if not ap:
            # Not a registered school reference AP -> ignore rogue/hotspot noise
            continue

        if whitelist_ap_ids and ap.id not in whitelist_ap_ids:
            # AP excluded by user's survey selection whitelist -> ignore
            continue

        if scan_item.rssi < fingerprint.min_rssi_cutoff:
            # Below signal strength cutoff threshold -> ignore distant weak signal
            continue

        sample = FingerprintSample(
            fingerprint_id=fingerprint.id,
            access_point_id=ap.id,
            rssi=scan_item.rssi,
        )
        accepted_samples.append(sample)

    if accepted_samples:
        db.add_all(accepted_samples)
        fingerprint.sample_count += 1  # Increment completed scan count
        await db.commit()
        logger.debug(
            "Ingested %d valid readings for fingerprint %s (total scans: %d)",
            len(accepted_samples),
            fingerprint.id,
            fingerprint.sample_count,
        )

    return len(accepted_samples)


async def calculate_and_save_ap_stats(db: AsyncSession, fingerprint_id: uuid.UUID) -> Fingerprint:
    """Compute mathematical mean, median, standard deviation, and quality score from raw samples."""
    fingerprint = await get_fingerprint_by_id(db, fingerprint_id)

    # Load all raw samples for this survey
    samples_stmt = select(FingerprintSample).where(FingerprintSample.fingerprint_id == fingerprint_id)
    samples_res = await db.execute(samples_stmt)
    samples = samples_res.scalars().all()

    if not samples:
        raise ConflictError("Cannot calculate statistics: Survey has 0 accepted samples.")

    # Group RSSI readings by AP
    ap_readings: Dict[uuid.UUID, List[int]] = {}
    for s in samples:
        ap_readings.setdefault(s.access_point_id, []).append(s.rssi)

    # Clear previous calculated stats
    existing_stats_stmt = select(FingerprintAPStat).where(FingerprintAPStat.fingerprint_id == fingerprint_id)
    existing_stats_res = await db.execute(existing_stats_stmt)
    for old_stat in existing_stats_res.scalars().all():
        await db.delete(old_stat)
    await db.flush()

    new_stats: List[FingerprintAPStat] = []
    stdevs: List[float] = []

    for ap_id, rssis in ap_readings.items():
        med = float(statistics.median(rssis))
        mean_val = float(statistics.mean(rssis))
        std_val = float(statistics.stdev(rssis)) if len(rssis) > 1 else 0.0
        stdevs.append(std_val)

        stat = FingerprintAPStat(
            fingerprint_id=fingerprint.id,
            access_point_id=ap_id,
            median_rssi=round(med, 2),
            mean_rssi=round(mean_val, 2),
            stddev_rssi=round(std_val, 2),
            sample_count=len(rssis),
        )
        new_stats.append(stat)

    fingerprint.ap_stats = new_stats

    # Calculate Quality Score (0.0 to 1.0 coverage and stability rating):
    # 1. AP Diversity (40% weight): Target >= 3 distinct APs for reliable multilateration
    ap_score = min(1.0, len(ap_readings) / 3.0) * 0.40

    # 2. Sample Depth (30% weight): Target >= 20 scan samples for statistical stability
    sample_score = min(1.0, fingerprint.sample_count / 20.0) * 0.30

    # 3. Signal Stability (30% weight): Average stddev < 5 dBm is ideal, > 13 dBm is noisy
    avg_stdev = statistics.mean(stdevs) if stdevs else 10.0
    stability_score = max(0.0, min(1.0, (13.0 - avg_stdev) / 8.0)) * 0.30

    fingerprint.quality_score = round(ap_score + sample_score + stability_score, 2)

    await db.commit()
    logger.info(
        "Calculated AP stats for fingerprint %s: %d APs, quality_score=%.2f",
        fingerprint.id,
        len(new_stats),
        fingerprint.quality_score,
    )
    return await get_fingerprint_by_id(db, fingerprint.id)




async def activate_fingerprint(db: AsyncSession, fingerprint_id: uuid.UUID) -> Fingerprint:
    """Calculate final AP stats and activate survey as the primary radio reference for its zone."""
    fingerprint = await calculate_and_save_ap_stats(db, fingerprint_id)

    # Archive any previously active fingerprint for this zone to guarantee single active survey
    archive_stmt = (
        update(Fingerprint)
        .where(
            Fingerprint.zone_id == fingerprint.zone_id,
            Fingerprint.status == FingerprintStatus.ACTIVE,
            Fingerprint.id != fingerprint.id,
        )
        .values(status=FingerprintStatus.ARCHIVED)
    )
    await db.execute(archive_stmt)

    fingerprint.status = FingerprintStatus.ACTIVE
    await db.commit()
    from app.services.localization_service import invalidate_fingerprint_cache

    invalidate_fingerprint_cache()
    logger.info("Activated fingerprint %s for zone %s", fingerprint.id, fingerprint.zone_id)
    return await get_fingerprint_by_id(db, fingerprint.id)


async def get_active_fingerprint_for_zone(db: AsyncSession, zone_id: uuid.UUID) -> Optional[Fingerprint]:
    """Retrieve the currently active fingerprint survey and AP distribution for a physical zone."""
    stmt = (
        select(Fingerprint)
        .options(
            selectinload(Fingerprint.ap_stats).selectinload(FingerprintAPStat.access_point),
        )
        .where(
            Fingerprint.zone_id == zone_id,
            Fingerprint.status == FingerprintStatus.ACTIVE,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
