
# stdlib
import unittest

# 3p
from nose.tools import eq_
from cassandra.cluster import Cluster

# project
from tests.contrib.config import CASSANDRA_CONFIG
from tests.test_tracer import get_dummy_tracer
from ddtrace.contrib.cassandra.patch import patch, unpatch
from ddtrace.contrib.cassandra.session import get_traced_cassandra, SERVICE
from ddtrace.ext import net, cassandra as cassx, errors
from ddtrace import Pin


class CassandraBase(object):
    """
    Needs a running Cassandra
    """
    TEST_QUERY = "SELECT * from test.person"
    TEST_KEYSPACE = "test"
    TEST_PORT = str(CASSANDRA_CONFIG['port'])
    TEST_SERVICE = 'test-cassandra'

    def _traced_session(self):
        # implement me
        pass

    def tearDown(self):
        self.cluster.connect().execute("DROP KEYSPACE IF EXISTS test")

    def setUp(self):
        if not Cluster:
            raise unittest.SkipTest("cassandra.cluster.Cluster is not available.")

        self.cluster = Cluster(port=CASSANDRA_CONFIG['port'])
        session = self.cluster.connect()
        session.execute("""CREATE KEYSPACE if not exists test WITH REPLICATION = {
            'class' : 'SimpleStrategy',
            'replication_factor': 1
        }""")
        session.execute("CREATE TABLE if not exists test.person (name text PRIMARY KEY, age int, description text)")
        session.execute("""INSERT INTO test.person (name, age, description) VALUES ('Cassandra', 100, 'A cruel mistress')""")

    def _assert_result_correct(self, result):
        eq_(len(result.current_rows), 1)
        for r in result:
            eq_(r.name, "Cassandra")
            eq_(r.age, 100)
            eq_(r.description, "A cruel mistress")

    def test_get_traced_cassandra(self):
        session, writer = self._traced_session()
        result = session.execute(self.TEST_QUERY)
        self._assert_result_correct(result)

        spans = writer.pop()
        assert spans, spans

        # another for the actual query
        eq_(len(spans), 1)

        query = spans[0]
        eq_(query.service, self.TEST_SERVICE)
        eq_(query.resource, self.TEST_QUERY)
        eq_(query.span_type, cassx.TYPE)

        eq_(query.get_tag(cassx.KEYSPACE), self.TEST_KEYSPACE)
        eq_(query.get_tag(net.TARGET_PORT), self.TEST_PORT)
        eq_(query.get_tag(cassx.ROW_COUNT), "1")
        eq_(query.get_tag(net.TARGET_HOST), "127.0.0.1")

    def test_trace_with_service(self):
        session, writer = self._traced_session()
        session.execute(self.TEST_QUERY)
        spans = writer.pop()
        assert spans
        eq_(len(spans), 1)
        query = spans[0]
        eq_(query.service, self.TEST_SERVICE)

    def test_trace_error(self):
        session, writer = self._traced_session()
        try:
            session.execute("select * from test.i_dont_exist limit 1")
        except Exception:
            pass
        else:
            assert 0

        spans = writer.pop()
        assert spans
        query = spans[0]
        eq_(query.error, 1)
        for k in (errors.ERROR_MSG, errors.ERROR_TYPE, errors.ERROR_STACK):
            assert query.get_tag(k)


class TestOldSchool(CassandraBase):
    """Test Cassandra instrumentation with the legacy interface"""

    TEST_SERVICE = 'test-cassandra-legacy'

    def _traced_session(self):
        tracer = get_dummy_tracer()
        tracer_cluster = get_traced_cassandra(tracer, service=self.TEST_SERVICE)
        session = tracer_cluster(port=CASSANDRA_CONFIG['port']).connect(self.TEST_KEYSPACE)
        return session, tracer.writer


class TestCassPatchDefault(CassandraBase):
    """Test Cassandra instrumentation with patching and default configuration"""

    TEST_SERVICE = SERVICE

    def tearDown(self):
        unpatch()
        CassandraBase.tearDown(self)

    def setUp(self):
        CassandraBase.setUp(self)
        patch()

    def _traced_session(self):
        tracer = get_dummy_tracer()
        cluster = Cluster(port=CASSANDRA_CONFIG['port'])

        Pin.get_from(cluster).clone(tracer=tracer).onto(cluster)
        return cluster.connect(self.TEST_KEYSPACE), tracer.writer

class TestCassPatchAll(TestCassPatchDefault):
    """Test Cassandra instrumentation with patching and custom service on all clusters"""

    TEST_SERVICE = 'test-cassandra-patch-all'

    def tearDown(self):
        unpatch()
        CassandraBase.tearDown(self)

    def setUp(self):
        CassandraBase.setUp(self)
        patch()

    def _traced_session(self):
        tracer = get_dummy_tracer()
        # pin the global Cluster to test if they will conflict
        Pin(service=self.TEST_SERVICE, tracer=tracer).onto(Cluster)
        cluster = Cluster(port=CASSANDRA_CONFIG['port'])

        return cluster.connect(self.TEST_KEYSPACE), tracer.writer


class TestCassPatchOne(TestCassPatchDefault):
    """Test Cassandra instrumentation with patching and custom service on one cluster"""

    TEST_SERVICE = 'test-cassandra-patch-one'

    def tearDown(self):
        unpatch()
        CassandraBase.tearDown(self)

    def setUp(self):
        CassandraBase.setUp(self)
        patch()

    def _traced_session(self):
        tracer = get_dummy_tracer()
        # pin the global Cluster to test if they will conflict
        Pin(service='not-%s' % self.TEST_SERVICE).onto(Cluster)
        cluster = Cluster(port=CASSANDRA_CONFIG['port'])

        Pin(service=self.TEST_SERVICE, tracer=tracer).onto(cluster)
        return cluster.connect(self.TEST_KEYSPACE), tracer.writer

    def test_patch_unpatch(self):
        # Test patch idempotence
        patch()
        patch()

        tracer = get_dummy_tracer()
        Pin.get_from(Cluster).clone(tracer=tracer).onto(Cluster)

        session = Cluster(port=CASSANDRA_CONFIG['port']).connect(self.TEST_KEYSPACE)
        session.execute(self.TEST_QUERY)

        spans = tracer.writer.pop()
        assert spans, spans
        eq_(len(spans), 1)

        # Test unpatch
        unpatch()

        session = Cluster(port=CASSANDRA_CONFIG['port']).connect(self.TEST_KEYSPACE)
        session.execute(self.TEST_QUERY)

        spans = tracer.writer.pop()
        assert not spans, spans

        # Test patch again
        patch()
        Pin.get_from(Cluster).clone(tracer=tracer).onto(Cluster)

        session = Cluster(port=CASSANDRA_CONFIG['port']).connect(self.TEST_KEYSPACE)
        session.execute(self.TEST_QUERY)

        spans = tracer.writer.pop()
        assert spans, spans
