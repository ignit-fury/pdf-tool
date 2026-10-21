"""One predicate for operation routing and the matching privacy disclosure."""
from collections.abc import Sized


def operation_location(operations: Sized) -> str:
    return 'server' if len(operations) else 'local'
