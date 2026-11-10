# Deployment

Local deployment uses Docker Compose with Mosquitto, TimescaleDB, Anvil, the FastAPI API, MQTT subscriber, and simulator. `make setup` builds images, generates gRPC stubs, deploys contracts, injects addresses, and seeds the database.

The supported deployment target is local Docker Compose. Configure PostgreSQL,
Mosquitto, Redis, Anvil, the FastAPI API, the MQTT subscriber, and the worker
through `infrastructure/docker/.env`; do not add cloud-provider credentials
or endpoints to the application configuration.
