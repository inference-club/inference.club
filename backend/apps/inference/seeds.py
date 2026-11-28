"""Seeds that can be replayed.

A request that leaves the seed out (or sends a "pick one for me" value such as
-1) still gets a concrete seed, chosen here, sent upstream and stored with the
request. Without that the model server draws its own and we never learn it, so
the result can't be made again. With it, "reproduce" is the same call with the
same number, on this deployment or another one.
"""

import random

SEED_MAX = 2**31 - 1


def pick_seed(value=None) -> int:
    """``value`` when it is a usable seed (an integer >= 0), else a fresh
    random one in [1, 2^31 - 1]."""
    if isinstance(value, bool):
        value = None
    try:
        seed = int(value)
    except (TypeError, ValueError):
        seed = -1
    return seed if seed >= 0 else random.randint(1, SEED_MAX)
