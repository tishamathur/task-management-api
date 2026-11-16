import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app, raise_server_exceptions=False)
    c.session_factory = Session
    yield c
    app.dependency_overrides.clear()


def register_and_login(client, username="tisha", email="tisha@example.com", password="Secret123"):
    r = client.post("/auth/register", json={"username": username, "email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------- Auth ----------------
def test_register_hashes_password(client):
    register_and_login(client)
    db = client.session_factory()
    user = db.query(User).one()
    assert user.hashed_password != "Secret123"
    assert user.hashed_password.startswith("$2")  # bcrypt
    db.close()


def test_register_response_has_no_password(client):
    r = client.post("/auth/register", json={"username": "abc", "email": "a@b.co", "password": "Secret123"})
    assert r.status_code == 201
    assert "password" not in r.text and "hashed_password" not in r.text


def test_duplicate_registration_400(client):
    register_and_login(client)
    r = client.post("/auth/register", json={"username": "tisha", "email": "new@example.com", "password": "Secret123"})
    assert r.status_code == 400


@pytest.mark.parametrize("payload", [
    {"username": "", "email": "a@b.co", "password": "Secret123"},
    {"username": "ab", "email": "a@b.co", "password": "Secret123"},
    {"username": "   ", "email": "a@b.co", "password": "Secret123"},
    {"username": "tisha", "email": "not-an-email", "password": "Secret123"},
    {"username": "tisha", "email": "a@b.co", "password": "short"},
    {"username": "tisha", "email": "a@b.co"},
])
def test_register_validation_400(client, payload):
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 400
    assert r.json()["detail"] == "Validation failed"


def test_login_wrong_password_401(client):
    register_and_login(client)
    r = client.post("/auth/login", json={"username": "tisha", "password": "WrongPass1"})
    assert r.status_code == 401


def test_login_unknown_user_401(client):
    r = client.post("/auth/login", json={"username": "ghost", "password": "Whatever1"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    h = register_and_login(client)
    assert client.get("/auth/me", headers=h).json()["username"] == "tisha"


# ---------------- Tasks ----------------
def test_tasks_require_auth(client):
    assert client.get("/tasks").status_code == 401
    assert client.post("/tasks", json={"title": "x"}).status_code == 401
    assert client.get("/tasks/1").status_code == 401
    assert client.delete("/tasks/1").status_code == 401


def test_create_and_get_task(client):
    h = register_and_login(client)
    r = client.post("/tasks", json={"title": "  Write report  ", "description": "Q4"}, headers=h)
    assert r.status_code == 201
    task = r.json()
    assert task["title"] == "Write report"  # trimmed
    assert task["status"] == "Pending"  # default
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["description"] == "Q4"


@pytest.mark.parametrize("payload", [
    {"title": ""},
    {"title": "   "},
    {},
    {"title": "ok", "status": "Done"},
])
def test_create_task_validation_400(client, payload):
    h = register_and_login(client)
    assert client.post("/tasks", json=payload, headers=h).status_code == 400


def test_status_filter(client):
    h = register_and_login(client)
    client.post("/tasks", json={"title": "a"}, headers=h)
    client.post("/tasks", json={"title": "b", "status": "In Progress"}, headers=h)
    client.post("/tasks", json={"title": "c", "status": "Completed"}, headers=h)
    client.post("/tasks", json={"title": "d", "status": "Completed"}, headers=h)

    assert len(client.get("/tasks", headers=h).json()) == 4
    assert len(client.get("/tasks?status=Pending", headers=h).json()) == 1
    assert len(client.get("/tasks?status=In Progress", headers=h).json()) == 1
    assert len(client.get("/tasks?status=Completed", headers=h).json()) == 2
    assert client.get("/tasks?status=Bogus", headers=h).status_code == 400


def test_update_task(client):
    h = register_and_login(client)
    tid = client.post("/tasks", json={"title": "a"}, headers=h).json()["id"]
    r = client.patch(f"/tasks/{tid}", json={"status": "Completed"}, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "Completed" and r.json()["title"] == "a"
    # PUT works too
    assert client.put(f"/tasks/{tid}", json={"title": "renamed"}, headers=h).json()["title"] == "renamed"


@pytest.mark.parametrize("payload", [{}, {"title": ""}, {"title": None}, {"status": "nope"}])
def test_update_validation_400(client, payload):
    h = register_and_login(client)
    tid = client.post("/tasks", json={"title": "a"}, headers=h).json()["id"]
    assert client.patch(f"/tasks/{tid}", json=payload, headers=h).status_code == 400


def test_delete_task(client):
    h = register_and_login(client)
    tid = client.post("/tasks", json={"title": "a"}, headers=h).json()["id"]
    assert client.delete(f"/tasks/{tid}", headers=h).status_code == 204
    assert client.get(f"/tasks/{tid}", headers=h).status_code == 404
    assert client.delete(f"/tasks/{tid}", headers=h).status_code == 404


def test_not_found_404(client):
    h = register_and_login(client)
    assert client.get("/tasks/999", headers=h).status_code == 404
    assert client.patch("/tasks/999", json={"title": "x"}, headers=h).status_code == 404


def test_users_cannot_touch_each_others_tasks(client):
    h1 = register_and_login(client, "alice", "alice@example.com")
    h2 = register_and_login(client, "bob", "bob@example.com")
    tid = client.post("/tasks", json={"title": "alice private"}, headers=h1).json()["id"]

    assert client.get("/tasks", headers=h2).json() == []
    assert client.get(f"/tasks/{tid}", headers=h2).status_code == 404
    assert client.patch(f"/tasks/{tid}", json={"title": "hacked"}, headers=h2).status_code == 404
    assert client.delete(f"/tasks/{tid}", headers=h2).status_code == 404
    assert client.get(f"/tasks/{tid}", headers=h1).json()["title"] == "alice private"


def test_pagination_validation(client):
    h = register_and_login(client)
    assert client.get("/tasks?limit=0", headers=h).status_code == 400
    assert client.get("/tasks?skip=-1", headers=h).status_code == 400


def test_unhandled_error_returns_500(client, monkeypatch):
    h = register_and_login(client)
    from app.routers import tasks as tasks_router

    def boom(*a, **k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tasks_router, "_get_own_task", boom)
    r = client.get("/tasks/1", headers=h)
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error"}
