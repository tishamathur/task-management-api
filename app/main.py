import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.database import Base, engine
from app.routers import auth, tasks

logger = logging.getLogger("task_api")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Task Management API",
    description="REST API with JWT authentication and per-user task CRUD.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Return 400 (instead of FastAPI's default 422) with a clean, readable error list."""
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
        message = err["msg"].removeprefix("Value error, ")
        errors.append({"field": ".".join(loc) or "request", "message": message})
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Validation failed", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "docs": "/docs"}


app.include_router(auth.router)
app.include_router(tasks.router)
