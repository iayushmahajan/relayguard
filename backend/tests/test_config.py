from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_settings_build_asyncpg_database_url() -> None:
    password = "secret"
    settings = Settings(
        postgres_db="relayguard_test",
        postgres_user="relayguard",
        postgres_password=password,
        postgres_host="localhost",
        postgres_port=5434,
    )

    url = make_url(settings.database_url)

    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "localhost"
    assert url.port == 5434
    assert url.database == "relayguard_test"
    assert url.username == "relayguard"
    assert password not in str(url)
