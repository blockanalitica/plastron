from tortoise import Model, fields


class Plastron(Model):
    revision = fields.CharField(max_length=255, unique=True)
    applied_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"<{self.__class__.__name__} revision: {self.revision}>"
