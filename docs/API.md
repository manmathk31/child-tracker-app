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

## 3. Web Views (Jinja2)

### 3.1 Live Safety Dashboard
`GET /dashboard`

Renders the responsive dashboard shell displaying current occupancy metrics and safety feeds. If no data exists, renders compliant empty states without fabricated metrics.
