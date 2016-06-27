"""
Trace queries along a session to a cassandra cluster
"""

# stdlib
import logging

# project
from ...util import deep_getattr

# 3p
_installed = False
try:
    from cassandra.cluster import Session as session
    _installed = True
except ImportError:
    session = object


log = logging.getLogger(__name__)



def trace(cassandra, tracer, service="cassandra", meta=None):
    """ Trace synchronous cassandra commands by patching the client """
    if inspect.ismodule(cassandra) and deep_getattr(cassandra, "Session.execute"):
        log.debug("Patching cassandra Session class")
        cassandra.Session = functools.partial(
            TracedSession,
            datadog_tracer=tracer,
            datadog_service=service,
        )
    elif hasattr(cassandra, "execute"):
        log.debug("Patching cassandra Session instance")
        safe_patch(cassandra, "execute", _patched_execute_command, service, meta, tracer)


class TracedSession(session):

    def __init__(self, *args, **kwargs):
        self._datadog_tracer = kwargs.pop("datadog_tracer", None)
        self._datadog_service = kwargs.pop("datadog_service", None)
        self._datadog_tags = kwargs.pop("datadog_tags", None)
        super(TracedSession, self).__init__(*args, **kwargs)

    def execute(self, query, *args, **options):
        if not self._datadog_tracer:
            return session.execute(query, *args, **options)

        with self._datadog_tracer.trace("cassandra.query", service=self._datadog_service) as span:
            query_string = _sanitize_query(query)
            span.resource = query_string

            span.set_tag("query", query_string)

            span.set_tags(_extract_session_metas(self))
            cluster = getattr(self, cluster, None)
            span.set_tags(_extract_cluster_metas(cluster))

            result = None
            try:
                result = super(TracedSession, self).execute(query, *args, **options)
                return result
            finally:
                span.set_tags(_extract_result_metas(result))


def _patched_execute_command(orig_command, service, meta, tracer):
    log.debug("Patching cassandra.Session.execute call for service %s", service)

    def traced_execute_command(self, query, *args, **options):
        with tracer.trace("cassandra.query", service=service) as span:
            query_string = _sanitize_query(query)

            span.resource = query_string
            span.set_tag("query", query_string)

            span.set_tags(_extract_session_metas(self))
            cluster = getattr(self, cluster, None)
            span.set_tags(_extract_cluster_metas(cluster))

            try:
                result = orig_command(self, query, *args, **options)
                return result
            finally:
                span.set_tags(_extract_result_metas(result))

    return traced_execute_command


def _extract_session_metas(session):
    metas = {}

    if getattr(session, "keyspace", None):
        # NOTE the keyspace can be overridden explicitly in the query itself
        # e.g. "Select * from trace.hash_to_resource"
        # currently we don't account for this, which is probably fine
        # since the keyspace info is contained in the query even if the metadata disagrees
        metas["keyspace"] = session.keyspace.lower()

    return metas

def _extract_cluster_metas(cluster):
    metas = {}
    if deep_getattr(cluster, "metadata.cluster_name"):
        metas["cluster_name"] = cluster.metadata.cluster_name
        # Needed for hostname grouping
        metas["out.section"] = cluster.metadata.cluster_name

    if getattr(cluster, "port", None):
        metas["port"] = cluster.port

    if getattr(cluster, "contact_points", None):
        metas["contact_points"] = cluster.contact_points
        # Use the first contact point as a persistent host
        if isinstance(cluster.contact_points, list) and len(cluster.contact_points) > 0:
            metas["out.host"] = cluster.contact_points[0]

    if getattr(cluster, "compression", None):
        metas["compression"] = cluster.compression
    if getattr(cluster, "cql_version", None):
        metas["cql_version"] = cluster.cql_version

    return metas

def _extract_result_metas(result):
    metas = {}
    if deep_getattr(result, "response_future.query"):
        query = result.response_future.query

        if getattr(query, "consistency_level", None):
            metas["consistency_level"] = query.consistency_level
        if getattr(query, "keyspace", None):
            # Overrides session.keyspace if the query has been prepared against a particular
            # keyspace
            metas["keyspace"] = query.keyspace.lower()

    if hasattr(result, "has_more_pages"):
        if result.has_more_pages:
            metas["paginated"] = True
        else:
            metas["paginated"] = False

    # NOTE(aaditya): this number only reflects the first page of results
    # which could be misleading. But a true count would require iterating through
    # all pages which is expensive
    if hasattr(result, "current_rows"):
        result_rows = result.current_rows or []
        metas["db.rowcount"] = len(result_rows)

    return metas

def _sanitize_query(query):
    """ Sanitize the query to something ready for the agent receiver
    - Cast to unicode
    - truncate if needed
    """
    # TODO (aaditya): fix this hacky type check. we need it to avoid circular imports
    if type(query).__name__ in ('SimpleStatement', 'PreparedStatement'):
        # reset query if a string is available
        query = getattr(query, "query_string", query)

    return unicode(query)[:RESOURCE_MAX_LENGTH]
