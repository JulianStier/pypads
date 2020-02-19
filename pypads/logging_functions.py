import datetime
from logging import warning, info

import mlflow
from mlflow.utils.autologging_utils import try_mlflow_log

from pypads.logging_util import try_write_artifact, WriteFormats
from pypads.validation.generic_visitor import default_visitor


def _to_folder_name(self, _pypads_context, _pypads_wrappe):
    return _pypads_context.__name__ + "/" + str(id(self)) + "/" + _pypads_wrappe.__name__


def _get_now():
    """
    Function for providing a current human readable timestamp.
    :return: timestamp
    """
    return datetime.datetime.now().strftime("%d_%b_%Y_%H-%M-%S.%f")


def log_init(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
             **kwargs):
    info("Pypads tracked class " + str(self.__class__) + " initialized.")
    _pypads_callback(*args, **kwargs)


def parameters(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
               **kwargs):
    """
    Function logging the parameters of the current pipeline object function call.
    :param self: Wrapper library object
    :param args: Input args to the real library call
    :param _pypads_wrappe: _pypads provided - wrapped library object
    :param _pypads_mapped_by: _pypads provided - wrapped library package
    :param _pypads_item: _pypads provided - wrapped function name
    :param _pypads_fn_stack: _pypads provided - stack of all the next functions to execute
    :param kwargs: Input kwargs to the real library call
    :return:
    """
    result = _pypads_callback(*args, **kwargs)

    try:
        # prevent wrapped_class from becoming unwrapped
        visitor = default_visitor(self)

        for k, v in visitor[0]["steps"][0]["hyper_parameters"]["model_parameters"].items():
            try_mlflow_log(mlflow.log_param,
                           _pypads_mapped_by.reference + "." + str(id(self)) + "." + _get_now() + "." + k + ".txt", v)
    except Exception as e:
        warning("Couldn't use visitor for parameter extraction. " + str(e) + " Omit logging for now.")
        # for i in range(len(args)):
        #    arg = args[i]
        #    try_mlflow_log(mlflow.log_param, _pypads_mapped_by + "." + str(id(self)) + "." + get_now() + ".args." + str(i), str(arg))
        #
        # for (k, v) in kwargs.items():
        #    try_mlflow_log(mlflow.log_param, _pypads_mapped_by + "." + str(id(self)) + "." + get_now() + ".kwargs." + str(k), str(v))

    return result


def output(self, *args, write_format=WriteFormats.pickle, _pypads_wrappe, _pypads_context, _pypads_mapped_by,
           _pypads_callback,
           **kwargs):
    """
    Function logging the output of the current pipeline object function call.
    :param write_format: Format the artifact should write to
    :param self: Wrapper library object
    :param args: Input args to the real library call
    :param _pypads_wrappe: _pypads provided - wrapped library object
    :param _pypads_mapped_by: _pypads provided - wrapped library package
    :param _pypads_item: _pypads provided - wrapped function name
    :param _pypads_fn_stack: _pypads provided - stack of all the next functions to execute
    :param kwargs: Input kwargs to the real library call
    :return:
    """
    result = _pypads_callback(*args, **kwargs)
    name = _to_folder_name(self, _pypads_context, _pypads_wrappe) + "/returns/" + str(id(_pypads_callback))
    try_write_artifact(name, result, write_format)
    return result


def input(self, *args, write_format=WriteFormats.pickle, _pypads_wrappe, _pypads_context, _pypads_mapped_by,
          _pypads_callback,
          **kwargs):
    """
    Function logging the input parameters of the current pipeline object function call.
    :param write_format: Format the artifact should write to
    :param self: Wrapper library object
    :param args: Input args to the real library call
    :param _pypads_wrappe: _pypads provided - wrapped library object
    :param _pypads_mapped_by: _pypads provided - wrapped library package
    :param _pypads_item: _pypads provided - wrapped function name
    :param _pypads_fn_stack: _pypads provided - stack of all the next functions to execute
    :param kwargs: Input kwargs to the real library call
    :return:
    """
    for i in range(len(args)):
        arg = args[i]
        name = _to_folder_name(self, _pypads_context, _pypads_wrappe) + "/args/" + str(i) + "_" + str(
            id(_pypads_callback))
        try_write_artifact(name, arg, write_format)

    for (k, v) in kwargs.items():
        name = _to_folder_name(self, _pypads_context, _pypads_wrappe) + "/kwargs/" + str(k) + "_" + str(
            id(_pypads_callback))
        try_write_artifact(name, v, write_format)

    result = _pypads_callback(*args, **kwargs)
    return result


def cpu(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback, **kwargs):
    import platform
    mlflow.set_tag("pypads.processor", platform.processor())
    return _pypads_callback(*args, **kwargs)


def metric(self, *args, _pypads_wrappe, artifact_fallback=False, _pypads_context, _pypads_mapped_by, _pypads_callback,
           **kwargs):
    """
    Function logging the wrapped metric function
    :param self: Wrapper library object
    :param args: Input args to the real library call
    :param pypads_wrappe: pypads provided - wrapped library object
    :param pypads_package: pypads provided - wrapped library package
    :param pypads_item: pypads provided - wrapped function name
    :param pypads_fn_stack: pypads provided - stack of all the next functions to execute
    :param kwargs: Input kwargs to the real library call
    :return:
    """
    result = _pypads_callback(*args, **kwargs)

    if result is not None:
        if isinstance(result, float):
            try_mlflow_log(mlflow.log_metric, _pypads_wrappe.__name__ + ".txt", result)
        else:
            warning("Mlflow metrics have to be doubles. Could log the return value of type '" + str(
                type(result)) + "' of '" + _pypads_wrappe.__name__ + "' as artifact instead.")

            # TODO search callstack for already logged functions and ignore?
            if artifact_fallback:
                info("Logging result if '" + _pypads_wrappe.__name__ + "' as artifact.")
                try_write_artifact(_pypads_wrappe.__name__, str(result), WriteFormats.text)

    if self is not None:
        if result is self._pads_wrapped_instance:
            return self
    return result


def log(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback, **kwargs):
    print("Called following function: " + str(_pypads_wrappe) + " on " + str(
        _pypads_context) + " defined by mapping: " + str(_pypads_callback) + ". Next call is " + str(
        _pypads_callback))
