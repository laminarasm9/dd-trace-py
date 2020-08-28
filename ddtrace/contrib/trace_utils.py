"""
This module contains utility functions for writing ddtrace integrations.
"""


def int_service(config, pin, default=None):
    """Returns the service name for an integration which is internal
    to the application. Internal meaning that the work belongs to the
    user's application. Eg. Web framework, sqlalchemy, servers.

    For internal integrations we prioritize overrides, then global defaults and
    lastly the default provided by the integration.
    """
    config = config or {}

    # Pin has top priority since it is user defined in code
    if pin and pin.service:
        return pin.service

    # Config is next since it is also configured via code
    # Note that both service and service_name are used by
    # integrations.
    if "service" in config and config.service is not None:
        return config.service
    if "service_name" in config and config.service_name is not None:
        return config.service_name

    global_service = config.global_config._get_service()
    if global_service:
        return global_service
    return default


def ext_service(config, pin, default):
    """Returns the service name for an integration which is external
    to the application. External meaning that the integration generates
    spans wrapping code that is outside the scope of the user's application. Eg. A database, RPC, cache, etc.
    """
    config = config or {}

    if pin and pin.service:
        return pin.service

    if "service" in config and config.service is not None:
        return config.service
    if "service_name" in config and config.service_name is not None:
        return config.service_name

    # A default is required since it's an external service.
    return default
