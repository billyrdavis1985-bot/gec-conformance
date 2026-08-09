#!/usr/bin/env python3
"""Command-line interface for the canonicalization differential rig."""

from __future__ import annotations

import argparse
import sys

from canon import Canonicalizer, load_json
from canon.corpus import BY_ID, CORPUS, high_value
from canon.differ import compare, report
from canon.rulesets import REGISTRY, get


def cmd_rulesets(_args) -> int:
    for name in sorted(REGISTRY):
        print(get(name).describe())
        print()
    return 0


def cmd_corpus(args) -> int:
    cases = high_value() if args.high_value else CORPUS
    print(f"{len(cases)} cases\n")
    for case in cases:
        mark = "*" if "high-value" in case.tags else " "
        print(f"{mark} {case.id:<8} [{case.question:<24}] {case.title}")
    return 0


def cmd_emit(args) -> int:
    canon = Canonicalizer(get(args.ruleset))
    value = load_json(sys.stdin.read()) if args.stdin else BY_ID[args.case].value
    raw = canon.emit(value)
    print(raw.decode("utf-8", errors="backslashreplace"))
    print(f"\ndigest: {canon.digest(value)}", file=sys.stderr)
    return 0


def cmd_diff(args) -> int:
    cases = high_value() if args.high_value else CORPUS
    left, right = get(args.left), get(args.right)
    results = compare(left, right, cases)
    print(report(left, right, results, verbose=args.verbose))
    return 1 if any(r.diverged for r in results) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="canonicalization differential rig")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("rulesets", help="show every ruleset and its decisions").set_defaults(func=cmd_rulesets)

    p_corpus = sub.add_parser("corpus", help="list corpus cases")
    p_corpus.add_argument("--high-value", action="store_true")
    p_corpus.set_defaults(func=cmd_corpus)

    p_emit = sub.add_parser("emit", help="emit canonical bytes for one case or stdin")
    p_emit.add_argument("ruleset")
    p_emit.add_argument("--case", default="STR-03")
    p_emit.add_argument("--stdin", action="store_true")
    p_emit.set_defaults(func=cmd_emit)

    p_diff = sub.add_parser("diff", help="compare two rulesets across the corpus")
    p_diff.add_argument("left")
    p_diff.add_argument("right")
    p_diff.add_argument("--high-value", action="store_true")
    p_diff.add_argument("-v", "--verbose", action="store_true")
    p_diff.set_defaults(func=cmd_diff)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
