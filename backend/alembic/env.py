import os

from alembic import context

from app.core.database import Base, make_engine
from app.models import domain  # noqa: F401

config = context.config
url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(url)
    with engine.connect() as connection:
        # Explicit transaction: DDL and version stamp must commit together on SQLite.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        context.configure(
            connection=connection, target_metadata=Base.metadata, render_as_batch=True, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
    engine.dispose()
