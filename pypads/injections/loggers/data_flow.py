import os
from typing import List, Type

from pydantic import BaseModel, HttpUrl

from pypads.app.injections.base_logger import LoggerCall, TrackedObject
from pypads.app.injections.injection import InjectionLogger
from pypads.model.models import ArtifactMetaModel, TrackedObjectModel, OutputModel
from pypads.utils.logging_util import WriteFormats


# TODO Literal for python 3.7 / 3.8?
class InputTO(TrackedObject):
    """
    Tracking object class for inputs of your tracked workflow.
    """

    class InputModel(TrackedObjectModel):
        uri: HttpUrl = "https://www.padre-lab.eu/onto/FunctionInput"

        class ParamModel(BaseModel):
            content_format: WriteFormats = WriteFormats.pickle
            name: str = ...
            value: ArtifactMetaModel = ...  # path to the artifact containing the param
            type: str = ...

            class Config:
                orm_mode = True
                arbitrary_types_allowed = True

        input: List[ParamModel] = []

    @classmethod
    def get_model_cls(cls) -> Type[BaseModel]:
        return cls.InputModel

    def add_arg(self, name, value, format):
        self._add_param(name, value, format, 0)

    def add_kwarg(self, name, value, format):
        self._add_param(name, value, format, "kwarg")

    def _add_param(self, name, value, format, type):
        path = os.path.join(self._base_path(), self._get_artifact_path(name))
        meta = ArtifactMetaModel(path=path,
                                 description="Input to function with index {} and type {}".format(len(self.input),
                                                                                                  type),
                                 format=format)
        self.input.append(self.InputModel.ParamModel(content_format=format, name=name, value=meta, type=type))
        self._store_artifact(value, meta)

    def _get_artifact_path(self, name):
        return os.path.join(self.tracked_by.original_call.to_folder(), "input", name)


class InputILF(InjectionLogger):
    """
    Function logging the input parameters of the current pipeline object function call.
    """

    name = "InputLogger"
    uri = "https://www.padre-lab.eu/onto/input-logger"

    class InputILFOutput(OutputModel):
        is_a: HttpUrl = "https://www.padre-lab.eu/onto/InputILF-Output"
        FunctionInput: InputTO.get_model_cls() = ...

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

        inputs = InputTO(tracked_by=_logger_call)
        for i in range(len(_args)):
            arg = _args[i]
            inputs.add_arg(str(i), arg, format=_pypads_write_format)

        for (k, v) in _kwargs.items():
            inputs.add_kwarg(str(k), v, format=_pypads_write_format)
        inputs.store(_logger_output,key="FunctionInput")


class OutputTO(TrackedObject):
    """
    Tracking object class for inputs of your tracked workflow.
    """

    def _path_name(self):
        return "inputs"

    class OutputModel(TrackedObjectModel):
        uri: HttpUrl = "https://www.padre-lab.eu/onto/FunctionOutput"

        content_format: WriteFormats = WriteFormats.pickle
        output: str = ...  # Path to the output holding file

        class Config:
            orm_mode = True
            arbitrary_types_allowed = True

    @classmethod
    def get_model_cls(cls) -> Type[BaseModel]:
        return cls.OutputModel

    def __init__(self, value, format, *args, call: LoggerCall, **kwargs):
        super().__init__(*args, content_format=format, tracked_by=call, **kwargs)
        path = os.path.join(self._base_path(), self.tracked_by.original_call.to_folder(), "output")
        self.output = path
        self._store_artifact(value, ArtifactMetaModel(path=path,
                                                      description="Output of function call {}".format(
                                                          self.tracked_by.original_call),
                                                      format=format))


class OutputILF(InjectionLogger):
    """
    Function logging the output of the current pipeline object function call.
    """

    name = "OutputLogger"
    uri = "https://www.padre-lab.eu/onto/output-logger"

    class OutputILFOutput(OutputModel):
        is_a: HttpUrl = "https://www.padre-lab.eu/onto/OutputILF-Output"
        FunctionOutput: OutputTO.get_model_cls() = ...

        class Config:
            orm_mode = True

    @classmethod
    def output_schema_class(cls):
        return cls.OutputILFOutput

    def __post__(self, ctx, *args, _pypads_write_format=WriteFormats.pickle, _logger_call, _pypads_result,
                 _logger_output, **kwargs):
        """
        :param ctx:
        :param args:
        :param _pypads_write_format:
        :param kwargs:
        :return:
        """
        output = OutputTO(_pypads_result, format=_pypads_write_format, call=_logger_call)
        output.store(_logger_output, key="FunctionOutput")
