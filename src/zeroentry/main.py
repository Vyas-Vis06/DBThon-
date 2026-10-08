"""Application factory. Run with: uvicorn --factory zeroentry.main:create_app"""

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, get_settings
from .db import database_status, make_engine, make_sessionmaker
from .errors import install_error_handlers
from .log import configure_logging, mask_url
from .maintenance import maintain
from .routers import accountability, admin, auth, complaints, detection, events, incident_reports, money, permits, reference, reports
from .security import SlidingWindowLimiter

log = logging.getLogger("zeroentry")
WEB = Path(__file__).parent / "web"
API = "/api/v1"

# The UI is same-origin static HTML + JS: nothing is loaded from a third party, so the policy can be strict.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log.info("starting ZeroEntry %s (%s) -> %s", __version__, settings.app_env, mask_url(settings.database_url))
        stop = asyncio.Event()
        task = None
        if settings.safety_sweep_interval_seconds:
            task = asyncio.create_task(maintain(engine, settings.safety_sweep_interval_seconds,
                                               stop, app.state.maintenance))
        try:
            yield
        finally:
            stop.set()
            if task:
                await task
            engine.dispose()

    app = FastAPI(title="ZeroEntry", version=__version__, lifespan=lifespan,
                  docs_url=None if settings.app_env == "production" else "/docs",
                  redoc_url=None, openapi_url=None if settings.app_env == "production" else "/openapi.json")
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.maintenance = {"interval_seconds": settings.safety_sweep_interval_seconds}
    app.state.login_limiter = SlidingWindowLimiter(settings.login_ip_limit, 60)   # per process; see security.py
    install_error_handlers(app)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            if name == "Content-Security-Policy" and request.url.path in ("/docs", "/openapi.json"):
                continue                               # Swagger UI loads its assets from a CDN; development only
            response.headers.setdefault(name, value)
        return response

    @app.get("/health", tags=["system"])
    def health() -> JSONResponse:
        """Liveness plus a real database round-trip. 503 when the database is unreachable."""
        try:
            return JSONResponse({"status": "ok", "version": __version__, "database": "up", **database_status(engine)})
        except Exception:  # noqa: BLE001 - any failure means "not healthy"; details go to the log
            log.exception("health check failed")
            return JSONResponse({"status": "degraded", "version": __version__, "database": "down"}, status_code=503)

    for module in (auth, reference, complaints, permits, detection, money, reports, incident_reports, events, accountability, admin):
        app.include_router(module.router, prefix=API)

    if (WEB / "static").is_dir():                      # the browser UI: one HTML shell, one ES module per screen
        app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/app/dashboard")

        @app.get("/app/{page}", include_in_schema=False)
        def page(page: str) -> FileResponse:
            known = page.isidentifier() and (WEB / "static" / "pages" / f"{page}.js").is_file()   # isidentifier: no path tricks
            return FileResponse(WEB / "shell.html", status_code=200 if known else 404)

    return app
