import os

TORTOISE_ORM = {
    "connections": {"default": os.getenv("DB_CONN")},
    "apps": {
        "app": {"models": ["models"], "default_connection": "default"},
        "posts": {"models": ["other_models"], "default_connection": "default"},
    },
}
