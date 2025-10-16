import pytest
from tortoise import Model, fields

from plastron.ddl.postgres import PostgresDDL


@pytest.mark.parametrize(
    ("prefix", "table", "columns", "expected"),
    [
        ("idx", "users", ["bar", "baz"], "idx_users_bar_baz_b93269"),
        (
            "uniq",
            "usersarelongerthanthis",
            ["bar", "baz"],
            "uniq_usersarelo_bar_baz_53db2c",
        ),
        ("uniq", "users", ["barlongbongdingdong", "baz"], "uniq_users_barlong_4bcc01"),
        (
            "uniq",
            "usersarelongerthanthis",
            ["barlongbongdingdong", "baz"],
            "uniq_usersarelo_barlong_29e9c1",
        ),
        (
            "IDX",
            "uSeRs",
            ["bAr", "bAz"],
            "idx_users_bar_baz_80698b",
        ),  # returns lowercase
    ],
)
def test_get_index_name(prefix, table, columns, expected):
    ddl = PostgresDDL()
    idx_name = ddl._get_index_name(prefix, table, columns)
    assert idx_name == expected
    assert len(idx_name) <= 30


def test_get_index_name_raises_for_long_prefix():
    ddl = PostgresDDL()
    with pytest.raises(ValueError, match="contain more than 4 characters"):
        ddl._get_index_name("thisiswaylonger", "a", ["b"])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a", '"a"'),
        (5, '"5"'),
        (False, '"False"'),
    ],
)
def test_quote(value, expected):
    ddl = PostgresDDL()
    quoted_value = ddl.quote(value)
    assert quoted_value == expected


@pytest.mark.parametrize(
    ("default", "auto_now_add", "auto_now", "expected"),
    [
        ("a", False, False, "DEFAULT a"),
        ("a", True, False, "DEFAULT CURRENT_TIMESTAMP"),
        ("a", False, True, "DEFAULT a"),
        ("a", True, True, "DEFAULT CURRENT_TIMESTAMP"),
    ],
)
def test_column_default_generator(default, auto_now_add, auto_now, expected):
    ddl = PostgresDDL()
    sql = ddl._column_default_generator(default, auto_now_add, auto_now)
    assert sql == expected


@pytest.mark.parametrize(
    ("field_fn", "expected"),
    [
        (lambda: fields.CharField(max_length=256, default="abc"), "DEFAULT 'abc'"),
        (lambda: fields.BooleanField(default=True), "DEFAULT TRUE"),
        (lambda: fields.IntField(default=555), "DEFAULT 555"),
        (lambda: fields.IntField(default=lambda: 5), ""),
        (lambda: fields.UUIDField(default="abc"), ""),  # Not supported
        (lambda: fields.TextField(default="abc"), ""),  # Not supported
        (lambda: fields.JSONField(default="abc"), ""),  # Not supported
        (lambda: fields.IntField(), ""),
    ],
)
def test_get_field_default(field_fn, expected):
    ddl = PostgresDDL()

    class Dummy(Model):
        pass

    default = ddl._get_field_default(field_fn(), "dummy", Dummy())
    assert default == expected


@pytest.mark.parametrize(
    ("field_kw", "expected"),
    [
        ({"auto_now": True}, "DEFAULT CURRENT_TIMESTAMP"),
        ({"auto_now_add": True}, "DEFAULT CURRENT_TIMESTAMP"),
    ],
)
def test_get_field_default_auto_now(field_kw, expected):
    ddl = PostgresDDL()

    class Dummy(Model):
        dt = fields.DatetimeField(**field_kw)

    model = Dummy()
    default = ddl._get_field_default(model._meta.fields_map["dt"], "dummy", model)
    assert default == expected


@pytest.mark.parametrize(
    ("field_fn", "expected"),
    [
        (lambda: fields.IntField(), '"foo" INT NOT NULL'),
        (lambda: fields.IntField(null=True), '"foo" INT'),
        (lambda: fields.IntField(unique=True), '"foo" INT NOT NULL UNIQUE'),
        (lambda: fields.IntField(null=True, unique=True), '"foo" INT UNIQUE'),
        (
            lambda: fields.IntField(primary_key=True),
            '"foo" SERIAL NOT NULL PRIMARY KEY',
        ),
        (
            lambda: fields.IntField(primary_key=True, unique=True),
            '"foo" SERIAL NOT NULL PRIMARY KEY',
        ),
        (
            lambda: fields.IntField(default=5),
            # This is not a valid sql as it doesn't go through `_get_field_default` but
            # for testing the functionality of _get_field_sql is enough to test that
            # default is set
            '"foo" INT NOT NULL 5',
        ),
        (
            lambda: fields.IntField(primary_key=True, generated=True),
            '"foo" SERIAL NOT NULL PRIMARY KEY',
        ),
        (
            lambda: fields.IntField(primary_key=True, generated=False),
            '"foo" INT NOT NULL PRIMARY KEY',
        ),
    ],
)
def test_get_field_sql(field_fn, expected):
    ddl = PostgresDDL()
    field = field_fn()
    sql = ddl._get_field_sql(field, "dummy", "foo", field.default)
    assert sql == expected


def test_create_table():
    ddl = PostgresDDL()

    class Dummy(Model):
        foo = fields.IntField()

        class Meta:
            table = "dummy"

    model = Dummy()
    sql = ddl.create_table(model)
    assert (
        sql
        == """CREATE TABLE IF NOT EXISTS "dummy" (
"id" SERIAL NOT NULL PRIMARY KEY,
"foo" INT NOT NULL);"""
    )


def test_create_table_with_constraints():
    ddl = PostgresDDL()

    class Dummy(Model):
        foo = fields.IntField()

        class Meta:
            table = "dummy"
            unique_together = ["id", "foo"]

    model = Dummy()
    sql = ddl.create_table(model)
    assert (
        sql
        == """CREATE TABLE IF NOT EXISTS "dummy" (
"id" SERIAL NOT NULL PRIMARY KEY,
"foo" INT NOT NULL,
CONSTRAINT "uniq_dummy_id_foo_bcf821" UNIQUE ("id", "foo"));"""
    )


@pytest.mark.parametrize(
    ("columns", "index_type", "expected"),
    [
        (
            ["foo"],
            None,
            'CREATE INDEX IF NOT EXISTS "idx_dummy_foo_ef06c5" ON "dummy" ("foo");',
        ),
        (
            ["foo", "bar"],
            None,
            'CREATE INDEX IF NOT EXISTS "idx_dummy_foo_bar_7e187e" '
            'ON "dummy" ("foo", "bar");',
        ),
        (
            ["foo"],
            "btree",
            'CREATE INDEX IF NOT EXISTS "idx_dummy_foo_ef06c5" '
            'ON "dummy" USING btree ("foo");',
        ),
    ],
)
def test_add_index(columns, index_type, expected):
    ddl = PostgresDDL()
    sql = ddl.add_index("dummy", columns, index_type)
    assert sql == expected


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        (["foo"], 'DROP INDEX IF EXISTS "idx_dummy_foo_ef06c5";'),
        (["foo", "bar"], 'DROP INDEX IF EXISTS "idx_dummy_foo_bar_7e187e";'),
    ],
)
def test_drop_index(columns, expected):
    ddl = PostgresDDL()
    sql = ddl.drop_index("dummy", columns)
    assert sql == expected


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        (
            ["foo"],
            'ALTER TABLE "dummy" ADD CONSTRAINT "uniq_dummy_foo_ef06c5" '
            'UNIQUE ("foo");',
        ),
        (
            ["foo", "bar"],
            'ALTER TABLE "dummy" ADD CONSTRAINT "uniq_dummy_foo_bar_7e187e" '
            'UNIQUE ("foo", "bar");',
        ),
    ],
)
def test_add_unique_constraint(columns, expected):
    ddl = PostgresDDL()
    sql = ddl.add_unique_constraint("dummy", columns)
    assert sql == expected


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        (["foo"], 'ALTER TABLE "dummy" DROP CONSTRAINT "uniq_dummy_foo_ef06c5";'),
        (
            ["foo", "bar"],
            'ALTER TABLE "dummy" DROP CONSTRAINT "uniq_dummy_foo_bar_7e187e";',
        ),
    ],
)
def test_drop_unique_constraint(columns, expected):
    ddl = PostgresDDL()
    sql = ddl.drop_unique_constraint("dummy", columns)
    assert sql == expected


def test_add_column():
    ddl = PostgresDDL()
    sql = ddl.add_column("dummy", "foo", fields.IntField())
    assert sql == 'ALTER TABLE "dummy" ADD COLUMN "foo" INT NOT NULL;'


def test_drop_column():
    ddl = PostgresDDL()
    sql = ddl.drop_column("dummy", "foo")
    assert sql == 'ALTER TABLE "dummy" DROP COLUMN "foo";'


@pytest.mark.parametrize(
    ("old_kw", "new_kw", "expected"),
    [
        pytest.param(
            {"db_index": False},
            {"db_index": True},
            'CREATE INDEX IF NOT EXISTS "idx_dummy_foo_ef06c5" ON "dummy" ("foo");',
            id="add_index",
        ),
        pytest.param(
            {"db_index": True},
            {"db_index": False},
            'DROP INDEX IF EXISTS "idx_dummy_foo_ef06c5";',
            id="drop_index",
        ),
        pytest.param(
            {"unique": False},
            {"unique": True},
            'ALTER TABLE "dummy" ADD CONSTRAINT "uniq_dummy_foo_ef06c5" '
            'UNIQUE ("foo");',
            id="add_constraint",
        ),
        pytest.param(
            {"unique": True},
            {"unique": False},
            'ALTER TABLE "dummy" DROP CONSTRAINT "uniq_dummy_foo_ef06c5";',
            id="drop_constraint",
        ),
        pytest.param(
            {"null": False},
            {"null": True},
            'ALTER TABLE "dummy" ALTER COLUMN "foo" SET NOT NULL;',
            id="add_null",
        ),
        pytest.param(
            {"null": True},
            {"null": False},
            'ALTER TABLE "dummy" ALTER COLUMN "foo" DROP NOT NULL;',
            id="drop_null",
        ),
        pytest.param(
            {"null": False, "unique": False, "db_index": False},
            {"null": True, "unique": True, "db_index": True},
            """CREATE INDEX IF NOT EXISTS "idx_dummy_foo_ef06c5" ON "dummy" ("foo");
ALTER TABLE "dummy" ADD CONSTRAINT "uniq_dummy_foo_ef06c5" UNIQUE ("foo");
ALTER TABLE "dummy" ALTER COLUMN "foo" SET NOT NULL;""",
            id="multiple_things",
        ),
    ],
)
def test_alter_column(old_kw, new_kw, expected):
    ddl = PostgresDDL()

    class Dummy(Model):
        foo = fields.IntField(**old_kw)

        class Meta:
            table = "dummy"

    model = Dummy()
    sql = ddl.alter_column("dummy", "foo", model, fields.IntField(**new_kw))
    assert sql == expected


@pytest.mark.parametrize(
    ("old_kw", "new_kw", "expected"),
    [
        pytest.param(
            {"auto_now": False},
            {"auto_now": True},
            'ALTER TABLE "dummy" ALTER COLUMN "foo" SET DEFAULT CURRENT_TIMESTAMP;',
            id="auto_now-true",
        ),
        pytest.param(
            {"auto_now_add": False},
            {"auto_now_add": True},
            'ALTER TABLE "dummy" ALTER COLUMN "foo" SET DEFAULT CURRENT_TIMESTAMP;',
            id="auto_now_add-true",
        ),
        pytest.param(
            {"auto_now": True},
            {"auto_now_add": True},
            "",  # postgres doesn't distinguish beteween the two, so its noop
            id="auto_now-to-auto_now_add",
        ),
        pytest.param(
            {"auto_now_add": True},
            {"auto_now": True},
            "",  # postgres doesn't distinguish beteween the two, so its noop
            id="auto_now_add-to-auto_now",
        ),
    ],
)
async def test_alter_column_auto_now(old_kw, new_kw, expected):
    ddl = PostgresDDL()

    class Dummy(Model):
        foo = fields.DatetimeField(**old_kw)

        class Meta:
            table = "dummy"

    model = Dummy()

    field = fields.DatetimeField(**new_kw)
    # Hack because tortoise is not initialized
    field.model_field_name = "foo"

    sql = ddl.alter_column("dummy", "foo", model, field)
    assert sql == expected


def test_alter_column_field_type():
    ddl = PostgresDDL()

    class Dummy(Model):
        foo = fields.IntField()

        class Meta:
            table = "dummy"

    model = Dummy()
    sql = ddl.alter_column("dummy", "foo", model, fields.CharField(max_length=255))
    assert (
        sql == 'ALTER TABLE "dummy" ALTER COLUMN "foo" TYPE VARCHAR(255) '
        'USING "foo"::VARCHAR(255);'
    )


def test_drop_table():
    ddl = PostgresDDL()
    sql = ddl.drop_table("dummy")
    assert sql == 'DROP TABLE IF EXISTS "dummy" CASCADE;'
