import os
import shutil
from pathlib import Path

import pytest

from plastron.cli import _load_config, _load_tortoise_config
from plastron.exceptions import ConfigError


@pytest.mark.parametrize(
    "cfg_path",
    [
        "settings.TORTOISE_ORM",  # module based
        "settings.SettingsClass.TORTOISE_ORM",  # class based
    ],
)
@pytest.mark.scenario("basic")
async def test_load_tortoise_config(plast, cfg_path):
    cfg = await _load_tortoise_config(cfg_path)
    assert cfg == {
        "connections": {"default": os.getenv("DB_CONN")},
        "apps": {
            "app": {"models": ["models", "plastron.models"]},
            "posts": {"models": ["other_models"]},
        },
    }


@pytest.mark.parametrize(
    "cfg_path",
    [
        "settings.WRONG_KEY",  # module based
        "settings.SettingsClass.WRONG_KEY",  # class based
    ],
)
@pytest.mark.scenario("basic")
async def test_load_tortoise_config_error(plast, cfg_path):
    with pytest.raises(
        ConfigError, match="Can't find Tortoise config in module 'settings'"
    ):
        await _load_tortoise_config(cfg_path)


@pytest.mark.parametrize(
    ("pyproject_path", "tortoise_orm", "location"),
    [
        ("./pyproject.toml", None, None),
        ("./pyproject.toml", "settings.TORTOISE_ORM_DIFFERENT_KEY", None),
        ("./pyproject.toml", "settings.TORTOISE_ORM", "./new_location"),
        ("./Doesnt-exist", "settings.TORTOISE_ORM", "./new_location"),
    ],
)
@pytest.mark.scenario("basic")
async def test_load_config(plast, pyproject_path, tortoise_orm, location):
    cfg = await _load_config(pyproject_path, tortoise_orm, location)
    assert cfg == {
        "base_dir": None,
        "tortoise_orm": tortoise_orm or "settings.TORTOISE_ORM",
        "location": location or "./migrations",
        "tortoise": {
            "connections": {"default": os.getenv("DB_CONN")},
            "apps": {
                "app": {"models": ["models", "plastron.models"]},
                "posts": {"models": ["other_models"]},
            },
        },
    }


@pytest.mark.scenario("basic")
@pytest.mark.plast_invoke_without_command
async def test_cli_default_setup(plast):
    ctx_dump = {}
    await plast["invoke"]([], ctx_dump=ctx_dump)

    assert ctx_dump["obj"] == {
        "config": {
            "base_dir": None,
            "tortoise_orm": "settings.TORTOISE_ORM",
            "location": "./migrations",
            "tortoise": {
                "connections": {"default": os.getenv("DB_CONN")},
                "apps": {
                    "app": {"models": ["models", "plastron.models"]},
                    "posts": {"models": ["other_models"]},
                },
            },
            "default_connection": "default",
        }
    }
    # Check that migration folder was created
    assert plast["migrations_folder"].exists()


@pytest.mark.parametrize(
    ("tortoise_orm", "location"),
    [
        (None, None),
        ("settings.TORTOISE_ORM_DIFFERENT_KEY", None),
        ("settings.TORTOISE_ORM", "./new_location"),
    ],
)
@pytest.mark.scenario("basic")
@pytest.mark.plast_invoke_without_command
async def test_cli_setup_with_params(plast, tortoise_orm, location):
    ctx_dump = {}
    params = []
    if tortoise_orm:
        params.append(f"--tortoise-orm={tortoise_orm}")
    if location:
        params.append(f"--location={location}")

    await plast["invoke"](params, ctx_dump=ctx_dump)
    assert ctx_dump["obj"] == {
        "config": {
            "base_dir": None,
            "tortoise_orm": tortoise_orm or "settings.TORTOISE_ORM",
            "location": location or "./migrations",
            "tortoise": {
                "connections": {"default": os.getenv("DB_CONN")},
                "apps": {
                    "app": {"models": ["models", "plastron.models"]},
                    "posts": {"models": ["other_models"]},
                },
            },
            "default_connection": "default",
        }
    }
    # Check that migration folder was created
    assert plast["migrations_folder"].exists()


@pytest.mark.scenario("basic")
@pytest.mark.plast_invoke_without_command
async def test_cli_setup_with_custom_pyproject_path(plast):
    Path("./my_folder").mkdir(parents=True, exist_ok=True)
    pyproject = Path("pyproject.toml")
    shutil.move(pyproject, "./my_folder/notpyprojectname.toml")

    assert pyproject.exists() is False

    ctx_dump = {}
    await plast["invoke"](
        ["--pyproject=./my_folder/notpyprojectname.toml"], ctx_dump=ctx_dump
    )
    assert ctx_dump["obj"] == {
        "config": {
            "base_dir": None,
            "tortoise_orm": "settings.TORTOISE_ORM",
            "location": "./migrations",
            "tortoise": {
                "connections": {"default": os.getenv("DB_CONN")},
                "apps": {
                    "app": {"models": ["models", "plastron.models"]},
                    "posts": {"models": ["other_models"]},
                },
            },
            "default_connection": "default",
        }
    }
    # Check that migration folder was created
    assert plast["migrations_folder"].exists()
