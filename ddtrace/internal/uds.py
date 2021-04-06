import socket
from typing import Any

from ..compat import httplib


class UDSHTTPConnection(httplib.HTTPConnection):  # type: ignore[name-defined]
    """An HTTP connection established over a Unix Domain Socket."""

    # It's "important" to keep the hostname and port arguments here; while there are not used by the connection
    # mechanism, they are actually used as HTTP headers such as `Host`.
    def __init__(self, path, https, *args, **kwargs):
        # type: (str, bool, *Any, **Any) -> None
        if https:
            httplib.HTTPSConnection.__init__(self, *args, **kwargs)
        else:
            httplib.HTTPConnection.__init__(self, *args, **kwargs)
        self.path = path

    def connect(self):
        # type: () -> None
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.path)
        self.sock = sock
