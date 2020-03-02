import os
from types import GeneratorType
from typing import Iterable

import mlflow
from pypads.logging_util import WriteFormats, to_folder_name

from pypadsext.concepts.dataset import Crawler
from pypadsext.concepts.util import persistent_hash, split_output_inv, get_by_tag

DATASETS = "datasets"


def dataset(self, *args, write_format=WriteFormats.pickle, _pypads_wrappe, _pypads_context, _pypads_mapped_by,
            _pypads_callback, **kwargs):
    """
        Function logging the loaded dataset.
        :param self: Wrapper library object
        :param args: Input args to the real library call
        :param _pypads_wrappe: _pypads provided - wrapped library object
        :param _pypads_mapped_by: _pypads provided - wrapped library package
        :param _pypads_item: _pypads provided - wrapped function name
        :param _pypads_fn_stack: _pypads provided - stack of all the next functions to execute
        :param kwargs: Input kwargs to the real library call
        :return:
        """
    from pypads.base import get_current_pads
    from pypadsext.base import PyPadrePads
    pads: PyPadrePads = get_current_pads()

    # get the dataset object
    result = _pypads_callback(*args, **kwargs)

    # Get additional arguments if given by the user
    _kwargs = dict()
    if pads.cache.run_exists("dataset_kwargs"):
        _kwargs = pads.cache.run_get("dataset_kwargs")

    # Scrape the data object
    crawler = Crawler(result, ctx=_pypads_context, callback=_pypads_callback, kw=args)
    data, metadata, targets = crawler.crawl(**_kwargs)
    pads.cache.run_add("data", data)
    pads.cache.run_add("shape", metadata.get("shape"))
    pads.cache.run_add("targets", targets)

    # get the current active run
    experiment_run = mlflow.active_run()

    # setting the dataset object name
    if hasattr(result, "name"):
        ds_name = result.name
    elif pads.cache.run_exists("dataset_name") and pads.cache.run_get("dataset_name") is not None:
        ds_name = pads.cache.run_get("dataset_name")
    else:
        ds_name = _pypads_wrappe.__name__

    # Look for metadata information given by the user when using the decorators
    if pads.cache.run_exists("dataset_meta"):
        metadata = {**metadata, **pads.cache.run_get("dataset_meta")}

    # get the repo or create new where datasets are stored
    repo = mlflow.get_experiment_by_name(DATASETS)
    if repo is None:
        repo = mlflow.get_experiment(mlflow.create_experiment(DATASETS))

    # add data set if it is not already existing with name and hash check
    try:
        _hash = persistent_hash(str(result))
    except Exception:
        Warning("Could not compute the hash of the dataset object, falling back to dataset name hash...")
        _hash = persistent_hash(str(ds_name))

    _stored = get_by_tag("pypads.dataset.hash", str(_hash), repo.experiment_id)
    if not _stored:
        with pads.api.intermediate_run(experiment_id=repo.experiment_id) as run:
            dataset_id = run.info.run_id

            pads.cache.run_add("dataset_id", dataset_id, experiment_run.info.run_id)
            mlflow.set_tag("pypads.dataset", ds_name)
            mlflow.set_tag("pypads.dataset.hash", _hash)
            name = os.path.join(to_folder_name(self, _pypads_context, _pypads_wrappe), "data",
                                str(id(_pypads_callback)))
            pads.api.log_mem_artifact(name, data, write_format=write_format, meta=metadata)

        mlflow.set_tag("pypads.datasetID", dataset_id)
    else:
        # look for the existing dataset and reference it to the active run
        if len(_stored) > 1:
            Warning("multiple existing datasets with the same hash!!!")
        else:
            dataset_id = _stored.pop().info.run_id
            mlflow.set_tag("pypads.datasetID", dataset_id)

    return result


def predictions(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
                write_format=WriteFormats.text,
                **kwargs):
    from pypads.base import get_current_pads
    from pypadsext.base import PyPadrePads
    pads: PyPadrePads = get_current_pads()

    result = _pypads_callback(*args, **kwargs)

    # check if there exists information of the current split
    num = 0
    split_info = None
    if pads.cache.run_exists("current_split"):
        num = pads.cache.run_get("current_split")
    if pads.cache.run_exists(num):
        split_info = pads.cache.run_get(num).get("split_info", None)

    # check if the estimator computes decision scores
    probabilities = None
    if hasattr(self, "predict_proba") or hasattr(self, "_predict_proba"):
        try:
            probabilities = self.predict_proba(*args, **kwargs)
        except Exception as e:
            print(str(e))

    # depending on available info log the predictions
    if split_info is None:
        Warning("No split information were found in the cache of the current run, "
                "individual decision tracking might be missing Truth values, try to decorate you splitter!")
        pads.cache.run_add(num, {'predictions': {str(i): {'predicted': result[i]} for i in range(len(result))}})
        if probabilities is not None:
            for i in pads.cache.run_get(num).get('predictions').keys():
                pads.cache.run_get(num).get('predictions').get(str(i)).update(
                    {'probabilities': probabilities[int(i)]})
        if pads.cache.run_exists("targets"):
            try:
                targets = pads.cache.run_get("targets")
                if isinstance(targets, Iterable) and len(targets) == len(result):
                    for i in pads.cache.run_get(num).get('predictions').keys():
                        pads.cache.run_get(num).get('predictions').get(str(i)).update(
                            {'truth': targets[int(i)]})
            except Exception:
                Warning("Could not add the truth values")
    else:
        try:
            for i, sample in enumerate(split_info.get('test')):
                pads.cache.run_get(num).get('predictions').get(str(sample)).update({'predicted': result[i]})

            if probabilities is not None:
                for i, sample in enumerate(split_info.get('test')):
                    pads.cache.run_get(num).get('predictions').get(str(sample)).update(
                        {'probabilities': probabilities[i]})
        except Exception as e:
            print(e)

    name = os.path.join(to_folder_name(self, _pypads_context, _pypads_wrappe), "decisions", str(id(_pypads_callback)))
    pads.api.log_mem_artifact(name, pads.cache.run_get(num), write_format=write_format)

    return result


def split(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback, **kwargs):
    from pypads.base import get_current_pads
    from pypadsext.base import PyPadrePads
    pads: PyPadrePads = get_current_pads()

    result = _pypads_callback(*args, **kwargs)

    # TODO add truth values if targets are present
    if isinstance(result, GeneratorType):
        def generator():
            num = -1
            for r in result:
                num += 1
                pads.cache.run_add("current_split", num)
                split_info = split_output_inv(r, fn=_pypads_callback)
                pads.cache.run_add(num, {"split_info": split_info})
                yield r
    else:
        def generator():
            split_info = split_output_inv(result, fn=_pypads_callback)
            pads.cache.run_add("current_split", 0)
            pads.cache.run_add(0, {"split_info": split_info})

            return result

    return generator()


def hyperparameters(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback, **kwargs):
    from pypads.base import get_current_pads
    from pypadsext.base import PyPadrePads
    pads: PyPadrePads = get_current_pads()

    def tracer(frame, event, arg):
        if event == 'return':
            params = frame.f_locals.copy()
            key = _pypads_callback.__wrapped__.__qualname__ if hasattr(_pypads_callback,
                                                                       "__wrapped__") else _pypads_callback.__qualname__
            pads.cache.run_add(key, params)

    import sys
    # tracer is activated on next call, return or exception
    sys.setprofile(tracer)
    try:
        fn = _pypads_callback
        if hasattr(_pypads_callback, "__wrapped__"):
            fn = _pypads_callback.__wrapped__
        fn(*args, **kwargs)
    finally:
        # deactivate tracer
        sys.setprofile(None)

    params = pads.cache.run_get(fn.__qualname__)
    for key, param in params.items():
        pads.api.log_param(key, param)

    result = _pypads_callback(*args, **kwargs)

    return result