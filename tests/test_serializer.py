from pathlib import Path

import aiofiles
import aiofiles.os
import pytest
from tortoise import fields

from plastron.serializer import Serializer


@pytest.mark.parametrize(
    ("field_fn", "expected_kwargs"),
    [
        pytest.param(
            lambda: fields.IntField(),
            {},
            id="IntField",
        ),
        pytest.param(
            lambda: fields.IntField(
                unique=True,
                primary_key=True,
                db_index=True,
                default=4,
                source_field="my_int",
            ),
            {
                "unique": True,
                "primary_key": True,
                "db_index": True,
                "default": 4,
                "source_field": "my_int",
                "generated": True,
            },
            id="IntField-set_values",
        ),
        pytest.param(
            lambda: fields.CharField(null=True, max_length=123, db_index=True),
            {"max_length": 123, "null": True, "db_index": True},
            id="CharField",
        ),
        pytest.param(
            lambda: fields.DecimalField(
                max_digits=6, decimal_places=3, source_field="my_decimal"
            ),
            {"max_digits": 6, "decimal_places": 3, "source_field": "my_decimal"},
            id="CharField",
        ),
        pytest.param(
            lambda: fields.DatetimeField(auto_now=True, unique=True),
            {"auto_now": True, "auto_now_add": False, "unique": True},
            id="DatetimeField-auto_now",
        ),
        pytest.param(
            lambda: fields.DatetimeField(auto_now_add=True),
            {"auto_now": False, "auto_now_add": True},
            id="DatetimeField-auto_now_add",
        ),
        pytest.param(
            lambda: fields.TimeField(auto_now=True),
            {"auto_now": True, "auto_now_add": False},
            id="TimeField-auto_now",
        ),
        pytest.param(
            lambda: fields.TimeField(auto_now_add=True),
            {"auto_now": False, "auto_now_add": True},
            id="TimeField-auto_now_add",
        ),
        pytest.param(
            lambda: fields.DateField(unique=True),
            {"unique": True},
            id="DateField-unique",
        ),
        pytest.param(
            lambda: fields.DateField(db_index=True),
            {"db_index": True},
            id="DateField-db_index",
        ),
    ],
)
def test_gather_field_kwargs(field_fn, expected_kwargs):
    serializer = Serializer([])
    kwargs = serializer._gather_field_kwargs(field_fn())
    assert kwargs == expected_kwargs


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(5, 5, id="integer"),
        pytest.param("5", '"5"', id="string"),
        pytest.param(False, False, id="bool"),
    ],
)
def test_value_to_code(value, expected):
    serializer = Serializer([])
    code = serializer._value_to_code(value)
    assert code == expected


@pytest.mark.parametrize(
    ("field_fn", "expected"),
    [
        pytest.param(
            lambda: fields.IntField(),
            "fields.IntField()",
            id="IntField",
        ),
        pytest.param(
            lambda: fields.IntField(
                unique=True,
                primary_key=True,
                db_index=True,
                default=4,
                source_field="my_int",
            ),
            "fields.IntField(unique=True, primary_key=True, db_index=True, "
            'default=4, source_field="my_int", generated=True)',
            id="IntField-set_values",
        ),
    ],
)
def test_field_to_code(field_fn, expected):
    serializer = Serializer([])
    code = serializer._field_to_code(field_fn())
    assert code == expected


@pytest.mark.parametrize(
    ("operation_fn", "upgrade_ops", "downgrade_ops"),
    [
        pytest.param(
            lambda: (
                "CreateTable",
                "users",
                {
                    "name": "users",
                    "fields": [
                        ("id", fields.IntField(primary_key=True)),
                        ("email", fields.CharField(max_length=256)),
                    ],
                    "unique_together": ["id", "email"],
                    "indexes": [["id"], ["email"]],
                },
            ),
            [
                'op.CreateTable("users", fields=[("id", fields.IntField('
                "unique=True, primary_key=True, db_index=True, generated=True)),"
                '("email", fields.CharField(max_length=256))'
                '], unique_together=["id", "email"])',
                'op.AddIndex("users", columns=["id"])',
                'op.AddIndex("users", columns=["email"])',
            ],
            [
                'op.DropTable("users")',
                'op.DropIndex("users", columns=["id"])',
                'op.DropIndex("users", columns=["email"])',
            ],
            id="CreateTable",
        ),
        pytest.param(
            lambda: (
                "CreateTable",
                "users",
                {
                    "name": "users",
                    "fields": [
                        ("id", fields.IntField(primary_key=True)),
                        ("email", fields.CharField(max_length=256)),
                    ],
                    "unique_together": ["id", "email"],
                    "indexes": [],
                },
            ),
            [
                'op.CreateTable("users", fields=[("id", fields.IntField('
                "unique=True, primary_key=True, db_index=True, generated=True)),"
                '("email", fields.CharField(max_length=256))'
                '], unique_together=["id", "email"])',
            ],
            ['op.DropTable("users")'],
            id="CreateTable-no_indexes",
        ),
        pytest.param(
            lambda: (
                "CreateTable",
                "users",
                {
                    "name": "users",
                    "fields": [
                        ("id", fields.IntField(primary_key=True)),
                        ("email", fields.CharField(max_length=256)),
                    ],
                    "unique_together": [],
                    "indexes": [],
                },
            ),
            [
                'op.CreateTable("users", fields=[("id", fields.IntField('
                "unique=True, primary_key=True, db_index=True, generated=True)),"
                '("email", fields.CharField(max_length=256))'
                "], unique_together=[])",
            ],
            ['op.DropTable("users")'],
            id="CreateTable-no_unique_together",
        ),
        pytest.param(
            lambda: (
                "DropTable",
                "users",
                {
                    "name": "users",
                    "fields": [
                        ("id", fields.IntField(primary_key=True)),
                        ("email", fields.CharField(max_length=256)),
                    ],
                    "unique_together": ["id", "email"],
                    "indexes": [["id"], ["email"]],
                },
            ),
            [
                'op.DropIndex("users", columns=["id"])',
                'op.DropIndex("users", columns=["email"])',
                'op.DropTable("users")',
            ],
            [
                'op.CreateTable("users", fields=[("id", fields.IntField('
                "unique=True, primary_key=True, db_index=True, generated=True)),"
                '("email", fields.CharField(max_length=256))'
                '], unique_together=["id", "email"])',
                'op.AddIndex("users", columns=["id"])',
                'op.AddIndex("users", columns=["email"])',
            ],
            id="DropTable",
        ),
        pytest.param(
            lambda: ("AddUniqueTogether", "users", ["foo", "bar"]),
            ['op.AddUniqueTogether("users", columns=["foo", "bar"])'],
            ['op.DropUniqueTogether("users", columns=["foo", "bar"])'],
            id="AddUniqueTogether",
        ),
        pytest.param(
            lambda: ("AddUniqueTogether", "users", [("foo", "bar"), ("one", "two")]),
            [
                'op.AddUniqueTogether("users", '
                'columns=[["foo", "bar"], ["one", "two"]])',
            ],
            [
                'op.DropUniqueTogether("users", '
                'columns=[["foo", "bar"], ["one", "two"]])'
            ],
            id="AddUniqueTogether_multiple",
        ),
        pytest.param(
            lambda: ("DropUniqueTogether", "users", ["foo", "bar"]),
            ['op.DropUniqueTogether("users", columns=["foo", "bar"])'],
            ['op.AddUniqueTogether("users", columns=["foo", "bar"])'],
            id="DropUniqueTogether",
        ),
        pytest.param(
            lambda: ("AddIndex", "users", ["foo", "bar"]),
            ['op.AddIndex("users", columns=["foo", "bar"])'],
            ['op.DropIndex("users", columns=["foo", "bar"])'],
            id="AddIndex",
        ),
        pytest.param(
            lambda: ("DropIndex", "users", ["foo", "bar"]),
            ['op.DropIndex("users", columns=["foo", "bar"])'],
            ['op.AddIndex("users", columns=["foo", "bar"])'],
            id="DropIndex",
        ),
        pytest.param(
            lambda: (
                "AddColumn",
                "users",
                {
                    "name": "bio",
                    "field": fields.CharField(max_length=256, unique=True),
                },
            ),
            [
                'op.AddColumn("users", "bio", fields.CharField(max_length=256, '
                "unique=True))",
            ],
            ['op.DropColumn("users", "bio")'],
            id="AddColumn",
        ),
        pytest.param(
            lambda: (
                "DropColumn",
                "users",
                {
                    "name": "bio",
                    "field": fields.CharField(max_length=256, unique=True),
                },
            ),
            ['op.DropColumn("users", "bio")'],
            [
                'op.AddColumn("users", "bio", '
                "fields.CharField(max_length=256, unique=True))"
            ],
            id="DropColumn",
        ),
        pytest.param(
            lambda: (
                "AlterColumn",
                "users",
                {
                    "name": "bio",
                    "old_field": fields.CharField(max_length=256),
                    "new_field": fields.CharField(max_length=256, unique=True),
                },
            ),
            [
                'op.AlterColumn("users", "bio", fields.CharField(max_length=256, '
                "unique=True))",
            ],
            ['op.AlterColumn("users", "bio", fields.CharField(max_length=256))'],
            id="AlterColumn",
        ),
    ],
)
def test_serialize_operation(operation_fn, upgrade_ops, downgrade_ops):
    serializer = Serializer([])
    serializer._serialize_operation(operation_fn())

    assert len(serializer.upgrade_operations) == len(upgrade_ops)
    for op, expected_op in zip(
        serializer.upgrade_operations, upgrade_ops, strict=False
    ):
        assert op == expected_op

    assert len(serializer.downgrade_operations) == len(downgrade_ops)
    for op, expected_op in zip(
        serializer.downgrade_operations, downgrade_ops, strict=False
    ):
        assert op == expected_op


def test_serialize_operation_raises_for_invalid_operation():
    serializer = Serializer([])
    with pytest.raises(NotImplementedError, match="Missing serializer for operation"):
        serializer._serialize_operation(("NotExisting", "not", "existing"))


def test_serialize():
    ops = [
        ("DropUniqueTogether", "users", ["foo", "bar"]),
        ("AddIndex", "users", ["foo", "bar"]),
        (
            "DropColumn",
            "users",
            {
                "name": "bio",
                "field": fields.CharField(max_length=256, unique=True),
            },
        ),
    ]
    serializer = Serializer(ops)
    serializer._serialize()

    assert len(serializer.upgrade_operations) == len(ops)

    for op, serialized in zip(ops, serializer.upgrade_operations, strict=True):
        assert op[0] in serialized


async def test_write_migration_file(tmp_path, freezer, monkeypatch):
    import plastron

    monkeypatch.setattr(plastron, "__version__", "9.9.9")
    freezer.move_to("2025-10-08")

    path = tmp_path / Path("./mig")
    path.mkdir()
    ops = [
        ("DropUniqueTogether", "users", ["foo", "bar"]),
        ("AddIndex", "users", ["foo", "bar"]),
        (
            "DropColumn",
            "users",
            {
                "name": "bio",
                "field": fields.CharField(max_length=256, unique=True),
            },
        ),
    ]
    serializer = Serializer(ops)

    revision = "rev_1"
    down_revision = [""]
    fname = await serializer.write_migration_file(revision, down_revision, path)

    # Check that migration file actually exists on correct path
    migrations = [f for f in await aiofiles.os.listdir(path) if f.endswith(".py")]
    assert migrations == [fname]

    # Check contents
    async with aiofiles.open(path / fname) as f:
        contents = await f.read()

    assert (
        contents
        == """# Generated by Plastron 9.9.9 on 2025-10-08T00:00:00+00:00
from tortoise import fields

from plastron import operations as op


revision = "rev_1"
down_revision = ""

upgrade_operations = [
    op.DropUniqueTogether("users", columns=["foo", "bar"]),
    op.AddIndex("users", columns=["foo", "bar"]),
    op.DropColumn("users", "bio"),
]

downgrade_operations = [
    op.AddColumn("users", "bio", fields.CharField(max_length=256, unique=True)),
    op.DropIndex("users", columns=["foo", "bar"]),
    op.AddUniqueTogether("users", columns=["foo", "bar"]),
]
"""
    )


@pytest.mark.parametrize(
    ("down_revision", "expected"),
    [
        pytest.param(
            ["rev_1"],
            '"rev_1"',
            id="single",
        ),
        pytest.param(
            ["rev_1", "rev_666"],
            '("rev_1", "rev_666")',
            id="multiple",
        ),
    ],
)
async def test_write_migration_file_down_revisions(
    tmp_path, freezer, monkeypatch, down_revision, expected
):
    import plastron

    monkeypatch.setattr(plastron, "__version__", "9.9.9")
    freezer.move_to("2025-10-08")

    path = tmp_path / Path("./mig")
    path.mkdir()
    ops = [
        ("DropUniqueTogether", "users", ["foo", "bar"]),
        ("AddIndex", "users", ["foo", "bar"]),
        (
            "DropColumn",
            "users",
            {
                "name": "bio",
                "field": fields.CharField(max_length=256, unique=True),
            },
        ),
    ]
    serializer = Serializer(ops)

    revision = "rev_1"
    down_revision = down_revision
    fname = await serializer.write_migration_file(revision, down_revision, path)

    async with aiofiles.open(path / fname) as f:
        contents = await f.read()

    assert (
        contents
        == f"""# Generated by Plastron 9.9.9 on 2025-10-08T00:00:00+00:00
from tortoise import fields

from plastron import operations as op


revision = "rev_1"
down_revision = {expected}

upgrade_operations = [
    op.DropUniqueTogether("users", columns=["foo", "bar"]),
    op.AddIndex("users", columns=["foo", "bar"]),
    op.DropColumn("users", "bio"),
]

downgrade_operations = [
    op.AddColumn("users", "bio", fields.CharField(max_length=256, unique=True)),
    op.DropIndex("users", columns=["foo", "bar"]),
    op.AddUniqueTogether("users", columns=["foo", "bar"]),
]
"""
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, "_auto.py"),
        ("foo", "_foo.py"),
        ("foo bar baz 123", "_foo_bar_baz_123.py"),
        ("66 22   33", "_66_22_33.py"),
        ("mIgR4Ti0n N4M3", "_migr4ti0n_n4m3.py"),
    ],
)
async def test_write_migration_file_migration_name(tmp_path, name, expected):
    path = tmp_path / Path("./mig")
    path.mkdir()
    serializer = Serializer([])

    revision = "rev_1"
    down_revision = [""]
    fname = await serializer.write_migration_file(
        revision, down_revision, path, migration_name=name
    )
    assert fname.endswith(expected)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, "auto"),
        ("            ", "auto"),  # bunch of empty spaces
        ("foo", "foo"),
        ("foo bar baz 123", "foo_bar_baz_123"),
        ("66 22   33", "66_22_33"),  # removes multiple empty spaces
        ("mIgR4Ti0n N4M3", "migr4ti0n_n4m3"),  # lowercase
        ("mIgR4Ti0n-N4M3", "migr4ti0n-n4m3"),  # allows dashes
    ],
)
def test_clean_migration_name(name, expected):
    serializer = Serializer([])
    mig_name = serializer._clean_migration_name(name)
    assert mig_name == expected


@pytest.mark.parametrize(
    "name",
    ["č", "//", "/", "\\", "%", "$"],
)
def test_clean_migration_name_raises_value_error_for_invalid_characters(name):
    serializer = Serializer([])
    with pytest.raises(ValueError, match="Invalid migration name"):
        serializer._clean_migration_name(name)


def test_create_table_op():
    serializer = Serializer([])
    op = serializer._create_table_op(
        "users",
        {
            "name": "users",
            "fields": [
                ("id", fields.IntField(primary_key=True)),
                ("email", fields.CharField(max_length=256)),
            ],
            "unique_together": ["id", "email"],
            "indexes": [["id"], ["email"]],
        },
    )
    assert op == (
        'op.CreateTable("users", fields=[("id", fields.IntField('
        "unique=True, primary_key=True, db_index=True, generated=True)),"
        '("email", fields.CharField(max_length=256))'
        '], unique_together=["id", "email"])'
    )


def test_add_index_op():
    serializer = Serializer([])
    op = serializer._add_index_op("users", ["foo", "bar"])
    assert op == 'op.AddIndex("users", columns=["foo", "bar"])'


def test_drop_index_op():
    serializer = Serializer([])
    op = serializer._drop_index_op("users", ["foo", "bar"])
    assert op == 'op.DropIndex("users", columns=["foo", "bar"])'


def test_drop_table():
    serializer = Serializer([])
    op = serializer._drop_table_op("users")
    assert op == 'op.DropTable("users")'


def test_add_unique_together_op():
    serializer = Serializer([])
    op = serializer._add_unique_together_op("users", ["foo", "bar"])
    assert op == 'op.AddUniqueTogether("users", columns=["foo", "bar"])'


def test_drop_unique_together_op():
    serializer = Serializer([])
    op = serializer._drop_unique_together_op("users", ["foo", "bar"])
    assert op == 'op.DropUniqueTogether("users", columns=["foo", "bar"])'


def test_add_column_op():
    serializer = Serializer([])
    op = serializer._add_column_op(
        "users",
        {
            "name": "bio",
            "field": fields.CharField(max_length=256, unique=True),
        },
    )
    assert op == (
        'op.AddColumn("users", "bio", fields.CharField(max_length=256, unique=True))'
    )


def test_drop_column_op():
    serializer = Serializer([])
    op = serializer._drop_column_op("users", "bio")
    assert op == 'op.DropColumn("users", "bio")'


def test_alter_column_op():
    serializer = Serializer([])
    op = serializer._alter_column_op(
        "users", "bio", fields.CharField(max_length=256, unique=True)
    )
    assert op == (
        'op.AlterColumn("users", "bio", fields.CharField(max_length=256, unique=True))'
    )


@pytest.mark.parametrize(
    ("field_fn", "extra"),
    [
        pytest.param(
            lambda: fields.IntField(
                unique=True,
                primary_key=True,
                db_index=True,
                default=5,
                source_field="bio",
                generated=True,
            ),
            {},
            id="IntField",
        ),
        pytest.param(
            lambda: fields.CharField(max_length=256, null=False),
            {"max_length": 256},
            id="CharField",
        ),
        pytest.param(
            lambda: fields.DatetimeField(auto_now=True),
            {"auto_now": False, "auto_now_add": False},
            id="DatetimeField",
        ),
        pytest.param(
            lambda: fields.DatetimeField(auto_now_add=True),
            {"auto_now": False, "auto_now_add": False},
            id="DatetimeField-auto_now_add",
        ),
        pytest.param(
            lambda: fields.DateField(unique=True),
            {},
            id="DatetimeField-auto_now_add",
        ),
        pytest.param(
            lambda: fields.DecimalField(max_digits=10, decimal_places=4),
            {"max_digits": 10, "decimal_places": 4},
            id="DatetimeField-auto_now_add",
        ),
    ],
)
def test_construct_base_field(field_fn, extra):
    serializer = Serializer([])
    field = field_fn()
    cls = serializer._construct_base_field(field)

    default_map = {
        "null": False,
        "unique": False,
        "pk": False,  # primary_key
        "index": False,  # db_index
        "default": None,
        "source_field": None,
        "generated": False,
    }

    for k, v in default_map.items():
        assert getattr(cls, k) == v, f"Kwarg {k} has non-default value"

    for k, v in extra.items():
        assert getattr(cls, k) == v, f"Extra kwarg {k} has invalid value"
