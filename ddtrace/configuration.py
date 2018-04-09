from copy import deepcopy


class ConfigException(Exception):
    """Configuration exception when an integration that is not available
    is called in the `Config` object.
    """
    pass


class Config(object):
    """Configuration object that exposes an API to set and retrieve
    global settings for each integration. All integrations must use
    this instance to register their defaults, so that they're public
    available and can be updated by users.
    """
    def __init__(self):
        # use a dict as underlying storing mechanism
        self._config = {}

    def __getattr__(self, name):
        try:
            return self._config[name]
        except KeyError as e:
            raise ConfigException(
                'Integration "{}" is not registered in this configuration'.format(e.message)
            )

    def _add(self, integration, settings):
        """Internal API that registers an integration with given default
        settings.

        :param str integration: The integration name (i.e. `requests`)
        :param dict settings: A dictionary that contains integration settings;
            to preserve immutability of these values, the dictionary is copied
            since it contains integration defaults.
        """

        self._config[integration] = deepcopy(settings)
