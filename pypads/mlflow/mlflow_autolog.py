import gorilla
from mlflow.utils import experimental

added_autologs = set()
mlflow_autolog_fns = {}
mlflow_autolog_callbacks = []


def _to_patch_id(patch):
    return str(patch.desitination)


def fake_gorilla_apply(patch):
    if patch.name not in mlflow_autolog_fns:
        mlflow_autolog_fns[patch.name] = {}
    mlflow_autolog_fns[patch.name][patch.destination] = patch


# For now only take last added callback
def fake_gorilla_get_original_attribute(clz, fn_name):
    return mlflow_autolog_callbacks.pop()


gorilla.apply = fake_gorilla_apply
gorilla.get_original_attribute = fake_gorilla_get_original_attribute


def _is_package_available(name):
    import importlib
    spam_loader = importlib.util.find_spec(name)
    return spam_loader is not None


# TODO cleanup
@experimental
def autologgers(self, *args, _pypads_autologgers=None, _pypads_wrappe, _pypads_context, _pypads_mapped_by,
                _pypads_callback, **kwargs):
    if _pypads_autologgers is None:
        _pypads_autologgers = ["keras", "tensorflow", "xgboost", "gluon", "spark"]

    if 'tensorflow' in _pypads_autologgers and 'tensorflow' not in added_autologs and _is_package_available(
            'tensorflow'):
        added_autologs.add('tensorflow')
        from mlflow import tensorflow
        tensorflow.autolog()

    if 'keras' in _pypads_autologgers and 'keras' not in added_autologs and _is_package_available('keras'):
        added_autologs.add('keras')
        from mlflow import keras
        keras.autolog()

    if 'xgboost' in _pypads_autologgers and 'xgboost' not in added_autologs and _is_package_available('xgboost'):
        added_autologs.add('xgboost')
        from mlflow import xgboost
        xgboost.autolog()

    if 'gluon' in _pypads_autologgers and 'gluon' not in added_autologs and _is_package_available('gluon'):
        added_autologs.add('gluon')
        from mlflow import gluon
        gluon.autolog()

    if 'spark' in _pypads_autologgers and 'spark' not in added_autologs and _is_package_available('spark'):
        added_autologs.add('spark')
        from mlflow import spark
        spark.autolog()

    if _pypads_wrappe.__name__ in mlflow_autolog_fns:
        for ctx, patch in mlflow_autolog_fns[_pypads_wrappe.__name__].items():
            if ctx == _pypads_context or issubclass(_pypads_context, ctx):
                mlflow_autolog_callbacks.append(_pypads_callback)

                # TODO hacky fix for keras
                if 'keras' in str(_pypads_mapped_by.library) and args[5] is None:
                    tmp_args = list(args)
                    tmp_args[5] = []
                    args = tuple(tmp_args)

                    def unbound(self, *args, **kwargs):
                        return _pypads_callback(*args, **kwargs)

                    mlflow_autolog_callbacks.pop()
                    mlflow_autolog_callbacks.append(unbound)

                return patch.obj(self, *args, **kwargs)
    return _pypads_callback(*args, **kwargs)
