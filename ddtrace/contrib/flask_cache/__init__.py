"""
The flask cache tracer will track any access to a cache backend.
You can this tracer together with the Flask tracer middleware.

To install the tracer, do the following::

    from flask import Flask

    from ddtrace import tracer
    from ddtrace.contrib.flask_cache import get_traced_cache

    app = Flask(__name__)

    # get the traced Cache class
    Cache = get_traced_cache(tracer, service='flask-cache-experiments')

    # use the Cache as usual
    cache = Cache(app, config={'CACHE_TYPE': 'simple'})

    @cache.cached(timeout=50)
    def home():
        return "Hello world!"
"""

from ..util import require_modules

required_modules = ['flask_cache']

with require_modules(required_modules) as missing_modules:
    if not missing_modules:
        from .tracers import get_traced_cache

        __all__ = ['get_traced_cache']
