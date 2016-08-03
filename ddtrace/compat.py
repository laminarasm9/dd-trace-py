import sys

PY2 = sys.version_info[0] == 2

stringify = str

if PY2:
    from urllib import urlencode
    import httplib
    stringify = unicode
    from Queue import Queue
    try:
        from cStringIO import StringIO
    except ImportError:
        from StringIO import StringIO
else:
    from queue import Queue
    from urllib.parse import urlencode
    import http.client as httplib
    from io import StringIO


try:
    import ujson as json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        import json

def iteritems(obj, **kwargs):
    func = getattr(obj, "iteritems", None)
    if not func:
        func = obj.items
    return func(**kwargs)

if PY2:
    numeric_types = (int, long, float)
else:
    numeric_types = (int, float)


__all__ = [
    'PY2',
    'urlencode',
    'httplib',
    'stringify',
    'Queue',
    'StringIO',
    'json',
    'iteritems'
]
