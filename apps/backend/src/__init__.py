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
