import os

TORTOISE_ORM = {
    "connections": {"default": os.getenv("DB_CONN")},
    "apps": {
        "app": {"models": ["models"]},
        "posts": {"models": ["other_models"]},
    },
}

TORTOISE_ORM_DIFFERENT_KEY = {
    "connections": {"default": os.getenv("DB_CONN")},
    "apps": {
        "app": {"models": ["models"]},
        "posts": {"models": ["other_models"]},
    },
}


class SettingsClass:
    TORTOISE_ORM = {
        **TORTOISE_ORM,
    }
