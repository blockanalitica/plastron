import contextlib
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

import aiofiles.os
import click
from tortoise import Tortoise, connections
from tortoise.exceptions import OperationalError
from tortoise.transactions import in_transaction

from plastron.constants import COLORS
from plastron.models import Plastron
from plastron.serializer import Serializer
from plastron.utils import (
    generate_revision_id,
    graph_heads,
    kahn_toposort,
    load_module_py,
)


def _build_graph(migrations):
    nodes = set()
    parents = defaultdict(set)
    children = defaultdict(set)

    def add_edge(p, c):
        children[p].add(c)
        parents[c].add(p)

    for mig in migrations:
        rev = mig.revision
        down = mig.down_revision
        nodes.add(rev)

        if down:
            if isinstance(down, (list, tuple)):
                for d in down:
                    nodes.add(d)
                    children[d].add(rev)
                    parents[rev].add(d)
            else:
                nodes.add(down)
                children[down].add(rev)
                parents[rev].add(down)
        else:
            # Ensure key exists
            parents[rev] = set()

        if rev not in children:
            # Ensure key exists
            children[rev] = set()

    return nodes, parents, children


@asynccontextmanager
async def maybe_in_transaction(run_in_transaction, db_connection_name):
    if run_in_transaction:
        async with in_transaction(db_connection_name) as conn:
            yield conn
    else:
        yield connections.get(db_connection_name)


class Migrator:
    @classmethod
    async def init(cls, migrations_folder):
        self = cls()
        self.migrations_folder = migrations_folder

        self.module_map = await self._load_migration_modules()
        self.nodes, self.parents, self.children = _build_graph(self.module_map.values())
        self.revisions = kahn_toposort(self.nodes, self.parents, self.children)

        return self

    async def _load_migration_modules(self):
        module_map = {}
        migrations = [
            f
            for f in await aiofiles.os.listdir(self.migrations_folder)
            if f.endswith(".py")
        ]
        modules = []
        for migration in migrations:
            file_path = Path(self.migrations_folder) / migration
            module = load_module_py(file_path, migration.replace(".py", ""))
            modules.append(module)
            module_map[module.revision] = module

        return module_map

    def _describe_model(self, model):
        dsc = model.describe(serializable=False)
        info = {
            "name": dsc["table"],
            "fields": list(model._meta.fields_map.items()),
            "unique_together": sorted(dsc["unique_together"]),
            "indexes": sorted(dsc["indexes"]),
        }
        # TODO: ForeignKeyField, OneToOneField, ManyToManyField
        # normalize ordering inside lists for stability
        # data_fields = sorted(info["data_fields"], key=lambda f: f["db_column"])
        # info["columns"] = [info["pk_field"], *data_fields]
        # # TODO not checked
        # info["fk_fields"] = sorted(info["fk_fields"], key=lambda f: f["db_column"])
        # # TODO not checked
        # info["o2o_fields"] = sorted(info["o2o_fields"], key=lambda f: f["db_column"])
        # # TODO not checked
        # info["m2m_fields"] = sorted(info["m2m_fields"], key=lambda f: f["db_column"])
        # info["unique_together"] = sorted(
        #     [tuple(x) for x in info.get("unique_together", [])]
        # )
        # info["indexes"] = sorted([tuple(x) for x in info.get("indexes", [])])
        # models[info["table"]] = info
        return info

    def _describe_app_models(self):
        models = {}
        for app_config in Tortoise.apps.values():
            for model in app_config.values():
                info = self._describe_model(model)
                models[info["name"]] = info

        # Sort them by model name for stability
        models = dict(sorted(models.items()))
        return models

    def _build_models_from_revisions(self, revisions):
        models = {}
        for rev in revisions:
            ops = self.module_map[rev].upgrade_operations

            for op in ops:
                # update_model_structure mutates `models` dict
                op.update_model_structure(models)

        return models

    def _describe_revision_models(self):
        models = self._build_models_from_revisions(self.revisions)

        described = {}
        if models:
            for model in models.values():
                info = self._describe_model(model)
                described[info["name"]] = info
        return described

    async def _get_applied_revisions(self):
        try:
            revs = (
                await Plastron.all().order_by("id").values_list("revision", flat=True)
            )
        except OperationalError:
            revs = []
        return revs

    async def _detect_unapplied_revisions(self):
        applied_revs = await self._get_applied_revisions()
        return [rev for rev in self.revisions if rev not in applied_revs]

    def _fields_differ(self, old_field, new_field):
        old_info = old_field.describe(serializable=True)
        new_info = new_field.describe(serializable=True)

        keys_to_keep = {
            "field_type",
            "db_column",
            "generated",
            "nullable",
            "unique",
            "indexed",
            "default",
            "constraints",
            "auto_now",
            "auto_now_add",
        }
        old_sig = {key: old_info.get(key) for key in keys_to_keep}
        new_sig = {key: new_info.get(key) for key in keys_to_keep}
        return old_sig != new_sig

    def _diff_columns(self, table_name, old_fields, new_fields):
        ops = []

        old_fields_map = dict(old_fields)
        new_fields_map = dict(new_fields)
        old_fields_set = set(old_fields_map)
        new_fields_set = set(new_fields_map)

        # Drops first (safe for FKs), then adds, then alters.
        for field_name in old_fields_set - new_fields_set:
            ops.append(
                (
                    "DropColumn",
                    table_name,
                    {"name": field_name, "field": old_fields_map[field_name]},
                )
            )

        # Adds
        for field_name in new_fields_set - old_fields_set:
            ops.append(
                (
                    "AddColumn",
                    table_name,
                    {"name": field_name, "field": new_fields_map[field_name]},
                )
            )

        # Alters
        for field_name in old_fields_set & new_fields_set:
            old_field = old_fields_map[field_name]
            new_field = new_fields_map[field_name]
            if self._fields_differ(old_field, new_field):
                ops.append(
                    (
                        "AlterColumn",
                        table_name,
                        {
                            "name": field_name,
                            "new_field": new_fields_map[field_name],
                            "old_field": old_fields_map[field_name],
                        },
                    )
                )

        return ops

    def diff_table(self, old_table, new_table):
        ops = []
        table_name = new_table["name"]

        # 1) Fields (order: drops → adds → alters)  # TODO
        ops.extend(
            self._diff_columns(table_name, old_table["fields"], new_table["fields"])
        )

        # TODO: Foreign keys, onetoone field, manytomany field
        # def _map_by_name(items):
        #     return {i["name"]: i for i in items}
        # _compare_fields(
        #     _map_by_name(old_table.get("data_fields", [])),
        #     _map_by_name(new_table.get("data_fields", [])),
        #     table_name,
        #     "data",
        #     ops,
        # )
        # _compare_fields(
        #     _map_by_name(old_table.get("fk_fields", [])),
        #     _map_by_name(new_table.get("fk_fields", [])),
        #     table_name,
        #     "fk",
        #     ops,
        # )
        # _compare_fields(
        #     _map_by_name(old_table.get("o2o_fields", [])),
        #     _map_by_name(new_table.get("o2o_fields", [])),
        #     table_name,
        #     "o2o",
        #     ops,
        # )
        # _compare_fields(
        #     _map_by_name(old_table.get("m2m_fields", [])),
        #     _map_by_name(new_table.get("m2m_fields", [])),
        #     table_name,
        #     "m2m",
        #     ops,
        # )

        # 2) unique_together (treat as constraints)
        old_ut_set = {tuple(ut) for ut in old_table.get("unique_together") or []}
        new_ut_set = {tuple(ut) for ut in new_table.get("unique_together") or []}
        for ut in sorted(old_ut_set - new_ut_set):
            ops.append(("DropUniqueTogether", table_name, list(ut)))
        for ut in sorted(new_ut_set - old_ut_set):
            ops.append(("AddUniqueTogether", table_name, list(ut)))

        # 3) indexes
        old_indexes = old_table.get("indexes") or []
        new_indexes = new_table.get("indexes") or []
        old_idx_map = {",".join(i): i for i in old_indexes}
        new_idx_map = {",".join(i): i for i in new_indexes}
        for key in set(old_idx_map) - set(new_idx_map):
            ops.append(("DropIndex", table_name, old_idx_map[key]))
        for key in set(new_idx_map) - set(old_idx_map):
            ops.append(("AddIndex", table_name, new_idx_map[key]))

        return ops

    def diff_models(self, old_models, new_models):
        ops = []
        # tables created
        for k in sorted(set(new_models) - set(old_models)):
            ops.append(("CreateTable", k, new_models[k]))

        # tables dropped
        for k in sorted(set(old_models) - set(new_models)):
            ops.append(("DropTable", k, old_models[k]))

        # per-table diffs
        for k in sorted(set(old_models) & set(new_models)):
            ops.extend(self.diff_table(old_models[k], new_models[k]))

        return ops

    # TODO: tests
    def ensure_single_head(self):
        down_revision = graph_heads(self.nodes, self.children)
        if len(down_revision) > 1:
            click.echo(
                click.style(
                    "Multiple head revisions are present:",
                    fg=COLORS["yellow"],
                )
            )
            for rev in down_revision:
                click.echo(rev)

            click.echo(
                click.style(
                    'These need to be merged (use "plastron merge" '
                    "to merge the branches)",
                    fg=COLORS["yellow"],
                )
            )
            return False
        return True

    async def makemigrations(self, name=None):
        # TODO: tests
        if not self.ensure_single_head():
            return

        new = self._describe_app_models()
        old = self._describe_revision_models()

        ops = self.diff_models(old, new)
        if ops:
            revision = generate_revision_id()
            down_revision = graph_heads(self.nodes, self.children)

            serializer = Serializer(ops)
            filename = await serializer.write_migration_file(
                revision, down_revision, self.migrations_folder, migration_name=name
            )
            click.echo(f"Created migration file {filename}")
        else:
            click.echo("Nothing to migrate.")

    # TODO: tests
    async def merge_heads(self, name=None):
        down_revision = graph_heads(self.nodes, self.children)
        if len(down_revision) == 0:
            click.echo("No divergent heads found — nothing to merge.")
            return

        if len(down_revision) == 1:
            click.echo("Only one head exists; merge not required.")
            return

        revision = generate_revision_id()
        serializer = Serializer([])
        filename = await serializer.write_migration_file(
            revision, down_revision, self.migrations_folder, migration_name=name
        )
        click.echo(f"Created merge migration file {filename}")

    # TODO: tests
    async def _execute_sql(self, sql, run_in_transaction, db_connection_name):
        async with maybe_in_transaction(run_in_transaction, db_connection_name) as conn:
            dialect = getattr(conn.capabilities, "dialect", "")

            # Postgres wraps multi-statement queries in an implicit transaction,
            # so CREATE/DROP INDEX CONCURRENTLY must be executed separately.
            if not run_in_transaction and dialect == "postgres":
                # Manually acquire a raw asyncpg connection from the Tortoise connection
                # pool. This bypasses Tortoise's transaction wrapper so we can control
                # the isolation level.
                async with conn.acquire_connection() as raw_conn:
                    # asyncpg only accepts one statement per execute()
                    # run each separately to stay outside any transaction block.
                    for sql_cmd in [s.strip() for s in sql.split(";") if s.strip()]:
                        await raw_conn.execute(sql_cmd)

            else:
                await conn.execute_script(sql)

    async def upgrade(self, db_connection_name, revision=None):
        unapplied_revs = await self._detect_unapplied_revisions()
        if not unapplied_revs:
            click.echo("No revisions to apply")
            return

        applied_revs = [rev for rev in self.revisions if rev not in unapplied_revs]
        models = self._build_models_from_revisions(applied_revs)

        # If revision is passed in, only upgrade up to and including the revision
        if revision:
            unapplied_revs = [rev for rev in unapplied_revs if rev <= revision]

        for rev in unapplied_revs:
            # TODO: test run_in_transaction
            run_in_transaction = getattr(
                self.module_map[rev], "run_in_transaction", True
            )

            ops = self.module_map[rev].upgrade_operations
            sqls = []
            for op in ops:
                sqls.append(op.sql(models))
                # Update models with the operation so we have the latest state
                op.update_model_structure(models)

            sql_cmd = "\n".join(sqls)

            click.echo(f"Applying revision {rev}", nl=False)

            # It's possible that migration doesn't return any sql
            if sql_cmd:
                await self._execute_sql(sql_cmd, run_in_transaction, db_connection_name)

            await Plastron.create(revision=rev, applied=True)

            click.echo(f" -> {click.style('Done', fg=COLORS['green'])}")

    async def downgrade(self, db_connection_name, revision=None):
        applied_revs = await self._get_applied_revisions()
        if not applied_revs:
            click.echo("No revisions were applied, so we can't downgrade.")
            return

        models = self._build_models_from_revisions(applied_revs)

        # If revision is passed in, only downgrade down to and including the revision
        if revision:
            revisions_to_revert = [rev for rev in applied_revs if rev >= revision]
        else:
            # TODO: test this
            # reverse only last revision if no revision is passed in
            revisions_to_revert = applied_revs[-1:]

        # Revisions need to be from last to first
        for rev in reversed(revisions_to_revert):
            # TODO: test run_in_transaction
            run_in_transaction = getattr(
                self.module_map[rev], "run_in_transaction", True
            )
            ops = self.module_map[rev].downgrade_operations
            sqls = []
            for op in ops:
                sqls.append(op.sql(models))
                # Update models with the operation so we have the latest state
                op.update_model_structure(models)

            sql_cmd = "\n".join(sqls)

            click.echo(f"Downgrading revision {rev}", nl=False)

            # It's possible that migration doesn't return any sql
            if sql_cmd:
                await self._execute_sql(sql_cmd, run_in_transaction, db_connection_name)

            # If we've downgraded the initial migration, Plastron table doens't
            # exist anymore, so we need to suppress OperationalError
            # Also do this outside of the transaction, otherwise the transaction will
            # abort if it comes to OperationalError
            with contextlib.suppress(OperationalError):
                await Plastron.filter(revision=rev).delete()

            click.echo(f" -> {click.style('Done', fg=COLORS['green'])}")

    async def check(self):
        revisions = await self._detect_unapplied_revisions()
        return [(rev, f"{self.module_map[rev].__name__}.py") for rev in revisions]
