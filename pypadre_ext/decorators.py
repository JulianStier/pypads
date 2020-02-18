from logging import warning
from types import GeneratorType
from typing import Tuple

import mlflow
from boltons.funcutils import wraps

from pypads.base import PyPads
from pypads.logging_functions import get_now
from pypads.logging_util import all_tags, try_write_artifact, WriteFormats

DATASETS = "datasets"


class PyPadsEXT(PyPads):
    def __init__(self, *args, **kwargs):
        self._cache = dict()
        super().__init__(*args, **kwargs)
        PyPads.current_pads = self

    # ------------------------------------------- public API methods ------------------------
    def run_id(self):
        return self.run.info.run_id

    def experiment_id(self):
        return self.experiment.experiment_id

    def active_run(self):
        return mlflow.active_run() and mlflow.active_run() == self.run

    def start_run(self):
        if self.active_run():
            mlflow.end_run()
            self.run = mlflow.start_run(experiment_id=self._experiment.experiment_id)

    def stop_run(self):
        if self.active_run():
            mlflow.end_run()
        else:
            self._run = self.mlf.get_run(mlflow.active_run().info.run_id)
            mlflow.end_run()

    def resume_run(self):
        try:
            mlflow.start_run(run_id=self.run_id)
        except Exception:
            mlflow.end_run()
            mlflow.start_run(run_id=self.run_id)

    @property
    def cache(self):
        return self._cache

    def add(self, key, value):
        if key in self.cache:
            self.cache.get(key).update(value)
        else:
            self.cache.update({key: value})

    def pop(self, key, value):
        if key in self.cache:
            if self.cache.get(key) == value:
                return self.cache.pop(key)
        return None

    # ------------------------------------------- decorators --------------------------------

    def dataset(self, name, metadata=None):
        def dataset_decorator(f_create_dataset):
            @wraps(f_create_dataset)
            def wrap_dataset(*args, **kwargs):
                dataset = f_create_dataset(*args, **kwargs)

                repo = mlflow.get_experiment_by_name(DATASETS)
                if repo is None:
                    repo = mlflow.get_experiment(mlflow.create_experiment(DATASETS))

                # add data set if it is not already existing
                if not any(t["name"] == name for t in all_tags(repo.experiment_id)):
                    # stop the current run
                    self.stop_run()
                    run = mlflow.start_run(experiment_id=repo.experiment_id)

                    dataset_id = run.info.run_id
                    self.add("dataset_id", dataset_id)
                    self.add("dataset_name", name)
                    mlflow.set_tag("name", name)
                    name_ = f_create_dataset.__qualname__ + "[" + str(id(dataset)) + "]." + name + "_data"
                    if hasattr(dataset, "data"):
                        if hasattr(dataset.data, "__self__") or hasattr(dataset.data, "__func__"):
                            try_write_artifact(name_, dataset.data(), WriteFormats.pickle)
                            self.add("data", dataset.data())
                        else:
                            try_write_artifact(name_, dataset.data, WriteFormats.pickle)
                            self.add("data", dataset.data)
                    else:
                        try_write_artifact(name_, dataset, WriteFormats.pickle)

                    if metadata:
                        name_ = f_create_dataset.__qualname__ + "[" + str(id(dataset)) + "]." + name + "_metadata"
                        try_write_artifact(name_, metadata, WriteFormats.text)
                    elif hasattr(dataset, "metadata"):
                        name_ = f_create_dataset.__qualname__ + "[" + str(id(dataset)) + "]." + name + "_metadata"
                        if hasattr(dataset.metadata, "__self__") or hasattr(dataset.metadata, "__func__"):
                            try_write_artifact(name_, dataset.metadata(), WriteFormats.text)
                        else:
                            try_write_artifact(name_, dataset.metadata, WriteFormats.text)
                    self.resume_run()
                    mlflow.set_tag("dataset", dataset_id)

                return dataset

            return wrap_dataset

        return dataset_decorator

    def splitter(self, ):
        def decorator(f_splitter):
            @wraps(f_splitter)
            def wrapper(*args, **kwargs):
                splits = f_splitter(*args, **kwargs)
                ds_name = self.cache.get("dataset_name", None)
                ds_id = self.cache.get("dataset_id", None)
                run_id = self.run.info.run_id
                if isinstance(splits, GeneratorType):
                    for num, train_idx, test_idx, targets in splits:

                        self.add(run_id, {
                            str(num): {'dataset': ds_name, 'dataset_id': ds_id, 'train_indices': train_idx,
                                       'test_indices': test_idx}})

                        if targets is not None:
                            warning(
                                "Your splitter does not provide targets information, Truth values will be missing from "
                                "the logged predictions")
                            self.cache.get(run_id).get(str(num)).update(
                                {'predictions': {str(sample): {'truth': targets[sample]} for sample in test_idx}})
                        name = 'Split_{}_{}_information.txt'.format(num, get_now())
                        try_write_artifact(name,
                                           {'dataset': ds_name, 'train_indices': train_idx, 'test_indices': test_idx},
                                           WriteFormats.text)
                        yield num, train_idx, test_idx
                else:
                    num, train_idx, test_idx, targets = splits

                    self.add(run_id, {
                        str(num): {'dataset': ds_name, 'dataset_id': ds_id, 'train_indices': train_idx,
                                   'test_indices': test_idx}})

                    if targets:
                        warning(
                            "Your splitter does not provide targets information, Truth values will be missing from "
                            "the logged predictions")
                        self.cache.get(run_id).get(str(num)).update(
                            {'predictions': {str(sample): {'truth': targets[sample]} for sample in test_idx}})
                    name = 'Split_{}_{}_information'.format(num, get_now())
                    try_write_artifact(name,
                                       {'dataset': ds_name, 'dataset_id': ds_id, 'train_indices': train_idx,
                                        'test_indices': test_idx},
                                       WriteFormats.text)
                    return num, train_idx, test_idx

            return wrapper

        return decorator

    def grid_search(self):
        def decorator(f_grid):
            @wraps(f_grid)
            def wrapper(*args, **kwargs):
                grid = f_grid(*args, **kwargs)

                for element in grid['grid']:
                    execution_params = dict()
                    for param, idx in zip(grid['parameters'], range(0, len(grid['parameters']))):
                        execution_params[param] = element[idx]
                    name = "Grid_params_{}".format(get_now())
                    try_write_artifact(name, execution_params, WriteFormats.text)
                    yield execution_params

            return wrapper

        return decorator


def unpack(kwargs_obj: dict, *args):
    """
    Unpacks a dict object into a tuple. You can pass tuples for setting default values.
    :param kwargs_obj:
    :param args:
    :return:
    """
    empty = object()
    arg_list = []
    for entry in args:
        if isinstance(entry, str):
            arg_list.append(kwargs_obj.get(entry))
        elif isinstance(entry, Tuple):
            key, *rest = entry
            default = empty if len(rest) == 0 else rest[0]
            if default is empty:
                arg_list.append(kwargs_obj.get(key))
            else:
                arg_list.append(kwargs_obj.get(key, default))
        else:
            raise ValueError("Pass a tuple or string not: " + str(entry))
    return tuple(arg_list)


