from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from education_platform.core.config import get_settings
from education_platform.db import models as _models
from education_platform.db.base import Base
from education_platform.db.url import to_sync_url

_ = _models

config = context.config
settings = get_settings()
database_url = to_sync_url(settings.database_url)
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    # disable_existing_loggers defaults to True, which silently sets `.disabled = True`
    # on every logger that already exists at this point -- harmless when `alembic` runs
    # as its own CLI process, but this test suite runs migrations in-process (see
    # conftest.py's `migrated_database` fixture), after pytest has already imported and
    # created loggers for every `education_platform.*` module under test. Without this,
    # any of those loggers goes permanently silent for the rest of the test session the
    # instant the first DB-touching test runs alembic -- not just uncaptured by caplog,
    # genuinely dropped, since `Logger.disabled` short-circuits before level/propagation
    # are even checked.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
