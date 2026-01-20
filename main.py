import os
import time
from urllib.parse import quote_plus

from flask import Flask, render_template, redirect, url_for, request, session
from sqlalchemy import create_engine, text


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


# ---------------------------
# Cloud SQL (MySQL) via unix socket
# ---------------------------
def get_engine():
    db_user = os.environ["DB_USER"]
    db_pass = quote_plus(os.environ["DB_PASS"])
    db_name = os.environ["DB_NAME"]
    instance = os.environ["INSTANCE_CONNECTION_NAME"]

    socket_path = f"/cloudsql/{instance}"
    uri = f"mysql+pymysql://{db_user}:{db_pass}@/{db_name}?unix_socket={socket_path}"
    return create_engine(uri, pool_pre_ping=True)


engine = get_engine()


def wait_for_db(max_wait_seconds=30):
    deadline = time.time() + max_wait_seconds
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(2)


def init_db():
    wait_for_db(30)
    with engine.begin() as conn:
        # Include description because menu.html expects item.description
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description VARCHAR(255) DEFAULT '',
                price DECIMAL(6,2) NOT NULL
            )
        """))

        # Seed if empty
        count = conn.execute(text("SELECT COUNT(*) FROM menu_items")).scalar() or 0
        if count == 0:
            conn.execute(text("""
                INSERT INTO menu_items (name, description, price) VALUES
                ('Chicken Burger', 'Crispy chicken burger with salad.', 10.49),
                ('Margherita Pizza', 'Classic cheese & tomato pizza.', 9.99),
                ('Fries', 'Golden fries with seasoning.', 3.49),
                ('Coke', '330ml can.', 1.99)
            """))


_db_ready = False


@app.before_request
def ensure_db_ready():
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


# ---------------------------
# Cart helpers
# ---------------------------
def get_cart():
    # { "item_id": qty }
    return session.get("cart", {})


def build_cart_items(cart):
    if not cart:
        return [], 0.0

    ids = [int(i) for i in cart.keys()]
    placeholders = ", ".join(str(i) for i in ids)

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT id, name, price FROM menu_items WHERE id IN ({placeholders})")
        ).mappings().all()

    items_by_id = {r["id"]: r for r in rows}

    cart_items = []
    total = 0.0

    for item_id_str, qty in cart.items():
        item_id = int(item_id_str)
        if item_id not in items_by_id:
            continue

        price = float(items_by_id[item_id]["price"])
        qty = int(qty)
        line_total = price * qty
        total += line_total

        cart_items.append({
            "id": item_id,
            "name": items_by_id[item_id]["name"],
            "price": price,
            "qty": qty,
            "line_total": line_total
        })

    return cart_items, total


# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def home():
    return redirect(url_for("menu"))


@app.get("/menu")
def menu():
    with engine.connect() as conn:
        menu_items = conn.execute(
            text("SELECT id, name, description, price FROM menu_items ORDER BY id ASC")
        ).mappings().all()

    # Your template expects variable name: menu
    return render_template("menu.html", title="Menu", menu=menu_items)


@app.post("/cart/add/<int:item_id>")
def cart_add(item_id):
    cart = get_cart()
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    session["cart"] = cart
    return redirect(url_for("cart"))


@app.get("/cart")
def cart():
    cart_dict = get_cart()
    cart_items, total = build_cart_items(cart_dict)

    # Your template expects: cart_items
    # (If your cart.html also displays total, add it there; harmless to pass anyway.)
    return render_template("cart.html", title="Cart", cart_items=cart_items, total=total)


@app.post("/cart/remove/<int:item_id>")
def cart_remove(item_id):
    cart = get_cart()
    cart.pop(str(item_id), None)
    session["cart"] = cart
    return redirect(url_for("cart"))


@app.get("/admin")
def admin():
    return render_template("admin.html", title="Admin")


# Local-only run
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)

