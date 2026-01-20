import os
from functools import wraps
from decimal import Decimal

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import create_engine, text


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

    nxt = request.args.get("next")
    return redirect(nxt or url_for("menu"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    flash("Logged out.", "info")
    return redirect(url_for("menu"))


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
    return render_template("menu.html", menu=menu_items, user=current_user())


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
