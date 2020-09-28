import os
from typing import List, Type

from pydantic import BaseModel

from pypads.app.injections.base_logger import LoggerCall, TrackedObject, LoggerOutput
from pypads.app.injections.injection import InjectionLogger
from pypads.model.logger_output import OutputModel, TrackedObjectModel
from pypads.utils.logging_util import FileFormats


class InputTO(TrackedObject):
    """
    Tracking object class for inputs of your tracked workflow.
    """

    class InputModel(TrackedObjectModel):
        category: str = "FunctionInput"
        inputs: List[str] = []

    @classmethod
    def get_model_cls(cls) -> Type[BaseModel]:
        return cls.InputModel

    def add_arg(self, name, value, format):
        self._add_param(name, value, format, "argument")

    def add_kwarg(self, name, value, format):
        self._add_param(name, value, format, "keyword-argument")

    def _add_param(self, name, value, format, type):
        path = self.get_artifact_path(name)
        description = "Input to function with index {} and type {}".format(len(self.inputs), type)
        self.inputs.append(self.store_artifact(path, value, write_format=format, description=description))

    def get_artifact_path(self, name):
        return os.path.join(self.get_dir(), "input", name)


class InputILF(InjectionLogger):
    """
    Function logging the input parameters of the current pipeline object function call.
    """

    name = "Generic-InputLogger"
    category = "InputLogger"

    class InputILFOutput(OutputModel):
        category: str = "InputILF-Output"
        FunctionInput: str = ...

        class Config:
            orm_mode = True

    @classmethod
    def output_schema_class(cls):
        return cls.InputILFOutput

    def __pre__(self, ctx, *args, _pypads_write_format=None, _logger_call: LoggerCall, _logger_output, _args, _kwargs,
                **kwargs):
        """
        :param ctx:
        :param args:
        :param _pypads_write_format:
        :param kwargs:
        :return:
        """

        inputs = InputTO(part_of=_logger_output)
        for i in range(len(_args)):
            arg = _args[i]
            inputs.add_arg(str(i), arg, format=_pypads_write_format)

        for (k, v) in _kwargs.items():
            inputs.add_kwarg(str(k), v, format=_pypads_write_format)
        inputs.store(_logger_output, key="FunctionInput")


class OutputTO(TrackedObject):
    """
    Tracking object class for inputs of your tracked workflow.
    """

    def _path_name(self):
        return "inputs"

    class OutputModel(TrackedObjectModel):
        category: str = "FunctionOutput"

        output: str = ...  # Path to the output holding file

        class Config:
            orm_mode = True
            arbitrary_types_allowed = True

    @classmethod
    def get_model_cls(cls) -> Type[BaseModel]:
        return cls.OutputModel

    def __init__(self, value, format, *args, part_of: LoggerOutput, **kwargs):
        super().__init__(*args, content_format=format, part_of=part_of, **kwargs)
        self.output = self.store_artifact(self.get_artifact_path(), value, write_format=format,
                                          description="Output of function call {}".format(
                                              self._tracked_by.original_call))

    def get_artifact_path(self, name="output"):
        return super().get_artifact_path(name)


class OutputILF(InjectionLogger):
    """
    Function logging the output of the current pipeline object function call.
    """

    name = "GenericOutputLogger"
    category = "OutputLogger"

    class OutputILFOutput(OutputModel):
        category: str = "OutputILF-Output"
        FunctionOutput: str = ...

        class Config:
            orm_mode = True

    @classmethod
    def output_schema_class(cls):
        return cls.OutputILFOutput

    def __post__(self, ctx, *args, _pypads_write_format=FileFormats.pickle, _logger_call, _pypads_result,
                 _logger_output, **kwargs):
        """
        :param ctx:
        :param args:
        :param _pypads_write_format:
        :param kwargs:
        :return:
        """
        output = OutputTO(_pypads_result, format=_pypads_write_format, part_of=_logger_output)
        output.store(_logger_output, key="FunctionOutput")
