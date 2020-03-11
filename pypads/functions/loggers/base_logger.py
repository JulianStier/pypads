from _py_abc import ABCMeta
from logging import exception, warning

import mlflow

from pypads.functions.analysis.time_keeper import timed, add_run_time
from pypads.logging_util import get_current_call_str
from pypads.util import is_package_available


class MissingDependencyError(Exception):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class DependencyMixin(object):
    @staticmethod
    def _needed_packages():
        """
        List of needed packages
        :return:
        """
        return []

    def _check_dependencies(self):
        """
        Raise error if dependencies are missing
        :return:
        """
        missing = []
        for package in self._needed_packages():
            if not is_package_available(package):
                missing.append(package)
        if len(missing) > 0:
            raise MissingDependencyError("Can't log " + str(self) + ". Missing dependencies: " + ", ".join(missing))


# noinspection PyBroadException
class LoggingFunction(DependencyMixin):
    __metaclass__ = ABCMeta
    """
    This class should be used to define new loggers
    """

    def __init__(self, **static_parameters):
        self._static_parameters = static_parameters

    def __pre__(self, ctx, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback, **kwargs):
        """
        The function to be called before executing the log anchor
        :param ctx:
        :param args:
        :param _pypads_wrappe:
        :param _pypads_context:
        :param _pypads_mapped_by:
        :param _pypads_callback:
        :param kwargs:
        :return:
        """
        raise NotImplementedError()

    # noinspection PyMethodMayBeStatic
    def _handle_failure(self, ctx, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
                        _pypads_hook_params, _pypads_error, **kwargs):
        try:
            mlflow.set_tag("pypads_failure", str(_pypads_error))
            exception(
                "Tracking failed for " + get_current_call_str(ctx, _pypads_context, _pypads_wrappe) + " with: " + str(
                    _pypads_error))
        except Exception:
            exception("Tracking failed for " + str(_pypads_wrappe) + " with: " + str(_pypads_error))

    def __call__(self, ctx, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
                 _pypads_hook_params, **kwargs):
        """
        The call of the loggingFunction
        :param ctx:
        :param args:
        :param _pypads_wrappe:
        :param _pypads_context:
        :param _pypads_mapped_by:
        :param _pypads_callback:
        :param kwargs:
        :return:
        """
        # Add the static parameters to our passed parameters
        _pypads_hook_params = {**self._static_parameters, **_pypads_hook_params}

        # Call function to be executed before the tracked function
        _pypads_pre_return = None
        dependency_error = None

        try:
            self._check_dependencies()
            _pypads_pre_return, time = timed(lambda: self.__pre__(ctx, *args, _pypads_wrappe=_pypads_wrappe,
                                                                  _pypads_context=_pypads_context,
                                                                  _pypads_mapped_by=_pypads_mapped_by,
                                                                  _pypads_callback=_pypads_callback,
                                                                  **{**_pypads_hook_params, **kwargs}))
            add_run_time(
                get_current_call_str(ctx, _pypads_context, _pypads_wrappe) + "." + self.__class__.__name__ + ".__pre__",
                time)
        except NotImplementedError:
            pass
        except MissingDependencyError as e:
            dependency_error = e
        except Exception as e:
            self._handle_failure(ctx, *args, _pypads_wrappe=_pypads_wrappe, _pypads_context=_pypads_context,
                                 _pypads_mapped_by=_pypads_mapped_by, _pypads_callback=_pypads_callback,
                                 _pypads_error=e, _pypads_hook_params=_pypads_hook_params,
                                 **kwargs)

        # Call the output producing code
        out, time = timed(
            lambda: self.call_wrapped(ctx, *args, _pypads_wrappe=_pypads_wrappe, _pypads_context=_pypads_context,
                                      _pypads_mapped_by=_pypads_mapped_by, _pypads_callback=_pypads_callback,
                                      _kwargs=kwargs,
                                      **_pypads_hook_params))

        try:
            add_run_time(get_current_call_str(ctx, _pypads_context, _pypads_wrappe), time)
        except ValueError as e:
            pass

        # Call function to be executed after the tracked function
        try:
            self._check_dependencies()
            _, time = timed(
                lambda: self.__post__(ctx, *args, _pypads_wrappe=_pypads_wrappe, _pypads_context=_pypads_context,
                                      _pypads_mapped_by=_pypads_mapped_by, _pypads_callback=_pypads_callback,
                                      _pypads_result=out,
                                      _pypads_pre_return=_pypads_pre_return, **{**_pypads_hook_params, **kwargs}))
            add_run_time(get_current_call_str(ctx, _pypads_context,
                                              _pypads_wrappe) + "." + self.__class__.__name__ + ".__post__", time)
        except NotImplementedError:
            pass
        except MissingDependencyError as e:
            dependency_error = e
        except Exception as e:
            self._handle_failure(ctx, *args, _pypads_wrappe=_pypads_wrappe, _pypads_context=_pypads_context,
                                 _pypads_mapped_by=_pypads_mapped_by, _pypads_callback=_pypads_callback,
                                 _pypads_error=e, _pypads_hook_params=_pypads_hook_params,
                                 **kwargs)

        if dependency_error:
            warning(str(dependency_error))
        return out

    # noinspection PyMethodMayBeStatic
    def call_wrapped(self, ctx, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
                     _kwargs, **_pypads_hook_params):
        """
        The real call of the wrapped function. Be carefull when you change this.
        Exceptions here will not be catched automatically and might break your workflow.
        :param ctx:
        :param args:
        :param _pypads_wrappe:
        :param _pypads_context:
        :param _pypads_mapped_by:
        :param _pypads_callback:
        :param _pypads_hook_params:
        :param kwargs:
        :return:
        """
        return _pypads_callback(*args, **_kwargs)

    def __post__(self, ctx, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback, _pypads_result,
                 **kwargs):
        """
        The function to be called after executing the log anchor
        :param ctx:
        :param args:
        :param _pypads_wrappe:
        :param _pypads_context:
        :param _pypads_mapped_by:
        :param _pypads_callback:
        :param kwargs:
        :return:
        """
        raise NotImplementedError()
