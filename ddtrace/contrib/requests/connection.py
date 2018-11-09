import logging

import ddtrace
from ddtrace import config

from ...compat import parse
from ...ext import http
from ...propagation.http import HTTPPropagator
from .constants import DEFAULT_SERVICE

log = logging.getLogger(__name__)


def _extract_service_name(session, span, hostname=None):
    """Extracts the right service name based on the following logic:
    - `requests` is the default service name
    - users can change it via `session.service_name = 'clients'`
    - if the Span doesn't have a parent, use the set service name
      or fallback to the default
    - if the Span has a parent, use the set service name or the
      parent service value if the set service name is the default
    - if `split_by_domain` is used, always override users settings
      and use the network location as a service name

    The priority can be represented as:
    Updated service name > parent service name > default to `requests`.
    """
    cfg = config.get_from(session)
    if cfg['split_by_domain'] and hostname:
        return hostname

    service_name = cfg['service_name']
    if (service_name == DEFAULT_SERVICE and
            span._parent is not None and
            span._parent.service is not None):
        service_name = span._parent.service
    return service_name


def _wrap_send(func, instance, args, kwargs):
    """Trace the `Session.send` instance method"""
    # TODO[manu]: we already offer a way to provide the Global Tracer
    # and is ddtrace.tracer; it's used only inside our tests and can
    # be easily changed by providing a TracingTestCase that sets common
    # tracing functionalities.
    tracer = getattr(instance, 'datadog_tracer', ddtrace.tracer)

    # skip if tracing is not enabled
    if not tracer.enabled:
        return func(*args, **kwargs)

    request = kwargs.get('request') or args[0]
    if not request:
        return func(*args, **kwargs)

    # sanitize url of query
    parsed_uri = parse.urlparse(request.url)
    hostname = parsed_uri.hostname
    if parsed_uri.port:
        hostname = '{}:{}'.format(hostname, parsed_uri.port)
    sanitized_url = parse.urlunparse((
        parsed_uri.scheme,
        parsed_uri.netloc,
        parsed_uri.path,
        parsed_uri.params,
        None, # drop parsed_uri.query
        parsed_uri.fragment
    ))

    with tracer.trace('requests.request', span_type=http.TYPE) as span:
        # update the span service name before doing any action
        span.service = _extract_service_name(instance, span, hostname=hostname)

        # propagate distributed tracing headers
        if config.get_from(instance).get('distributed_tracing'):
            propagator = HTTPPropagator()
            propagator.inject(span.context, request.headers)

        response = None
        try:
            response = func(*args, **kwargs)
            return response
        finally:
            try:
                span.set_tag(http.METHOD, request.method.upper())
                span.set_tag(http.URL, sanitized_url)
                if response is not None:
                    span.set_tag(http.STATUS_CODE, response.status_code)
                    # `span.error` must be an integer
                    span.error = int(500 <= response.status_code)
            except Exception:
                log.debug("requests: error adding tags", exc_info=True)
