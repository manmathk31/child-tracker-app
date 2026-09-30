# ChildTrack Data Model Specification

This document is the authoritative definition of the ChildTrack database architecture. All SQLAlchemy models and Alembic migrations must strictly align with this specification.

---

## 1. Architectural Principles

1. **UUID Primary Keys**: Every primary entity uses a `UUIDv4` primary key (`id`) rather than an autoincrement integer. This ensures uniqueness across multiple schools, campuses, and offline sync buffers.
2. **Server-side Timestamps**: All entities include `created_at` and `updated_at` timestamps with UTC timezone enforcement.
3. **Soft Deletes**: Entities referenced by audit or historical tracking tables (`students`, `devices`, `zones`, `access_points`) employ soft deletion via `is_active: bool`. Rows are never hard-deleted if referenced by historical records.
4. **Foreign Key Integrity**: Foreign keys explicitly define `ON DELETE RESTRICT` for core tracking relationships to prevent accidental data cascades.
5. **Hot-Path Indexing**: Columns filtered or ordered on ingestion and live dashboard queries (`devices.last_seen_at`, `location_records.recorded_at`, `alerts.status`) are explicitly indexed.

---

## 2. Entity Schemas

### 2.1 `users`
Represents administrative personnel, teachers, and system operators.
- `id` (UUID, PK)
- `email` (VARCHAR(255), UNIQUE, NOT NULL, INDEX)
- `hashed_password` (VARCHAR(255), NOT NULL)
- `full_name` (VARCHAR(255), NOT NULL)
- `role` (ENUM('admin', 'teacher'), NOT NULL, DEFAULT 'teacher')
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `last_login_at` (TIMESTAMPTZ, NULLABLE)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.2 `students`
Represents children enrolled in the institution.
- `id` (UUID, PK)
- `student_code` (VARCHAR(64), UNIQUE, NOT NULL, INDEX) — School-assigned identifier
- `full_name` (VARCHAR(255), NOT NULL)
- `class_name` (VARCHAR(64), NOT NULL) — e.g. "Grade 3A"
- `age` (INTEGER, NOT NULL)
- `photo_url` (VARCHAR(512), NULLABLE)
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.3 `devices` (Wearables)
ESP32-based hardware wearables assigned to students.
- `id` (UUID, PK)
- `device_code` (VARCHAR(64), UNIQUE, NOT NULL, INDEX) — e.g. "WB-001"
- `mac_address` (VARCHAR(17), UNIQUE, NOT NULL, INDEX) — e.g. "AA:BB:CC:DD:EE:FF"
- `battery_percent` (INTEGER, NOT NULL, DEFAULT 100) — 0 to 100
- `firmware_version` (VARCHAR(32), NULLABLE)
- `last_seen_at` (TIMESTAMPTZ, NULLABLE, INDEX)
- `status` (ENUM('online', 'offline'), NOT NULL, DEFAULT 'offline')
- `student_id` (UUID, FK -> students.id, NULLABLE, UNIQUE, ON DELETE SET NULL)
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.4 `zones`
Monitored indoor or outdoor zones within the school facility.
- `id` (UUID, PK)
- `name` (VARCHAR(128), UNIQUE, NOT NULL)
- `description` (TEXT, NULLABLE)
- `building` (VARCHAR(64), NULLABLE)
- `floor` (VARCHAR(32), NULLABLE)
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.5 `access_points`
Wi-Fi Access Points fixed in physical locations.
- `id` (UUID, PK)
- `name` (VARCHAR(128), NOT NULL)
- `bssid` (VARCHAR(17), UNIQUE, NOT NULL, INDEX) — Standard MAC format
- `channel` (INTEGER, NULLABLE)
- `zone_id` (UUID, FK -> zones.id, NULLABLE, ON DELETE RESTRICT)
- `is_active` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.6 `fingerprints`
Fingerprint survey sets for a specific zone.
- `id` (UUID, PK)
- `zone_id` (UUID, FK -> zones.id, NOT NULL, ON DELETE RESTRICT)
- `created_by` (UUID, FK -> users.id, NOT NULL, ON DELETE RESTRICT)
- `sample_count` (INTEGER, NOT NULL, DEFAULT 0)
- `quality_score` (FLOAT, NULLABLE) — 0.0 to 1.0 calculated coverage metric
- `status` (ENUM('draft', 'active'), NOT NULL, DEFAULT 'draft')
- `notes` (TEXT, NULLABLE)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.7 `fingerprint_ap_stats`
Processed statistical representations used by the localization engine.
- `id` (UUID, PK)
- `fingerprint_id` (UUID, FK -> fingerprints.id, NOT NULL, ON DELETE CASCADE)
- `access_point_id` (UUID, FK -> access_points.id, NOT NULL, ON DELETE RESTRICT)
- `median_rssi` (FLOAT, NOT NULL)
- `mean_rssi` (FLOAT, NOT NULL)
- `stddev_rssi` (FLOAT, NOT NULL)
- `sample_count` (INTEGER, NOT NULL)

### 2.8 `fingerprint_samples`
Raw RSSI survey vectors collected during calibration.
- `id` (UUID, PK)
- `fingerprint_id` (UUID, FK -> fingerprints.id, NOT NULL, ON DELETE CASCADE)
- `access_point_id` (UUID, FK -> access_points.id, NOT NULL, ON DELETE RESTRICT)
- `rssi` (INTEGER, NOT NULL)
- `collected_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.9 `allowed_zones`
Defines permissions for students within zones.
- `id` (UUID, PK)
- `student_id` (UUID, FK -> students.id, NOT NULL, ON DELETE CASCADE)
- `zone_id` (UUID, FK -> zones.id, NOT NULL, ON DELETE CASCADE)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
- Unique constraint: `(student_id, zone_id)`

### 2.10 `location_records`
Audit trail of student localization estimates.
- `id` (UUID, PK)
- `student_id` (UUID, FK -> students.id, NOT NULL, ON DELETE RESTRICT, INDEX)
- `device_id` (UUID, FK -> devices.id, NOT NULL, ON DELETE RESTRICT, INDEX)
- `zone_id` (UUID, FK -> zones.id, NULLABLE, ON DELETE RESTRICT, INDEX) — NULL indicates Unknown/Low Confidence
- `confidence` (FLOAT, NOT NULL) — 0.0 to 1.0
- `raw_scan` (JSONB / JSON, NOT NULL) — Full telemetry payload
- `recorded_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW(), INDEX)

### 2.11 `alerts`
Safety and operational notifications requiring teacher/admin awareness.
- `id` (UUID, PK)
- `student_id` (UUID, FK -> students.id, NULLABLE, ON DELETE SET NULL, INDEX)
- `device_id` (UUID, FK -> devices.id, NULLABLE, ON DELETE SET NULL)
- `zone_id` (UUID, FK -> zones.id, NULLABLE, ON DELETE SET NULL)
- `type` (ENUM('sos', 'fall', 'restricted_zone', 'low_battery', 'offline', 'low_confidence', 'out_of_zone'), NOT NULL)
- `severity` (ENUM('info', 'warning', 'critical'), NOT NULL)
- `status` (ENUM('active', 'acknowledged', 'resolved'), NOT NULL, DEFAULT 'active', INDEX)
- `message` (TEXT, NOT NULL)
- `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW(), INDEX)
- `acknowledged_by` (UUID, FK -> users.id, NULLABLE, ON DELETE SET NULL)
- `acknowledged_at` (TIMESTAMPTZ, NULLABLE)
- `resolved_at` (TIMESTAMPTZ, NULLABLE)

### 2.12 `alert_settings`
Configurable threshold parameters.
- `id` (UUID, PK) — Singleton row
- `offline_threshold_minutes` (INTEGER, NOT NULL, DEFAULT 5)
- `critical_offline_threshold_minutes` (INTEGER, NOT NULL, DEFAULT 15)
- `low_battery_percent` (INTEGER, NOT NULL, DEFAULT 20)
- `min_localization_confidence` (FLOAT, NOT NULL, DEFAULT 0.45)
- `restricted_zone_alerts_enabled` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `fall_detection_enabled` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `sos_alerts_enabled` (BOOLEAN, NOT NULL, DEFAULT TRUE)
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())

### 2.13 `school_settings`
Organization-level configuration.
- `id` (UUID, PK) — Singleton row
- `school_name` (VARCHAR(255), NOT NULL, DEFAULT "School")
- `building_name` (VARCHAR(255), NOT NULL, DEFAULT "Main Campus")
- `timezone` (VARCHAR(64), NOT NULL, DEFAULT "UTC")
- `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT NOW())
