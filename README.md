# Restaurant App (Cloud Systems Development)

Flask web application deployed on **Google App Engine** that demonstrates:
- **Cloud SQL (MySQL)** for structured data (menu items + users)
- **Firestore** for semi/unstructured data (reviews, audit logs, item_stats)
- **Google Cloud Function (HTTP)** to update review statistics
- **Security improvements** including password hashing + Secret Manager

---

## Features
### Customer
- Browse menu (Cloud SQL)
- Add items to cart (session-based)
- Register / Login / Logout (hashed passwords)
- Leave reviews (Firestore)
- View menu item **avg rating** + **review count** (Firestore item_stats)

### Admin
- View audit logs (Firestore audit_logs)

### Dashboard
- Combines Cloud SQL menu items with Firestore stats and latest reviews.

---

## Architecture (High level)
- **App Engine (Flask)** serves UI + REST endpoints
- **Cloud SQL (MySQL)** stores structured relational data:
  - `menu_items` (id, name, description, price)
  - `users` (id, username, password_hash, role)
- **Firestore** stores semi/unstructured data:
  - `reviews` (username, item_id, rating, comment, created_at)
  - `item_stats` (item_id, review_count, total_rating, avg_rating, updated_at)
  - `audit_logs` (event, username, ip, meta, created_at)
- **Cloud Function (Gen2 HTTP)** updates Firestore `item_stats` when a review is created
  - Called from `/reviews` POST using `requests.post(...)`
  - Protected with internal token header

---

## How this meets the coursework requirements
### 1) Data persistence (SQL + NoSQL)
- Cloud SQL stores menu + user accounts (structured, relational)
- Firestore stores reviews/audit logs/stats (semi-structured documents)

### 2) Cloud security
- **Authentication**: login/logout + password hashing (`werkzeug.security`)
- **Secret Manager**: secrets removed from `app.yaml` and stored securely
- **Internal token**: Cloud Function protected via header (`X-Internal-Token`)
- (Optional/mention) least-privilege IAM on secret access

### 3) Cloud APIs + Functions
- **Google Cloud Function** used to update stats (review_count/avg_rating)
- **REST API endpoint**: `/api/menu` returns JSON menu list

### 4) Deployment plan
- App Engine Standard for Flask app
- Cloud SQL instance connection via unix socket `/cloudsql/<INSTANCE_CONNECTION_NAME>`
- Firestore database selected via `FIRESTORE_DB`
- Cloud Function deployed in same region and called from app

---

## Environment variables / Secrets
These values are required for the app:

- `DB_USER`
- `DB_PASS` (**Secret Manager**)
- `DB_NAME`
- `INSTANCE_CONNECTION_NAME`
- `SECRET_KEY` (**Secret Manager recommended**)
- `ADMIN_USER` (optional)
- `ADMIN_PASS` (**Secret Manager recommended**)
- `FIRESTORE_DB`
- `REVIEW_STATS_URL`
- `INTERNAL_TOKEN` (**Secret Manager recommended**)

---

## Local development (optional)
If running locally, you must provide DB credentials and may need a different DB connection method
(host/port instead of unix socket). App Engine uses unix socket by default.

---

## Unit tests
Tests are in `tests/`.

Run:
```bash
python -m pytest -q tests
