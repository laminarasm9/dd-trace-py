import unittest

from nose.tools import eq_, ok_

# project
from ddtrace.ext import net
from ddtrace.tracer import Tracer, Span
from ddtrace.contrib.flask_cache import get_traced_cache
from ddtrace.contrib.flask_cache.utils import _extract_conn_tags, _resource_from_cache_prefix
from ddtrace.contrib.flask_cache.tracers import TYPE, CACHE_BACKEND

# 3rd party
from flask import Flask


class FlaskCacheUtilsTest(unittest.TestCase):
    SERVICE = "test-flask-cache"

    def test_extract_redis_connection_metadata(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        traced_cache = Cache(app, config={"CACHE_TYPE": "redis"})
        # extract client data
        meta = _extract_conn_tags(traced_cache.cache._client)
        expected_meta = {'out.host': 'localhost', 'out.port': 6379, 'out.redis_db': 0}
        eq_(meta, expected_meta)

    def test_extract_memcached_connection_metadata(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        traced_cache = Cache(app, config={"CACHE_TYPE": "memcached"})
        # extract client data
        meta = _extract_conn_tags(traced_cache.cache._client)
        expected_meta = {'out.host': '127.0.0.1', 'out.port': 11211}
        eq_(meta, expected_meta)

    def test_extract_memcached_multiple_connection_metadata(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        config = {
            "CACHE_TYPE": "memcached",
            "CACHE_MEMCACHED_SERVERS": [
                ("127.0.0.1", 11211),
                ("localhost", 11211),
            ],
        }
        traced_cache = Cache(app, config=config)
        # extract client data
        meta = _extract_conn_tags(traced_cache.cache._client)
        expected_meta = {
            'out.host': '127.0.0.1',
            'out.port': 11211,
        }
        eq_(meta, expected_meta)

    def test_default_span_tags(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})
        # test tags and attributes
        with cache._TracedCache__trace("flask_cache.cmd") as span:
            eq_(span.service, cache._datadog_service)
            eq_(span.span_type, TYPE)
            eq_(span.meta[CACHE_BACKEND], "simple")
            ok_(net.TARGET_HOST not in span.meta)
            ok_(net.TARGET_PORT not in span.meta)

    def test_default_span_tags_for_redis(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "redis"})
        # test tags and attributes
        with cache._TracedCache__trace("flask_cache.cmd") as span:
            eq_(span.service, cache._datadog_service)
            eq_(span.span_type, TYPE)
            eq_(span.meta[CACHE_BACKEND], "redis")
            eq_(span.meta[net.TARGET_HOST], 'localhost')
            eq_(span.meta[net.TARGET_PORT], '6379')

    def test_default_span_tags_memcached(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "memcached"})
        # test tags and attributes
        with cache._TracedCache__trace("flask_cache.cmd") as span:
            eq_(span.service, cache._datadog_service)
            eq_(span.span_type, TYPE)
            eq_(span.meta[CACHE_BACKEND], "memcached")
            eq_(span.meta[net.TARGET_HOST], "127.0.0.1")
            eq_(span.meta[net.TARGET_PORT], "11211")

    def test_resource_from_cache_with_prefix(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        traced_cache = Cache(app, config={"CACHE_TYPE": "redis", "CACHE_KEY_PREFIX": "users"})
        # expect a resource with a prefix
        expected_resource = "GET users"
        resource = _resource_from_cache_prefix("GET", traced_cache.cache)
        eq_(resource, expected_resource)

    def test_resource_from_cache_with_empty_prefix(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        traced_cache = Cache(app, config={"CACHE_TYPE": "redis", "CACHE_KEY_PREFIX": ""})
        # expect a resource with a prefix
        expected_resource = "GET"
        resource = _resource_from_cache_prefix("GET", traced_cache.cache)
        eq_(resource, expected_resource)

    def test_resource_from_cache_without_prefix(self):
        # create the TracedCache instance for a Flask app
        tracer = Tracer()
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "redis"})
        # expect only the resource name
        expected_resource = "GET"
        resource = _resource_from_cache_prefix("GET", cache.config)
        eq_(resource, expected_resource)
