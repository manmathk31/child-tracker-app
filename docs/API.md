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

