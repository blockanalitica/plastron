import textwrap
import time
from hashlib import sha256

import pytest
from ulid import ULID

from plastron.utils import (
    generate_hash,
    generate_revision_id,
    graph_heads,
    kahn_toposort,
    load_module_py,
)


def test_generate_revision_id(freezer):
    freezer.move_to("2025-10-08")
    rid = str(ULID.from_timestamp(time.time())).lower()
    rev = generate_revision_id()
    # We compare just the first 10 chars as those are timestamp, the last two are random
    assert rev[:10] == rid[:10]


def test_kahn_toposort_simple_dag():
    nodes = {"A", "B", "C"}
    parents = {"B": ["A"], "C": ["B"]}
    children = {"A": ["B"], "B": ["C"]}
    result = kahn_toposort(nodes, parents, children)
    assert result == ["A", "B", "C"]


def test_kahn_toposort_multiple_roots():
    nodes = {"A", "B", "C", "D"}
    parents = {"C": ["A"], "D": ["B"]}
    children = {"A": ["C"], "B": ["D"]}
    result = kahn_toposort(nodes, parents, children)
    # Valid topological orders: one root before its children
    assert set(result) == {"A", "B", "C", "D"}
    assert result.index("A") < result.index("C")
    assert result.index("B") < result.index("D")


def test_kahn_toposort_disconnected_nodes():
    nodes = {"A", "B", "C"}
    parents = {"B": ["A"]}
    children = {"A": ["B"]}
    result = kahn_toposort(nodes, parents, children)
    # C is disconnected, but still should appear
    assert set(result) == {"A", "B", "C"}
    assert result.index("A") < result.index("B")


def test_kahn_toposort_cycle_detection():
    nodes = {"A", "B"}
    parents = {"A": ["B"], "B": ["A"]}
    children = {"A": ["B"], "B": ["A"]}
    with pytest.raises(ValueError, match="Cycle detected"):
        kahn_toposort(nodes, parents, children)


def test_kahn_toposort_single_node():
    nodes = {"A"}
    parents = {}
    children = {}
    assert kahn_toposort(nodes, parents, children) == ["A"]


def test_graph_heads_simple_graph():
    nodes = {"A", "B", "C"}
    children = {"A": ["B"], "B": ["C"], "C": []}
    result = graph_heads(nodes, children)
    assert result == ["C"]


def test_graph_heads_multiple_heads():
    nodes = {"A", "B", "C", "D"}
    children = {"A": ["B"], "B": ["C"], "C": [], "D": []}
    result = graph_heads(nodes, children)
    assert set(result) == {"C", "D"}


def test_graph_heads_no_heads():
    nodes = {"A", "B"}
    children = {"A": ["B"], "B": ["A"]}
    result = graph_heads(nodes, children)
    assert result == []


def test_graph_heads_empty_graph():
    nodes = set()
    children = {}
    assert graph_heads(nodes, children) == []


def test_graph_heads_missing_in_children():
    # Node not present in children dict at all should count as having no children
    nodes = {"A", "B"}
    children = {"A": ["B"]}
    result = graph_heads(nodes, children)
    assert result == ["B"]


def test_load_module_py_loads_valid_module(tmp_path):
    # Create a temporary Python file
    code = textwrap.dedent("""
        VALUE = 42
        def greet():
            return "hello"
    """)
    file_path = tmp_path / "mymodule.py"
    file_path.write_text(code)

    module = load_module_py(file_path, "mymodule")
    assert hasattr(module, "VALUE")
    assert module.VALUE == 42
    assert module.greet() == "hello"


def test_load_module_py_module_id_is_used(tmp_path):
    code = "X = 'ok'"
    file_path = tmp_path / "mymodule2.py"
    file_path.write_text(code)

    module = load_module_py(file_path, "custom_id")
    assert module.X == "ok"
    assert module.__name__ == "custom_id"


def test_load_module_py_invalid_file_path(tmp_path):
    bad_path = tmp_path / "does_not_exist.py"
    with pytest.raises(FileNotFoundError):
        load_module_py(bad_path, "bad")


def test_load_module_py_syntax_error_in_module(tmp_path):
    code = "def broken(: pass"  # invalid syntax
    file_path = tmp_path / "broken.py"
    file_path.write_text(code)

    with pytest.raises(SyntaxError):
        load_module_py(file_path, "broken")


def test_load_module_py_module_reloads_without_conflict(tmp_path):
    code = "VAL = 1"
    file_path = tmp_path / "repeat.py"
    file_path.write_text(code)

    m1 = load_module_py(file_path, "repeat_mod")
    file_path.write_text("VAL = 1337")
    m2 = load_module_py(file_path, "repeat_mod")

    # Each load executes the file anew
    assert m1.VAL == 1
    assert m2.VAL == 1337


def test_generate_hash_same_input_produces_same_hash():
    h1 = generate_hash("a", "b", length=10)
    h2 = generate_hash("a", "b", length=10)
    assert h1 == h2
    assert len(h1) == 10


def test_generate_hash_different_inputs_produce_different_hashes():
    h1 = generate_hash("a", "b", length=12)
    h2 = generate_hash("a", "c", length=12)
    assert h1 != h2
    assert len(h2) == 12


def test_generate_hash_order_affects_hash():
    h1 = generate_hash("x", "y", length=16)
    h2 = generate_hash("y", "x", length=16)
    assert h1 != h2


@pytest.mark.parametrize("length", [1, 5, 10, 32, 64])
def test_generate_hash_hash_length_truncation(length):
    result = generate_hash("foo", "bar", length=length)
    assert len(result) == length
    # Full hexdigest is 64 chars, all must match prefix of real sha256
    expected = sha256(b"foo;bar").hexdigest()
    assert result == expected[:length]


def test_generate_hash_empty_strings_are_handled():
    h1 = generate_hash("", "", length=8)
    h2 = sha256(b";").hexdigest()[:8]
    assert h1 == h2


def test_generate_hash_unicode_characters_supported():
    h = generate_hash("α", "β", length=16)  # noqa: RUF001
    assert isinstance(h, str)
    assert len(h) == 16


def test_generate_hash_single_argument():
    h = generate_hash("abc", length=10)
    expected = sha256(b"abc").hexdigest()[:10]
    assert h == expected
