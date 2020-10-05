import uuid
from enum import Enum
from typing import Union

from pydantic import BaseModel, Field, root_validator


class ResultType(Enum):
    artifact = 'artifact'
    parameter = 'parameter'
    metric = 'metric'
    tag = 'tag'
    tracked_object = 'tracked_object'
    output = 'output'
    logger_call = 'loggerCall'
    logger = 'logger'
    schema = 'schema'
    library = 'library'


class Entry(BaseModel):
    clazz: str = None  # Class of the model
    category: str = ...  # Human readable class representation. This will be converted in ontology entries.
    storage_type: Union[ResultType, str] = ...  # Should generally be one of ResultType

    @root_validator
    def set_default(cls, values):
        if values['clazz'] is None:
            values['clazz'] = str(cls)
        return values


class IdBasedEntry(Entry):
    uid: uuid.UUID = Field(default_factory=uuid.uuid4, alias="_id")
