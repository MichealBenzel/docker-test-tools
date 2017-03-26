"""Utility for managing wiremock based services.

For more info about wiremock visit: http://wiremock.org
"""
import os
import json
import glob
import logging

import requests


class WiremockError(Exception):
    """Raised on wiremock controller failures."""
    pass


class WiremockController(object):
    """Utility for managing wiremock based services.

    Usage example:

    >>> controller = WiremockController(url='http://test.service:9999')
    >>> controller.set_mapping_from_dir('some/config/dir')
    >>> controller.reset_mapping()
    """
    def __init__(self, url):
        """Initialize the wiremock controller.

        :param str url: wiremock service url.
        """
        self.url = url
        self.admin_url = os.path.join(url, "__admin")
        self.admin_mapping_url = os.path.join(self.admin_url, "mappings")
        self.mapping_reset_url = os.path.join(self.admin_mapping_url, 'reset')

    def set_mapping_from_dir(self, dir_path):
        """Set wiremock service mapping based on given directory.

        :param str dir_path: directory path to scan - should contain json mapping files.
        """
        logging.debug('Setting service %s wiremock mapping using directory %s', self.url, dir_path)
        mapping_files_pattern = os.path.join(dir_path, '*.json')
        self.set_mapping_from_files(glob.iglob(mapping_files_pattern))

    def set_mapping_from_files(self, json_paths):
        """Set wiremock service mapping based on given json paths.

        :param list json_paths: list of json stub file paths.
        """
        for json_path in json_paths:
            self.set_mapping_from_file(json_path)

    def set_mapping_from_file(self, json_path):
        """Set wiremock service mapping based on given json path.

        :param str json_path: json stub file path.
        """
        logging.debug('Setting service %s wiremock mapping using file %s', self.url, json_path)
        with open(json_path, 'r') as json_file:
            json_object = json.load(json_file)
        self.set_mapping_from_json(json_object)

    def set_mapping_from_json(self, json_object):
        """Set wiremock service mapping based on given json object.

        :param json_object: json data of mapping stub.
        :raise WiremockError: on failure to configure service.
        """
        logging.debug('Setting service %s wiremock mapping using json: %s', self.url, json_object)
        try:
            requests.post(self.admin_mapping_url, json=json_object).raise_for_status()
        except:
            logging.exception("Failed setting service %s wiremock mapping using json: %s",  self.url, json_object)
            raise WiremockError("Failed setting service %s wiremock mapping using json: %s" % (self.url, json_object))

    def reset_mapping(self):
        """Reset wiremock service mapping.

        :raise WiremockError: on failure to reset service mapping.
        """
        logging.debug('Resetting %s wiremock mapping', self.url)
        try:
            requests.post(self.mapping_reset_url).raise_for_status()
        except:
            logging.exception('Failed resetting %s wiremock mapping', self.url)
            raise WiremockError('Failed resetting %s wiremock mapping' % self.url)