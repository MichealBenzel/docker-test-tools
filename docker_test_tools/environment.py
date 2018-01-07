import os
import logging
import subprocess

import waiting
from functools import partial
from contextlib import contextmanager

from docker_test_tools import logs
from docker_test_tools import stats
from docker_test_tools import utils
from docker_test_tools import config
from docker_test_tools.api_version import get_server_api_version

log = logging.getLogger(__name__)


class EnvironmentController(object):
    """Utility for managing environment operations."""

    def __init__(self, project_name, compose_path, log_path, collect_stats=False, reuse_containers=False):

        self.log_path = log_path
        self.compose_path = compose_path
        self.project_name = project_name
        self.reuse_containers = reuse_containers

        self.environment_variables = self._get_environment_variables()
        self.services = self.get_services()

        self.encoding = self.environment_variables.get('PYTHONIOENCODING', 'utf-8')
        self.work_dir = os.path.dirname(self.log_path)

        self.logs_collector = logs.LogCollector(
            log_path=log_path,
            encoding=self.encoding,
            project_name=project_name,
            compose_path=compose_path,
            environment_variables=self.environment_variables,
        )

        self.plugins = []
        self.plugins.append(self.logs_collector)
        if collect_stats:
            self.plugins.append(stats.StatsCollector(encoding=self.encoding,
                                                     project=self.project_name,
                                                     target_dir_path=self.work_dir,
                                                     environment_variables=self.environment_variables))

    @classmethod
    def from_file(cls, config_path):
        """Return an environment controller based on the given config.

        :return EnvironmentController: controller based on the given config
        """
        config_object = config.Config(config_path=config_path)
        return cls(log_path=config_object.log_path,
                   project_name=config_object.project_name,
                   collect_stats=config_object.collect_stats,
                   compose_path=config_object.docker_compose_path,
                   reuse_containers=config_object.reuse_containers)

    def get_services(self):
        """Get the services info based on the compose file.

        :return dict: of format {'service-name': check_callback}
        """
        log.debug("Getting environment services, using docker compose: %s", self.compose_path)
        try:
            services_output = subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'config', '--services'],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )

        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed getting environment services, reason: %s" % error.output)

        return utils.to_str(services_output).strip().split('\n')

    def setup(self):
        """Sets up the environment using docker commands.

        Should be called once before *all* the tests start.
        """
        try:
            log.debug("Setting up the environment")
            self.cleanup()
            self.run_containers()

            for plugin in self.plugins:
                try:
                    plugin.start()
                except:
                    logging.warning("Failed starting Plugin %s, skipping", plugin)

        except:
            log.exception("Setup failure, tearing down the test environment")
            self.teardown()
            raise

    def teardown(self):
        """Tears down the environment using docker commands.

        Should be called once after *all* the tests finish.
        """
        log.debug("Tearing down the environment")
        try:
            for plugin in self.plugins:
                try:
                    plugin.stop()
                except:
                    logging.warning("Failed stopping Plugin %s, skipping", plugin)
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup the environment.

        Kills and removes the environment containers.
        """
        if self.reuse_containers:
            log.warning("Container reuse enabled: Skipping environment cleanup")
            return

        self.kill_containers()
        self.remove_containers()

    def run_containers(self):
        """Run environment containers."""
        log.debug("Running environment containers, using docker compose: %s", self.compose_path)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'up', '--build', '-d'],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed running environment containers, reason: %s" % error.output)

    def remove_containers(self):
        """Remove the environment containers."""
        log.debug("Removing environment containers, using docker compose: %s", self.compose_path)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'rm', '-f'],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed removing environment containers, reason: %s" % error.output)

    def kill_containers(self):
        """Kill the environment containers."""
        log.debug("Killing environment containers, using docker compose: %s", self.compose_path)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'kill'],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed running environment containers, reason: %s" % error.output)

    def kill_container(self, name):
        """Kill the container.

        :param str name: container name as it appears in the docker compose file.
        """
        self.validate_service_name(name)
        log.debug("Killing %s container", name)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'kill', name],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed killing container %s reason: %s" % (name, error.output))

    def restart_container(self, name):
        """Restart the container.

        :param str name: container name as it appears in the docker compose file.
        """
        self.validate_service_name(name)
        log.debug("Restarting container %s", name)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'restart', name],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed restarting container %s reason: %s" % (name, error.output))

    def pause_container(self, name):
        """Pause the container.

        :param str name: container name as it appears in the docker compose file.
        """
        self.validate_service_name(name)
        log.debug("Pausing %s container", name)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'pause', name],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed pausing container %s reason: %s" % (name, error.output))

    def unpause_container(self, name):
        """Unpause the container.

        :param str name: container name as it appears in the docker compose file.
        """
        self.validate_service_name(name)
        log.debug("Unpausing %s container", name)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'unpause', name],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed unpausing container %s reason: %s" % (name, error.output))

    def stop_container(self, name):
        """Stop the container.

        :param str name: container name as it appears in the docker compose file.
        """
        self.validate_service_name(name)
        log.debug("Stopping %s container", name)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'stop', name],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed stopping container %s reason: %s" % (name, error.output))

    def start_container(self, name):
        """Start the container.

        :param str name: container name as it appears in the docker compose file.
        """
        self.validate_service_name(name)
        log.debug("Starting %s container", name)
        try:
            subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'start', name],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed starting container %s reason: %s" % (name, error.output))

    def get_container_id(self, name):
        """Get container id by name.

        :param str name: container name as it appears in the docker compose file.
        """
        self.validate_service_name(name)
        try:
            output = subprocess.check_output(
                ['docker-compose', '-f', self.compose_path, '-p', self.project_name, 'ps', '-q', name],
                stderr=subprocess.STDOUT, env=self.environment_variables
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("Failed getting container %s id, reason: %s" % (name, error.output))

        return utils.to_str(output)

    def is_container_ready(self, name):
        """Return True if the container is in ready state.

        If a health check is defined, a healthy container will be considered as ready.
        If no health check is defined, a running container will be considered as ready.

        :param str name: container name as it appears in the docker compose file.
        """
        status_output = self._inspect(name, result_format='{{json .State}}')

        if '"Health":' in status_output:
            is_ready = '"Status":"healthy"' in status_output
        else:
            is_ready = '"Status":"running"' in status_output

        log.debug("Container %s ready: %s", name, is_ready)
        return is_ready

    def container_status(self, name):
        """Returns container status

        :param str name: container name as it appears in the docker compose file.
        """
        return self._inspect(name, '{{json .State.Status}}')

    def wait_for_services(self, services=None, interval=1, timeout=60):
        """Wait for the services checks to pass.

        If the service compose configuration contains an health check, the method will wait for a 'healthy' state.
        If it doesn't the method will wait for a 'running' state.
        """
        services = services if services else self.services
        log.info('Waiting for %s to reach the required state', services)
        checks_callbacks = [partial(self.is_container_ready, name) for name in services]
        return utils.run_health_checks(checks=checks_callbacks, interval=interval, timeout=timeout)

    @contextmanager
    def container_down(self, name, health_check=None, interval=1, timeout=60):
        """Container down context manager.

        Simulate container down scenario by killing the container within the context,
        once context ends restart the container and wait for the service check to pass.

        :param str name: container name as it appears in the docker compose file.
        :param callable health_check: a callable used to determine if the service has recovered.
        :param int interval: interval (in seconds) between checks.
        :param int timeout: timeout (in seconds) for all checks to pass.

        Usage:

        >>> with controller.service_down(name='consul'):
        >>>     # container will be down in this context
        >>>
        >>> # container will be back up after context end
        """
        self.validate_service_name(name)
        self.kill_container(name=name)
        try:
            yield
        finally:
            self.restart_container(name=name)
            self.wait_for_health(name=name, health_check=health_check, interval=interval, timeout=timeout)

    @contextmanager
    def container_paused(self, name, health_check=None, interval=1, timeout=60):
        """Container pause context manager.

        Pause the container within the context, once context ends un-pause the container and wait for
        the service check to pass.

        :param str name: container name as it appears in the docker compose file.
        :param callable health_check: a callable used to determine if the service has recovered.
        :param int interval: interval (in seconds) between checks.
        :param int timeout: timeout (in seconds) for all checks to pass.

        Usage:

        >>> with controller.container_paused(name='consul'):
        >>>     # container will be paused in this context
        >>>
        >>> # container will be back up after context end
        """
        self.validate_service_name(name)
        self.pause_container(name=name)
        try:
            yield
        finally:
            self.unpause_container(name=name)
            self.wait_for_health(name=name, health_check=health_check, interval=interval, timeout=timeout)

    @contextmanager
    def container_stopped(self, name, health_check=None, interval=1, timeout=60):
        """Container stopped context manager.

        Stop the container within the context, once context ends start the container and wait for
        the service check to pass.

        :param str name: container name as it appears in the docker compose file.
        :param callable health_check: a callable used to determine if the service has recovered.
        :param int interval: interval (in seconds) between checks.
        :param int timeout: timeout (in seconds) for all checks to pass.

        Usage:

        >>> with controller.container_stopped(name='consul'):
        >>>     # container will be stopped in this context
        >>>
        >>> # container will be back up after context end
        """
        self.validate_service_name(name)
        self.stop_container(name=name)
        try:
            yield
        finally:
            self.start_container(name=name)
            self.wait_for_health(name=name, health_check=health_check, interval=interval, timeout=timeout)

    def wait_for_health(self, name, health_check=None, interval=1, timeout=60):
        """Container stopped context manager.

        :param str name: container name as it appears in the docker compose file.
        :param callable health_check: a callable used to determine if the service has recovered.
        :param int interval: interval (in seconds) between checks.
        :param int timeout: timeout (in seconds) for all checks to pass.
        """
        log.debug("Waiting for %s container to be healthy", name)
        health_check = health_check if health_check else lambda: self.is_container_ready(name)
        waiting.wait(health_check, sleep_seconds=interval, timeout_seconds=timeout)

    def validate_service_name(self, name):
        if name not in self.services:
            raise ValueError('Invalid service name: %r, must be one of %s' % (name, self.services))

    @staticmethod
    def _get_environment_variables():
        """Set the compose api version according to the server's api version"""
        server_api_version = get_server_api_version()
        log.debug("docker server api version is %s, updating environment_variables", server_api_version)
        env = os.environ.copy()
        env['COMPOSE_API_VERSION'] = env['DOCKER_API_VERSION'] = server_api_version
        return env

    def update_plugins(self, message):
        for plugin in self.plugins:
            plugin.update(message=message)

    def _inspect(self, name, result_format='{{json}}'):
        """
        Returns the inspect content of a container
        :param name: name of container
        :param result_format: format of inspect output
        """
        self.validate_service_name(name)
        log.debug("Getting %s container state", name)
        container_id = self.get_container_id(name)
        try:
            inspect_output = subprocess.check_output(
                r"docker inspect --format='{}' {}".format(result_format, container_id),
                shell=True, stderr=subprocess.STDOUT, env=self.environment_variables
            )

        except subprocess.CalledProcessError as error:
            logging.warning("Failed getting container %s state, reason: %s", name, error.output)
            return ''

        return utils.to_str(inspect_output).strip('"\n')
