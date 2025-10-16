from types import SimpleNamespace

import pytest
from tortoise import Tortoise, fields

from plastron.migrator import Migrator, _build_graph
from plastron.utils import load_module_py
from tests._utils import _check_table_exists, _list_migrations, _write_migration_py


@pytest.fixture
async def migrator(plast):
    return await Migrator.init(migrations_folder=plast["migrations_folder"])


def _make_table(name, fields_list, unique_together=None, indexes=None):
    return {
        "name": name,
        "fields": list(fields_list),
        "unique_together": sorted(unique_together or []),
        "indexes": sorted(indexes or []),
    }


def _fake_migration(revision, down_revision=""):
    return SimpleNamespace(revision=revision, down_revision=down_revision)


def _same_callable_default():
    return 42


@pytest.mark.scenario("basic")
@pytest.mark.db
def test_describe_app_models(migrator):
    models = migrator._describe_app_models()
    assert len(models) == 4
    assert list(models) == ["plastron", "post", "profile", "user"]
    # verify that the dictionary has something in it
    assert models["user"]["name"] == "user"


@pytest.mark.scenario("basic")
@pytest.mark.db
async def test_describe_model(migrator):
    info = migrator._describe_model(Tortoise.apps["app"]["Profile"])
    assert list(info.keys()) == ["name", "fields", "unique_together", "indexes"]
    assert info["name"] == "profile"
    assert info["unique_together"] == [["full_name", "city"]]
    assert info["indexes"] == [["city"], ["full_name", "city"]]

    assert len(info["fields"]) == 4
    assert info["fields"][0][0] == "profile_id"
    assert info["fields"][1][0] == "full_name"
    assert info["fields"][2][0] == "city"
    assert info["fields"][3][0] == "password"


@pytest.mark.parametrize(
    ("make_old", "make_new", "expected"),
    [
        pytest.param(
            lambda: fields.BooleanField(
                null=False,
                default=False,
                db_index=False,
                unique=False,
                source_field="applied",
            ),
            lambda: fields.BooleanField(
                null=False,
                default=False,
                db_index=False,
                unique=False,
                source_field="applied",
            ),
            False,
            id="identical",
        ),
        pytest.param(
            lambda: fields.BooleanField(null=False, default=False, source_field="x"),
            lambda: fields.CharField(
                max_length=10, null=False, default="0", source_field="x"
            ),
            True,
            id="field_type-differs",
        ),
        pytest.param(
            lambda: fields.IntField(null=False, source_field="foo"),
            lambda: fields.IntField(null=False, source_field="bar"),
            True,
            id="db_column-differs",
        ),
        pytest.param(
            lambda: fields.IntField(primary_key=True),  # generated=True
            lambda: fields.IntField(primary_key=False),  # generated=False
            True,
            id="generated-differs",
        ),
        pytest.param(
            lambda: fields.BooleanField(null=False, default=False, source_field="a"),
            lambda: fields.BooleanField(null=True, default=False, source_field="a"),
            True,
            id="nullable-differs",
        ),
        pytest.param(
            lambda: fields.CharField(max_length=10, unique=False, source_field="u"),
            lambda: fields.CharField(max_length=10, unique=True, source_field="u"),
            True,
            id="unique-differs",
        ),
        pytest.param(
            lambda: fields.CharField(max_length=10, db_index=False, source_field="i"),
            lambda: fields.CharField(max_length=10, db_index=True, source_field="i"),
            True,
            id="indexed-differs",
        ),
        pytest.param(
            lambda: fields.BooleanField(default=False, source_field="d"),
            lambda: fields.BooleanField(default=True, source_field="d"),
            True,
            id="default-differs",
        ),
        pytest.param(
            lambda: fields.IntField(default=_same_callable_default, source_field="dc"),
            lambda: fields.IntField(default=_same_callable_default, source_field="dc"),
            False,
            id="default-callable-equals",
        ),
        # TODO:
        # pytest.param(
        #     lambda: fields.IntField(default=lambda: 1, source_field="dc2"),
        #     lambda: fields.IntField(default=lambda: 3, source_field="dc2"),
        #     True,
        #     id="default-callable-differs",
        # ),
        pytest.param(
            lambda: fields.CharField(max_length=64, source_field="name"),
            lambda: fields.CharField(max_length=128, source_field="name"),
            True,
            id="constraints-differ",
        ),
    ],
)
def test_fields_differ(migrator, make_old, make_new, expected):
    old = make_old()
    new = make_new()
    assert migrator._fields_differ(old, new) is expected


@pytest.mark.parametrize(
    ("table_name", "old_fields", "new_fields", "expected_op_types"),
    [
        pytest.param(
            "user",
            lambda: [("a", fields.BooleanField(null=False, default=False))],
            lambda: [("a", fields.BooleanField(null=False, default=False))],
            [],
            id="identical",
        ),
        pytest.param(
            "user",
            lambda: [("a", fields.IntField())],
            lambda: [("a", fields.IntField()), ("b", fields.CharField(max_length=123))],
            ["AddColumn"],
            id="add-only",
        ),
        pytest.param(
            "user",
            lambda: [("a", fields.IntField()), ("b", fields.CharField(max_length=123))],
            lambda: [("a", fields.IntField())],
            ["DropColumn"],
            id="drop-only",
        ),
        pytest.param(
            "article",
            lambda: [("flag", fields.BooleanField(null=False, default=False))],
            lambda: [("flag", fields.BooleanField(null=True, default=False))],
            ["AlterColumn"],
            id="alter-only",
        ),
        pytest.param(
            "mix",
            lambda: [
                ("x", fields.IntField()),
                ("y", fields.CharField(max_length=123, db_column="ycol", unique=False)),
            ],
            lambda: [
                (
                    "y",
                    fields.CharField(max_length=123, db_column="ycol", unique=True),
                ),  # unique changed → alter
                ("z", fields.BooleanField(default=True)),  # new → add
            ],
            ["DropColumn", "AddColumn", "AlterColumn"],
            id="mixed-drop-add-alter",
        ),
    ],
)
def test_diff_columns_categories_and_payloads(
    migrator, table_name, old_fields, new_fields, expected_op_types
):
    old = old_fields()
    new = new_fields()

    ops = migrator._diff_columns(table_name, old, new)

    # expected kinds present
    op_types = [op[0] for op in ops]
    for t in expected_op_types:
        assert t in op_types

    # verify operation ordering: drops first, then adds, then alters
    order_map = {"DropColumn": 0, "AddColumn": 1, "AlterColumn": 2}
    ordered_types = sorted(op_types, key=lambda k: order_map[k]) if op_types else []
    assert op_types == ordered_types

    # payload shape and identity checks
    for op in ops:
        op_type = op[0]
        assert op[1] == table_name

        match op_type:
            case "DropColumn":
                # (op_type, table, {"name": field_name, "field": <fields.Field>})
                payload = op[2]
                assert set(payload) == {"name", "field"}
                assert dict(old)[payload["name"]] is payload["field"]
            case "AddColumn":
                # (op_type, table, {"name": field_name, "field": <fields.Field>})
                payload = op[2]
                assert set(payload) == {"name", "field"}
                assert dict(new)[payload["name"]] is payload["field"]
            case "AlterColumn":
                # (op_type, table, {"name": field_name, "new_field": <fields.Field>,
                # "old_field": <fields.Field>})
                payload = op[2]
                assert set(payload) == {"name", "new_field", "old_field"}
                assert dict(new)[payload["name"]] is payload["new_field"]
                assert dict(old)[payload["name"]] is payload["old_field"]
            case _:
                raise NotImplementedError


def test_diff_table_no_changes(migrator):
    old = _make_table(
        "user",
        [
            ("id", fields.IntField(primary_key=True)),
            ("email", fields.CharField(max_length=64, db_index=True)),
        ],
        unique_together=[("email",)],
        indexes=[("email",)],
    )
    new = _make_table(
        "user",
        [
            ("id", fields.IntField(primary_key=True)),
            ("email", fields.CharField(max_length=64, db_index=True)),
        ],
        unique_together=[("email",)],
        indexes=[("email",)],
    )

    ops = migrator.diff_table(old, new)
    assert ops == []


def test_diff_table_fields_only(migrator):
    old = _make_table(
        "article",
        [
            ("id", fields.IntField(primary_key=True)),
            ("title", fields.CharField(max_length=64)),
        ],
    )
    new = _make_table(
        "article",
        [
            ("id", fields.IntField(primary_key=True)),
            ("title", fields.CharField(max_length=64, null=True)),
        ],
    )

    ops = migrator.diff_table(old, new)
    kinds = [op[0] for op in ops]
    assert kinds == ["AlterColumn"]
    assert ops[0][1] == "article"
    assert ops[0][2]["name"] == "title"
    assert ops[0][2]["new_field"] is dict(new["fields"])["title"]
    assert ops[0][2]["old_field"] is dict(old["fields"])["title"]


def test_diff_table_unique_together_add_and_drop():
    m = Migrator()
    old = _make_table(
        "user",
        [("id", fields.IntField(primary_key=True))],
        unique_together=[("email", "tenant"), ("x", "y")],
    )
    new = _make_table(
        "user",
        [("id", fields.IntField(primary_key=True))],
        unique_together=[
            ("email",)
        ],  # drop ("email","tenant") and ("x","y"), add ("email",)
    )

    ops = m.diff_table(old, new)
    assert [op[0] for op in ops] == [
        "DropUniqueTogether",
        "DropUniqueTogether",
        "AddUniqueTogether",
    ]

    # table name correct
    assert all(op[1] == "user" for op in ops)
    # payload correct
    assert ops[0][2] == ["email", "tenant"]
    assert ops[1][2] == ["x", "y"]
    assert ops[2][2] == ["email"]


def test_diff_table_indexes_add_and_drop(migrator):
    old = _make_table(
        "log",
        [
            ("id", fields.IntField(primary_key=True)),
            ("level", fields.CharField(max_length=64)),
        ],
        indexes=[("created_at",), ("level",)],
    )
    new = _make_table(
        "log",
        [
            ("id", fields.IntField(primary_key=True)),
            ("level", fields.CharField(max_length=64)),
        ],
        indexes=[("level",), ("source",)],  # drop created_at, add source
    )

    ops = migrator.diff_table(old, new)

    assert [op[0] for op in ops] == ["DropIndex", "AddIndex"]
    # table name correct
    assert all(op[1] == "log" for op in ops)
    # payload correct
    assert ops[0][2] == ("created_at",)
    assert ops[1][2] == ("source",)


def test_diff_table_mixed_category_ordering(migrator):
    """
    Fields ops must come first, then unique together ops, then index ops.
    """
    old = _make_table(
        "mix",
        [
            ("a", fields.IntField()),
            ("b", fields.CharField(max_length=64)),
        ],  # will alter b
        unique_together=[("u1", "u2")],  # will drop this
        indexes=[("ix_old",), ("ix_keep",)],
    )
    new = _make_table(
        "mix",
        [
            ("a", fields.IntField()),
            ("b", fields.CharField(max_length=64, null=True)),
            ("c", fields.BooleanField(default=True)),
        ],  # add c, alter b
        unique_together=[("u3",)],  # add this
        indexes=[("ix_keep",), ("ix_new",)],  # drop ix_old, add ix_new
    )

    ops = migrator.diff_table(old, new)
    assert [op[0] for op in ops] == [
        "AddColumn",
        "AlterColumn",
        "DropUniqueTogether",
        "AddUniqueTogether",
        "DropIndex",
        "AddIndex",
    ]
    # quick sanity on names/payloads without assuming inner ordering
    assert ops[0][2]["name"] == "c"
    assert ops[1][2]["name"] == "b"
    assert ops[2][2] == ["u1", "u2"]
    assert ops[3][2] == ["u3"]
    assert ops[4][2] == ("ix_old",)
    assert ops[5][2] == ("ix_new",)


async def test_load_migration_modules_maps_by_revision_and_ignores_non_py(
    tmp_path, migrator
):
    path = migrator.migrations_folder

    rev_1 = "1_mig"
    rev_2 = "2_mig"
    await _write_migration_py(path, rev_1, revision=rev_1)
    await _write_migration_py(path, rev_2, revision=rev_2)
    (path / "README.txt").write_text("ignore me", encoding="utf-8")

    module_map = await migrator._load_migration_modules()

    # Only .py files, keyed by their "revision" variable
    assert set(module_map.keys()) == {rev_1, rev_2}

    assert module_map[rev_1].revision == rev_1
    assert module_map[rev_2].revision == rev_2

    # Loaded modules should have __name__ equal to the filename (no .py),
    # because load_module_py(module_id=filename_without_ext) is used
    assert module_map[rev_1].__name__ == rev_1
    assert module_map[rev_2].__name__ == rev_2


async def test_load_migration_modules_empty_folder_returns_empty_dict(migrator):
    module_map = await migrator._load_migration_modules()
    assert module_map == {}


def test_build_graph_single_root_no_parents():
    migs = [_fake_migration("a", None)]
    nodes, parents, children = _build_graph(migs)

    assert nodes == {"a"}
    assert parents["a"] == set()
    assert children["a"] == set()


def test_build_graph_linear_chain():
    # a -> b -> c
    migs = [
        _fake_migration("a", None),
        _fake_migration("b", "a"),
        _fake_migration("c", "b"),
    ]
    nodes, parents, children = _build_graph(migs)

    assert nodes == {"a", "b", "c"}
    assert parents["a"] == set()
    assert parents["b"] == {"a"}
    assert parents["c"] == {"b"}

    assert children["a"] == {"b"}
    assert children["b"] == {"c"}
    # leaf should still exist with an empty set
    assert children["c"] == set()


def test_build_graph_branch_with_multi_parents():
    #    a
    #   / \
    #  b   c
    #   \ /
    #    d
    migs = [
        _fake_migration("a", None),
        _fake_migration("b", "a"),
        _fake_migration("c", "a"),
        _fake_migration("d", ("b", "c")),
    ]
    nodes, parents, children = _build_graph(migs)

    assert nodes == {"a", "b", "c", "d"}
    assert parents["a"] == set()
    assert parents["b"] == {"a"}
    assert parents["c"] == {"a"}
    assert parents["d"] == {"b", "c"}

    assert children["a"] == {"b", "c"}
    assert children["b"] == {"d"}
    assert children["c"] == {"d"}
    assert children["d"] == set()


def test_build_graph_multiple_roots_and_disconnected_components():
    # Component 1: a -> b
    # Component 2: x (root, no edges)
    migs = [
        _fake_migration("a", None),
        _fake_migration("b", "a"),
        _fake_migration("x", None),
    ]
    nodes, parents, children = _build_graph(migs)

    assert nodes == {"a", "b", "x"}

    # Component 1 checks
    assert parents["a"] == set()
    assert parents["b"] == {"a"}
    assert children["a"] == {"b"}
    assert children["b"] == set()

    # Component 2 checks
    assert parents["x"] == set()
    assert children["x"] == set()


def test_build_graph_keys_exist_for_all_seen_revisions():
    # Ensure every revision encountered appears in both parents and children,
    # even if empty (root or leaf).
    migs = [_fake_migration("root", None), _fake_migration("child", "root")]
    nodes, parents, children = _build_graph(migs)

    for r in nodes:
        assert r in parents
        assert r in children
        # Sets should be actual set instances
        assert isinstance(parents[r], set)
        assert isinstance(children[r], set)


@pytest.mark.scenario("basic_applied")
async def test_init(plast):
    path = plast["migrations_folder"]
    mig = await Migrator.init(migrations_folder=path)

    assert len(mig.module_map) == 3
    assert mig.migrations_folder == path
    assert sorted(mig.nodes) == ["01k714bysv68", "01k714em4veg", "01k714g3xp0q"]
    assert mig.parents == {
        "01k714em4veg": {"01k714bysv68"},
        "01k714bysv68": set(),
        "01k714g3xp0q": {"01k714em4veg"},
    }
    assert mig.children == {
        "01k714bysv68": {"01k714em4veg"},
        "01k714em4veg": {"01k714g3xp0q"},
        "01k714g3xp0q": set(),
    }
    assert mig.revisions == ["01k714bysv68", "01k714em4veg", "01k714g3xp0q"]


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_detect_unapplied_revisions(migrator):
    revs = await migrator._detect_unapplied_revisions()
    assert revs == ["01k714bysv68", "01k714em4veg", "01k714g3xp0q"]


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_detect_unapplied_revisions_partially_applied(migrator):
    await migrator.upgrade("default", "01k714em4veg")
    revs = await migrator._detect_unapplied_revisions()
    assert revs == ["01k714g3xp0q"]


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_detect_unapplied_revisions_all_applied(migrator):
    # apply all first
    await migrator.upgrade("default")

    revs = await migrator._detect_unapplied_revisions()
    assert revs == []


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_check(migrator):
    revs = await migrator.check()
    assert revs == [
        ("01k714bysv68", "01k714bysv68_auto.py"),
        ("01k714em4veg", "01k714em4veg_auto.py"),
        ("01k714g3xp0q", "01k714g3xp0q_auto.py"),
    ]

    await migrator.upgrade("default", "01k714em4veg")
    revs = await migrator.check()
    assert revs == [
        ("01k714g3xp0q", "01k714g3xp0q_auto.py"),
    ]


@pytest.mark.scenario("missing_migration")
def test_build_models_from_revisions(migrator):
    models = migrator._build_models_from_revisions(migrator.revisions)

    assert len(models) == 4
    assert list(models) == ["plastron", "profile", "user", "post"]
    # Check if migrations added `updated_at` field
    assert "updated_at" in models["user"]._meta.fields_map
    # Check that auto_now_add was correctly set to true on `created_at`
    assert not models["user"]._meta.fields_map["created_at"].auto_now
    assert models["user"]._meta.fields_map["created_at"].auto_now_add


@pytest.mark.scenario("missing_migration")
def test_build_models_from_revisions_up_to_specific(migrator):
    models = migrator._build_models_from_revisions(["01k714bysv68"])

    assert len(models) == 3
    assert list(models) == ["plastron", "profile", "user"]
    # updated_at shouldn't be there as it's added in second migration
    assert "updated_at" not in models["user"]._meta.fields_map
    # created_at should have auto_now set to true
    assert models["user"]._meta.fields_map["created_at"].auto_now


@pytest.mark.scenario("missing_migration")
def test_describe_revision_models(migrator):
    models = migrator._describe_revision_models()
    assert len(models) == 4
    assert list(models) == ["plastron", "profile", "user", "post"]
    assert models["user"]["name"] == "user"


def test_diff_models_create_table(migrator):
    old = {
        "tag": {
            "name": "tag",
            "fields": [("id", fields.IntField(primary_key=True))],
            "unique_together": [],
            "indexes": [],
        },
    }
    new = {
        "post": {
            "name": "post",
            "fields": [("id", fields.IntField(primary_key=True))],
            "unique_together": [],
            "indexes": [],
        },
        "user": {
            "name": "user",
            "fields": [("id", fields.IntField(primary_key=True))],
            "unique_together": [],
            "indexes": [],
        },
        "tag": old["tag"],
    }
    diff = migrator.diff_models(old, new)
    assert diff == [
        ("CreateTable", "post", new["post"]),
        ("CreateTable", "user", new["user"]),
    ]


def test_diff_models_drop_table(migrator):
    old = {
        "post": {
            "name": "post",
            "fields": [("id", fields.IntField(primary_key=True))],
            "unique_together": [],
            "indexes": [],
        },
        "user": {
            "name": "user",
            "fields": [("id", fields.IntField(primary_key=True))],
            "unique_together": [],
            "indexes": [],
        },
        "tag": {
            "name": "tag",
            "fields": [("id", fields.IntField(primary_key=True))],
            "unique_together": [],
            "indexes": [],
        },
    }
    new = {"tag": old["tag"]}
    diff = migrator.diff_models(old, new)
    assert diff == [
        ("DropTable", "post", old["post"]),
        ("DropTable", "user", old["user"]),
    ]


def test_diff_models_table_diff(migrator):
    post_fields = [("id", fields.IntField(primary_key=True))]
    old = {
        "post": {
            "name": "post",
            "fields": post_fields,
            "unique_together": [],
            "indexes": [],
        },
    }

    foo_field = fields.CharField(max_length=64)
    new = {
        "post": {
            "name": "post",
            "fields": [*post_fields, ("foo", foo_field)],
            "unique_together": [["id", "foo"]],
            "indexes": [],
        }
    }
    diff = migrator.diff_models(old, new)
    assert diff == [
        ("AddColumn", "post", {"name": "foo", "field": foo_field}),
        ("AddUniqueTogether", "post", ["id", "foo"]),
    ]


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_makemigrations(migrator, plast, freezer):
    freezer.move_to("2025-10-10")
    migs = await _list_migrations(plast["migrations_folder"])
    assert len(migs) == 3

    await migrator.makemigrations()

    migs = await _list_migrations(plast["migrations_folder"])
    assert len(migs) == 4
    assert migs[3].startswith("01k75pnn00")

    mig = migs[3]
    module = load_module_py(plast["migrations_folder"] / mig, mig.replace(".py", ""))
    assert module.revision.startswith("01k75pnn00")
    assert module.down_revision == "01k714g3xp0q"

    assert len(module.upgrade_operations) == 1
    assert len(module.downgrade_operations) == 1


@pytest.mark.scenario("basic")
@pytest.mark.db
async def test_makemigrations_fresh_start(migrator, plast, freezer):
    freezer.move_to("2025-10-10")
    migs = await _list_migrations(plast["migrations_folder"])
    assert len(migs) == 0

    await migrator.makemigrations()

    migs = await _list_migrations(plast["migrations_folder"])
    assert len(migs) == 1
    mig = migs[0]
    assert mig.startswith("01k75pnn00")

    module = load_module_py(plast["migrations_folder"] / mig, mig.replace(".py", ""))
    assert module.revision.startswith("01k75pnn00")
    assert module.down_revision is None

    assert len(module.upgrade_operations) == 6
    assert len(module.downgrade_operations) == 6


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_upgrade(migrator):
    await migrator.upgrade("default")

    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 3
    assert revs[0].revision == "01k714g3xp0q"
    assert revs[1].revision == "01k714em4veg"
    assert revs[2].revision == "01k714bysv68"

    assert await _check_table_exists("post")
    assert await _check_table_exists("profile")
    assert await _check_table_exists("user")


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_upgrade_to_revision(migrator):
    await migrator.upgrade("default", "01k714em4veg")

    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 2
    assert revs[0].revision == "01k714em4veg"
    assert revs[1].revision == "01k714bysv68"
    assert await _check_table_exists("post")
    assert await _check_table_exists("profile")
    assert await _check_table_exists("user")


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_downgrade(migrator):
    # Downgrade by default should only downgrade one migration
    # First upgrade and check we have all the tables
    await migrator.upgrade("default")
    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 3
    assert await _check_table_exists("post")
    assert await _check_table_exists("profile")
    assert await _check_table_exists("user")

    # Now downgrade and check that tables don't exist anymore
    await migrator.downgrade("default")

    revs = await Plastron.all()
    assert len(revs) == 2

    assert await _check_table_exists("plastron")
    assert await _check_table_exists("post")
    assert await _check_table_exists("profile")
    assert await _check_table_exists("user")


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_downgrade_all(migrator):
    # First upgrade and check we have all the tables
    await migrator.upgrade("default")
    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 3
    assert await _check_table_exists("post")
    assert await _check_table_exists("profile")
    assert await _check_table_exists("user")

    # Now downgrade and check that tables don't exist anymore
    await migrator.downgrade("default", "01k714bysv68")

    assert await _check_table_exists("plastron") is False
    assert await _check_table_exists("post") is False
    assert await _check_table_exists("profile") is False
    assert await _check_table_exists("user") is False


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_downgrade_to_revision(migrator):
    # First upgrade and check we have all the tables
    await migrator.upgrade("default")
    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 3
    assert await _check_table_exists("post")
    assert await _check_table_exists("profile")
    assert await _check_table_exists("user")

    # Now downgrade and check that correct tables don't exist anymore
    await migrator.downgrade("default", "01k714em4veg")

    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 1
    assert await _check_table_exists("profile")
    assert await _check_table_exists("user")
    assert await _check_table_exists("post") is False


@pytest.mark.scenario("missing_migration")
@pytest.mark.db
async def test_get_applied_revisions(migrator):
    await migrator.upgrade("default")
    from plastron.models import Plastron

    revs = await Plastron.all()
    assert len(revs) == 3
    revs = await migrator._get_applied_revisions()
    # It needs to return them in applied order (first to last) aka ordered by id asc
    assert revs == ["01k714bysv68", "01k714em4veg", "01k714g3xp0q"]
