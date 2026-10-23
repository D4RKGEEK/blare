"""Flask capture.

Uses Flask's ``got_request_exception`` signal rather than WSGI middleware:
Flask converts an unhandled exception into a 500 response inside the request
context, so with ``PROPAGATE_EXCEPTIONS`` off (the production default) nothing
ever reaches a WSGI wrapper.
"""

from __future__ import annotations

import contextlib
from typing import Any


def install(app: Any, client: Any = None) -> None:
    """Attach Blare to a Flask app::

    from blare.integrations.flask import install
    install(app)
    """
    from flask import got_request_exception, request

    def handler(sender: Any, exception: BaseException, **_: Any) -> None:
        target = client
        if target is None:
            from .. import get_client

            target = get_client()
        if target is None:
            return
        context: dict[str, Any] = {}
        # Outside a request context there is nothing to attach, which is fine.
        with contextlib.suppress(Exception):
            context = {"method": request.method, "path": request.path, "status": 500}
        target.capture_exception(exception, request=context or None)

    # Strong reference: Flask's signals hold the receiver weakly, so a local
    # function would be garbage collected and the alerts would silently stop.
    app.extensions.setdefault("blare", {})["receiver"] = handler
    got_request_exception.connect(handler, app, weak=False)
