import importlib.util
import os.path
import sys
from collections import deque
from hashlib import sha256

from ulid import ULID

from plastron.exceptions import ConfigError


# TODO: tests
def add_base_dir_to_sys_path(path):
    if not os.path.isdir(path):
        raise ConfigError(f"base_dir folder does not exist: {path}")
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


def generate_revision_id():
    # ULIDs first 10 chars are timestamp, all after are randomness. We keep just 2
    # random chars as that's more than enough for plastron
    return str(ULID())[:12].lower()


def load_module_py(file_path, module_id):
    spec = importlib.util.spec_from_file_location(module_id, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kahn_toposort(nodes, parents, children):
    indeg = {n: len(parents.get(n, ())) for n in nodes}
    q = deque([n for n, d in indeg.items() if d == 0])
    order = []

    while q:
        n = q.popleft()
        order.append(n)
        for c in children.get(n, ()):
            indeg[c] -= 1
            if indeg[c] == 0:
                q.append(c)

    if len(order) != len(nodes):
        raise ValueError("Cycle detected (not a DAG).")
    return order


def graph_heads(nodes, children):
    return [n for n in nodes if not children.get(n)]


def generate_hash(*args, length):
    # Hash a set of string values and get a digest of the given length.
    return sha256(";".join(args).encode("utf-8")).hexdigest()[:length]
