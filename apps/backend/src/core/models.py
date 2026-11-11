"""Register canonical SQLModel tables for every process, without creating a schema."""


def register_models():
    # Relationship names are resolved when the first ORM query runs. Standalone
    # MQTT/worker processes must register the same models as the FastAPI process.
    import src.modules.auth.models
    import src.modules.community.models
    import src.modules.device.models
    import src.modules.energy.models
    import src.modules.home.models
    import src.modules.settlement.models
    import src.modules.wallet.models  # noqa: F401
