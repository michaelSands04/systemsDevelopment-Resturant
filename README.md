# Restaurant App (Cloud Systems Development)

Flask web application deployed on **Google App Engine (Standard)** demonstrating:
- **Cloud SQL (MySQL)** for structured relational data (menu items + users)
- **Firestore** for semi/unstructured data (reviews, audit logs, item_stats)
- **Google Cloud Function (Gen2 HTTP)** to update aggregated review statistics
- **Security improvements** including password hashing + **Secret Manager** for secrets
- **RESTful API endpoints** for menu, reviews, and statistics

---

## Features

### Customer
- Browse menu (Cloud SQL)
- Add items to cart (session-based)
- Register / Login / Logout (hashed passwords)
- Leave reviews (Firestore)
- View menu item **avg rating** + **review count** (Firestore `item_stats`)
- View **Stats Dashboard** (top items + latest reviews, SQL + Firestore combined)

### Admin
- View audit logs (Firestore `audit_logs`) via `/admin/logs`

---

## Architecture (High level)

### App Engine (Flask)
- Serves HTML pages + REST API endpoints.
- Connects to Cloud SQL via unix socket: `/cloudsql/<INSTANCE_CONNECTION_NAME>`

### Cloud SQL (MySQL)
Stores structured relational data:
- `menu_items` (id, name, description, price)
- `users` (id, username, password_hash, role, created_at)

### Firestore (NoSQL)
Stores semi/unstructured documents:
- `reviews` (username, item_id, rating, comment, created_at)
- `item_stats` (item_id, review_count, total_rating, avg_rating, updated_at)
- `audit_logs` (event, username, ip, meta, created_at)

### Cloud Function (Gen2 HTTP)
Updates Firestore `item_stats` whenever a review is created:
- Triggered from `/reviews` POST with `requests.post(...)`
- Protected via `X-Internal-Token` header (internal auth)

---

## REST API endpoints

These endpoints return JSON (used for integration/testing/evidence):

- `GET /api/menu`  
  Returns all menu items from Cloud SQL.

- `GET /api/reviews?limit=20&item_id=2`  
  Returns latest reviews from Firestore (optional filtering by item_id).

- `GET /api/stats?limit=20`  
  Returns Cloud SQL menu items joined with Firestore `item_stats`.

---

## How this meets the coursework requirements

### 1) Data persistence (SQL + NoSQL)
- Cloud SQL stores menu items + user accounts (structured, relational)
- Firestore stores reviews, audit logs, and aggregated review stats (semi/unstructured)

### 2) Cloud security
- **Authentication**: login/logout with password hashing (`werkzeug.security`)
- **Secret Manager**: secrets removed from config and stored securely
- **Internal token**: Cloud Function protected via header (`X-Internal-Token`)
- **Audit logging**: login/logout/review creation logged to Firestore `audit_logs`

### 3) Cloud APIs + Cloud Functions
- **Cloud Function** updates stats in Firestore (review_count/avg_rating)
- **REST APIs** expose data (menu, reviews, stats) for integration and testing

### 4) Deployment plan
- Flask app deployed to **Google App Engine (Standard)**
- Cloud SQL connection via unix socket on App Engine
- Firestore database chosen via `FIRESTORE_DB`
- Cloud Function deployed and called using `REVIEW_STATS_URL`

---

## Environment variables / Secrets

Required configuration:

### Cloud SQL
- `DB_USER`
- `DB_PASS` (**Secret Manager**)
- `DB_NAME`
- `INSTANCE_CONNECTION_NAME`

### Flask / Auth
- `SECRET_KEY` (**Secret Manager recommended**)
- `ADMIN_USER` (optional)
- `ADMIN_PASS` (**Secret Manager recommended**)

### Firestore / Function integration
- `FIRESTORE_DB`
- `REVIEW_STATS_URL`
- `INTERNAL_TOKEN` (**Secret Manager recommended**)

---

## Testing (Pytest)

Tests are located in `tests/` and include:
- Smoke tests for key pages (e.g. `/`, `/menu`, `/reviews`)
- REST API tests for:
  - `/api/menu`
  - `/api/reviews`
  - `/api/stats`
- Uses **SQLite in-memory** + **Fake Firestore** stubs so tests run without cloud resources.

Run tests:
```bash
pip install -r requirements.txt
python -m pytest -q tests
