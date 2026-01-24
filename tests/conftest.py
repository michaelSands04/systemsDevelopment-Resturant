import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash


# ---------------- Fake Firestore ----------------
class _FakeSnap:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, data=None):
        self._data = data

    def get(self, **kwargs):
        return _FakeSnap(self._data)


class _FakeCollection:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._limit = None
        self._where = None

    def where(self, field, op, value):
        self._where = (field, op, value)
        return self

    def add(self, data):
        self.store.setdefault(self.name, []).append(data)
        return ("fake_id", None)

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        items = self.store.get(self.name, [])

        if self._where:
            field, op, value = self._where
            if op == "==":
                items = [d for d in items if d.get(field) == value]

        if self._limit:
            items = items[: self._limit]

        class _FakeDoc:
            def __init__(self, i, d):
                self.id = f"doc{i}"
                self._d = d

            def to_dict(self):
                return self._d

        return [_FakeDoc(i, d) for i, d in enumerate(items)]

    def document(self, doc_id):
        if self.name == "item_stats":
            for d in self.store.get("item_stats", []):
                if str(d.get("item_id")) == str(doc_id):
                    return _FakeDocRef(d)
        return _FakeDocRef(None)


class FakeFirestoreClient:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return _FakeCollection(self.store, name)


# ---------------- Pytest fixtures ----------------
@pytest.fixture(autouse=True)
def _stub_infra(monkeypatch):
    # env vars to keep main.py happy
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASS", "test")
    monkeypatch.setenv("DB_NAME", "test")
    monkeypatch.setenv("INSTANCE_CONNECTION_NAME", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("FIRESTORE_DB", "resturantdb2")

    import main

    # shared in-memory sqlite across connections
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # create tables + seed data
    with engine.begin() as conn:
        # menu_items
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price REAL NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                image_url TEXT
            )
        """))
        conn.execute(text("DELETE FROM menu_items"))
        conn.execute(text("""
            INSERT INTO menu_items (id, name, description, price, category, image_url) VALUES
            (1, 'Chicken Burger', 'Test item', 10.49, 'burger', 'https://example.com/burger.jpg'),
            (2, 'Margherita Pizza', 'Test item', 9.99, 'pizza', 'https://example.com/pizza.jpg'),
            (3, 'Fries', 'Test item', 3.49, 'sides', 'https://example.com/fries.jpg'),
            (4, 'Coke', 'Test item', 1.99, 'drink', 'https://example.com/coke.jpg')
        """))

        # users
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'customer',
                created_at TEXT
            )
        """))
        conn.execute(text("DELETE FROM users"))
        conn.execute(
            text("""
                INSERT INTO users (id, username, password_hash, role, created_at)
                VALUES (:id, :u, :ph, :r, :t)
            """),
            {
                "id": 1,
                "u": "testuser",
                "ph": generate_password_hash("Password123!"),
                "r": "customer",
                "t": "2026-01-01T00:00:00Z",
            },
        )
        conn.execute(
            text("""
                INSERT INTO users (id, username, password_hash, role, created_at)
                VALUES (:id, :u, :ph, :r, :t)
            """),
            {
                "id": 2,
                "u": "admin",
                "ph": generate_password_hash("AdminPass123!"),
                "r": "admin",
                "t": "2026-01-01T00:00:00Z",
            },
        )

        # orders tables (MATCHES main.py: total_price + menu_item_id)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                total_price REAL NOT NULL DEFAULT 0,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                menu_item_id INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                unit_price REAL NOT NULL
            )
        """))

    # patch app DB + infra
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "db_fs", FakeFirestoreClient())


@pytest.fixture()
def client():
    import main
    main.app.config["TESTING"] = True
    # if you enabled CSRF, keep tests working:
    main.app.config["WTF_CSRF_ENABLED"] = False

    with main.app.test_client() as c:
        yield c

