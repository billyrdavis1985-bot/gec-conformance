"""
Decode table construction for a distance-d repetition code.

The table is TOTAL: every syntactically possible detection-event pattern has an
entry. There is no fallback branch, and therefore no path that testing can miss.
This is a contract requirement (§4), not a stylistic choice — a decoder with a
default case has a code path whose behaviour is asserted rather than exercised.

Determinism obligations discharged here:

  - No floating point. Weights are integer Manhattan distances on the
    (round, position) detector lattice.
  - Ties are broken by an explicit total order, not by whichever pairing the
    matching search happened to visit first. Two runs, two interpreters, and two
    iteration orders must select the same correction.
  - The table is content-addressed. Its digest is pinned in the contract, so a
    decode result is only meaningful together with the table that produced it.
"""

from __future__ import annotations

import hashlib
import itertools
import json

# Guard: the table is exhaustive over 2**(rounds * (distance - 1)) patterns.
# Beyond this the enumeration is not tractable and the capability must refuse
# rather than silently switch to an on-line decoder with different behaviour.
MAX_DETECTOR_BITS = 20


class TableError(Exception):
    """Raised when a table cannot be constructed under the stated constraints."""


def detector_count(distance: int, rounds: int) -> int:
    return rounds * (distance - 1)


def _detector_coords(distance: int, rounds: int) -> list[tuple[int, int]]:
    """Detector index -> (round, position), row-major.

    Detector d = r * (distance - 1) + p is the parity check between data qubits
    p and p+1, measured in round r.
    """
    return [(r, p) for r in range(rounds) for p in range(distance - 1)]


def _pair_cost(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Integer Manhattan cost between two detectors on the space-time lattice."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _boundary_cost(coord: tuple[int, int], distance: int) -> int:
    """Cost of matching a lone detector to the nearer spatial boundary."""
    _, position = coord
    return min(position + 1, (distance - 1) - position)


def _min_weight_matching(
    detectors: tuple[int, ...], coords: list[tuple[int, int]], distance: int
) -> tuple[int, tuple[tuple[int, ...], ...]]:
    """Exhaustive minimum-weight matching with a deterministic tie-break.

    Returns (total_cost, matching), where matching is a sorted tuple of pairs;
    a 1-tuple denotes a detector matched to the boundary.

    Exhaustive rather than heuristic: the detector counts here are small, and an
    exact search removes any dependence on search order. Among equal-cost
    matchings the lexicographically smallest is selected, which is a property of
    the result rather than of the traversal.
    """
    if not detectors:
        return 0, ()

    best: tuple[int, tuple[tuple[int, ...], ...]] | None = None

    def search(remaining: tuple[int, ...], acc: list[tuple[int, ...]], cost: int) -> None:
        nonlocal best
        if best is not None and cost > best[0]:
            return
        if not remaining:
            candidate = (cost, tuple(sorted(acc)))
            if best is None or candidate < best:
                best = candidate
            return

        head, rest = remaining[0], remaining[1:]

        # Option 1: match head to the boundary.
        search(rest, acc + [(head,)], cost + _boundary_cost(coords[head], distance))

        # Option 2: pair head with each later detector.
        for i, other in enumerate(rest):
            pair_cost = _pair_cost(coords[head], coords[other])
            search(rest[:i] + rest[i + 1 :], acc + [(head, other)], cost + pair_cost)

    search(detectors, [], 0)
    assert best is not None
    return best


def _correction_parity(
    matching: tuple[tuple[int, ...], ...], coords: list[tuple[int, int]], distance: int
) -> int:
    """Logical correction implied by a matching: 0 or 1.

    For a repetition code the logical observable flips when a correction chain
    crosses the chosen reference boundary. A chain crosses when it terminates on
    the left boundary; boundary-matched detectors are the only chains that can.
    """
    parity = 0
    for group in matching:
        if len(group) == 1:
            _, position = coords[group[0]]
            # Left boundary is nearer (ties go left, stated explicitly).
            if position + 1 <= (distance - 1) - position:
                parity ^= 1
    return parity


def build_table(distance: int, rounds: int) -> dict[str, int]:
    """Return the total decode table: detection-event bitstring -> parity."""
    if distance < 3 or distance % 2 == 0:
        raise TableError(f"distance must be odd and >= 3, got {distance}")
    if rounds < 1:
        raise TableError(f"rounds must be >= 1, got {rounds}")

    bits = detector_count(distance, rounds)
    if bits > MAX_DETECTOR_BITS:
        raise TableError(
            f"distance={distance}, rounds={rounds} needs {bits} detector bits; "
            f"exhaustive table construction is capped at {MAX_DETECTOR_BITS}. "
            "The capability refuses rather than substituting a different decoder."
        )

    coords = _detector_coords(distance, rounds)
    table: dict[str, int] = {}

    for pattern in itertools.product("01", repeat=bits):
        key = "".join(pattern)
        fired = tuple(i for i, ch in enumerate(key) if ch == "1")
        _, matching = _min_weight_matching(fired, coords, distance)
        table[key] = _correction_parity(matching, coords, distance)

    return table


def table_artifact(distance: int, rounds: int) -> dict:
    """Table plus the parameters that define it, ready for content addressing."""
    return {
        "table_format": "1.0.0",
        "code": "repetition",
        "distance": distance,
        "rounds": rounds,
        "detector_bits": detector_count(distance, rounds),
        "tie_break": "lexicographically smallest minimum-weight matching; "
        "boundary ties resolve left",
        "table": build_table(distance, rounds),
    }


def table_digest(artifact: dict) -> str:
    """SHA-256 over the canonical JSON form of the table artifact."""
    raw = json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
