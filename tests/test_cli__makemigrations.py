import pytest

from tests._utils import _list_migrations


@pytest.mark.scenario("basic")
async def test_makemigrations_no_migrations_yet(plast, freezer):
    freezer.move_to("2025-10-09")

    # 1) Run once, should create one migration file
    result = await plast["invoke"](["makemigrations"])
    files = await _list_migrations(plast["migrations_folder"])
    assert len(files) == 1
    assert "Created migration file" in result.stdout

    # 2) Run second time, shouldn't crate any migrations, should output message
    result = await plast["invoke"](["makemigrations"])
    files = await _list_migrations(plast["migrations_folder"])
    # Should still only have one migration
    assert len(files) == 1
    assert result.stdout == "Nothing to migrate.\n"


@pytest.mark.scenario("missing_migration")
async def test_makemigrations_missing_migration(plast, freezer):
    freezer.move_to("2025-10-09")

    # 1) Run once, should create one migration file
    result = await plast["invoke"](["makemigrations"])
    files = await _list_migrations(plast["migrations_folder"])

    assert len(files) == 4
    assert "Created migration file" in result.stdout

    # 2) Run second time, shouldn't crate any migrations, should output message
    result = await plast["invoke"](["makemigrations"])
    files = await _list_migrations(plast["migrations_folder"])
    # Should still only have one migration
    assert len(files) == 4
    assert result.stdout == "Nothing to migrate.\n"


@pytest.mark.scenario("missing_migration")
async def test_makemigrations_custom_name(plast, freezer):
    freezer.move_to("2025-10-09")

    # 1) Run once, should create one migration file
    result = await plast["invoke"](["makemigrations", "--name=foo bar baz 123"])
    files = await _list_migrations(plast["migrations_folder"])

    assert len(files) == 4
    assert "Created migration file" in result.stdout
    assert "_foo_bar_baz_123.py" in result.stdout
