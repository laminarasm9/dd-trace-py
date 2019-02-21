# flake8: noqa
import threading
import asyncio
import aiohttp_jinja2

from urllib import request
from nose.tools import eq_
from aiohttp.test_utils import unittest_run_loop

from ddtrace.pin import Pin
from ddtrace.constants import ANALYTICS_SAMPLE_RATE_KEY
from ddtrace.contrib.aiohttp.patch import patch, unpatch
from ddtrace.contrib.aiohttp.middlewares import trace_app

from .utils import TraceTestCase


class TestRequestTracing(TraceTestCase):
    """
    Ensures that the trace includes all traced components.
    """
    def enable_tracing(self):
        # enabled tracing:
        #   * middleware
        #   * templates
        trace_app(self.app, self.tracer)
        patch()
        Pin.override(aiohttp_jinja2, tracer=self.tracer)

    def disable_tracing(self):
        unpatch()

    @unittest_run_loop
    @asyncio.coroutine
    def test_full_request(self):
        # it should create a root span when there is a handler hit
        # with the proper tags
        request = yield from self.client.request('GET', '/template/')
        eq_(200, request.status)
        yield from request.text()
        # the trace is created
        traces = self.tracer.writer.pop_traces()
        eq_(1, len(traces))
        eq_(2, len(traces[0]))
        request_span = traces[0][0]
        template_span = traces[0][1]
        # request
        eq_('aiohttp-web', request_span.service)
        eq_('aiohttp.request', request_span.name)
        eq_('GET /template/', request_span.resource)
        # template
        eq_('aiohttp-web', template_span.service)
        eq_('aiohttp.template', template_span.name)
        eq_('aiohttp.template', template_span.resource)

    @unittest_run_loop
    @asyncio.coroutine
    def test_analytics_global_on_integration_default(self):
        """
        When making a request
            When an integration trace search is not event sample rate is not set and globally trace search is enabled
                We expect the root span to have the appropriate tag
        """
        # it should create a root span when there is a handler hit
        # with the proper tags
        with self.override_global_config(dict(analytics=True)):
            request = yield from self.client.request('GET', '/template/')
            self.assertEqual(200, request.status)
            yield from request.text()

        # Assert root span sets the appropriate metric
        root = self.get_root_span()
        root.assert_matches(
            name='aiohttp.request',
            metrics={
                ANALYTICS_SAMPLE_RATE_KEY: 1.0,
            },
        )

        # Assert non-root spans do not have this metric set
        for span in self.spans:
            if span == root:
                continue
            self.assertIsNone(span.get_metric(ANALYTICS_SAMPLE_RATE_KEY))

    @unittest_run_loop
    @asyncio.coroutine
    def test_analytics_global_on_integration_on(self):
        """
        When making a request
            When an integration trace search is enabled and sample rate is set and globally trace search is enabled
                We expect the root span to have the appropriate tag
        """
        # it should create a root span when there is a handler hit
        # with the proper tags
        with self.override_global_config(dict(analytics=True)):
            with self.override_config('aiohttp', dict(analytics=True, analytics_sample_rate=0.5)):
                request = yield from self.client.request('GET', '/template/')
                self.assertEqual(200, request.status)
                yield from request.text()

        # Assert root span sets the appropriate metric
        root = self.get_root_span()
        root.assert_matches(
            name='aiohttp.request',
            metrics={
                ANALYTICS_SAMPLE_RATE_KEY: 0.5,
            },
        )

        # Assert non-root spans do not have this metric set
        for span in self.spans:
            if span == root:
                continue
            self.assertIsNone(span.get_metric(ANALYTICS_SAMPLE_RATE_KEY))

    @unittest_run_loop
    @asyncio.coroutine
    def test_analytics_global_off_integration_default(self):
        """
        When making a request
            When an integration trace search is not set and sample rate is set and globally trace search is disabled
                We expect the root span to not include tag
        """
        # it should create a root span when there is a handler hit
        # with the proper tags
        with self.override_global_config(dict(analytics=False)):
            request = yield from self.client.request('GET', '/template/')
            self.assertEqual(200, request.status)
            yield from request.text()

        # Assert root span sets the appropriate metric
        root = self.get_root_span()
        self.assertIsNone(root.get_metric(ANALYTICS_SAMPLE_RATE_KEY))

        # Assert non-root spans do not have this metric set
        for span in self.spans:
            if span == root:
                continue
            self.assertIsNone(span.get_metric(ANALYTICS_SAMPLE_RATE_KEY))


    @unittest_run_loop
    @asyncio.coroutine
    def test_analytics_global_off_integration_on(self):
        """
        When making a request
            When an integration trace search is enabled and sample rate is set and globally trace search is disabled
                We expect the root span to have the appropriate tag
        """
        # it should create a root span when there is a handler hit
        # with the proper tags
        with self.override_global_config(dict(analytics=False)):
            with self.override_config('aiohttp', dict(analytics=True, analytics_sample_rate=0.5)):
                request = yield from self.client.request('GET', '/template/')
                self.assertEqual(200, request.status)
                yield from request.text()

        # Assert root span sets the appropriate metric
        root = self.get_root_span()
        root.assert_matches(
            name='aiohttp.request',
            metrics={
                ANALYTICS_SAMPLE_RATE_KEY: 0.5,
            },
        )

        # Assert non-root spans do not have this metric set
        for span in self.spans:
            if span == root:
                continue
            self.assertIsNone(span.get_metric(ANALYTICS_SAMPLE_RATE_KEY))

    @unittest_run_loop
    @asyncio.coroutine
    def test_multiple_full_request(self):
        # it should handle multiple requests using the same loop
        def make_requests():
            url = self.client.make_url('/delayed/')
            response = request.urlopen(str(url)).read().decode('utf-8')
            eq_('Done', response)

        # blocking call executed in different threads
        threads = [threading.Thread(target=make_requests) for _ in range(10)]
        for t in threads:
            t.daemon = True
            t.start()

        # we should yield so that this loop can handle
        # threads' requests
        yield from asyncio.sleep(0.5)
        for t in threads:
            t.join(timeout=0.5)

        # the trace is created
        traces = self.tracer.writer.pop_traces()
        eq_(10, len(traces))
        eq_(1, len(traces[0]))
