# 🐢 Plastron

[![PyPI version](https://img.shields.io/pypi/v/tortoise-plastron.svg?style=flat&color=blue)](https://pypi.org/project/tortoise-plastron/)
[![Python versions](https://img.shields.io/pypi/pyversions/tortoise-plastron.svg?style=flat)](https://pypi.org/project/tortoise-plastron/)
[![License](https://img.shields.io/github/license/blockanalitica/plastron.svg?style=flat)](./LICENSE)
[![Build](https://github.com/blockanalitica/plastron/actions/workflows/tests.yml/badge.svg)](https://github.com/blockanalitica/plastron/actions)

> A lightweight migration tool for [Tortoise ORM](https://tortoise.github.io/), inspired by Alembic and Django migrations.
>
> [Plastron (Wikipedia)](https://en.wikipedia.org/wiki/Turtle_shell#Plastron)

## 🚀 Introduction

**Plastron** is a lightweight database migration tool designed specifically for **TortoiseORM**. It aims to bring the familiarity of Alembic-style (or Django-style) migrations to the Tortoise ecosystem — clean, simple, and minimal.

---

## 📦 Installation

Install directly from PyPI:

```bash
pip install tortoise-plastron
```

---

## ⚙️ Configuration

Plastron can be configured thorugh `pyproject.toml`:

```toml
[tool.plastron]
tortoise_orm = "my_project.settings.TORTOISE_ORM"
location = "./src/migrations"
base_dir = "./src"
```

### Options

| Key            | Description                                                                                   |
| -------------- | --------------------------------------------------------------------------------------------- |
| `tortoise_orm` | Path to your Tortoise ORM config dict. Required to locate models and connect to the database. |
| `location`     | Directory where migration files are stored.                                                   |
| `base_dir`     | (Optional) Added to `sys.path` for module resolution (useful with `src/` layout).             |

---

## ⚡️ Quickstart

Once you’ve defined your Tortoise ORM models, you can start managing migrations.

### 🧱 Create a new migration

After modifying your models, run:

```bash
plastron makemigrations
```

This will automatically detect changes and create a new migration file, for example: `01k7rd69n7fp_auto.py`

You can also provide a custom name for better readability:

```bash
plastron makemigrations --name "add_user_table"
```

This will create something like: `01k7rd69n7fp_add_user_table.py`

---

### ⬆️ Apply migrations

To apply all unapplied migrations:

```bash
plastron upgrade
```

This runs each migration sequentially in order.

If you want to upgrade to a **specific revision**:

```bash
# TODO
```

---

### ⬇️ Downgrade (rollback)

To revert your database to the **previous revision**:

```bash
plastron downgrade
```

By default, this downgrades **just the last applied migration**.

If you want to downgrade to a **specific revision**:

```bash
# TODO
```

---

### 🔍 Check unapplied migrations

To see which migrations have not been applied yet:

```bash
plastron check
```

This will output a list of unapplied revisions.

---

## 🧩 Merge & Validation

### 🔗 Merge migrations

When your migration history diverges (for example, two developers generate migrations on different branches), you can end up with **multiple heads** — independent final revisions.

To fix this, Plastron provides a merge feature:

```bash
plastron merge
```

This creates a **new migration file** that joins the multiple heads into a single unified migration graph, ensuring a clean linear history.

Use this whenever your CI or validation command reports more than one head revision.

---

### ✅ Validate heads

This command checks if your migration history contains **multiple head revisions** — a common issue when working on concurrent feature branches.

```bash
plastron validate-heads
```

It’s particularly useful in **CI pipelines**, where you want to fail early if your migrations have diverged.
If this happens, you’ll need to **create a merge migration** or manually adjust the migration order.

---

## 🧪 CI Integration

You can easily integrate Plastron into your CI workflow to check if you have multiple head branches aka migration conflicts (example using GitHub Actions):

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install tortoise-plastron
      - run: plastron validate-heads
```

---

## ⚠️ Limitations (WIP)

Currently unsupported features:

- Table rename
- Column rename
- Foreign keys
- One to one keys
- Many to many keys
- and most likely other things that we haven't came accross yet

---

## 🧾 License & Disclaimer

Plastron is provided under the Apache 2.0 License **without any warranty**.  
Use at your own risk. Always back up your database before running migrations.
