from pypads import util
from pypads.autolog.mappings import AlgorithmMapping
from pypads.base import PyPads, PypadsApi, PypadsDecorators, DEFAULT_CONFIG, DEFAULT_EVENT_MAPPING

from pypadsext.analysis.doc_parsing import doc
from pypadsext.concepts.splitter import default_split
from pypadsext.concepts.util import _create_ctx
from pypadsext.functions.logging_functions import dataset, predictions, split, hyperparameters
from pypadsext.functions.management.randomness import set_random_seed
from pypadsext.util import get_class_that_defined_method

# --- Pypads App ---

# Extended mappings. We allow to log parameters, output or input, datasets
DEFAULT_PYPADRE_MAPPING = {
    "dataset": dataset,
    "predictions": predictions,
    "splits": split,
    "hyperparameters": hyperparameters,
    "doc": doc
}

# Extended config.
# Pypads mapping files shouldn't interact directly with the logging functions,
# but define events on which different logging functions can listen.
# This config defines such a listening structure.
# {"recursive": track functions recursively. Otherwise check the callstack to only track the top level function.}
DEFAULT_PYPADRE_CONFIG = {"events": {
    "dataset": {"on": ["pypads_dataset"]},
    "predictions": {"on": ["pypads_predict"]},
    "splits": {"on": ["pypads_split"]},
    "hyperparameters": {"on": ["pypads_params"]},
    "doc": {"on": ["pypads_dataset", "pypads_fit", "pypads_transform", "pypads_predict"]}
}}


class PyPadrePadsActuators:

    def __init__(self, pypads):
        self._pypads = pypads

    def set_random_seed(self, seed=None):
        # Set seed if needed
        if seed is None:
            import random
            # import sys
            # seed = random.randrange(sys.maxsize)
            # Numpy only allows for a max value of 2**32 - 1
            seed = random.randrange(2 ** 32 - 1)
        self._pypads.cache.run_add('seed', seed)
        set_random_seed(seed)

    # noinspection PyMethodMayBeStatic
    def default_splitter(self, data, **kwargs):
        ctx = _create_ctx(self._pypads.cache.run_cache().cache)
        ctx.update({"data": data})
        return default_split(ctx, **kwargs)


class PyPadrePadsApi(PypadsApi):

    def __init__(self, pypads):
        super().__init__(pypads)

    def track_dataset(self, fn, ctx=None, name=None, metadata=None, mapping: AlgorithmMapping = None, **kwargs):
        if metadata is None:
            metadata = {}
        self._pypads.cache.run_add('dataset_name', name)
        self._pypads.cache.run_add('dataset_meta', metadata)
        self._pypads.cache.run_add('dataset_kwargs', kwargs)
        return self.track(fn, ctx, ["pypads_dataset"], mapping=mapping)

    def track_splits(self, fn, ctx=None, mapping: AlgorithmMapping = None):
        return self.track(fn, ctx, ["pypads_split"], mapping=mapping)

    def track_parameters(self, fn, ctx=None, mapping: AlgorithmMapping = None):
        return self.track(fn, ctx, ["pypads_params"], mapping=mapping)


class PyPadrePadsDecorators(PypadsDecorators):
    # ------------------------------------------- decorators --------------------------------
    def dataset(self, mapping=None, name=None, metadata=None, **kwargs):
        def track_decorator(fn):
            ctx = get_class_that_defined_method(fn)
            return self._pypads.api.track_dataset(ctx=ctx, fn=fn, name=name, metadata=metadata, mapping=mapping,
                                                  **kwargs)

        return track_decorator

    def splitter(self, mapping=None):
        def track_decorator(fn):
            ctx = get_class_that_defined_method(fn)
            return self._pypads.api.track_splits(ctx=ctx, fn=fn, mapping=mapping)

        return track_decorator

    def hyperparameters(self, mapping=None):
        def track_decorator(fn):
            ctx = get_class_that_defined_method(fn)
            return self._pypads.api.track_parameters(ctx=ctx, fn=fn, mapping=mapping)

        return track_decorator


class PyPadrePads(PyPads):
    def __init__(self, *args, config=None, event_mapping=None, **kwargs):
        config = config or util.dict_merge(DEFAULT_CONFIG, DEFAULT_PYPADRE_CONFIG)
        event_mapping = event_mapping or util.dict_merge(DEFAULT_EVENT_MAPPING, DEFAULT_PYPADRE_MAPPING)
        super().__init__(*args, config=config, event_mapping=event_mapping, **kwargs)
        self._api = PyPadrePadsApi(self)
        self._decorators = PyPadrePadsDecorators(self)
        self._actuators = PyPadrePadsActuators(self)

    @property
    def actuators(self):
        return self._actuators
