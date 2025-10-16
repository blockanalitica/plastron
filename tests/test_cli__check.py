import pytest


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_check_no_applied_migrations(plast, freezer):
    freezer.move_to("2025-10-09")
    result = await plast["invoke"](["check"])

    assert (
        result.stdout
        == """New revisions detected:
Revision 01k714bysv68 (01k714bysv68_auto.py)
Revision 01k714em4veg (01k714em4veg_auto.py)
Revision 01k714g3xp0q (01k714g3xp0q_auto.py)
"""
    )


# @pytest.mark.scenario("missing_migration")
# async def test_check_one_missing_after_already_upgraded(plast, freezer):
#     freezer.move_to("2025-10-09")

#     await plast["invoke"](["upgrade"])
#     await plast["invoke"](["makemigrations"])

#     result = await plast["invoke"](["check"])

#     assert "New revisions detected:" in result.stdout
#     assert "Revision 01k714bysv" in result.stdout

#     lines = [line for line in result.stdout.split("\n") if line]
#     assert len(lines) == 2
