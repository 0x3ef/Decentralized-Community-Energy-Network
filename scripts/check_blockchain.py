"""Seed SQLModel telemetry and verify the normal local energy/ETH/SUN cycle."""

from demo_scenario import run

if __name__ == "__main__":
    try:
        run(transport="database")
    except Exception as error:
        raise SystemExit(
            f"Blockchain check stopped ({type(error).__name__}): {error}. "
            "No success claimed; retain scenario.json and rerun to resume."
        ) from None
