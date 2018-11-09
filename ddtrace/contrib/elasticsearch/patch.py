import elasticsearch
import wrapt
from elasticsearch.exceptions import TransportError

from .quantize import quantize

from ...compat import urlencode
from ...ext import elasticsearch as elasticsearchx, http, AppTypes
from ...pin import Pin
from ...utils.wrappers import unwrap


# NB: We are patching the default elasticsearch.transport module
def patch():

    if getattr(elasticsearch, '_datadog_patch', False):
        return
    setattr(elasticsearch, '_datadog_patch', True)
    wrapt.wrap_function_wrapper('elasticsearch.transport', 'Transport.perform_request', _perform_request)
    Pin(
        service=elasticsearchx.SERVICE,
        app=elasticsearchx.APP,
        app_type=AppTypes.db
    ).onto(elasticsearch.transport.Transport)


def unpatch():
    if getattr(elasticsearch, '_datadog_patch', False):
        setattr(elasticsearch, '_datadog_patch', False)
        unwrap(elasticsearch.transport.Transport, 'perform_request')

def _perform_request(func, instance, args, kwargs):
    pin = Pin.get_from(instance)
    if not pin or not pin.enabled():
        return func(*args, **kwargs)

    with pin.tracer.trace("elasticsearch.query") as span:
        # Don't instrument if the trace is not sampled
        if not span.sampled:
            return func(*args, **kwargs)

        method, url = args
        params = kwargs.get('params')
        body = kwargs.get('body')

        span.service = pin.service
        span.span_type = elasticsearchx.TYPE
        span.set_tag(elasticsearchx.METHOD, method)
        span.set_tag(elasticsearchx.URL, url)
        span.set_tag(elasticsearchx.PARAMS, urlencode(params))
        if method == "GET":
            span.set_tag(elasticsearchx.BODY, instance.serializer.dumps(body))
        status = None

        span = quantize(span)

        try:
            result = func(*args, **kwargs)
        except TransportError as e:
            span.set_tag(http.STATUS_CODE, getattr(e, 'status_code', 500))
            raise

        try:
            # Optional metadata extraction with soft fail.
            if isinstance(result, tuple) and len(result) == 2:
                # elasticsearch<2.4; it returns both the status and the body
                status, data = result
            else:
                # elasticsearch>=2.4; internal change for ``Transport.perform_request``
                # that just returns the body
                data = result

            took = data.get("took")
            if took:
                span.set_metric(elasticsearchx.TOOK, int(took))
        except Exception:
            pass

        if status:
            span.set_tag(http.STATUS_CODE, status)

        return result
