"""The smallest possible installation: a script that crashes.

cd python
BLARE_SINKS=console python examples/plain_script.py
"""

import blare

blare.init(service="nightly-job")


def charge(order_id):
    raise ValueError(f"order {order_id} has no payment method")


if __name__ == "__main__":
    # Nothing catches this. Blare alerts, then the process dies as it would
    # have without Blare installed.
    charge(4821)
