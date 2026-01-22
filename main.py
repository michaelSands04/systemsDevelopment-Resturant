import os
from functools import wraps
from decimal import Decimal
from datetime import datetime, timezone
import json
import requests
from datetime import datetime, timezone
from google.cloud import firestore
from google.cloud.firestore_v1.field_path import FieldPath


from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import create_engine, text
from google.cloud import firestore

FIRESTORE_DB = os.environ.get("FIRESTORE_DB", "resturantdb2")
db_fs = firestore.Client(database=FIRESTORE_DB)




app = Flask(__name__)

# IMPORTANT: In production you should use Secret Manager later.
# For now: use env var if set, else fallback.
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# ---- DB / Engine ----
_engine = None


def get_engine():
    """
    Create (and cache) SQLAlchemy engine for Cloud SQL MySQL.
    Uses Unix socket on App Engine Standard: /cloudsql/<INSTANCE_CONNECTION_NAME>
    """
    global _engine
    if _engine is not None:
        return _engine

    db_user = os.environ["DB_USER"]
    db_pass = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]
    instance = os.environ["INSTANCE_CONNECTION_NAME"]

    socket_path = f"/cloudsql/{instance}"

    uri = (
        f"mysql+pymysql://{db_user}:{db_pass}@/{db_name}"
        f"?unix_socket={socket_path}"
        f"&charset=utf8mb4"
    )

    _engine = create_engine(
        uri,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=2,
    )
    return _engine


def init_db():
    """
    Ensure required tables exist and seed starter data.
    Runs safely multiple times.
    """
    engine = get_engine()
    with engine.begin() as conn:
        # Menu items
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description VARCHAR(255) NOT NULL DEFAULT '',
                price DECIMAL(10,2) NOT NULL
            )
        """))

        # Users table for auth
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'customer',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Seed menu if empty
        count = conn.execute(text("SELECT COUNT(*) FROM menu_items")).scalar()
        if int(count) == 0:
            conn.execute(text("""
                INSERT INTO menu_items (name, description, price) VALUES
                ('Chicken Burger', 'Crispy chicken burger with salad.', 10.49),
                ('Margherita Pizza', 'Classic cheese & tomato pizza.', 9.99),
                ('Fries', 'Golden fries with seasoning.', 3.49),
                ('Coke', '330ml can.', 1.99)
            """))

        # Optional: bootstrap an admin user (set these in app.yaml later)
        admin_user = os.environ.get("ADMIN_USER")
        admin_pass = os.environ.get("ADMIN_PASS")
        if admin_user and admin_pass:
            existing = conn.execute(
                text("SELECT id FROM users WHERE username=:u"),
                {"u": admin_user}
            ).fetchone()
            if not existing:
                conn.execute(
                    text("INSERT INTO users (username, password_hash, role) VALUES (:u, :ph, 'admin')"),
                    {"u": admin_user, "ph": generate_password_hash(admin_pass)}
                )


@app.before_request
def ensure_db_ready():
    # Ensures DB tables exist before routes execute.
    init_db()


# ---- Auth helpers ----
def current_user():
    """
    Returns a dict like {"id":..., "username":..., "role":...} or None
    """
    return session.get("user")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


# ---- Logging ---- 
from datetime import datetime, timezone

from datetime import datetime, timezone

from datetime import datetime, timezone

def log_event(event: str, username: str | None, ip: str | None = None, meta: dict | None = None):
    try:
        db_fs.collection("audit_logs").add({
            "event": event,
            "username": username,          
            "ip": ip,
            "meta": meta or {},
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        # Log to App Engine logs, but don't crash the page
        app.logger.exception("Firestore audit log failed: %s", e)



def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash("Please log in.", "warning")
            return redirect(url_for("login"))
        if user.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("menu"))
        return fn(*args, **kwargs)
    return wrapper


# ---- Pages ----
@app.route("/")
def home():
    return render_template("home.html", user=current_user())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", user=current_user())

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    password2 = request.form.get("password2", "")

    if len(username) < 3:
        flash("Username must be at least 3 characters.", "danger")
        return redirect(url_for("register"))
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("register"))
    if password != password2:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("register"))

    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE username=:u"),
            {"u": username}
        ).fetchone()
        if existing:
            flash("That username is already taken.", "danger")
            return redirect(url_for("register"))

        conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :ph, 'customer')"),
            {"u": username, "ph": generate_password_hash(password)}
        )

    flash("Account created. Please log in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", user=current_user())

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, username, password_hash, role FROM users WHERE username=:u"),
            {"u": username}
        ).fetchone()

    if not row or not check_password_hash(row.password_hash, password):
        flash("Invalid username or password.", "danger")
        return redirect(url_for("login"))

    session["user"] = {"id": row.id, "username": row.username, "role": row.role}
    flash("Logged in successfully.", "success")

    
    log_event("login", row.username, request.remote_addr)

    nxt = request.args.get("next")
    return redirect(nxt or url_for("menu"))



@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    flash("Logged out.", "info")
    log_event("logout", (current_user() or {}).get("username"), request.remote_addr)

    return redirect(url_for("menu"))

from datetime import datetime, timezone
from google.cloud import firestore

from datetime import datetime, timezone
from google.cloud import firestore

@app.route("/reviews", methods=["GET", "POST"])
def reviews():
    user = current_user()  # your existing helper returns session.get("user") or None

    # --- Load menu items from Cloud SQL (for dropdown + name lookup) ---
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, name
            FROM menu_items
            ORDER BY id ASC
        """)).fetchall()

    menu_items = [{"id": r.id, "name": r.name} for r in rows]

    # --- POST: create a new review in Firestore ---
    if request.method == "POST":
        if not user:
            flash("Please log in to leave a review.", "warning")
            return redirect(url_for("login", next="/reviews"))

        # Read + validate item_id
        item_id_raw = request.form.get("item_id", "").strip()
        if not item_id_raw.isdigit():
            flash("Please select a valid menu item.", "danger")
            return redirect(url_for("reviews"))

        item_id = int(item_id_raw)

        # Optional: ensure item_id is actually in your SQL menu
        valid_ids = {m["id"] for m in menu_items}
        if item_id not in valid_ids:
            flash("That menu item does not exist.", "danger")
            return redirect(url_for("reviews"))

        # Read + validate rating/comment
        rating = int(request.form.get("rating", "5"))
        rating = max(1, min(5, rating))
        comment = request.form.get("comment", "").strip()

        # Save in Firestore (NoSQL)
        db_fs.collection("reviews").add({
            "username": user["username"],
            "item_id": int(item_id),     # ensure it's an int
            "rating": int(rating),       # ensure it's an int
            "comment": comment,
            "created_at": datetime.now(timezone.utc),
})

# Call internal stats function (HTTP Cloud Function)
        try:
            url = os.environ.get("REVIEW_STATS_URL")
            token = os.environ.get("INTERNAL_TOKEN")

            if url and token:
                requests.post(
            url,
            json={"item_id": int(item_id), "rating": int(rating)},
            headers={"X-Internal-Token": token},
            timeout=5,
        )
        except Exception as e:
    # optional: print(e) or log it
            pass
        
        

        # Audit log (Firestore audit_logs)
        log_event(
            "review_created",
            user["username"],
            request.remote_addr,
            {"item_id": item_id, "rating": rating}
        )

        flash("Thanks for your review!", "success")
        return redirect(url_for("reviews"))

    # --- GET: show latest 20 reviews ---
    docs = (
        db_fs.collection("reviews")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(20)
        .stream()
    )

    review_list = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id
        review_list.append(data)

    # Pass menu items to template for dropdown
    return render_template("reviews.html", user=user, menu_items=menu_items, reviews=review_list)



@app.route("/admin/logs")
@admin_required
def admin_logs():
    docs = (
        db_fs.collection("audit_logs")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(50)
        .stream()
    )

    logs = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id
        logs.append(data)

    return render_template("admin_logs.html", logs=logs, user=current_user())



@app.route("/menu")
def menu():
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, name, description, price
            FROM menu_items
            ORDER BY id ASC
        """)).fetchall()

    menu_items = [
        {"id": r.id, "name": r.name, "description": r.description, "price": float(r.price)}
        for r in rows
    ]

    # --- Pull rating stats from Firestore (item_stats/{item_id}) ---
    for m in menu_items:
        try:
            doc = db_fs.collection("item_stats").document(str(m["id"])).get()
            if doc.exists:
                s = doc.to_dict() or {}
                m["avg_rating"] = s.get("avg_rating")
                m["review_count"] = int(s.get("review_count", 0))
            else:
                m["avg_rating"] = None
                m["review_count"] = 0
        except Exception:
            # Don't break menu page if Firestore is temporarily unavailable
            m["avg_rating"] = None
            m["review_count"] = 0

    return render_template("menu.html", menu=menu_items, user=current_user())

@app.route("/stats")
def stats():
    # 1) Read top rated item stats from Firestore
    docs = (
        db_fs.collection("item_stats")
        .order_by("avg_rating", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )

    stats_list = []
    item_ids = []
    for d in docs:
        data = d.to_dict() or {}
        # doc id is item_id as string
        data["item_id"] = d.id
        stats_list.append(data)
        item_ids.append(int(d.id))

    # 2) Map item_id -> menu item info from Cloud SQL
    menu_lookup = {}
    if item_ids:
        engine = get_engine()
        with engine.begin() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, name, price
                    FROM menu_items
                    WHERE id IN :ids
                """).bindparams(ids=tuple(item_ids))
            ).fetchall()

        menu_lookup = {r.id: {"name": r.name, "price": float(r.price)} for r in rows}

    # 3) Merge into a display-friendly list
    top_items = []
    for s in stats_list:
        iid = int(s.get("item_id"))
        mi = menu_lookup.get(iid, {"name": f"Item {iid}", "price": None})
        top_items.append({
            "item_id": iid,
            "name": mi["name"],
            "price": mi["price"],
            "avg_rating": s.get("avg_rating", 0),
            "review_count": s.get("review_count", 0),
        })

    # 4) Also show latest reviews (optional but looks great)
    rdocs = (
        db_fs.collection("reviews")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )
    latest_reviews = []
    for d in rdocs:
        data = d.to_dict() or {}
        data["id"] = d.id
        # attach menu name for readability
        iid = data.get("item_id")
        try:
            iid_int = int(iid)
            data["item_name"] = menu_lookup.get(iid_int, {}).get("name", f"Item {iid_int}")
        except Exception:
            data["item_name"] = "Unknown"
        latest_reviews.append(data)

    return render_template(
        "stats.html",
        user=current_user(),
        top_items=top_items,
        latest_reviews=latest_reviews
    )


# ---- Cart (session-based) ----
def get_cart():
    return session.setdefault("cart", {})  # {item_id: qty}


@app.route("/cart")
def cart():
    cart_map = get_cart()
    engine = get_engine()

    cart_items = []
    total = Decimal("0.00")

    if cart_map:
        item_ids = [int(k) for k in cart_map.keys()]
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT id, name, price FROM menu_items WHERE id IN :ids").bindparams(ids=tuple(item_ids))
            ).fetchall()

        price_lookup = {r.id: Decimal(str(r.price)) for r in rows}
        name_lookup = {r.id: r.name for r in rows}

        for item_id_str, qty in cart_map.items():
            item_id = int(item_id_str)
            qty = int(qty)
            price = price_lookup.get(item_id, Decimal("0.00"))
            name = name_lookup.get(item_id, "Unknown item")
            line_total = price * qty
            total += line_total
            cart_items.append({
                "id": item_id,
                "name": name,
                "qty": qty,
                "price": float(price),
                "line_total": float(line_total),
            })

    return render_template("cart.html", cart_items=cart_items, total=float(total), user=current_user())


@app.route("/cart/add/<int:item_id>", methods=["POST"])
def cart_add(item_id):
    cart_map = get_cart()
    cart_map[str(item_id)] = int(cart_map.get(str(item_id), 0)) + 1
    session.modified = True
    return redirect(url_for("menu"))


@app.route("/cart/remove/<int:item_id>", methods=["POST"])
def cart_remove(item_id):
    cart_map = get_cart()
    cart_map.pop(str(item_id), None)
    session.modified = True
    return redirect(url_for("cart"))


# ---- Admin (protected) ----
@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", user=current_user())


# ---- Simple REST API (optional small win) ----
@app.route("/api/menu")
def api_menu():
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, name, description, price FROM menu_items ORDER BY id ASC")).fetchall()
    return jsonify([
        {"id": r.id, "name": r.name, "description": r.description, "price": float(r.price)}
        for r in rows
    ])


if __name__ == "__main__":
    # Local only (App Engine uses gunicorn entrypoint)
    app.run(host="127.0.0.1", port=8080, debug=True)
