import time

# 3p
from django import template
from django.template.backends.dummy import TemplateStrings
from nose.tools import eq_

from ddtrace.contrib.django.templates import patch_template
from ddtrace.tracer import Tracer
from ...test_tracer import DummyWriter


def test_template():
    # trace and ensure it works
    writer = DummyWriter()
    tracer = Tracer(writer=writer)
    assert not writer.pop()
    patch_template(tracer)

    # setup a test template
    params = {
        'DIRS': [],
        'APP_DIRS': True,
        'NAME': 'foo',
        'OPTIONS': {},
    }
    engine = TemplateStrings(params)
    engine.debug = False
    engine.template_libraries = None
    engine.template_builtins = None

    t = template.Template("hello {{name}}", engine=engine)
    c = template.Context({'name':'matt'})

    start = time.time()
    eq_(t.render(c), 'hello matt')
    end = time.time()

    spans = writer.pop()
    assert spans, spans
    eq_(len(spans), 1)

    span = spans[0]
    eq_(span.span_type, 'template')
    eq_(span.name, 'django.template')
    eq_(span.get_tag('django.template_name'), 'unknown')
    assert start < span.start < span.start + span.duration < end

