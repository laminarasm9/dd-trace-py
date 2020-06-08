"""CPU profiling collector."""
from __future__ import absolute_import

import collections
import logging
import sys
import threading
import weakref

from ddtrace import compat
from ddtrace.profiling import _attr
from ddtrace.profiling import _periodic
from ddtrace.profiling import collector
from ddtrace.profiling import event
from ddtrace.profiling.collector import _traceback
from ddtrace.utils import formats
from ddtrace.vendor import attr
from ddtrace.vendor import six


_LOG = logging.getLogger(__name__)


if "gevent" in sys.modules:
    try:
        import gevent.monkey
    except ImportError:
        _LOG.error("gevent loaded but unable to import gevent.monkey")
        from ddtrace.vendor.six.moves._thread import get_ident as _thread_get_ident
    else:
        _thread_get_ident = gevent.monkey.get_original("thread" if six.PY2 else "_thread", "get_ident")

    # NOTE: bold assumption: this module is always imported by the MainThread.
    # The python `threading` module makes that assumption and it's beautiful we're going to do the same.
    _main_thread_id = _thread_get_ident()
else:
    from ddtrace.vendor.six.moves._thread import get_ident as _thread_get_ident
    if six.PY2:
        _main_thread_id = threading._MainThread().ident
    else:
        _main_thread_id = threading.main_thread().ident


# NOTE: Do not use LOG here. This code runs under a real OS thread and is unable to acquire any lock of the `logging`
# module without having gevent crashing our dedicated thread.


# Those are special features that might not be available depending on your Python version and platform
FEATURES = {
    "cpu-time": False,
    "stack-exceptions": False,
}

IF UNAME_SYSNAME == "Linux":
    FEATURES['cpu-time'] = True

    from posix.time cimport timespec, clock_gettime
    from posix.types cimport clockid_t
    from cpython.exc cimport PyErr_SetFromErrno

    cdef extern from "<pthread.h>":
        # POSIX says this might be a struct, but CPython relies on it being an unsigned long.
        # We should be defining pthread_t here like this:
        # ctypedef unsigned long pthread_t
        # but e.g. musl libc defines pthread_t as a struct __pthread * which breaks the arithmetic Cython
        # wants to do.
        # We pay this with a warning at compilation time, but it works anyhow.
        int pthread_getcpuclockid(unsigned long thread, clockid_t *clock_id)

    cdef p_pthread_getcpuclockid(tid):
        cdef clockid_t clock_id
        if pthread_getcpuclockid(tid, &clock_id) == 0:
            return clock_id
        PyErr_SetFromErrno(OSError)

    # Python < 3.3 does not have `time.clock_gettime`
    cdef p_clock_gettime_ns(clk_id):
        cdef timespec tp
        if clock_gettime(clk_id, &tp) == 0:
            return int(tp.tv_nsec + tp.tv_sec * 10e8)
        PyErr_SetFromErrno(OSError)

    class _ThreadTime(object):
        def __init__(self):
            # This uses a tuple of (thread unique id, pthread_id) as the key to identify the thread: you'd think using
            # the pthread_t id would be enough, but the glibc reuses the id.
            self._last_thread_time = {}

        def __call__(self, thread_ids):
            threads_cpu_time = {}
            for pthread_id, thread_native_id in thread_ids.items():
                key = (pthread_id, thread_native_id)
                # TODO: Use QueryThreadCycleTime on Windows?
                # ⚠ WARNING ⚠
                # `pthread_getcpuclockid` can make Python segfault if the thread is does not exist anymore.
                # In order avoid this, this function must be called with the GIL being held the entire time.
                # This is why this whole file is compiled down to C: we make sure we never release the GIL between
                # calling sys._current_frames() and pthread_getcpuclockid, making sure no thread disappeared.
                try:
                    clock_id = p_pthread_getcpuclockid(pthread_id)
                except OSError:
                    cpu_time = self._last_thread_time.get(key, 0)
                else:
                    try:
                        cpu_time = p_clock_gettime_ns(clock_id)
                    except OSError:
                        cpu_time = self._last_thread_time.get(key, 0)
                # Do a max(0, …) here just in case the result is < 0:
                # This should never happen, but it can happen if the one chance in a billion happens:
                # A new thread has been created and has the same native id and the same pthread_id.
                threads_cpu_time[pthread_id] = max(0, cpu_time - self._last_thread_time.get(key, cpu_time))
                self._last_thread_time[key] = cpu_time

            # Clear cache
            keys = list(thread_ids.items())
            for key in list(self._last_thread_time.keys()):
                if key not in keys:
                    del self._last_thread_time[key]

            return threads_cpu_time
ELSE:
    class _ThreadTime(object):
        def __init__(self):
            self._last_process_time = compat.process_time_ns()

        def __call__(self, thread_ids):
            current_process_time = compat.process_time_ns()
            cpu_time = current_process_time - self._last_process_time
            self._last_process_time = current_process_time
            # Spread the consumed CPU time on all threads.
            # It's not fair, but we have no clue which CPU used more unless we can use `pthread_getcpuclockid`
            # Check that we don't have zero thread — _might_ very rarely happen at shutdown
            nb_threads = len(thread_ids)
            if nb_threads == 0:
                cpu_time = 0
            else:
                cpu_time //= nb_threads
            return {
                tid: cpu_time
                for tid in thread_ids
            }


@event.event_class
class StackBasedEvent(event.SampleEvent):
    thread_id = attr.ib(default=None)
    thread_name = attr.ib(default=None)
    thread_native_id = attr.ib(default=None)
    frames = attr.ib(default=None)
    nframes = attr.ib(default=None)
    trace_ids = attr.ib(default=None)


@event.event_class
class StackSampleEvent(StackBasedEvent):
    """A sample storing executions frames for a thread."""

    # Wall clock
    wall_time_ns = attr.ib(default=0)
    # CPU time in nanoseconds
    cpu_time_ns = attr.ib(default=0)


@event.event_class
class StackExceptionSampleEvent(StackBasedEvent):
    """A a sample storing raised exceptions and their stack frames."""

    exc_type = attr.ib(default=None)


# The head lock (the interpreter mutex) is only exposed in a data structure in Python ≥ 3.7
IF PY_MAJOR_VERSION >= 3 and PY_MINOR_VERSION >= 7:
    FEATURES['stack-exceptions'] = True

    from cpython cimport PyInterpreterState
    from cpython cimport PyInterpreterState_Head, PyInterpreterState_Next
    from cpython cimport PyInterpreterState_ThreadHead, PyThreadState_Next

    from cpython.object cimport PyObject

    from cpython.pythread cimport (
        PyThread_acquire_lock, PyThread_release_lock,
        WAIT_LOCK,
        PyThread_type_lock,
        PY_LOCK_ACQUIRED
    )

    cdef extern from "<Python.h>":
        # This one is provided as an opaque struct from Cython's cpython/pystate.pxd,
        # but we need to access some of its fields so we redefine it here.
        ctypedef struct PyThreadState:
            unsigned long thread_id
            PyObject* frame

        _PyErr_StackItem * _PyErr_GetTopmostException(PyThreadState *tstate)

        ctypedef struct _PyErr_StackItem:
            PyObject* exc_type
            PyObject* exc_value
            PyObject* exc_traceback

    IF PY_MINOR_VERSION == 7:
        # Python 3.7
        cdef extern from "<internal/pystate.h>":

            cdef struct pyinterpreters:
                PyThread_type_lock mutex

            ctypedef struct _PyRuntimeState:
                pyinterpreters interpreters

            cdef extern _PyRuntimeState _PyRuntime

    ELIF PY_MINOR_VERSION >= 8:
        # Python 3.8
        cdef extern from "<internal/pycore_pystate.h>":

            cdef struct pyinterpreters:
                PyThread_type_lock mutex

            ctypedef struct _PyRuntimeState:
                pyinterpreters interpreters

            cdef extern _PyRuntimeState _PyRuntime


cdef get_thread_name(thread_id):
    # This is a special case for gevent:
    # When monkey patching, gevent replaces all active threads by their greenlet equivalent.
    # This means there's no chance to find the MainThread in the list of _active threads.
    # Therefore we special case the MainThread that way.
    # If native threads are started using gevent.threading, they will be inserted in threading._active
    # so we will find them normally.
    if thread_id == _main_thread_id:
        return "MainThread"

    # Since we own the GIL, we can safely run this and assume no change will happen, without bothering to lock anything
    try:
        return threading._active[thread_id].name
    except KeyError:
        try:
            return threading._limbo[thread_id].name
        except KeyError:
            return "Anonymous Thread %d" % thread_id


cdef stack_collect(ignore_profiler, thread_time, max_nframes, interval, wall_time, thread_span_links):
    current_exceptions = []

    IF PY_MAJOR_VERSION >= 3 and PY_MINOR_VERSION >= 7:
        cdef PyInterpreterState* interp
        cdef PyThreadState* tstate
        cdef _PyErr_StackItem* exc_info
        cdef PyThread_type_lock lmutex = _PyRuntime.interpreters.mutex

        running_threads = []

        # This is an internal lock but we do need it.
        # See https://bugs.python.org/issue1021318
        if PyThread_acquire_lock(lmutex, WAIT_LOCK) == PY_LOCK_ACQUIRED:
            # Do not try to do anything fancy here:
            # Even calling print() will deadlock the program has it will try
            # to lock the GIL and somehow touching this mutex.
            try:
                interp = PyInterpreterState_Head()

                while interp:
                    tstate = PyInterpreterState_ThreadHead(interp)
                    while tstate:
                        # The frame can be NULL
                        if tstate.frame:
                            running_threads.append((tstate.thread_id, <object>tstate.frame))

                        exc_info = _PyErr_GetTopmostException(tstate)
                        if exc_info and exc_info.exc_type and exc_info.exc_traceback:
                            current_exceptions.append(
                                (tstate.thread_id, <object>exc_info.exc_type, <object>exc_info.exc_traceback)
                            )

                        tstate = PyThreadState_Next(tstate)

                    interp = PyInterpreterState_Next(interp)
            finally:
                PyThread_release_lock(lmutex)
    ELSE:
        running_threads = list(sys._current_frames().items())

    running_thread_ids = {t[0] for t in running_threads}

    if thread_span_links:
        thread_span_links.clear_threads(running_thread_ids)

    if ignore_profiler:
        running_thread_ids -= _periodic.PERIODIC_THREAD_IDS

    # Build a dict of pthread_t id -> native thread id
    # We need to use both as pthread_id can be reused for new thread, messing with the CPU time clock
    thread_native_ids = {}

    for thread_id in running_thread_ids:
        try:
            thread_obj = threading._active[thread_id]
        except KeyError:
            # This should not happen, unless somebody started a thread without
            # using the `threading` module; in that case, ignore the thread altogether.
            # In that case, well… just use the thread_id as native_id 🤞
            native_id = thread_id
        else:
            # We prioritize using native ids since we expect them to be surely unique for a program. This is less true
            # for hashes since they are relative to the memory address which can easily be the same across different
            # objects.
            try:
                native_id = thread_obj.native_id
            except AttributeError:
                # Python < 3.8
                native_id = hash(thread_obj)

        thread_native_ids[thread_id] = native_id

    cpu_time = thread_time(thread_native_ids)

    stack_events = []
    for tid, frame in running_threads:
        if ignore_profiler and tid in _periodic.PERIODIC_THREAD_IDS:
            continue
        if thread_span_links:
            spans = thread_span_links.get_active_leaf_spans_from_thread_id(tid)
        else:
            spans = set()
        frames, nframes = _traceback.pyframe_to_frames(frame, max_nframes)
        stack_events.append(
            StackSampleEvent(
                thread_id=tid,
                thread_native_id=thread_native_ids.get(tid),
                thread_name=get_thread_name(tid),
                trace_ids=set(span.trace_id for span in spans),
                nframes=nframes, frames=frames,
                wall_time_ns=wall_time,
                cpu_time_ns=cpu_time[tid],
                sampling_period=int(interval * 1e9),
            ),
        )

    exc_events = []
    for tid, exc_type, exc_traceback in current_exceptions:
        if ignore_profiler and tid in _periodic.PERIODIC_THREAD_IDS:
            continue
        frames, nframes = _traceback.traceback_to_frames(exc_traceback, max_nframes)
        exc_events.append(
            StackExceptionSampleEvent(
                thread_id=tid,
                thread_name=get_thread_name(tid),
                thread_native_id=thread_native_ids.get(tid),
                nframes=nframes,
                frames=frames,
                sampling_period=int(interval * 1e9),
                exc_type=exc_type,
            ),
        )

    return stack_events, exc_events


@attr.s(slots=True, eq=False)
class _ThreadSpanLinks(object):

    _thread_id_to_spans = attr.ib(factory=lambda: collections.defaultdict(weakref.WeakSet), repr=False, init=False)
    # WeakSet is not thread safe unfortunately
    _lock = attr.ib(factory=threading.Lock, repr=False, init=False)

    def link_span(self, span):
        """Link a span to its running environment.

        Track threads, tasks, etc.
        """
        # In _theory_, this should be thread-safe because it's entirely done in C.
        # Since it's a CPython specific detail, we ignore that fact and play it self by locking.
        with self._lock:
            self._thread_id_to_spans[_thread_get_ident()].add(span)

    def clear_threads(self, existing_thread_ids):
        """Clear the stored list of threads based on the list of existing thread ids.

        If any thread that is part of this list was stored, its data will be deleted.

        :param existing_thread_ids: A set of thread ids to keep.
        """
        with self._lock:
            # Iterate over a copy of the list of keys since it's mutated during our iteration.
            for thread_id in list(self._thread_id_to_spans.keys()):
                if thread_id not in existing_thread_ids:
                    del self._thread_id_to_spans[thread_id]

    def get_active_leaf_spans_from_thread_id(self, thread_id):
        """Return the latest active spans for a thread.

        In theory this should return a single span, though if multiple children span are active without being finished,
        there can be several spans returned.

        :param thread_id: The thread id.
        :return: A set with the active spans.
        """
        with self._lock:
            spans = set(self._thread_id_to_spans.get(thread_id, ()))

        # Iterate over a copy so we can modify the original
        for span in spans.copy():
            if not span.finished:
                try:
                    spans.remove(span._parent)
                except KeyError:
                    pass

        return {span for span in spans if not span.finished}


@attr.s(slots=True)
class StackCollector(collector.PeriodicCollector):
    """Execution stacks collector."""
    # This is the minimum amount of time the thread will sleep between polling interval,
    # no matter how fast the computer is.
    MIN_INTERVAL_TIME = 0.01    # sleep at least 10 ms

    # This need to be a real OS thread in order to catch
    _real_thread = True
    _interval = attr.ib(default=MIN_INTERVAL_TIME, repr=False)

    max_time_usage_pct = attr.ib(factory=_attr.from_env("DD_PROFILING_MAX_TIME_USAGE_PCT", 2, float))
    nframes = attr.ib(factory=_attr.from_env("DD_PROFILING_MAX_FRAMES", 64, int))
    ignore_profiler = attr.ib(factory=_attr.from_env("DD_PROFILING_IGNORE_PROFILER", True, formats.asbool))
    tracer = attr.ib(default=None)
    _thread_time = attr.ib(init=False, repr=False)
    _last_wall_time = attr.ib(init=False, repr=False)
    _thread_span_links = attr.ib(default=None, init=False, repr=False)

    @max_time_usage_pct.validator
    def _check_max_time_usage(self, attribute, value):
        if value <= 0 or value > 100:
            raise ValueError("Max time usage percent must be greater than 0 and smaller or equal to 100")

    def start(self):
        self._thread_time = _ThreadTime()
        self._last_wall_time = compat.monotonic_ns()
        if self.tracer is not None:
            self._thread_span_links = _ThreadSpanLinks()
            self.tracer.on_start_span(self._thread_span_links.link_span)
        super(StackCollector, self).start()

    def stop(self):
        super(StackCollector, self).stop()
        if self.tracer is not None:
            self.tracer.deregister_on_start_span(self._thread_span_links.link_span)

    def _compute_new_interval(self, used_wall_time_ns):
        interval = (used_wall_time_ns / (self.max_time_usage_pct / 100.0)) - used_wall_time_ns
        return max(interval / 1e9, self.MIN_INTERVAL_TIME)

    def collect(self):
        # Compute wall time
        now = compat.monotonic_ns()
        wall_time = now - self._last_wall_time
        self._last_wall_time = now

        all_events = stack_collect(
            self.ignore_profiler, self._thread_time, self.nframes, self.interval, wall_time, self._thread_span_links,
        )

        used_wall_time_ns = compat.monotonic_ns() - now
        self.interval = self._compute_new_interval(used_wall_time_ns)

        return all_events
