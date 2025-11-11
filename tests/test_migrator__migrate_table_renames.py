import pytest

from plastron.migrator import Migrator
from tests._utils import _check_table_exists


@pytest.fixture
async def migrator(plast):
    return await Migrator.init(migrations_folder=plast["migrations_folder"])


@pytest.mark.scenario("table_renames")
@pytest.mark.db
async def test_upgrade(migrator):
    await migrator.upgrade("default")

    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 3
    assert revs[0].revision == "01k9tjfh9p3c"
    assert revs[1].revision == "01k9tjdq7g82"
    assert revs[2].revision == "01k9tjd21v81"

    assert await _check_table_exists("userprofile")
    assert await _check_table_exists("user")
