# Task Management REST API

A secure REST API where users register, log in, and manage **their own** tasks.
Built with **FastAPI, SQLAlchemy, SQLite, bcrypt and JWT**.

## Features
- **Authentication** – registration + login, passwords hashed with **bcrypt**, stateless **JWT** bearer tokens (30 min expiry)
- **Task CRUD** – create, read, update, delete; every query is scoped to the logged-in user
- **Status filter** – `GET /tasks?status=Pending | In Progress | Completed` (plus `skip` / `limit` pagination)
- **Validation & errors** – empty/blank fields, bad emails, short passwords, invalid status → clean `400` responses
- **29 automated tests** (pytest) covering auth, CRUD, validation, ownership isolation and the 500 handler

## Project structure
```
app/
  main.py        # app setup + global error handlers (400 / 500)
  config.py      # settings from environment variables
  database.py    # engine, session, Base
  models.py      # User, Task, TaskStatus
  schemas.py     # Pydantic request/response models + validation
  security.py    # bcrypt hashing, JWT create/decode
  deps.py        # get_current_user dependency (401)
  routers/
    auth.py      # /auth/register, /auth/login, /auth/me
    tasks.py     # /tasks CRUD
tests/test_api.py
```

## Run it
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"   # Windows: set SECRET_KEY=...
uvicorn app.main:app --reload
```
Interactive docs: http://127.0.0.1:8000/docs (click **Authorize** and paste your token)

Run tests: `pytest -q`

## Endpoints
| Method | Path | Auth | Description | Success |
|---|---|---|---|---|
| POST | `/auth/register` | – | Create account | 201 |
| POST | `/auth/login` | – | Get JWT | 200 |
| GET | `/auth/me` | ✔ | Current user | 200 |
| POST | `/tasks` | ✔ | Create task | 201 |
| GET | `/tasks?status=&skip=&limit=` | ✔ | List own tasks | 200 |
| GET | `/tasks/{id}` | ✔ | Get one task | 200 |
| PATCH | `/tasks/{id}` | ✔ | Update title/description/status | 200 |
| DELETE | `/tasks/{id}` | ✔ | Delete task | 204 |

## Status codes
| Code | When |
|---|---|
| 400 | Validation failure (blank title, invalid status, bad email, short password), duplicate username/email |
| 401 | Missing/invalid/expired token, wrong login credentials |
| 404 | Task doesn't exist **or belongs to another user** (ownership is never leaked) |
| 500 | Unexpected server error – generic message returned, details logged server-side |

## Try it with curl
```bash
# register + login
curl -X POST localhost:8000/auth/register -H "Content-Type: application/json" \
  -d '{"username":"tisha","email":"tisha@example.com","password":"Secret123"}'
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"username":"tisha","password":"Secret123"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# create, filter, update, delete
curl -X POST localhost:8000/tasks -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Finish API project","status":"In Progress"}'
curl "localhost:8000/tasks?status=In%20Progress" -H "Authorization: Bearer $TOKEN"
curl -X PATCH localhost:8000/tasks/1 -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"Completed"}'
curl -X DELETE localhost:8000/tasks/1 -H "Authorization: Bearer $TOKEN"
```

## Design notes (good interview talking points)
- bcrypt for passwords (salted, slow by design); JWT carries only the user id and an expiry
- Same error message for unknown user vs wrong password, so usernames can't be enumerated
- Other users' tasks return 404, not 403, so task ids aren't exposed
- Validation errors overridden from FastAPI's default 422 to 400 to match the spec
- Possible next steps: refresh tokens, Alembic migrations, Docker, PostgreSQL, rate limiting on login
