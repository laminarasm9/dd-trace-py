"""Samplers manage the client-side trace sampling

Any `sampled = False` trace won't be written, and can be ignored by the instrumentation.
"""

import logging
import array

from .span import MAX_TRACE_ID

log = logging.getLogger(__name__)


class DefaultSampler(object):
    """Default sampler, sampling all the traces"""

    def sample(self, span):
        span.sampled = True


class RateSampler(object):
    """Sampler based on a rate

    Keep (100 * `sample_rate`)% of the traces.
    It samples randomly, its main purpose is to reduce the instrumentation footprint.
    """

    def __init__(self, sample_rate):
        if sample_rate <= 0:
            log.error("sample_rate is negative or null, disable the Sampler")
            sample_rate = 1
        elif sample_rate > 1:
            sample_rate = 1

        self.set_sample_rate(sample_rate)

        log.info("initialized RateSampler, sample %s%% of traces", 100 * sample_rate)

    def set_sample_rate(self, sample_rate):
        self.sample_rate = sample_rate
        self.sampling_id_threshold = sample_rate * MAX_TRACE_ID

    def sample(self, span):
        span.sampled = span.trace_id <= self.sampling_id_threshold
        # `weight` is an attribute applied to all spans to help scaling related statistics
        span.weight = 1 / (self.sample_rate or 1)


class ThroughputSampler(object):
    """Sampler applying a strict limit over the trace volume

    Stop tracing once reached more than `tps` traces per second.
    Computation is based on a circular buffer over the last `BUFFER_DURATION` with a `BUFFER_SIZE` size.
    """

    # Reasonable values
    BUCKETS_PER_S = 5
    BUFFER_DURATION = 4
    BUFFER_SIZE = BUCKETS_PER_S * BUFFER_DURATION

    def __init__(self, tps):
        self.tps = tps

        self.limit = tps * self.BUFFER_DURATION

        # Circular buffer counting sampled traces over the last `BUFFER_DURATION`
        self.counter = array.array('L', [0] * self.BUFFER_SIZE)
        # Last time we sampled a trace, multiplied by `BUCKETS_PER_S`
        self.last_track_time = 0

        log.info("initialized ThroughputSampler, sample up to %s traces/s", tps)

    def sample(self, span):
        now = int(span.start * self.BUCKETS_PER_S)
        last_track_time = self.last_track_time
        if now > last_track_time:
            self.last_track_time = now
            self.expire_buckets(last_track_time, now)

        span.sampled = self.count_traces() < self.limit

        if span.sampled:
            self.counter[self.key_from_time(now)] += 1

        return span

    def key_from_time(self, t):
        return t % self.BUFFER_SIZE

    def expire_buckets(self, start, end):
        period = min(self.BUFFER_SIZE, (end - start))
        for i in range(period):
            self.counter[self.key_from_time(start + i + 1)] = 0

    def count_traces(self):
        return sum(self.counter)
