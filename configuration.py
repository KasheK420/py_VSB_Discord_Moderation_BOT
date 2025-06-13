import json
from threading import Lock


class Configuration:
    _singleton = None
    _lock = Lock()

    def __init__(self):
        """
        Initializes the Configuration singleton instance.
        Loads the configuration from 'configuration.json'.
        """
        if Configuration._singleton is not None:
            raise Exception("Configuration is a singleton and has already been initialized.")
        Configuration._singleton = self
        self.conf = {}
        self.refresh()

    def refresh(self):
        """
        Refreshes the configuration cache by reloading 'configuration.json'.
        """
        try:
            with open("configuration.json", encoding="utf-8") as file:
                self.conf = json.load(file)
        except FileNotFoundError:
            raise Exception("Configuration file 'configuration.json' not found.")
        except json.JSONDecodeError as e:
            raise Exception(f"Configuration file is not a valid JSON: {e}")
        except Exception as e:
            raise Exception(f"Failed to load configuration: {e}")

    @staticmethod
    def get_instance():
        """
        Ensures that a single instance of Configuration exists.
        Returns the singleton instance.
        """
        with Configuration._lock:
            if Configuration._singleton is None:
                Configuration()
        return Configuration._singleton

    @staticmethod
    def get(key: str, default=None):
        """
        Fetches a value from the configuration using dot notation.
        Returns the default value if the key does not exist.

        :param key: The dot-separated key (e.g., "channels.audit-log").
        :param default: The default value to return if the key is not found.
        :return: The value corresponding to the key, or the default.
        """
        instance = Configuration.get_instance()
        accessors = key.split(".")
        data = instance.conf
        for accessor in accessors:
            if not isinstance(data, dict):
                return default
            data = data.get(accessor)
            if data is None:
                return default
        return data
