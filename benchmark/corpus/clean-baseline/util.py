"""Fixture: entirely clean code. Any finding here is a false positive."""


def clamp(value, low, high):
    """Return value constrained to [low, high]."""
    if low > high:
        raise ValueError("low must be <= high")
    return max(low, min(value, high))


def chunk(items, size):
    """Split items into lists of at most size (size >= 1)."""
    if size < 1:
        raise ValueError("size must be >= 1")
    return [items[i : i + size] for i in range(0, len(items), size)]
