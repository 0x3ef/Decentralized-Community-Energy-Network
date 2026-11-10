from fastapi import FastAPI
from src.modules.auth.routes import auth_router
from src.modules.wallet.routes import wallet_router
from src.modules.home.routes import home_router
from src.modules.device.routes import device_router
from src.modules.energy.routes import energy_router
from src.modules.marketplace.routes import marketplace_router
from src.core.errors import register_all_errors
from src.middleware import register_middleware


version = "v1"

version_prefix =f"/api/{version}"

app = FastAPI(
    title="P2P Energy Trading Platform",
    version=version,
    openapi_url=f"{version_prefix}/openapi.json",
    docs_url=f"{version_prefix}/docs",
    redoc_url=f"{version_prefix}/redoc"
)

register_all_errors(app)

register_middleware(app)


app.include_router(auth_router, prefix=f"{version_prefix}/auth", tags=["auth"])
app.include_router(wallet_router, prefix=f"{version_prefix}/wallet", tags=["wallet"])
app.include_router(home_router, prefix=f"{version_prefix}/home", tags=["home"])
app.include_router(device_router, prefix=f"{version_prefix}/device", tags=["device"])
app.include_router(energy_router, prefix=f"{version_prefix}/energy", tags=["energy"])
app.include_router(marketplace_router, prefix=f"{version_prefix}/marketplace", tags=["marketplace"])

from src.modules.community.routes import router as community_router
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from src.core.db import AsyncSessionFactory

app.include_router(community_router, prefix=f"{version_prefix}/communities", tags=["communities"])

@app.exception_handler(ValueError)
async def invalid_operation(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})

@app.exception_handler(PermissionError)
async def forbidden_operation(request: Request, exc: PermissionError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})

@app.exception_handler(LookupError)
async def missing_operation(request: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.get("/health")
async def health():
    async with AsyncSessionFactory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}


from sqlalchemy.exc import IntegrityError
@app.exception_handler(IntegrityError)
async def integrity_conflict(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Operation conflicts with an existing record or accounting constraint"})
