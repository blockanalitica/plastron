import pytest
from tortoise import Model, fields

from plastron.operations import (
    AddColumn,
    AddIndex,
    AddUniqueTogether,
    AlterColumn,
    CreateTable,
    DropColumn,
    DropIndex,
    DropTable,
    DropUniqueTogether,
)


def test_create_table_create_model():
    op = CreateTable(
        "users",
        fields=[
            (
                "id",
                fields.IntField(
                    null=False,
                    unique=True,
                    primary_key=True,
                    db_index=True,
                    generated=True,
                ),
            ),
            (
                "email",
                fields.CharField(
                    max_length=256,
                    null=False,
                    unique=False,
                    primary_key=False,
                    db_index=False,
                    generated=False,
                ),
            ),
        ],
        unique_together=["id", "email"],
    )

    model = op._create_model()
    info = model.describe(serializable=True)
    assert info == {
        "name": "None.users",
        "app": None,
        "table": "users",
        "abstract": False,
        "description": None,
        "docstring": None,
        "unique_together": (["id", "email"],),
        "indexes": [],
        "pk_field": {
            "name": "id",
            "field_type": "IntField",
            "db_column": "id",
            "python_type": "int",
            "generated": True,
            "nullable": False,
            "unique": True,
            "indexed": True,
            "default": None,
            "description": None,
            "docstring": None,
            "constraints": {"ge": -2147483648, "le": 2147483647},
            "db_field_types": {"": "INT"},
        },
        "data_fields": [
            {
                "name": "email",
                "field_type": "CharField",
                "db_column": "email",
                "python_type": "str",
                "generated": False,
                "nullable": False,
                "unique": False,
                "indexed": False,
                "default": None,
                "description": None,
                "docstring": None,
                "constraints": {"max_length": 256},
                "db_field_types": {"": "VARCHAR(256)", "oracle": "NVARCHAR2(256)"},
            }
        ],
        "fk_fields": [],
        "backward_fk_fields": [],
        "o2o_fields": [],
        "backward_o2o_fields": [],
        "m2m_fields": [],
    }


def test_create_table_update_model_structure():
    op = CreateTable(
        "users",
        fields=[
            (
                "id",
                fields.IntField(
                    null=False,
                    unique=True,
                    primary_key=True,
                    db_index=True,
                    generated=True,
                ),
            ),
            (
                "email",
                fields.CharField(
                    max_length=256,
                    null=False,
                    unique=False,
                    primary_key=False,
                    db_index=False,
                    generated=False,
                ),
            ),
        ],
        unique_together=["id", "email"],
    )

    models = {}
    op.update_model_structure(models)

    assert len(models) == 1
    assert "users" in models
    assert models["users"].__name__ == "users"


def test_create_table_sql():
    op = CreateTable(
        "users",
        fields=[
            (
                "id",
                fields.IntField(
                    null=False,
                    unique=True,
                    primary_key=True,
                    db_index=True,
                    generated=True,
                ),
            ),
            (
                "email",
                fields.CharField(
                    max_length=256,
                    null=False,
                    unique=False,
                    primary_key=False,
                    db_index=False,
                    generated=False,
                ),
            ),
        ],
        unique_together=["id", "email"],
    )
    models = {}
    sql = op.sql(models)
    assert (
        sql
        == """CREATE TABLE IF NOT EXISTS "users" (
"id" SERIAL NOT NULL PRIMARY KEY,
"email" VARCHAR(256) NOT NULL,
CONSTRAINT "uniq_users_id_emai_ab91a5" UNIQUE ("id", "email"));"""
    )


@pytest.mark.parametrize(
    ("starting", "columns", "expected"),
    [
        (None, ("email",), [("email",)]),
        ([], ("email", "phone"), [("email", "phone")]),
        ([("a",)], ("b",), [("a",), ("b",)]),
        ([("a",)], ["x", "y"], [("a",), ["x", "y"]]),  # preserves input type as-is
    ],
)
def test_add_index_update_model_structure(starting, columns, expected):
    op = AddIndex("users", columns=columns)

    class DummyModel(Model):
        class Meta:
            indexes = starting

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert models["users"]._meta.indexes == expected


def test_add_index_sql():
    op = AddIndex("users", columns=["email"])
    sql = op.sql({})
    assert (
        sql
        == 'CREATE INDEX IF NOT EXISTS "idx_users_email_133a6f" ON "users" ("email");'
    )


@pytest.mark.parametrize(
    ("starting", "columns", "expected"),
    [
        ([("email", "phone")], ("email", "phone"), []),
        ([("a",), ("b",)], ("b",), [("a",)]),
    ],
)
def test_drop_index_update_model_structure(starting, columns, expected):
    op = DropIndex("users", columns=columns)

    class DummyModel(Model):
        class Meta:
            indexes = starting

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert models["users"]._meta.indexes == expected


def test_drop_index_sql():
    op = DropIndex("users", columns=["email"])
    sql = op.sql({})
    assert sql == 'DROP INDEX IF EXISTS "idx_users_email_133a6f";'


@pytest.mark.parametrize(
    ("starting", "columns", "expected"),
    [
        (None, ("email",), [("email",)]),
        ([], ("email", "phone"), [("email", "phone")]),
        ([("a",)], ("b",), [("a",), ("b",)]),
        ([("a",)], ["x", "y"], [("a",), ["x", "y"]]),  # preserves input type as-is
    ],
)
def test_add_unique_together_update_model_structure(starting, columns, expected):
    op = AddUniqueTogether("users", columns=columns)

    class DummyModel(Model):
        class Meta:
            unique_together = starting

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert models["users"]._meta.unique_together == expected


def test_add_unique_together_sql():
    op = AddUniqueTogether("users", columns=["email"])
    sql = op.sql({})
    assert (
        sql == 'ALTER TABLE "users" ADD CONSTRAINT "uniq_users_email_133a6f" UNIQUE '
        '("email");'
    )


@pytest.mark.parametrize(
    ("starting", "columns", "expected"),
    [
        ([("email", "phone")], ("email", "phone"), []),
        ([("a",), ("b",)], ("b",), [("a",)]),
    ],
)
def test_drop_unique_together_update_model_structure(starting, columns, expected):
    op = DropUniqueTogether("users", columns=columns)

    class DummyModel(Model):
        class Meta:
            unique_together = starting

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert models["users"]._meta.unique_together == expected


def test_drop_unique_together_sql():
    op = DropUniqueTogether("users", columns=["email"])
    sql = op.sql({})
    assert sql == 'ALTER TABLE "users" DROP CONSTRAINT "uniq_users_email_133a6f";'


def test_add_column_update_model_structure():
    field = fields.CharField(max_length=256)
    op = AddColumn("users", "bio", field)

    class DummyModel(Model):
        pass

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert models["users"]._meta.fields_map["bio"] == field


def test_add_column_unique_together_sql():
    op = AddColumn("users", "bio", fields.CharField(max_length=256))
    sql = op.sql({})
    assert sql == 'ALTER TABLE "users" ADD COLUMN "bio" VARCHAR(256) NOT NULL;'


def test_drop_column_update_model_structure():
    op = DropColumn("users", "bio")

    class DummyModel(Model):
        bio = fields.CharField(max_length=256)

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert "bio" not in models["users"]._meta.fields_map
    assert "bio" not in models["users"]._meta.fields_db_projection


def test_drop_column_unique_together_sql():
    op = DropColumn("users", "bio")
    sql = op.sql({})
    assert sql == 'ALTER TABLE "users" DROP COLUMN "bio";'


def test_alter_column_update_model_structure():
    field = fields.CharField(max_length=256)
    op = AlterColumn("users", "bio", field)

    class DummyModel(Model):
        bio = fields.IntField()

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert models["users"]._meta.fields_map["bio"] == field


def test_alter_column_unique_together_sql():
    field = fields.CharField(max_length=256)
    op = AlterColumn("users", "bio", field)

    class DummyModel(Model):
        bio = fields.IntField()

    models = {"users": DummyModel()}
    sql = op.sql(models)
    assert (
        sql == 'ALTER TABLE "users" ALTER COLUMN "bio" TYPE VARCHAR(256) '
        'USING "bio"::VARCHAR(256);'
    )


def test_drop_table_sql():
    op = DropTable("users")
    sql = op.sql({})
    assert sql == 'DROP TABLE IF EXISTS "users" CASCADE;'


def test_drop_table_update_model_structure():
    op = DropTable("users")

    class DummyModel(Model):
        pass

    models = {"users": DummyModel()}
    op.update_model_structure(models)
    assert "users" not in models
