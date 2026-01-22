import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# -------- Fake Firestore --------
class _FakeSnap:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None
    def to_dict(self):
        return self._data

class _FakeDocRef:
    def __init__(self, data=None):
        self._data = data
    def get(self):
        return _FakeSnap(self._data)

class _FakeCollection:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._limit = None

    # writes
    def add(self, data):
        self.store.setdefault(self.name, []).append(data)
        return ("fake_id", None)

    # reads (chainable)
    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def stream(self):
        # Return list of fake docs with minimal interface
        items = self.store.get(self.name, [])
        if self._limit:
            items = items[: self._limit]
        class _FakeDoc:
            def __init__(self, i, d):
                self.id = f"doc{i}"
                self._d = d
            def to_dict(self):
                return self._d
        return [_FakeDoc(i, d) for i, d in enumerate(items)]

    # doc lookup: item_stats/<id>
    def document(self, doc_id):
        # try find item_stats by matching item_id
        if self.name == "item_stats":
            for d in self.store.get("item_stats", []):
                if str(d.get("item_id")) == str(doc_id) or str(d.get("item_id")) == str(int(doc_id)):
                    return _FakeDocRef(d)
        return _FakeDocRef(None)

class FakeFirestoreClient:
    def __init__(self):
        self.store = {}
    def collection(self, name):
        return _FakeCollection(self.store, name)

# -------- Pytest fixtures --------
@pytest.fixture(autouse=True)
def _stub_infra(monkeypatch):
    """
    Runs automatically for every test.
    - Provide env vars (so KeyError doesn't happen)
    - Replace Cloud SQL engine with in-memory SQLite
    - Replace Firestore client with a fake in-memory store
    """
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASS", "test")
    monkeypatch.setenv("DB_NAME", "test")
    monkeypatch.setenv("INSTANCE_CONNECTION_NAME", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("FIRESTORE_DB", "resturantdb2")

    import main

    # SQLite in-memory DB shared across connections
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create minimal tables + seed data used by /menu and /reviews
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price REAL NOT NULL
            )
        """))
        conn.execute(text("DELETE FROM menu_items"))
        conn.execute(text("""
            INSERT INTO menu_items (id, name, description, price) VALUES
            (1, 'Chicken Burger', 'Test item', 10.49),
            (2, 'Margherita Pizza', 'Test item', 9.99),
            (3, 'Fries', 'Test item', 3.49),
            (4, 'Coke', 'Test item', 1.99)
        """))

    # Patch your app to use SQLite instead of Cloud SQL during tests
    monkeypatch.setattr(main, "get_engine", lambda: engine)

    # Prevent your before_request init_db() from running Cloud SQL logic
    monkeypatch.setattr(main, "init_db", lambda: None)

    # Patch Firestore client
    monkeypatch.setattr(main, "db_fs", FakeFirestoreClient())

@pytest.fixture()
def client():
    import main
    main.app.config["TESTING"] = True
    with main.app.test_client() as c:
        yield c
