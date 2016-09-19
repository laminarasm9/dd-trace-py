
# stdlib
import logging
import random

# 3p
from wrapt import ObjectProxy

# project
import ddtrace
from ddtrace.ext import memcached
from ddtrace.ext import net
from .addrs import parse_addresses


log = logging.getLogger(__name__)


class TracedClient(ObjectProxy):
    """ TracedClient is a proxy for a pylibmc.Client that times it's network operations. """

    _service = None
    _tracer = None

    def __init__(self, client, service=memcached.SERVICE, tracer=None):
        """ Create a traced client that wraps the given memcached client. """
        super(TracedClient, self).__init__(client)
        self._service = service
        self._tracer = tracer or ddtrace.tracer  # default to the global client

        # attempt to collect the pool of urls this client talks to
        try:
            self._addresses = parse_addresses(client.addresses)
        except Exception:
            log.exception("error setting addresses")

        # attempt to set the service info
        try:
            self._tracer.set_service_info(
                service=service,
                app=memcached.SERVICE,
                app_type=memcached.TYPE)
        except Exception:
            log.exception("error setting service info")

    def clone(self, *args, **kwargs):
        # rewrap new connections.
        cloned = self.__wrapped__.clone(*args, **kwargs)
        return TracedClient(cloned, tracer=self._tracer, service=self._service)

    def get(self, *args, **kwargs):
        return self._trace_cmd("get", *args, **kwargs)

    def set(self, *args, **kwargs):
        return self._trace_cmd("set", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._trace_cmd("delete", *args, **kwargs)

    def gets(self, *args, **kwargs):
        return self._trace_cmd("gets", *args, **kwargs)

    def touch(self, *args, **kwargs):
        return self._trace_cmd("touch", *args, **kwargs)

    def cas(self, *args, **kwargs):
        return self._trace_cmd("cas", *args, **kwargs)

    def incr(self, *args, **kwargs):
        return self._trace_cmd("incr", *args, **kwargs)

    def decr(self, *args, **kwargs):
        return self._trace_cmd("decr", *args, **kwargs)

    def append(self, *args, **kwargs):
        return self._trace_cmd("append", *args, **kwargs)

    def prepend(self, *args, **kwargs):
        return self._trace_cmd("prepend", *args, **kwargs)

    def get_multi(self, *args, **kwargs):
        return self._trace_multi_cmd("get_multi", *args, **kwargs)

    def set_multi(self, *args, **kwargs):
        return self._trace_multi_cmd("set_multi", *args, **kwargs)

    def delete_multi(self, *args, **kwargs):
        return self._trace_multi_cmd("delete_multi", *args, **kwargs)

    def _trace_cmd(self, method_name, *args, **kwargs):
        """ trace the execution of the method with the given name and will
            patch the first arg.
        """
        method = getattr(self.__wrapped__, method_name)
        with self._span(method_name) as span:

            if args:
                span.set_tag(memcached.QUERY, "%s %s" % (method_name, args[0]))

            return method(*args, **kwargs)

    def _trace_multi_cmd(self, method_name, *args, **kwargs):
        """ trace the execution of the multi command with the given name. """
        method = getattr(self.__wrapped__, method_name)
        with self._span(method_name) as span:

            pre = kwargs.get('key_prefix')
            if pre:
                span.set_tag(memcached.QUERY, "%s %s" % (method_name, pre))

            return method(*args, **kwargs)

    def _span(self, cmd_name):
        """ Return a span timing the given command. """
        span = self._tracer.trace(
            "memcached.cmd",
            service=self._service,
            resource=cmd_name,
            span_type="cache")

        try:
            self._tag_span(span)
        except Exception:
            log.exception("error tagging span")

        return span

    def _tag_span(self, span):
        # FIXME[matt] the host selection is buried in c code. we can't tell what it's actually
        # using, so fallback to randomly choosing one. can we do better?
        if self._addresses:
            _, host, port, _ = random.choice(self._addresses)
            span.set_meta(net.TARGET_HOST, host)
            span.set_meta(net.TARGET_PORT, port)


