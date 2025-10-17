import importlib
import sys
import tomllib
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path

import asyncclick as click
from tortoise import Tortoise

from plastron import __version__
from plastron.constants import COLORS
from plastron.exceptions import ConfigError
from plastron.migrator import Migrator
from plastron.utils import add_base_dir_to_sys_path


def _load_pyproject(pyproject_path):
    path = Path(pyproject_path)
    if not path.exists():
        return {}

    with path.open("rb") as f:
        data = tomllib.load(f)

    tool = data.get("tool", {})
    return tool.get("plastron", {})


async def _load_tortoise_config(tortoise_config_path):
    splits = tortoise_config_path.split(".")
    config_path = ".".join(splits[:-1])
    tortoise_config = splits[-1]

    try:
        config_module = importlib.import_module(config_path)
    except ModuleNotFoundError:
        # If it's class based config, we need to handle 'mymodule.MyClass.TORTOISE_ORM'
        if len(splits) >= 3:
            config_path = ".".join(splits[:-2])
        else:
            raise ConfigError(
                f"Can't find Tortoise config in module '{config_path}'"
            ) from None
        try:
            config_module = importlib.import_module(config_path)
        except ModuleNotFoundError as e:
            raise ConfigError(
                f"Failed to import configuration module: {config_path}"
            ) from e

        config_class = getattr(config_module, splits[-2], None)
        config = getattr(config_class, tortoise_config, None)
    else:
        config = getattr(config_module, tortoise_config, None)

    if not config:
        raise ConfigError(f"Can't find Tortoise config in module '{config_path}'")

    # Create a deepcopy of the config, as to not mutate the original settings
    cfg = deepcopy(config)

    apps = cfg.get("apps", {})
    if apps:
        app = next(iter(apps.values()))
        # Append `plastron.models` to the first app in Tortoise ORM Config
        app.get("models", []).append("plastron.models")

    return cfg


async def _load_config(pyproject_path, tortoise_orm, location):
    file_cfg = _load_pyproject(pyproject_path)

    cfg = {
        "tortoise_orm": file_cfg.get("tortoise_orm"),
        "location": file_cfg.get("location"),
        "base_dir": file_cfg.get("base_dir"),
    }

    if tortoise_orm is not None:
        cfg["tortoise_orm"] = tortoise_orm
    if location is not None:
        cfg["location"] = location

    required_keys = ["tortoise_orm", "location"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        raise ConfigError(
            f"Missing required config: {', '.join(missing)}",
        )

    # TODO: tests
    if cfg["base_dir"]:
        # Add base_dir to sys.path as _load_tortoise_config already needs it
        add_base_dir_to_sys_path(cfg["base_dir"])

    cfg["tortoise"] = await _load_tortoise_config(cfg["tortoise_orm"])
    return cfg


@asynccontextmanager
async def db_connection(tortoise_config):
    await Tortoise.init(config=tortoise_config)
    try:
        yield
    finally:
        await Tortoise.close_connections()


async def _ensure_migration_folder(ctx):
    location = ctx.obj["config"]["location"]
    Path(location).mkdir(parents=True, exist_ok=True)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-v", "--version")
@click.option(
    "--pyproject",
    "pyproject_path",
    default="pyproject.toml",
    show_default=True,
    help="Path to the TOML configuration file.",
)
@click.option(
    "--tortoise-orm",
    help="Python path to the Tortoise ORM config dict (e.g. settings.TORTOISE_ORM).",
)
@click.option(
    "--location",
    help="Path to migrations folder.",
)
@click.pass_context
async def cli(ctx, pyproject_path, tortoise_orm, location):
    ctx.ensure_object(dict)
    config = await _load_config(pyproject_path, tortoise_orm, location)
    ctx.obj["config"] = config

    await _ensure_migration_folder(ctx)

    app = next(iter(config["tortoise"]["apps"].values()))
    ctx.obj["config"]["default_connection"] = app.get("default_connection", "default")


@cli.command(
    help="Generate new migrations based on the changes detected to your models."
)
@click.option(
    "--name",
    type=str,
    help="Give the migration a custom name instead of 'auto'",
)
@click.pass_context
async def makemigrations(ctx, name):
    async with db_connection(ctx.obj["config"]["tortoise"]):
        mig = await Migrator.init(migrations_folder=ctx.obj["config"]["location"])
        await mig.makemigrations(name=name)


# TODO: tests, also add revision support and --fake
@cli.command(help="Upgrade to later version.")
@click.option(
    "--fake",
    default=False,
    is_flag=True,
    help="Mark migrations as applied without executing them.",
)
@click.pass_context
async def upgrade(ctx, fake):
    # TODO: fake?
    async with db_connection(ctx.obj["config"]["tortoise"]):
        mig = await Migrator.init(migrations_folder=ctx.obj["config"]["location"])
        await mig.upgrade(
            db_connection_name=ctx.obj["config"]["default_connection"],
        )


# TODO: tests also add revision support
@cli.command(help="Downgrade to previous version.")
@click.pass_context
async def downgrade(ctx):
    async with db_connection(ctx.obj["config"]["tortoise"]):
        mig = await Migrator.init(migrations_folder=ctx.obj["config"]["location"])
        await mig.downgrade(
            db_connection_name=ctx.obj["config"]["default_connection"],
        )


# TODO: tests
@cli.command(help="Merge revision heads.")
@click.pass_context
@click.option(
    "--name",
    default="merge",
    type=str,
    help="Give the migration a custom name instead of 'merge'",
)
async def merge(ctx, name):
    mig = await Migrator.init(migrations_folder=ctx.obj["config"]["location"])
    await mig.merge_heads(name)


# TODO: tests
@cli.command(help="Show currently available heads (unapplied migrations).")
@click.pass_context
async def check(ctx):
    async with db_connection(ctx.obj["config"]["tortoise"]):
        mig = await Migrator.init(migrations_folder=ctx.obj["config"]["location"])
        unapplied_revisions = await mig.check()

    if not unapplied_revisions:
        click.echo("No new revisions detected.")
    else:
        click.echo(click.style("New revisions detected:", fg=COLORS["green"]))
        for revision, file in unapplied_revisions:
            click.echo(f"Revision {revision} ({file})")


# TODO: tests
@cli.command(
    help="Validates that revisions have only one head. Does sys.exit for use in CI."
)
@click.pass_context
async def validate_heads(ctx):
    mig = await Migrator.init(migrations_folder=ctx.obj["config"]["location"])
    code = 0
    if mig.ensure_single_head():
        click.echo("Only one head detected")
    else:
        code = 1

    sys.exit(code)


if __name__ == "__main__":
    cli()
