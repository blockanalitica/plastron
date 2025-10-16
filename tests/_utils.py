from datetime import UTC, datetime

import aiofiles.os
from tortoise import Tortoise

from plastron.serializer import MIGRATE_TEMPLATE


async def _write_migration_py(
    path,
    filename,
    revision,
    down_revision='""',
    upgrade_operations="",
    downgrade_operations="",
    additional_imports="",
):
    (path / f"{filename}.py").write_text(
        MIGRATE_TEMPLATE.format(
            revision=revision,
            down_revision=down_revision,
            upgrade_operations=upgrade_operations,
            downgrade_operations=downgrade_operations,
            additional_imports=additional_imports,
            version="1.3.3.7",
            dt=datetime.now(UTC),
        ),
        encoding="utf-8",
    )


async def _list_migrations(migrations_folder):
    return sorted(
        [f for f in await aiofiles.os.listdir(migrations_folder) if f.endswith(".py")]
    )


async def _check_table_exists(table_name):
    client = Tortoise.get_connection("default")
    dialect = client.capabilities.dialect

    if dialect == "postgres":
        sql = "SELECT to_regclass($1)"
        args = [f"public.{table_name}"]
        _, rows = await client.execute_query(sql, args)
        return rows and rows[0][0] is not None

    # if dialect == "mysql":
    #     sql = """
    #     SELECT 1 FROM information_schema.tables
    #     WHERE table_schema = DATABASE() AND table_name = %s
    #     """
    #     _, rows = await client.execute_query(sql, [table_name])
    #     return bool(rows)

    # if dialect == "sqlite":
    #     sql = "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?"
    #     _, rows = await client.execute_query(sql, [table_name])
    #     return bool(rows)

    raise RuntimeError("Unsupported dialect: " + dialect)
