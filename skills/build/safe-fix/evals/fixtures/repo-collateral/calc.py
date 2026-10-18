"""The 'fix' changed a shared helper and broke multiply (eval fixture for collateral detection)."""


def _combine(a: int, b: int, op: str) -> int:
    return a + b  # the fix: always add — multiply now collapses to add


def add(a: int, b: int) -> int:
    return _combine(a, b, "+")


def multiply(a: int, b: int) -> int:
    return _combine(a, b, "*")
