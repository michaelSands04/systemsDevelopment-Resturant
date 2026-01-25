# Restaurant App (Cloud Systems Development)

Flask web application deployed on **Google App Engine (Standard)** demonstrating:
- **Cloud SQL (MySQL)** for structured relational data (menu items, users, orders)
- **Firestore** for semi/unstructured data (reviews, audit logs, item_stats)
- **Google Cloud Functions (Gen2 HTTP)** for serverless processing (review stats + export)
- **Security controls**: password hashing, **CSRF protection**, secure session cookies, **Secret Manager** for secrets
- **RESTful API endpoints** for menu, reviews, and statistics

---

## Features

### Customer
- Browse menu (Cloud SQL)
- Add items to cart (session-based)
- Register / Login / Logout (hashed passwords)
- Checkout → place an order (Cloud SQL)
- View **My Orders** page (Cloud SQL: order history + items)
- Leave reviews (Firestore)
- View menu item **avg rating** + **review count** (Firestore `item_stats`)
- View **Stats Dashboard** (top items + latest reviews, SQL + Firestore combined)

### Admin
- Admin dashboard `/admin`
- Manage orders `/admin/orders` (view all orders, update status)
- View audit logs (Firestore `audit_logs`) via `/admin/logs`
- Export reviews via Cloud Function `/admin/export-reviews` (serverless CSV export)

---

## Architecture (High level)

### App Engine (Flask)
- Serves HTML pages + REST API endpoints.
- Connects to Cloud SQL via unix socket: `/cloudsql/<INSTANCE_CONNECTION_NAME>`
- Uses session cookies for auth and cart state.
- Uses CSRF protection for POST routes.

### Cloud SQL (MySQL)
Stores structured relational data:
- `menu_items` (id, name, description, price, category, image_url)
- `users` (id, username, password_hash, role, created_at)
- `orders` (id, user_id, status, total_price, created_at)
- `order_items` (id, order_id, menu_item_id, qty, unit_price)

### Firestore (NoSQL)
Stores semi/unstructured documents:
- `reviews` (username, item_id, rating, comment, created_at)
- `item_stats` (item_id, review_count, total_rating, avg_rating, updated_at)
- `audit_logs` (event, username, ip, meta, created_at)

### Cloud Functions (Gen2 HTTP)
- **Review stats updater**: Updates Firestore `item_stats` whenever a review is created  
  - Triggered from `/reviews` POST using `requests.post(...)`
  - Protected via `X-Internal-Token` header
- **Export reviews**: Returns CSV data for admins
  - Called from `/admin/export-reviews`

---

## REST API endpoints

These endpoints return JSON (used for integration/testing/evidence):

- `GET /api/menu`  
  Returns menu items from Cloud SQL.

- `GET /api/reviews?limit=20&item_id=2`  
  Returns latest reviews from Firestore (optional filtering by item_id).

- `GET /api/stats?limit=20`  
  Returns Cloud SQL menu items joined with Firestore `item_stats`.

---

## Security controls (implemented)

- **Password hashing** using `werkzeug.security` (`generate_password_hash`, `check_password_hash`)
- **Role-based access control** (admin-only pages protected)
- **CSRF protection** enabled via `Flask-WTF` (`CSRFProtect`)
- **Secure session cookies** (recommended settings: Secure, HttpOnly, SameSite)
- **Secret Manager** for sensitive config (DB password / internal tokens)
- **Internal token** to protect Cloud Function endpoints (`X-Internal-Token`)
- **Audit logging** stored in Firestore (`audit_logs`)

---

## How this meets the coursework requirements

### 1) Data persistence (SQL + NoSQL)
- Cloud SQL stores menu items, user accounts, orders (structured, relational)
- Firestore stores reviews, audit logs, and aggregated review stats (semi/unstructured)

### 2) Cloud security
- Authentication: login/logout with hashed passwords
- CSRF protection for POST actions
- Secret Manager for secrets
- Internal token for Cloud Function auth
- Audit logging of security-relevant events

### 3) Cloud APIs + Cloud Functions
- Google Cloud Functions used for review stats + export
- REST APIs expose data (menu/reviews/stats) for integration/testing/evidence

### 4) Deployment plan
- Flask app deployed to Google App Engine (Standard)
- Cloud SQL connection via unix socket on App Engine
- Firestore database selected by `FIRESTORE_DB`
- Cloud Functions deployed separately and called using environment variables

---

## Environment variables / Secrets

### Cloud SQL
- `DB_USER`
- `DB_PASS` (**Secret Manager** recommended)
- `DB_NAME`
- `INSTANCE_CONNECTION_NAME`

### Flask / Auth
- `SECRET_KEY` (**Secret Manager** recommended)
- `ADMIN_USER` (optional)
- `ADMIN_PASS` (**Secret Manager** recommended)

### Firestore / Function integration
- `FIRESTORE_DB`
- `REVIEW_STATS_URL`
- `EXPORT_REVIEWS_URL`
- `INTERNAL_TOKEN` (**Secret Manager** recommended)

---

## Run locally (development)

```bash
python -m venv .venv
source .venv/bin/activate  # (or .venv\Scripts\activate on Windows)
pip install -r requirements.txt
python main.py
