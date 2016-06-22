
try:
    from queue import Queue
except ImportError:
    from Queue import Queue

try:
    import ujson as json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        import json

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
