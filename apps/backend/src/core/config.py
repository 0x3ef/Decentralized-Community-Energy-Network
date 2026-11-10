"""Validated configuration; secrets are supplied by the environment."""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://solar:solar@localhost:5432/solar"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    REDIS_URL: str = "redis://localhost:6379/0"
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@example.com"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "localhost"
    MAIL_FROM_NAME: str = "Solar Energy Market"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True
    DOMAIN: str = "localhost:8000"
    WEB3_PROVIDER_URL: str = "http://localhost:8545"
    CHAIN_ID: int = 31337
    SUN_TOKEN_ADDRESS: str = ""
    MOCK_USD_ADDRESS: str = ""
    ENERGY_MARKET_ADDRESS: str = ""
    COMPENSATION_ADDRESS: str = ""
    REDUCTION_MANAGER_ADDRESS: str = ""
    BACKEND_PRIVATE_KEY: str = ""
    BLOCKCHAIN_CONFIRMATION_BLOCKS: int = 2
    BLOCKCHAIN_RECEIPT_TIMEOUT_SECONDS: int = 120
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_TOPIC: str = "solar/#"
    MQTT_QOS: int = 1
    MQTT_CLIENT_ID: str = "solar-subscriber"
    QUEUE_MAXSIZE: int = 10000
    BATCH_SIZE: int = 200
    BATCH_FLUSH_SECONDS: float = 1
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080", "http://127.0.0.1:8080"]
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def secure_configuration(self):
        if len(self.JWT_SECRET) < 32:
            raise ValueError("JWT_SECRET must have at least 32 characters")
        if self.ENVIRONMENT == "production" and self.CHAIN_ID in (31337, 1337):
            raise ValueError("Development chain is forbidden in production")
        return self

Config = Settings()
broker_url = Config.REDIS_URL
result_backend = Config.REDIS_URL
broker_connection_retry_on_startup = True
