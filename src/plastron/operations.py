import logging

from tortoise import Model

from plastron.ddl.postgres import PostgresDDL

log = logging.getLogger(__name__)


def _remove_field_from_model(model, field_name):
    meta = model._meta
    # This is almost full reverse of what `MetaInfo.add_field` function does
    field = meta.fields_map.pop(field_name, None)
    if not field:
        return  # not present

    meta.fields_db_projection.pop(field_name, None)

    meta.m2m_fields.discard(field_name)
    meta.backward_o2o_fields.discard(field_name)
    meta.backward_fk_fields.discard(field_name)


class Operation:
    def __init__(self):
        # TODO: determine DDL from the connection somehow
        self.ddl = PostgresDDL()

    def update_model_structure(self, models):
        raise NotImplementedError()

    def sql(self, models):
        raise NotImplementedError()


class CreateTable(Operation):
    def __init__(self, name, fields, unique_together=None):
        super().__init__()
        self.name = name
        self.fields = fields
        self.unique_together = unique_together or []

    def _create_model(self):
        attrs = dict(self.fields)

        # Meta with db table name
        class Meta:
            table = self.name
            unique_together = self.unique_together

        attrs["Meta"] = Meta

        model = type(self.name, (Model,), attrs)
        return model

    def update_model_structure(self, models):
        model = self._create_model()
        models[self.name] = model

    def sql(self, models):
        model = self._create_model()
        return self.ddl.create_table(model)


class DropTable(Operation):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def update_model_structure(self, models):
        del models[self.name]

    def sql(self, models):
        return self.ddl.drop_table(self.name)


# TODO: test concurrently
class AddIndex(Operation):
    def __init__(self, table, columns, concurrently=False):
        super().__init__()
        self.table = table
        self.columns = columns
        self.concurrently = concurrently

    def update_model_structure(self, models):
        model = models[self.table]
        if not model._meta.indexes:
            model._meta.indexes = []
        model._meta.indexes.append(self.columns)

    def sql(self, models):
        return self.ddl.add_index(
            self.table, self.columns, concurrently=self.concurrently
        )


# TODO: tests concurrently
class DropIndex(Operation):
    def __init__(self, table, columns, concurrently=False):
        super().__init__()
        self.table = table
        self.columns = columns
        self.concurrently = concurrently

    def update_model_structure(self, models):
        model = models[self.table]
        model._meta.indexes.remove(self.columns)

    def sql(self, models):
        return self.ddl.drop_index(
            self.table, self.columns, concurrently=self.concurrently
        )


class AddUniqueTogether(Operation):
    def __init__(self, table, columns):
        super().__init__()
        self.table = table
        self.columns = columns

    def update_model_structure(self, models):
        model = models[self.table]
        if not model._meta.unique_together:
            model._meta.unique_together = []
        model._meta.unique_together.append(self.columns)

    def sql(self, models):
        return self.ddl.add_unique_constraint(self.table, self.columns)


class DropUniqueTogether(Operation):
    def __init__(self, table, columns):
        super().__init__()
        self.table = table
        self.columns = columns

    def update_model_structure(self, models):
        model = models[self.table]
        model._meta.unique_together.remove(self.columns)

    def sql(self, models):
        return self.ddl.drop_unique_constraint(self.table, self.columns)


class AddColumn(Operation):
    def __init__(self, table, column_name, field):
        super().__init__()
        self.table = table
        self.column_name = column_name
        self.field = field

    def update_model_structure(self, models):
        model = models[self.table]
        model._meta.add_field(self.column_name, self.field)

    def sql(self, models):
        return self.ddl.add_column(self.table, self.column_name, self.field)


class DropColumn(Operation):
    def __init__(self, table, column_name):
        super().__init__()
        self.table = table
        self.column_name = column_name

    def update_model_structure(self, models):
        _remove_field_from_model(models[self.table], self.column_name)

    def sql(self, models):
        return self.ddl.drop_column(self.table, self.column_name)


class AlterColumn(Operation):
    def __init__(self, table, column_name, field):
        super().__init__()
        self.table = table
        self.column_name = column_name
        self.field = field

    def update_model_structure(self, models):
        model = models[self.table]
        _remove_field_from_model(model, self.column_name)
        model._meta.add_field(self.column_name, self.field)

    def sql(self, models):
        return self.ddl.alter_column(
            self.table, self.column_name, models[self.table], self.field
        )
