import pytest


@pytest.mark.scenario("basic")
async def test_upgrade_no_migrations(plast, freezer):
    freezer.move_to("2025-10-09")
    result = await plast["invoke"](["upgrade"])
    assert result.stdout == "No revisions to apply\n"


# @pytest.mark.scenario("missing_migration")
# async def test_check_upgrade_all_migrations(plast, freezer):
#     freezer.move_to("2025-10-09")

#     result = await plast["invoke"](["upgrade"])
#     print(result.stdout)
#     print(result.__dict__)
