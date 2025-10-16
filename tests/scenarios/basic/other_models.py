from tortoise import Model, fields


class Post(Model):
    # author = fields.ForeignKeyField(
    #     "app.User",
    #     related_name="posts",
    #     on_delete=fields.CASCADE,
    # )
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    # tags = fields.ManyToManyField("posts.Tag", related_name="posts")


# class Tag(Model):
#     name = fields.CharField(max_length=50, unique=True)
