import unittest

from ddtrace.tracer import Tracer
from ddtrace.contrib.flask_cache import get_traced_cache

from flask import Flask

from ...test_tracer import DummyWriter


class FlaskCacheTest(unittest.TestCase):
    SERVICE = "test-flask-cache"

    def test_constructor(self):
        """
        TracedCache must behave like the original flask ``Cache`` class
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # the cache must be connected to the current app
        assert app == cache.app
        assert cache.cache is not None
        # but it should be traced (with defaults)
        assert cache._datadog_tracer == tracer
        assert cache._datadog_service == self.SERVICE
        assert cache._datadog_meta is None

    def test_cache_get(self):
        """
        Flask-cache get must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.get("complex_operation")
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "GET")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.key": "complex_operation",
            "flask_cache.backend": "simple",
        }

        self.assertDictEqual(span.meta, expected_meta)

    def test_cache_set(self):
        """
        Flask-cache set must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.set("complex_operation", "with_a_result")
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "SET")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.key": "complex_operation",
            "flask_cache.backend": "simple",
        }

        self.assertDictEqual(span.meta, expected_meta)

    def test_cache_add(self):
        """
        Flask-cache add must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.add("complex_operation", 50)
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "ADD")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.key": "complex_operation",
            "flask_cache.backend": "simple",
        }

        self.assertDictEqual(span.meta, expected_meta)

    def test_cache_delete(self):
        """
        Flask-cache delete must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.delete("complex_operation")
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "DELETE")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.key": "complex_operation",
            "flask_cache.backend": "simple",
        }

        self.assertDictEqual(span.meta, expected_meta)

    def test_cache_delete_many(self):
        """
        Flask-cache delete_many must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.delete_many("complex_operation", "another_complex_op")
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "DELETE_MANY")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.key": "['complex_operation', 'another_complex_op']",
            "flask_cache.backend": "simple",
        }

        self.assertDictEqual(span.meta, expected_meta)

    def test_cache_clear(self):
        """
        Flask-cache clear must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.clear()
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "CLEAR")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.backend": "simple",
        }

        self.assertDictEqual(span.meta, expected_meta)

    def test_get_many(self):
        """
        Flask-cache get_many must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.get_many('first_complex_op', 'second_complex_op')
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "GET_MANY")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.key": "['first_complex_op', 'second_complex_op']",
            "flask_cache.backend": "simple",
        }

        self.assertDictEqual(span.meta, expected_meta)

    def test_set_many(self):
        """
        Flask-cache set_many must register a span
        """
        # initialize the dummy writer
        writer = DummyWriter()
        tracer = Tracer()
        tracer.writer = writer

        # create the TracedCache instance for a Flask app
        Cache = get_traced_cache(tracer, service=self.SERVICE)
        app = Flask(__name__)
        cache = Cache(app, config={"CACHE_TYPE": "simple"})

        # test get operation
        cache.set_many({
            'first_complex_op': 10,
            'second_complex_op': 20,
        })
        spans = writer.pop()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.service, self.SERVICE)
        self.assertEqual(span.resource, "SET_MANY")
        self.assertEqual(span.name, "flask_cache.command")
        self.assertEqual(span.span_type, "flask_cache")
        self.assertEqual(span.error, 0)

        expected_meta = {
            "flask_cache.key": "['first_complex_op', 'second_complex_op']",
            "flask_cache.backend": "simple",
        }

        self.assertEqual(span.meta["flask_cache.backend"], "simple")
        self.assertIn("first_complex_op", span.meta["flask_cache.key"])
        self.assertIn("second_complex_op", span.meta["flask_cache.key"])
