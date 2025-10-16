from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("plastron")
except PackageNotFoundError:
    import tomllib
    from pathlib import Path

    filepath = Path("./pyproject.toml")
    with filepath.open("rb") as f:
        pyproject = tomllib.load(f)
    __version__ = pyproject["project"]["version"]
