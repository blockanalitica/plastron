import os

TORTOISE_ORM = {
    "connections": {"default": os.getenv("DB_CONN")},
    "apps": {
        "app": {"models": ["models"]},
        "posts": {"models": ["other_models"]},
    },
}
