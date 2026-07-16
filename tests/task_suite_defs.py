"""task_suite_defs.py — 30 distinct, compact bug-fix tasks for the A/B suite.

Each task ships: buggy module, reference fix, and a pytest file. The suite's
--selftest proves integrity offline: tests FAIL on `buggy`, PASS on `fixed`.
Bugs span 30 different defect classes — not 30 variants of one template.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    key: str
    module: str      # module filename, e.g. "calc.py"
    buggy: str
    fixed: str
    tests: str


TASKS: list[Task] = [
    Task("off_by_one_month", "window.py",
         buggy='''from datetime import date, timedelta

def days_in_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days

def month_window(year, month):
    start = date(year, month, 1)
    end = start + timedelta(days=days_in_month(year, month) - 1)
    return start, end
''',
         fixed='''from datetime import date, timedelta

def days_in_month(year, month):
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days

def month_window(year, month):
    start = date(year, month, 1)
    end = start + timedelta(days=days_in_month(year, month))
    return start, end
''',
         tests='''from datetime import date
from window import month_window

def test_includes_last_day():
    start, end = month_window(2026, 2)
    assert start == date(2026, 2, 1) and end == date(2026, 3, 1)

def test_december():
    assert month_window(2026, 12)[1] == date(2027, 1, 1)
'''),

    Task("boundary_operator", "grades.py",
         buggy='''def passed(score):
    """Students pass with 60 or more."""
    return score > 60
''',
         fixed='''def passed(score):
    """Students pass with 60 or more."""
    return score >= 60
''',
         tests='''from grades import passed

def test_exact_cutoff():
    assert passed(60) is True

def test_below_and_above():
    assert passed(59) is False and passed(61) is True
'''),

    Task("integer_division", "stats.py",
         buggy='''def mean(values):
    return sum(values) // len(values)
''',
         fixed='''def mean(values):
    return sum(values) / len(values)
''',
         tests='''from stats import mean

def test_fractional_mean():
    assert mean([1, 2]) == 1.5

def test_integer_mean():
    assert mean([2, 4]) == 3
'''),

    Task("mutable_default", "registry.py",
         buggy='''def register(name, bucket=[]):
    bucket.append(name)
    return bucket
''',
         fixed='''def register(name, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(name)
    return bucket
''',
         tests='''from registry import register

def test_fresh_bucket_each_call():
    assert register("a") == ["a"]
    assert register("b") == ["b"]

def test_explicit_bucket():
    b = ["x"]
    assert register("y", b) == ["x", "y"]
'''),

    Task("sort_key_numeric", "ranking.py",
         buggy='''def rank_ids(ids):
    """Sort numeric string ids ascending by their numeric value."""
    return sorted(ids)
''',
         fixed='''def rank_ids(ids):
    """Sort numeric string ids ascending by their numeric value."""
    return sorted(ids, key=int)
''',
         tests='''from ranking import rank_ids

def test_numeric_order():
    assert rank_ids(["10", "9", "100"]) == ["9", "10", "100"]
'''),

    Task("greedy_regex", "tags.py",
         buggy='''import re

def first_tag(html):
    """Return the name of the FIRST tag, e.g. 'b' for '<b>x</b><i>y</i>'."""
    m = re.search(r"<(.+)>", html)
    return m.group(1) if m else None
''',
         fixed='''import re

def first_tag(html):
    """Return the name of the FIRST tag, e.g. 'b' for '<b>x</b><i>y</i>'."""
    m = re.search(r"<(.+?)>", html)
    return m.group(1) if m else None
''',
         tests='''from tags import first_tag

def test_first_tag_only():
    assert first_tag("<b>x</b><i>y</i>") == "b"

def test_single():
    assert first_tag("<div>") == "div"
'''),

    Task("missing_get_default", "config.py",
         buggy='''def timeout_of(cfg):
    """Timeout in seconds; missing key means the default of 30."""
    return cfg["timeout"]
''',
         fixed='''def timeout_of(cfg):
    """Timeout in seconds; missing key means the default of 30."""
    return cfg.get("timeout", 30)
''',
         tests='''from config import timeout_of

def test_default_when_missing():
    assert timeout_of({}) == 30

def test_explicit():
    assert timeout_of({"timeout": 5}) == 5
'''),

    Task("slice_end", "chunks.py",
         buggy='''def first_n(items, n):
    """Return the first n items (all items when n exceeds length)."""
    return items[1:n]
''',
         fixed='''def first_n(items, n):
    """Return the first n items (all items when n exceeds length)."""
    return items[:n]
''',
         tests='''from chunks import first_n

def test_first_two():
    assert first_n([1, 2, 3], 2) == [1, 2]

def test_over_length():
    assert first_n([1], 5) == [1]
'''),

    Task("accumulator_reset", "totals.py",
         buggy='''def totals_per_order(orders):
    """orders: list of lists of item prices -> total per order."""
    out = []
    total = 0
    for order in orders:
        for price in order:
            total += price
        out.append(total)
    return out
''',
         fixed='''def totals_per_order(orders):
    """orders: list of lists of item prices -> total per order."""
    out = []
    for order in orders:
        total = 0
        for price in order:
            total += price
        out.append(total)
    return out
''',
         tests='''from totals import totals_per_order

def test_independent_orders():
    assert totals_per_order([[1, 2], [3]]) == [3, 3]
'''),

    Task("case_insensitive", "search.py",
         buggy='''def contains(haystack, needle):
    """Case-insensitive containment check."""
    return needle in haystack
''',
         fixed='''def contains(haystack, needle):
    """Case-insensitive containment check."""
    return needle.lower() in haystack.lower()
''',
         tests='''from search import contains

def test_mixed_case():
    assert contains("Hello World", "hello") is True

def test_absent():
    assert contains("Hello", "bye") is False
'''),

    Task("negative_index", "recent.py",
         buggy='''def last_events(log, n):
    """The last n events, oldest first."""
    return log[-n:] if n else log[:]
''',
         fixed='''def last_events(log, n):
    """The last n events, oldest first."""
    return log[-n:] if n else []
''',
         tests='''from recent import last_events

def test_zero_means_none():
    assert last_events([1, 2, 3], 0) == []

def test_last_two():
    assert last_events([1, 2, 3], 2) == [2, 3]
'''),

    Task("shallow_copy", "board.py",
         buggy='''def empty_board(rows, cols):
    """rows x cols grid of zeros; cells must be independent."""
    return [[0] * cols] * rows
''',
         fixed='''def empty_board(rows, cols):
    """rows x cols grid of zeros; cells must be independent."""
    return [[0] * cols for _ in range(rows)]
''',
         tests='''from board import empty_board

def test_cells_independent():
    b = empty_board(2, 2)
    b[0][0] = 1
    assert b[1][0] == 0
'''),

    Task("is_vs_eq", "dedupe.py",
         buggy='''def count_matches(items, target):
    return sum(1 for x in items if x is target)
''',
         fixed='''def count_matches(items, target):
    return sum(1 for x in items if x == target)
''',
         tests='''from dedupe import count_matches

def test_equal_strings_built_at_runtime():
    target = "".join(["ab", "cd"])
    assert count_matches(["abcd", "abcd"], target) == 2
'''),

    Task("swallowed_exception", "parse_num.py",
         buggy='''def parse_int(text):
    """int(text) or None when text is not a number. Must not hide other errors."""
    try:
        return int(text)
    except Exception:
        return None
''',
         fixed='''def parse_int(text):
    """int(text) or None when text is not a number. Must not hide other errors."""
    try:
        return int(text)
    except (ValueError, TypeError):
        return None
''',
         tests='''import pytest
from parse_num import parse_int

class Boom:
    def __int__(self):
        raise MemoryError("must propagate")

def test_parses():
    assert parse_int("42") == 42 and parse_int("x") is None

def test_does_not_swallow_system_errors():
    with pytest.raises(MemoryError):
        parse_int(Boom())
'''),

    Task("percent_format", "report.py",
         buggy='''def pct(part, whole):
    """'42.5%' style string, one decimal."""
    return f"{part / whole:.1f}%"
''',
         fixed='''def pct(part, whole):
    """'42.5%' style string, one decimal."""
    return f"{part / whole * 100:.1f}%"
''',
         tests='''from report import pct

def test_simple():
    assert pct(1, 2) == "50.0%"

def test_precision():
    assert pct(425, 1000) == "42.5%"
'''),

    Task("pagination_pages", "pager.py",
         buggy='''def page_count(total, per_page):
    return total // per_page
''',
         fixed='''def page_count(total, per_page):
    return -(-total // per_page)
''',
         tests='''from pager import page_count

def test_partial_last_page():
    assert page_count(11, 5) == 3

def test_exact():
    assert page_count(10, 5) == 2
'''),

    Task("inverted_filter", "clean.py",
         buggy='''def drop_blank(lines):
    """Remove blank/whitespace-only lines."""
    return [l for l in lines if not l.strip()]
''',
         fixed='''def drop_blank(lines):
    """Remove blank/whitespace-only lines."""
    return [l for l in lines if l.strip()]
''',
         tests='''from clean import drop_blank

def test_drops_blank():
    assert drop_blank(["a", " ", "", "b"]) == ["a", "b"]
'''),

    Task("early_return_loop", "find_all.py",
         buggy='''def indexes_of(items, target):
    """ALL indexes where target occurs."""
    for i, x in enumerate(items):
        if x == target:
            return [i]
    return []
''',
         fixed='''def indexes_of(items, target):
    """ALL indexes where target occurs."""
    return [i for i, x in enumerate(items) if x == target]
''',
         tests='''from find_all import indexes_of

def test_multiple_hits():
    assert indexes_of([1, 2, 1], 1) == [0, 2]

def test_missing():
    assert indexes_of([1], 9) == []
'''),

    Task("strip_semantics", "keys.py",
         buggy='''def parse_kv(line):
    """'key = value' -> (key, value); values may legitimately contain '='."""
    key, value = line.split("=")
    return key.strip(), value.strip()
''',
         fixed='''def parse_kv(line):
    """'key = value' -> (key, value); values may legitimately contain '='."""
    key, value = line.split("=", 1)
    return key.strip(), value.strip()
''',
         tests='''from keys import parse_kv

def test_value_with_equals():
    assert parse_kv("url = a=b") == ("url", "a=b")

def test_simple():
    assert parse_kv("k = v") == ("k", "v")
'''),

    Task("ordered_unique", "uniq.py",
         buggy='''def unique(items):
    """Unique items, FIRST-SEEN ORDER preserved."""
    return list(set(items))
''',
         fixed='''def unique(items):
    """Unique items, FIRST-SEEN ORDER preserved."""
    return list(dict.fromkeys(items))
''',
         tests='''from uniq import unique

def test_order_preserved():
    assert unique([3, 1, 3, 2, 1]) == [3, 1, 2]
'''),

    Task("zip_truncation", "pair.py",
         buggy='''def pair_scores(names, scores):
    """Pair names with scores; missing scores become None."""
    return list(zip(names, scores))
''',
         fixed='''from itertools import zip_longest

def pair_scores(names, scores):
    """Pair names with scores; missing scores become None."""
    return list(zip_longest(names, scores))
''',
         tests='''from pair import pair_scores

def test_missing_scores_padded():
    assert pair_scores(["a", "b"], [1]) == [("a", 1), ("b", None)]
'''),

    Task("enumerate_start", "numbered.py",
         buggy='''def numbered(lines):
    """'1: first-line' style, 1-based."""
    return [f"{i}: {line}" for i, line in enumerate(lines)]
''',
         fixed='''def numbered(lines):
    """'1: first-line' style, 1-based."""
    return [f"{i}: {line}" for i, line in enumerate(lines, start=1)]
''',
         tests='''from numbered import numbered

def test_one_based():
    assert numbered(["a", "b"]) == ["1: a", "2: b"]
'''),

    Task("empty_base_case", "depth.py",
         buggy='''def max_depth(node):
    """Depth of a nested-list tree; [] has depth 1, non-list has depth 0."""
    return 1 + max(max_depth(c) for c in node)
''',
         fixed='''def max_depth(node):
    """Depth of a nested-list tree; [] has depth 1, non-list has depth 0."""
    if not isinstance(node, list):
        return 0
    if not node:
        return 1
    return 1 + max(max_depth(c) for c in node)
''',
         tests='''from depth import max_depth

def test_empty_list():
    assert max_depth([]) == 1

def test_nested():
    assert max_depth([1, [2, [3]]]) == 3
'''),

    Task("csv_maxsplit", "rows.py",
         buggy='''def parse_row(line):
    """'id,name,notes' -> 3 fields; notes may contain commas."""
    return line.split(",")
''',
         fixed='''def parse_row(line):
    """'id,name,notes' -> 3 fields; notes may contain commas."""
    return line.split(",", 2)
''',
         tests='''from rows import parse_row

def test_notes_keep_commas():
    assert parse_row("1,bob,hello, world") == ["1", "bob", "hello, world"]
'''),

    Task("sort_direction", "leaders.py",
         buggy='''def top3(scores):
    """Three HIGHEST scores, descending."""
    return sorted(scores)[:3]
''',
         fixed='''def top3(scores):
    """Three HIGHEST scores, descending."""
    return sorted(scores, reverse=True)[:3]
''',
         tests='''from leaders import top3

def test_highest_first():
    assert top3([5, 1, 9, 7]) == [9, 7, 5]
'''),

    Task("negative_modulo", "clock.py",
         buggy='''def hour_shift(hour, shift):
    """24h clock arithmetic; result always in 0..23."""
    return abs((hour + shift) % -24)
''',
         fixed='''def hour_shift(hour, shift):
    """24h clock arithmetic; result always in 0..23."""
    return (hour + shift) % 24
''',
         tests='''from clock import hour_shift

def test_wraps_backwards():
    assert hour_shift(1, -3) == 22

def test_forward():
    assert hour_shift(23, 2) == 1
'''),

    Task("join_separator", "path.py",
         buggy='''def breadcrumb(parts):
    """'a > b > c' style breadcrumb."""
    out = ""
    for p in parts:
        out += p + " > "
    return out
''',
         fixed='''def breadcrumb(parts):
    """'a > b > c' style breadcrumb."""
    return " > ".join(parts)
''',
         tests='''from path import breadcrumb

def test_no_trailing_separator():
    assert breadcrumb(["a", "b", "c"]) == "a > b > c"

def test_single():
    assert breadcrumb(["x"]) == "x"
'''),

    Task("dict_iteration_mutation", "prune.py",
         buggy='''def drop_zeros(counts):
    """Remove zero-valued keys IN PLACE and return the dict."""
    for k in counts:
        if counts[k] == 0:
            del counts[k]
    return counts
''',
         fixed='''def drop_zeros(counts):
    """Remove zero-valued keys IN PLACE and return the dict."""
    for k in list(counts):
        if counts[k] == 0:
            del counts[k]
    return counts
''',
         tests='''from prune import drop_zeros

def test_removes_zeros_in_place():
    d = {"a": 0, "b": 1, "c": 0}
    assert drop_zeros(d) == {"b": 1} and d == {"b": 1}
'''),

    Task("bool_string_parse", "flags.py",
         buggy='''def is_enabled(value):
    """Parse env-style flag: 'true'/'1'/'yes' (any case) -> True, else False."""
    return bool(value)
''',
         fixed='''def is_enabled(value):
    """Parse env-style flag: 'true'/'1'/'yes' (any case) -> True, else False."""
    return str(value).strip().lower() in {"true", "1", "yes"}
''',
         tests='''from flags import is_enabled

def test_false_string_is_false():
    assert is_enabled("false") is False

def test_truthy_spellings():
    assert is_enabled("TRUE") and is_enabled("1") and is_enabled("yes")
'''),

    Task("running_max_window", "peaks.py",
         buggy='''def window_max(values, k):
    """Max of each contiguous window of size k."""
    return [max(values[i:i + k]) for i in range(len(values))]
''',
         fixed='''def window_max(values, k):
    """Max of each contiguous window of size k."""
    return [max(values[i:i + k]) for i in range(len(values) - k + 1)]
''',
         tests='''from peaks import window_max

def test_window_count_and_values():
    assert window_max([1, 3, 2, 5], 2) == [3, 3, 5]
'''),
]

assert len(TASKS) == 30, f"suite must have exactly 30 tasks, has {len(TASKS)}"
assert len({t.key for t in TASKS}) == 30, "task keys must be unique"
