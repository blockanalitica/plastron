import contextlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path

import asyncclick as click
import pytest
from asyncclick.testing import CliRunner
from tortoise import Tortoise, connections

SCENARIOS = Path(__file__).parent / "scenarios"


@contextlib.contextmanager
def chdir_and_sys(dst):
    old_cwd = Path.cwd()
    old_sys = list(sys.path)
    try:
        os.chdir(dst)
        if str(dst) not in sys.path:
            sys.path.insert(0, str(dst))

        yield
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_sys


def _purge_app_modules(config):
    # Purge imported modules used for models between tests, otherwise it re-uses
    # previously imported modules, breaking the tests
    prefixes = []
    if Tortoise.apps:
        for app in config["apps"].values():
            for m in app["models"]:
                if isinstance(m, str):
                    # store the full module path as a purge prefix
                    prefixes.append(m)

    # remove each module AND its submodules
    to_del = [
        name
        for name in list(sys.modules)
        if any(name == p or name.startswith(p + ".") for p in prefixes)
    ]

    for name in to_del:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
async def plast(request, tmp_path):
    # Prepare working dir (unique per call)
    dst = tmp_path / f"proj_{len(list(tmp_path.iterdir()))}"
    dst.mkdir()

    # Pick up optional scenario from marker
    marker = request.node.get_closest_marker("scenario")
    scenario = marker.args[0] if marker else None
    if scenario:
        src = SCENARIOS / scenario
        if not src.exists():
            raise FileNotFoundError(f"Scenario '{scenario}' not found at {src}")
        shutil.copytree(src, dst, dirs_exist_ok=True)

    migrations_folder = dst / "migrations"
    if not migrations_folder.exists():
        migrations_folder.mkdir()

    runner = CliRunner()
    settings = None

    db_marker = request.node.get_closest_marker("db")

    with chdir_and_sys(dst):
        if scenario:
            spec = importlib.util.spec_from_file_location(
                "settings", str(dst / "settings.py")
            )
            settings = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(settings)

            if db_marker:
                apps = settings.TORTOISE_ORM.get("apps", {})
                if apps:
                    app = next(iter(apps.values()))
                    # Append `plastron.models` to the first app in Tortoise ORM Config
                    app.get("models", []).append("plastron.models")

                _purge_app_modules(config=settings.TORTOISE_ORM)
                await Tortoise.init(config=settings.TORTOISE_ORM)

                # Clean database before each test
                conn = connections.get("default")

                if conn.capabilities.dialect == "sqlite":
                    if os.path.exists(conn.filename):
                        os.remove(conn.filename)
                else:
                    await conn.execute_query("DROP SCHEMA public CASCADE;")
                    await conn.execute_query("CREATE SCHEMA public;")

        # Provide a click runner that runs in this cwd
        async def invoke(args, env=None, input=None, ctx_dump=None):  # noqa: A002
            importlib.invalidate_caches()
            from plastron.cli import cli  # freshly imported each call

            if ctx_dump is not None:

                @cli.result_callback()
                @click.pass_context
                def _tap(ctx, result, **_):
                    ctx_dump["ctx"] = ctx
                    ctx_dump["params"] = dict(ctx.params)
                    ctx_dump["obj"] = ctx.obj
                    ctx_dump["invoked_subcommand"] = ctx.invoked_subcommand
                    return result  # must return the original result

            if request.node.get_closest_marker("plast_invoke_without_command"):
                cli.invoke_without_command = True
                cli.no_args_is_help = False

            return await runner.invoke(cli, args, env=env, input=input)

        try:
            yield {
                "path": dst.resolve(),
                "invoke": invoke,
                "settings": settings,
                "migrations_folder": migrations_folder,
            }
        finally:
            if db_marker:
                _purge_app_modules(config=settings.TORTOISE_ORM)
                await Tortoise.close_connections()
