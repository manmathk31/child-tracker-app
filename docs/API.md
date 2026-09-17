# ChildTrack API Specification

This document details the REST API endpoints, conventions, and response contracts for ChildTrack.

---

## 1. Conventions

### 1.1 Base URL
- API endpoints: `/api/v1/*`
- System endpoints: `/health`
- Server-rendered views: `/`, `/dashboard`, `/students`, etc.

### 1.2 Request Headers
- `Content-Type: application/json`
- `Accept: application/json`
- `X-Request-ID: <uuid>` (optional client-supplied correlation ID; automatically generated if omitted)
- `Authorization: Bearer <jwt_access_token>` (for protected endpoints)

### 1.3 Uniform Error Response Structure
All 4xx and 5xx API responses follow this schema:
```json
{
  "error": {
    "code": "ERROR_CODE_STRING",
    "message": "Human-readable explanation of error condition",
    "details": {},
    "request_id": "c62bfad4-36a4-4ca8-9844-4861b5dd1341"
  }
}
```

---

## 2. Phase 0 Endpoints

### 2.1 System Health Check
`GET /health`

Verifies that the application server and its database connectivity are functional.

#### Response (Healthy)
**Status Code**: `200 OK`
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "0.1.0",
  "app_name": "ChildTrack",
  "environment": "development",
  "timestamp": "2026-09-17T00:00:00.000000Z"
}
```

#### Response (Degraded - Database Unavailable)
**Status Code**: `503 Service Unavailable`
```json
{
  "status": "degraded",
  "database": "disconnected",
  "version": "0.1.0",
  "app_name": "ChildTrack",
  "environment": "development",
  "timestamp": "2026-09-17T00:00:00.000000Z"
}
```

---

## 3. Phase 1 — Authentication Endpoints

### 3.1 Authenticate User (Login)
`POST /api/v1/auth/login`

Accepts email and password, validates credentials, sets an HttpOnly session cookie, and returns a signed JWT access token.

#### Request Body
```json
{
  "email": "admin@childtrack.local",
  "password": "Admin@12345"
}
```

#### Response (`200 OK`)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in_seconds": 1800,
  "user": {
    "id": "343d087d-150c-49c2-8360-ce3a3f848117",
    "email": "admin@childtrack.local",
    "full_name": "System Administrator",
    "role": "admin",
    "is_active": true,
    "last_login_at": "2026-09-17T02:24:41.000000Z",
    "created_at": "2026-09-17T02:24:41.000000Z",
    "updated_at": "2026-09-17T02:24:41.000000Z"
  }
}
```

### 3.2 Get Current User
`GET /api/v1/auth/me`

Returns the currently authenticated user's profile and active role.
**Headers**: `Authorization: Bearer <token>` or session cookie.

### 3.3 Create User (Admin only)
`POST /api/v1/auth/users`

Provisions a new user account with `admin` or `teacher` role.
**Headers**: `Authorization: Bearer <admin_token>`.

### 3.4 User Logout
`POST /api/v1/auth/logout`

Clears the session cookie.

---

## 4. Web Views (Jinja2)

### 4.1 Sign In Page
`GET /login` — Renders the mobile-responsive sign-in interface. Redirects to `/dashboard` if already logged in.
`POST /login` — Processes form submission, sets session cookie, and redirects to `/dashboard`.

### 4.2 Sign Out
`GET /logout` — Clears the session cookie and redirects to `/login`.

### 4.3 Live Safety Dashboard
`GET /dashboard` — Renders the responsive dashboard shell displaying current occupancy metrics and safety feeds. Unauthenticated visitors are automatically redirected to `/login`.

---

## 5. Phase 2 — Configuration & Entity Management Endpoints

### 5.1 Zones
- `GET /api/v1/zones` — List all active school zones with AP counts.
- `POST /api/v1/zones` — Create a new school zone (Admin only).
- `GET /api/v1/zones/{id}` — Retrieve zone details and associated access points.
- `PUT /api/v1/zones/{id}` — Update zone name/metadata (Admin only).
- `DELETE /api/v1/zones/{id}` — Soft-delete zone (Admin only).
- Web Views: `GET /zones`, `GET /zones/new`, `POST /zones/new`, `GET /zones/{id}`, `GET /zones/{id}/edit`, `POST /zones/{id}/edit`, `POST /zones/{id}/delete`.

### 5.2 Access Points
- `GET /api/v1/access-points` — List all registered Wi-Fi APs with physical zone mapping.
- `POST /api/v1/access-points` — Register an AP with BSSID and assigned zone (Admin only).
- `GET /api/v1/access-points/{id}` — Retrieve AP details.
- `PUT /api/v1/access-points/{id}` — Update AP label, channel, or zone mapping (Admin only).
- `DELETE /api/v1/access-points/{id}` — Soft-delete AP (Admin only).
- Web Views: `GET /access-points`, `GET /access-points/new`, `POST /access-points/new`, `GET /access-points/{id}/edit`, `POST /access-points/{id}/edit`, `POST /access-points/{id}/delete`.

### 5.3 ESP32 Wearable Devices
- `GET /api/v1/devices` — List all wearable hardware tags, battery levels, and assigned students.
- `POST /api/v1/devices` — Register a wearable device by MAC and engraved device code (Admin only).
- `GET /api/v1/devices/{id}` — Retrieve wearable telemetry and assignment details.
- `PUT /api/v1/devices/{id}` — Update wearable metadata or manual student pairing (Admin only).
- `DELETE /api/v1/devices/{id}` — Soft-delete wearable and clear student pairing (Admin only).
- Web Views: `GET /devices`, `GET /devices/new`, `POST /devices/new`, `GET /devices/{id}/edit`, `POST /devices/{id}/edit`, `POST /devices/{id}/delete`.

### 5.4 Students
- `GET /api/v1/students` — List enrolled students, assigned wearables, and permitted zones (supports `?class_name=` filter).
- `POST /api/v1/students` — Enroll a student, assign wearable tag, and whitelist permitted zones (Admin only).
- `GET /api/v1/students/{id}` — Retrieve student profile, live tracking status, and zone whitelist.
- `PUT /api/v1/students/{id}` — Modify student profile, assigned device, or allowed zones (Admin only).
- `DELETE /api/v1/students/{id}` — Soft-delete student and release assigned wearable (Admin only).
- Web Views: `GET /students`, `GET /students/new`, `POST /students/new`, `GET /students/{id}`, `GET /students/{id}/edit`, `POST /students/{id}/edit`, `POST /students/{id}/delete`.

### 5.5 System & Alert Settings
- `GET /api/v1/settings/school` — Retrieve school organization name, campus, and timezone.
- `PUT /api/v1/settings/school` — Update organization settings (Admin only).
- `GET /api/v1/settings/alerts` — Retrieve safety thresholds (offline timeout, low battery, confidence cutoff).
- `PUT /api/v1/settings/alerts` — Update safety alert thresholds and enable/disable SOS/fall alerts (Admin only).
- Web Views: `GET /settings`, `POST /settings/school`, `POST /settings/alerts` (Admin only).

---

## 6. Phase 3 — Wi-Fi RSSI Fingerprint Collection & Calibration Endpoints

### 6.1 Calibration Surveys
- `GET /api/v1/fingerprints` — List all calibration surveys with zone metadata, status, sample counts, and quality scores.
- `POST /api/v1/fingerprints` — Initialize a draft calibration survey session for a physical zone with optional AP whitelist and RSSI floor cutoff (Admin only).
- `GET /api/v1/fingerprints/{id}` — Retrieve full survey report including computed AP statistical distributions (`median_rssi`, `mean_rssi`, `stddev_rssi`).
- `POST /api/v1/fingerprints/{id}/samples` — Automated streaming endpoint for ESP32 calibration tags and tools. Receives bursts of observed Wi-Fi beacons (`{"scan": [{"bssid": "...", "rssi": -55}]}`), filters out rogue signals/hotspots and weak noise, and records raw sample vectors.
- `POST /api/v1/fingerprints/{id}/activate` — Finalizes the survey, calculates mathematical mean/median/stddev per AP, computes coverage quality score (0.0 to 1.0), and marks the survey as active (archiving any previously active survey for that zone) (Admin only).

### 6.2 Web Views
- `GET /fingerprints` — Overview list of all calibration surveys, quality ratings, and zone statuses.
- `GET /fingerprints/new` — Survey setup form with zone selector, RSSI cutoff threshold, and selective AP checkboxes (Admin only).
- `POST /fingerprints/new` — Creates draft survey session and redirects to calibration screen (Admin only).
- `GET /fingerprints/{id}/calibrate` — Interactive calibration dashboard with live sample progress counter, AP signal tables, and simulated scan burst trigger (Admin only).
- `POST /fingerprints/{id}/activate` — Finalizes and activates survey (Admin only).
- `GET /fingerprints/{id}` — Detailed report view showing AP distribution vectors, signal stability metrics, and observation counts.


