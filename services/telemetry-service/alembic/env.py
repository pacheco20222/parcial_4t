import asyncio

from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from telemetry_service.config import Settings
from telemetry_service.models import Base


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=Base.metadata, version_table_schema="telemetry", include_schemas=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    engine = create_async_engine(
        Settings().database_url(), connect_args={"server_settings": {"search_path": "telemetry,public"}}
    )
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url(),
        target_metadata=Base.metadata,
        version_table_schema="telemetry",
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
