from enum import Enum

from pypadsext.util import _is_package_available


class Data:
    class Types(Enum):
        if _is_package_available('sklearn'):
            from sklearn.utils import Bunch
            bunch = Bunch
        else:
            bunch = "sklearn.Bunch"
        if _is_package_available('numpy'):
            from numpy import ndarray
            Ndarray = ndarray
        else:
            ndarray = 'numpy.ndarray'
        if _is_package_available('pandas'):
            from pandas import DataFrame, Series
            dataframe = DataFrame
            series = Series
        else:
            dataframe = 'pandas.DataFrame'
            series = 'pandas.Series'
        if _is_package_available('networkx'):
            from networkx import Graph
            graph = Graph
        else:
            graph = 'networkx.Graph'
        dict = dict


def numpy_crawl(obj, **kwargs):
    metadata = {"type": str(Data.Types.ndarray.value), "shape": obj.shape}
    metadata = {**metadata, **kwargs}
    data = obj
    return data, metadata, None


def dataframe_crawl(obj, **kwargs):
    metadata = {"type": str(Data.Types.dataFrame.value), "shape": obj.shape, "features": obj.columns}
    metadata = {**metadata, **kwargs}
    data = obj
    targets = None
    if "target" in obj.columns:
        targets = data[[col for col in obj.columns if "target" in col]]
    return data, metadata, targets


def bunch_crawl(obj, **kwargs):
    import numpy as np
    data = np.concatenate([obj.get('data'), obj.get("target").reshape(len(obj.get("target")), 1)], axis=1)
    metadata = {"type": str(Data.Types.bunch.value), "features_names": obj.get("feature_names"),
                "target_names": list(obj.get("target_names")), "description": obj.get("DESCR"), "shape": data.shape}
    metadata = {**metadata, **kwargs}
    return data, metadata, obj.get("target")


def graph_crawl(obj, **kwargs):
    metadata = {"type": str(Data.Types.graph.value), "shape": (obj.number_of_edges(), obj.number_of_nodes())}
    metadata = {**metadata, **kwargs}
    data = obj
    return data, metadata, None


def object_crawl(obj, **kwargs):
    metadata = {"type": str(object)}
    metadata = {**metadata, **kwargs}
    if hasattr(obj, "shape"):
        metadata.update({"shape": obj.shape})
    targets = None
    if hasattr(obj, "targets"):
        targets = obj.targets
        metadata.update({"targets": targets})
    data = obj
    return data, metadata, targets


crawl_fns = {
    str(Data.Types.bunch.value): bunch_crawl,
    str(Data.Types.ndarray.value): numpy_crawl,
    str(Data.Types.dataframe.value): dataframe_crawl,
    str(Data.Types.graph.value): graph_crawl,
    str(object): object_crawl
}


def _identify_data_object(obj):
    """
    This function would try to get as much information from this object
    :param obj: obj to strip
    :return:
    """
    obj_ctx = None
    for _type in Data.Types:
        if type(_type.value) == "str":
            if type(obj) == _type.value:
                obj_ctx = _type.value
                break
        else:
            if isinstance(obj, _type.value):
                obj_ctx = _type.value
                break
    return obj_ctx


def _scrape_obj(obj, ctx=None, **kwargs):
    """
    Depending on the object type, crawl information from the object
    :param obj:
    :param ctx:
    :return:
    """
    _proxy_fn = crawl_fns[str(ctx)]
    data, metadata, targets = _proxy_fn(obj, **kwargs)
    return data, metadata, targets


def scrape_data(obj, **kwargs):
    ctx = _identify_data_object(obj)
    return _scrape_obj(obj, ctx, **kwargs)
