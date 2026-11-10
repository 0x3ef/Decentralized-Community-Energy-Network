from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str
    REDIS_URL: str = "redis://localhost:6379/0"
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int
    MAIL_SERVER: str
    MAIL_FROM_NAME: str
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True
    DOMAIN: str
    WEB3_PROVIDER_URL: str = "http://localhost:8545"
    CHAIN_ID: int 
    SUN_TOKEN_ADDRESS: str 
    ENERGY_MARKET_ADDRESS: str
    REDUCTION_MANAGER_ADDRESS: str
    BACKEND_PRIVATE_KEY: str
    BLOCKCHAIN_CONFIRMATION_BLOCKS: int
    BLOCKCHAIN_RECEIPT_TIMEOUT_SECONDS: int
    MQTT_HOST: str
    MQTT_PORT: int
    MQTT_TOPIC: str
    MQTT_QOS: int 
    MQTT_CLIENT_ID: str
    QUEUE_MAXSIZE: int
    BATCH_SIZE: int
    BATCH_FLUSH_SECONDS: int
    LOG_LEVEL: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


Config = Settings()


broker_url = Config.REDIS_URL
result_backend = Config.REDIS_URL
broker_connection_retry_on_startup = True