from tortoise import Model, fields


class User(Model):
    email = fields.CharField(max_length=256, unique=True, null=False, db_index=True)
    age = fields.IntField()
    revenue = fields.DecimalField(max_digits=6, decimal_places=4, null=True)
    created_at = fields.DatetimeField(auto_now=True)


class Profile(Model):
    profile_id = fields.IntField(primary_key=True)
    # user = fields.OneToOneField(
    #     "app.User", related_name="profile", on_delete=fields.CASCADE
    # )
    full_name = fields.CharField(max_length=256, null=True, db_index=True)
    city = fields.CharField(max_length=256)
    password = fields.CharField(max_length=100)

    class Meta:
        unique_together = ["full_name", "city"]
        indexes = [["city"], ["full_name", "city"]]
