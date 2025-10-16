from typing import TYPE_CHECKING

from tortoise.converters import encoders
from tortoise.fields import JSONField, TextField, UUIDField

from plastron.utils import generate_hash

if TYPE_CHECKING:
    pass


class PostgresDDL:
    dialect = "postgres"

    CREATE_TABLE = (
        'CREATE TABLE IF NOT EXISTS "{table_name}" (\n{columns}{constraints});'
    )
    DROP_TABLE = 'DROP TABLE IF EXISTS "{table_name}" CASCADE;'
    ADD_INDEX = (
        'CREATE INDEX{concurrently} IF NOT EXISTS "{index_name}" '
        'ON "{table_name}" {index_type}({column_names});'
    )
    DROP_INDEX = 'DROP INDEX{concurrently} IF EXISTS "{index_name}";'
    UNIQUE_CONSTRAINT_CREATE = 'CONSTRAINT "{index_name}" UNIQUE ({column_names})'
    ADD_UNIQUE_CONSTRAINT = (
        'ALTER TABLE "{table_name}" '
        'ADD CONSTRAINT "{constraint_name}" UNIQUE ({column_names});'
    )
    DROP_CONSTRAINT = 'ALTER TABLE "{table_name}" DROP CONSTRAINT "{constraint_name}";'

    ADD_COLUMN = 'ALTER TABLE "{table_name}" ADD COLUMN {column};'
    DROP_COLUMN = 'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}";'
    ALTER_COLUMN_TYPE = (
        'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
        "TYPE {datatype}{using};"
    )
    ALTER_COLUMN_NULL = (
        'ALTER TABLE "{table_name}" '
        'ALTER COLUMN "{column_name}" {set_drop_cmd} NOT NULL;'
    )
    ALTER_COLUMN_DEFAULT = (
        'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" {default_cmd};'
    )

    GENERATED_PK = '"{name}" {generated_sql}'
    COLUMN = '"{name}" {type}{nullable}{unique}{primary}{default}'

    def _get_index_name(self, prefix, table, columns):
        # NOTE: for compatibility, index name should not be longer than 30
        # characters (Oracle limit).
        if len(prefix) > 4:
            raise ValueError("prefix can't contain more than 4 characters")

        table_part = table[:10]
        columns_part = "_".join(columns)[:7]
        hashed = generate_hash(table, *columns, length=6)
        return f"{prefix}_{table_part}_{columns_part}_{hashed}".lower()

    def quote(self, value):
        return f'"{value}"'

    def _column_default_generator(self, default, auto_now_add=False, auto_now=False):
        return "DEFAULT {}".format("CURRENT_TIMESTAMP" if auto_now_add else default)

    def _get_field_default(self, field, table_name, model):
        auto_now_add = getattr(field, "auto_now_add", False)
        auto_now = getattr(field, "auto_now", False)

        is_valid_default = field.default is not None and not callable(field.default)
        is_valid_field_type = not isinstance(field, (UUIDField, TextField, JSONField))

        if (is_valid_default or auto_now or auto_now_add) and is_valid_field_type:
            default = field.to_db_value(field.default, model)
            if isinstance(default, bool):
                default = str(default).upper()
            else:
                default = encoders.get(type(default))(default)

            return self._column_default_generator(default, auto_now_add, auto_now)

        return ""

    def _get_field_sql(self, field, table_name, field_name, default):
        # if it's generated primary key, use a different template
        if field.pk and field.generated:
            return self.GENERATED_PK.format(
                name=field_name,
                generated_sql=field.get_for_dialect(self.dialect, "GENERATED_SQL"),
            )

        field_type = field.get_for_dialect(self.dialect, "SQL_TYPE")

        # TODO: Foreign keys and m2m keys don't work yet
        # if getattr(field, "reference", None):
        #     reference =field.reference

        #     to_field_name = reference.to_field_instance.source_field
        #     if not to_field_name:
        #         to_field_name = reference.to_field_instance.model_field_name

        #     related_table_name = reference.related_model._meta.db_table
        #     print(reference.db_constraint)
        #     if reference.db_constraint:
        #         field_creation_string = self._create_string(
        #             db_column=column_name,
        #             field_type=field_type,
        #             nullable=nullable,
        #             unique=unique,
        #             is_primary_key=field.pk,
        #             comment="",
        #             default=default,
        #         ) + self._create_fk_string(
        #             constraint_name=self._get_fk_name(
        #                 table_name,
        #                 column_name,
        #                 related_table_name,
        #                 to_field_name,
        #             ),
        #             db_column=column_name,
        #             table=related_table_name,
        #             field=to_field_name,
        #             on_delete=reference.on_delete,
        #             # comment=comment,
        #         )

        return self.COLUMN.format(
            name=field_name,
            type=field_type,
            nullable=" NOT NULL" if not field.null else "",
            unique=" UNIQUE" if field.unique and not field.pk else "",
            primary=" PRIMARY KEY" if field.pk else "",
            default=f" {default}" if default else "",
        )

    def create_table(self, model):
        columns = []
        constraints = []

        table_name = model._meta.db_table
        for field_name, field in model._meta.fields_map.items():
            default = self._get_field_default(field, table_name, model)
            columns.append(self._get_field_sql(field, table_name, field_name, default))

        if model._meta.unique_together:
            for ut in model._meta.unique_together:
                constraints.append(
                    self.UNIQUE_CONSTRAINT_CREATE.format(
                        index_name=self._get_index_name("uniq", table_name, ut),
                        column_names=", ".join([self.quote(f) for f in ut]),
                    )
                )

        return self.CREATE_TABLE.format(
            table_name=table_name,
            columns=",\n".join(columns),
            constraints=",\n{}".format(",\n".join(constraints)) if constraints else "",
        )

    def drop_table(self, table_name):
        return self.DROP_TABLE.format(table_name=table_name)

    # TODO: test concurrently
    def add_index(self, table, columns, index_type=None, concurrently=False):
        return self.ADD_INDEX.format(
            index_type=f"USING {index_type} " if index_type else "",
            concurrently=" CONCURRENTLY" if concurrently else "",
            index_name=self._get_index_name("idx", table, columns),
            table_name=table,
            column_names=", ".join([self.quote(c) for c in columns]),
        )

    # TODO: test concurrently
    def drop_index(self, table, columns, concurrently=False):
        return self.DROP_INDEX.format(
            index_name=self._get_index_name("idx", table, columns),
            concurrently=" CONCURRENTLY" if concurrently else "",
        )

    def add_unique_constraint(self, table, columns):
        return self.ADD_UNIQUE_CONSTRAINT.format(
            table_name=table,
            constraint_name=self._get_index_name("uniq", table, columns),
            column_names=", ".join([self.quote(c) for c in columns]),
        )

    def drop_unique_constraint(self, table, columns):
        return self.DROP_CONSTRAINT.format(
            table_name=table,
            constraint_name=self._get_index_name("uniq", table, columns),
        )

    def add_column(self, table, column_name, field):
        default = self._get_field_default(field, table, None)
        column = self._get_field_sql(field, table, column_name, default)
        return self.ADD_COLUMN.format(table_name=table, column=column)

    def drop_column(self, table, column_name):
        return self.DROP_COLUMN.format(table_name=table, column_name=column_name)

    def alter_column(self, table, column_name, model, new_field):
        old_field = model._meta.fields_map[column_name]
        sqls = []

        # Index
        if old_field.index != new_field.index:
            if new_field.index:
                sqls.append(self.add_index(table, [column_name]))
            else:
                sqls.append(self.drop_index(table, [column_name]))

        # Unique
        if old_field.unique != new_field.unique:
            if new_field.unique:
                sqls.append(self.add_unique_constraint(table, [column_name]))
            else:
                sqls.append(self.drop_unique_constraint(table, [column_name]))

        # Null
        if old_field.null != new_field.null:
            sqls.append(
                self.ALTER_COLUMN_NULL.format(
                    table_name=table,
                    column_name=column_name,
                    set_drop_cmd="SET" if new_field.null else "DROP",
                )
            )

        # Default (incl. auto_now and auto_now_add)
        new_default = self._get_field_default(new_field, table, model)
        old_default = self._get_field_default(old_field, table, model)
        if old_default != new_default:
            default_cmd = (
                f"SET {new_default}" if new_default is not None else "DROP DEFAULT"
            )
            sqls.append(
                self.ALTER_COLUMN_DEFAULT.format(
                    table_name=table, column_name=column_name, default_cmd=default_cmd
                )
            )

        # Field type
        if old_field.__class__.__name__ != new_field.__class__.__name__:
            db_field_types = new_field.get_db_field_types()
            datatype = db_field_types.get(self.dialect) or db_field_types.get("")
            sqls.append(
                self.ALTER_COLUMN_TYPE.format(
                    table_name=table,
                    column_name=column_name,
                    datatype=datatype,
                    using=f' USING "{column_name}"::{datatype}',
                )
            )
        return "\n".join(sqls)
