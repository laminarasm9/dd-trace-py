import os
import threading

import pytest

from ddtrace.profiling import _periodic
from ddtrace.profiling import _service


if os.getenv("DD_PROFILE_TEST_GEVENT", False):
    import gevent

    class Event(object):
        """
        We can't use gevent Events here[0], nor can we use native threading
        events (because gevent is not multi-threaded).

        So for gevent, since it's not multi-threaded and will not run greenlets
        in parallel (for our usage here, anyway) we can write a dummy Event
        class which just does a simple busy wait on a shared variable.

        [0] https://github.com/gevent/gevent/issues/891
        """

        state = False

        def wait(self):
            while not self.state:
                gevent.sleep(0.001)

        def set(self):
            self.state = True


else:
    Event = threading.Event


def test_periodic():
    x = {"OK": False}

    thread_started = Event()
    thread_continue = Event()

    def _run_periodic():
        thread_started.set()
        x["OK"] = True
        thread_continue.wait()

    def _on_shutdown():
        x["DOWN"] = True

    t = _periodic.PeriodicRealThread(0.001, _run_periodic, on_shutdown=_on_shutdown)
    t.start()
    thread_started.wait()
    assert t.ident in _periodic.PERIODIC_THREAD_IDS
    thread_continue.set()
    t.stop()
    t.join()
    assert x["OK"]
    assert x["DOWN"]
    assert t.ident not in _periodic.PERIODIC_THREAD_IDS
    if hasattr(threading, "get_native_id"):
        assert t.native_id is not None


def test_periodic_error():
    x = {"OK": False}

    thread_started = Event()
    thread_continue = Event()

    def _run_periodic():
        thread_started.set()
        thread_continue.wait()
        raise ValueError

    def _on_shutdown():
        x["DOWN"] = True

    t = _periodic.PeriodicRealThread(0.001, _run_periodic, on_shutdown=_on_shutdown)
    t.start()
    thread_started.wait()
    assert t.ident in _periodic.PERIODIC_THREAD_IDS
    thread_continue.set()
    t.stop()
    t.join()
    assert "DOWN" not in x
    assert t.ident not in _periodic.PERIODIC_THREAD_IDS


def test_gevent_class():
    if os.getenv("DD_PROFILE_TEST_GEVENT", False):
        assert isinstance(_periodic.PeriodicRealThread(1, sum), _periodic._GeventPeriodicThread)
    else:
        assert isinstance(_periodic.PeriodicRealThread(1, sum), _periodic.PeriodicThread)


def test_periodic_real_thread_name():
    def do_nothing():
        pass

    t = _periodic.PeriodicRealThread(interval=1, target=do_nothing)
    t.start()
    assert t in threading.enumerate()
    t.stop()
    t.join()


def test_periodic_service_start_stop():
    t = _periodic.PeriodicService(1)
    t.start()
    with pytest.raises(_service.ServiceAlreadyRunning):
        t.start()
    t.stop()
    t.join()
    t.stop()
    t.stop()
    t.join()
    t.join()


def test_periodic_join_stop_no_start():
    t = _periodic.PeriodicService(1)
    t.join()
    t.stop()
    t.join()
    t = _periodic.PeriodicService(1)
    t.stop()
    t.join()
    t.stop()
