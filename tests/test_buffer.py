import random
import threading

from unittest import TestCase
from nose.tools import eq_, ok_

from ddtrace.span import Span
from ddtrace.writer import Q as TraceBuffer
from ddtrace.buffer import ThreadLocalSpanBuffer


class TestInternalBuffers(TestCase):
    """
    Tests related to the client internal buffers
    """
    def test_thread_local_buffer(self):
        # the internal buffer must be thread-safe
        tb = ThreadLocalSpanBuffer()

        def _set_get():
            eq_(tb.get(), None)
            span = Span(tracer=None, name='client.testing')
            tb.set(span)
            eq_(span, tb.get())

        threads = [threading.Thread(target=_set_get) for _ in range(20)]

        for t in threads:
            t.daemon = True
            t.start()

        for t in threads:
            t.join()

    def test_trace_buffer_limit(self):
        # the trace buffer must have a limit, if the limit is reached a
        # trace must be discarded
        trace_buff = TraceBuffer(max_size=1)
        span_1 = Span(tracer=None, name='client.testing')
        span_2 = Span(tracer=None, name='client.testing')
        trace_buff.add(span_1)
        trace_buff.add(span_2)
        eq_(len(trace_buff._things), 1)
        eq_(trace_buff._things[0], span_2)

    def test_trace_buffer_closed(self):
        # the trace buffer must not add new elements if the buffer is closed
        trace_buff = TraceBuffer()
        trace_buff.close()
        span = Span(tracer=None, name='client.testing')
        result = trace_buff.add(span)

        # the item must not be added and the result should be False
        eq_(len(trace_buff._things), 0)
        eq_(result, False)

    def test_trace_buffer_pop(self):
        # the trace buffer must return all internal traces
        trace_buff = TraceBuffer()
        span_1 = Span(tracer=None, name='client.testing')
        span_2 = Span(tracer=None, name='client.testing')
        trace_buff.add(span_1)
        trace_buff.add(span_2)
        eq_(len(trace_buff._things), 2)

        # get the traces and be sure that the queue is empty
        traces = trace_buff.pop()
        eq_(len(trace_buff._things), 0)
        eq_(len(traces), 2)
        ok_(span_1 in traces)
        ok_(span_2 in traces)

    def test_trace_buffer_empty_pop(self):
        # the trace buffer must return None if it's empty
        trace_buff = TraceBuffer()
        traces = trace_buff.pop()
        eq_(traces, None)

    def test_trace_buffer_without_cap(self):
        # the trace buffer must have unlimited size if users choose that
        trace_buff = TraceBuffer(max_size=0)
        span_1 = Span(tracer=None, name='client.testing')
        span_2 = Span(tracer=None, name='client.testing')
        trace_buff.add(span_1)
        trace_buff.add(span_2)
        eq_(len(trace_buff._things), 2)
        ok_(span_1 in trace_buff._things)
        ok_(span_2 in trace_buff._things)
