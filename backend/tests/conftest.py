import os
import pytest


# Ohranimo povezavo razvojnega kontejnerja samo za izrecno izbrane PG teste.
_postgres_database_url = os.getenv("DATABASE_URL")


# Izolirane nastavitve testnega procesa; povezave v PostgreSQL se nadomestijo.
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost/test"
os.environ["JWT_SECRET"] = "test-only-signing-key-with-at-least-32-bytes"


def pytest_addoption(parser):
    parser.addoption("--postgres", action="store_true", help="Izvedi tudi integracijske teste na razvojni PostgreSQL bazi.")


@pytest.fixture
def postgres_database_url(request):
    if not request.config.getoption("--postgres"):
        pytest.skip("Za PostgreSQL integracijske teste uporabi --postgres.")
    if not _postgres_database_url or not _postgres_database_url.startswith("postgresql"):
        pytest.fail("Integracijske teste zaženi v backend kontejnerju z nastavljeno DATABASE_URL.")
    return _postgres_database_url


@pytest.fixture
def inventory_db(postgres_database_url):
    """Skupna seja za izrecno izbrane teste migriranih PostgreSQL tabel."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(postgres_database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            db = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
            try:
                yield db
            finally:
                db.close()
                transaction.rollback()
    finally:
        engine.dispose()
