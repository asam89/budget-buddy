from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.database import SessionLocal, engine, ensure_schema
from app.routers import (
    auth, accounts, transactions, plaid, dashboard,
    categories, budgets, bills, imports, entities, reports, export, settings,
    budget_setup, actuals, migration, insights, version, networth,
)
from app.services.other_migration import silent_delete_if_empty
from app.services.entity_seed import seed_default_entity
from app.services.entity_scope_migration import migrate_entity_scoping


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema(engine)
    with SessionLocal() as db:
        silent_delete_if_empty(db)
        seed_default_entity(db)
    migrate_entity_scoping(engine)
    yield


app = FastAPI(
    title="Budget Buddy",
    description="Local personal finance dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(bills.router)
app.include_router(plaid.router)
app.include_router(imports.router)
app.include_router(entities.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(export.router)
app.include_router(settings.router)
app.include_router(budget_setup.router)
app.include_router(actuals.router)
app.include_router(migration.router)
app.include_router(insights.router)
app.include_router(version.router)
app.include_router(networth.router)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


@app.middleware("http")
async def csrf_origin_guard(request: Request, call_next):
    """Reject cross-origin state-changing requests as defense-in-depth on top
    of the SameSite=Lax session cookie. Same-origin requests (Origin host ==
    request host) and requests without an Origin header (e.g. non-browser
    clients, top-level navigations) are allowed."""
    if get_settings().csrf_protect and request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin:
            origin_host = urlparse(origin).netloc
            if origin_host and origin_host != request.headers.get("host"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request blocked"},
                )
    return await call_next(request)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """Liveness probe for launchd/monitoring — no auth, no DB access."""
    return {"status": "ok", "version": app.version}

# Serve the React frontend
frontend_dist = (Path(__file__).parent.parent / "frontend" / "dist").resolve()
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # API routes are handled by their routers; never fall through to the SPA
        # (returning index.html for an unknown /api path masks 404s).
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        index = frontend_dist / "index.html"
        candidate = (frontend_dist / full_path).resolve()
        # Only serve files that resolve to somewhere inside frontend_dist —
        # this blocks path traversal (e.g. "../../etc/passwd").
        if candidate.is_file() and candidate.is_relative_to(frontend_dist):
            return FileResponse(candidate)
        return FileResponse(index)
