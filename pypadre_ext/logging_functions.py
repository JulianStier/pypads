import mlflow

from pypads.logging_util import try_write_artifact, WriteFormats, all_tags

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
    result = _pypads_callback(*args, **kwargs)
    from pypads.base import get_current_pads
    pads = get_current_pads()

    repo = mlflow.get_experiment_by_name(DATASETS)
    if repo is None:
        repo = mlflow.get_experiment(mlflow.create_experiment(DATASETS))

    # add data set if it is not already existing
    if "name" in kwargs:
        ds_name = kwargs.get("name")
    elif hasattr(result, "name"):
        ds_name = result.name
    else:
        ds_name = _pypads_wrappe.__name__
    if not any(t["name"] == ds_name for t in all_tags(repo.experiment_id)):
        pads.stop_run()
        run = mlflow.start_run(experiment_id=repo.experiment_id)
        dataset_id = run.info.run_id
        pads.add("dataset_id", dataset_id)
        pads.add("dataset_name", ds_name)
        mlflow.set_tag("name", ds_name)
        name = _pypads_context.__name__ + "[" + str(id(result)) + "]." + ds_name + "_data"

        if hasattr(result, "data"):
            if hasattr(result.data, "__self__") or hasattr(result.data, "__func__"):
                try_write_artifact(name, result.data(), write_format)
            else:
                try_write_artifact(name, result.data, write_format)
        else:
            try_write_artifact(name, result, write_format)

        if hasattr(result, "metadata"):
            name = _pypads_context.__name__ + "[" + str(id(result)) + "]." + ds_name + "_metadata"
            if hasattr(result.metadata, "__self__") or hasattr(result.metadata, "__func__"):
                try_write_artifact(name, result.metadata(), WriteFormats.text)
            else:
                try_write_artifact(name, result.metadata, WriteFormats.text)
        pads.resume_run()
        mlflow.set_tag("dataset", dataset_id)
    return result
