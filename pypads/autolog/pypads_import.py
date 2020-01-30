import ast
import glob
import importlib
import inspect
import json
import os
import sys
import types
from importlib._bootstrap_external import PathFinder, _LoaderBasics
from itertools import chain
from logging import warning, info, debug
from os.path import expanduser
from types import ModuleType

import mlflow
from boltons.funcutils import wraps

from pypads.logging_functions import log_init

punched_module = set()
punched_classes = set()
mapping_files = glob.glob(expanduser("~") + ".pypads/bindings/**.json")
mapping_files.extend(
    glob.glob(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + "/bindings/resources/mapping/**.json"))

mappings = {}
for m in mapping_files:
    with open(m) as json_file:
        name = os.path.basename(json_file.name)
        mappings[name] = json.load(json_file)


class Mapping:
    """
    Mapping for an algorithm defined by a pypads mapping file
    """

    def __init__(self, reference, library, algorithm, file, hooks):
        self._hooks = hooks
        self._algorithm = algorithm
        self._library = library
        self._reference = reference
        self._file = file

    @property
    def file(self):
        return self._file

    @property
    def reference(self):
        return self._reference

    @property
    def library(self):
        return self._library

    @property
    def algorithm(self):
        return self._algorithm

    @property
    def hooks(self):
        return self._hooks

    @hooks.setter
    def hooks(self, value):
        self._hooks = value


def get_implementations():
    """
    Get all mappings defined in all mapping files.
    :return:
    """
    for file, content in mappings.items():
        from pypads.base import get_current_pads
        if not get_current_pads().filter_mapping_files or file in get_current_pads():
            if "algorithms" in content:
                for alg in content["algorithms"]:
                    hooks = None
                    if "hooks" in alg:
                        hooks = alg["hooks"]
                    if alg["implementation"] and len(alg["implementation"]) > 0:
                        for library, reference in alg["implementation"].items():
                            yield Mapping(reference, library, alg, file, hooks)


found_classes = {}
found_fns = {}


def get_found(cache):
    for i, mapping in cache.items():
        yield mapping


def get_relevant_mappings():
    """
    Function to find all relevant mappings. This produces a generator getting extended with found subclasses
    :return:
    """
    return chain(get_implementations(), get_found(found_classes), get_found(found_fns))


class PyPadsLoader(_LoaderBasics):

    def __init__(self, spec):
        self.spec = spec

    def load_module(self, fullname):
        module = self.spec.loader.load_module(fullname)
        return module

    def create_module(self, spec):
        module = self.spec.loader.create_module(spec)
        return module

    def exec_module(self, module):
        out = self.spec.loader.exec_module(module)

        for name in dir(module):
            reference = getattr(module, name)
            if inspect.isclass(reference) and hasattr(reference, "mro"):
                try:
                    overlap = set(reference.mro()[1:]) & punched_classes
                    if bool(overlap):
                        # TODO maybe only for the first one
                        for o in overlap:
                            if reference not in punched_classes:
                                found_classes[reference.__module__ + "." + reference.__qualname__] = Mapping(
                                    reference.__module__ + "." + reference.__qualname__,
                                    o._pypads_mapping.library,
                                    o._pypads_mapping.algorithm,
                                    o._pypads_mapping.file,
                                    o._pypads_mapping.hooks)
                except Exception as e:
                    debug("Skipping superclasses of " + str(reference) + ". " + str(e))

        for mapping in get_relevant_mappings():
            if mapping.reference.startswith(module.__name__):
                if mapping.reference == module.__name__:
                    _wrap_module(module, mapping)
                else:
                    ref = mapping.reference
                    path = ref[len(module.__name__) + 1:].rsplit(".")
                    obj = module
                    ctx = obj
                    for seg in path:
                        try:
                            ctx = obj
                            obj = getattr(obj, seg)
                        except AttributeError:
                            obj = None
                            break

                    if obj:
                        if inspect.isclass(obj):
                            if mapping.reference == obj.__module__ + "." + obj.__name__:
                                _wrap_class(obj, ctx, mapping)

                        elif inspect.isfunction(obj):
                            _wrap_function(obj.__name__, ctx, mapping)
        return out


class PyPadsFinder(PathFinder):
    """
    Import lib extension. This finder provides a special loader if mapping files contain the object.
    """

    def find_spec(cls, fullname, path=None, target=None):
        if fullname not in sys.modules:
            path_ = sys.meta_path[
                    [i for i in range(len(sys.meta_path)) if isinstance(sys.meta_path[i], PyPadsFinder)].pop() + 1:]
            i = iter(path_)
            spec = None
            try:
                importer = None
                while not spec:
                    importer = next(i)
                    if hasattr(importer, "find_spec"):
                        spec = importer.find_spec(fullname, path)
                if spec and importer:
                    spec.loader = PyPadsLoader(importer.find_spec(fullname, path))
                    return spec
            except StopIteration:
                pass


def get_pypads_config():
    """
    Get configuration defined in the current mlflow run
    :return:
    """
    from pypads.base import get_current_pads
    from pypads.base import CONFIG_NAME
    pads = get_current_pads()
    run = pads.mlf.get_run(mlflow.active_run().info.run_id)
    if CONFIG_NAME in run.data.tags:
        return ast.literal_eval(run.data.tags[CONFIG_NAME])
    return {"events": {}}


def _wrap(wrappee, *args, **kwargs):
    """
    Wrap given object with pypads functionality
    :param wrappee:
    :param args:
    :param kwargs:
    :return:
    """
    if inspect.isclass(wrappee):
        _wrap_class(*args, **kwargs)

    elif inspect.isfunction(wrappee):
        _wrap_function(wrappee.__name__, *args, **kwargs)


def _wrap_module(module, mapping):
    """
    Function to wrap modules with pypads functionality
    :param module:
    :param mapping:
    :return:
    """
    if not hasattr(module, "_pypads_wrapped"):
        punched_module.add(module)
        if not mapping.hooks:
            content = mappings[mapping.file]
            if "default_hooks" in content:
                if "modules" in content["default_hooks"]:
                    if "fns" in content["default_hooks"]["modules"]:
                        mapping.hooks = content["default_hooks"]["fns"]

        for _name in dir(module):
            _wrap(getattr(module, _name), module, mapping)

        for k, v in mapping.hooks.items():
            for fn_name in v:
                found_classes[mapping.reference + "." + fn_name] = Mapping(mapping.reference + "." + fn_name,
                                                                           mapping.library, mapping.algorithm,
                                                                           mapping.file, mapping.hooks)

        setattr(module, "_pypads_wrapped", module)


def _wrap_class(clazz, ctx, mapping):
    """
    Wrap a class in given ctx with pypads functionality
    :param clazz:
    :param ctx:
    :param mapping:
    :return:
    """
    if clazz not in punched_classes:
        if not mapping.hooks:
            content = mappings[mapping.file]
            if "default_hooks" in content:
                if "classes" in content["default_hooks"]:
                    if "fns" in content["default_hooks"]["classes"]:
                        mapping.hooks = content["default_hooks"]["classes"]["fns"]

        if hasattr(clazz.__init__, "__module__"):
            original_init = getattr(clazz, "__init__")
            _wrap_method_helper(fn=original_init, hooks=[(log_init, {})], mapping=mapping, ctx=clazz,
                                fn_type="function")

        if mapping.hooks:
            for k, v in mapping.hooks.items():
                for fn_name in v:
                    _wrap_function(fn_name, clazz, mapping)

        reference_name = mapping.reference.rsplit('.', 1)[-1]
        setattr(clazz, "_pypads_mapping", mapping)
        setattr(clazz, "_pypads_wrapped", clazz)
        setattr(ctx, reference_name, clazz)
        punched_classes.add(clazz)


def get_hooked_fns(fn, mapping):
    """
    For a given fn find the hook functions defined in a mapping.
    :param fn:
    :param mapping:
    :return:
    """
    if not mapping.hooks:
        content = mappings[mapping.file]
        if "default_hooks" in content:
            if "fns" in content["default_hooks"]:
                mapping.hooks = content["default_hooks"]["fns"]

    pypads_fn = [k for k, v in mapping.hooks.items() if fn.__name__ in v]
    output = []
    config = get_pypads_config()
    for log_event, event_config in config["events"].items():
        hook_fns = event_config["on"]
        if "with" in event_config:
            hook_params = event_config["with"]
        else:
            hook_params = {}

        # If one hook_fns is in this config.
        if set(hook_fns) & set(pypads_fn):
            from pypads.base import get_current_pads
            pads = get_current_pads()
            fn = pads.function_registry.find_function(log_event)
            output.append((fn, hook_params))
    return output


def _wrapped_inner_function(ctx, *args, _pypads_hooked_fn, _pypads_hook_params, _pypads_wrappe, _pypads_context,
                            _pypads_callback, _pypads_mapped_by, **kwargs):
    """
    Wrapped function logic.
    :param ctx:
    :param args:
    :param _pypads_hooked_fn:
    :param _pypads_hook_params:
    :param _pypads_wrappe:
    :param _pypads_context:
    :param _pypads_item:
    :param _pypads_fn_stack:
    :param _pypads_mapped_by:
    :param kwargs:
    :return:
    """
    if ctx is not None:

        # Track hook execution to stop multiple exections of the same hook
        if not hasattr(ctx, "_pypads_active_calls"):
            setattr(ctx, "_pypads_active_calls", set())
        elif _pypads_hooked_fn in getattr(ctx, "_pypads_active_calls"):
            return _pypads_callback(*args, **kwargs)
        getattr(ctx, "_pypads_active_calls").add(_pypads_hooked_fn)

    try:

        # check for name collision
        if set([k for k, v in kwargs.items()]) & set(
                [k for k, v in _pypads_hook_params.items()]):
            warning("Hook parameter is overwriting a parameter in the standard "
                    "model call. This most likely will produce side effects.")

        out = _pypads_hooked_fn(ctx, _pypads_wrappe=_pypads_wrappe, _pypads_context=_pypads_context,
                                _pypads_callback=_pypads_callback,
                                _pypads_mapped_by=_pypads_mapped_by,
                                *args,
                                **{**kwargs, **_pypads_hook_params})

        if ctx is not None:
            getattr(ctx, "_pypads_active_calls").remove(_pypads_hooked_fn)
        return out
    except Exception as e:
        debug("Cleared cache entry for " + str(_pypads_wrappe) + " because of exception: " + str(e))
        if ctx is not None:
            getattr(ctx, "_pypads_active_calls").remove(_pypads_hooked_fn)
        raise e


def _wrap_method_helper(fn, hooks, mapping, ctx, fn_type=None):
    """
    Helper to differentiate between functions, classmethods, static methods and wrap them
    :param fn:
    :param hook:
    :param params:
    :param stack:
    :param mapping:
    :param ctx:
    :param fn_type:
    :param last_element:
    :return:
    """

    def get_wrapper(_pypads_hooked_fn, _pypads_hook_params, _pypads_wrappe,
                    _pypads_context, _pypads_callback, _pypads_mapped_by):
        if not fn_type or "staticmethod" in str(fn_type):
            @wraps(fn)
            def ctx_setter(*args, _pypads_hooked_fn=_pypads_hooked_fn, _pypads_callback=_pypads_callback,
                           _pypads_hook_params=_pypads_hook_params, _pypads_mapped_by=_pypads_mapped_by, **kwargs):
                debug("Static method hook " + str(ctx) + str(fn) + str(_pypads_hooked_fn))
                return _wrapped_inner_function(None, *args, _pypads_hooked_fn=_pypads_hooked_fn,
                                               _pypads_hook_params=_pypads_hook_params, _pypads_wrappe=_pypads_wrappe,
                                               _pypads_context=_pypads_context,
                                               _pypads_callback=_pypads_callback, _pypads_mapped_by=_pypads_mapped_by,
                                               **kwargs)

            return ctx_setter
        elif "function" in str(fn_type):
            @wraps(fn)
            def ctx_setter(self, *args, _pypads_hooked_fn=_pypads_hooked_fn, _pypads_callback=_pypads_callback,
                           _pypads_hook_params=_pypads_hook_params, _pypads_mapped_by=_pypads_mapped_by, **kwargs):
                debug("Method hook " + str(ctx) + str(fn) + str(_pypads_hooked_fn))
                return _wrapped_inner_function(self, *args, _pypads_hooked_fn=_pypads_hooked_fn,
                                               _pypads_hook_params=_pypads_hook_params, _pypads_wrappe=_pypads_wrappe,
                                               _pypads_context=_pypads_context,
                                               _pypads_callback=_pypads_callback, _pypads_mapped_by=_pypads_mapped_by,
                                               **kwargs)

            return ctx_setter
        else:
            @wraps(fn)
            def ctx_setter(cls, *args, _pypads_hooked_fn=_pypads_hooked_fn, _pypads_callback=_pypads_callback,
                           _pypads_hook_params=_pypads_hook_params, _pypads_mapped_by=_pypads_mapped_by, **kwargs):
                debug("Class method hook " + str(ctx) + str(fn) + str(_pypads_hooked_fn))
                return _wrapped_inner_function(cls, *args, _pypads_hooked_fn=_pypads_hooked_fn,
                                               _pypads_hook_params=_pypads_hook_params, _pypads_wrappe=_pypads_wrappe,
                                               _pypads_context=_pypads_context,
                                               _pypads_callback=_pypads_callback, _pypads_mapped_by=_pypads_mapped_by,
                                               **kwargs)  #

            return ctx_setter

    setattr(ctx, "_pypads_mapping_" + fn.__name__, mapping)
    setattr(ctx, "_pypads_original_" + fn.__name__, fn)

    if not fn_type or "staticmethod" in str(fn_type):
        @wraps(fn)
        def entry(*args, _pypads_hooks=hooks, _pypads_mapped_by=mapping, **kwargs):
            print("Call to tracked static method or function " + str(fn))
            callback = fn
            for (hook, params) in hooks:
                callback = get_wrapper(_pypads_hooked_fn=hook, _pypads_hook_params=params, _pypads_wrappe=fn,
                                       _pypads_context=ctx, _pypads_callback=callback, _pypads_mapped_by=mapping)
            return callback(*args, **kwargs)
    elif "function" in str(fn_type):
        @wraps(fn)
        def entry(self, *args, _pypads_hooks=hooks, _pypads_mapped_by=mapping, **kwargs):
            print("Call to tracked method " + str(fn))
            callback = types.MethodType(fn, self)
            for (hook, params) in hooks:
                callback = types.MethodType(
                    get_wrapper(_pypads_hooked_fn=hook, _pypads_hook_params=params, _pypads_wrappe=fn,
                                _pypads_context=ctx, _pypads_callback=callback, _pypads_mapped_by=mapping), self)

            return callback(*args, **kwargs)

    elif "classmethod" in str(fn_type):
        @wraps(fn)
        def entry(cls, *args, _pypads_hooks=hooks, _pypads_mapped_by=mapping, fn_type=fn_type, **kwargs):
            print("Call to tracked class method " + str(fn))
            callback = types.MethodType(fn, cls)
            for (hook, params) in hooks:
                callback = types.MethodType(
                    get_wrapper(_pypads_hooked_fn=hook, _pypads_hook_params=params, _pypads_wrappe=fn,
                                _pypads_context=ctx, _pypads_callback=callback, _pypads_mapped_by=mapping), cls)
            return callback(*args, **kwargs)
    else:
        return
    setattr(ctx, fn.__name__, entry)


def _wrap_function(fn_name, ctx, mapping):
    """
    Function to wrap the given fn_name on the ctx object with pypads function calls
    :param fn_name:
    :param ctx:
    :param mapping:
    :return:
    """
    if inspect.isclass(ctx):
        defining_class = None
        if not hasattr(ctx, "__dict__") or fn_name not in ctx.__dict__:
            mro = ctx.mro()
            for c in mro[1:]:
                defining_class = ctx
                if hasattr(ctx, "__dict__") and fn_name in defining_class.__dict__ and callable(
                        defining_class.__dict__[fn_name]):
                    break
                defining_class = None
        else:
            defining_class = ctx

        if defining_class:

            fn = None
            if hasattr(defining_class, "_pypads_original_" + fn_name):
                fn = getattr(defining_class, "_pypads_original_" + fn_name)
            else:
                try:
                    fn = getattr(defining_class, fn_name)
                except Exception as e:
                    warning(str(e))

            # skip wrong extractions TODO fix for structure like <class 'sklearn.utils.metaestimators._IffHasAttrDescriptor'>
            if not fn or not callable(fn):
                return

            if isinstance(fn, property):
                fn = fn.fget

            hooks = get_hooked_fns(fn, mapping)
            if len(hooks) > 0:
                _wrap_method_helper(fn=fn, hooks=hooks, mapping=mapping, ctx=ctx,
                                    fn_type=type(defining_class.__dict__[fn.__name__]))
    elif hasattr(ctx, fn_name):
        if hasattr(ctx, "_pypads_original_" + fn_name):
            fn = getattr(ctx, "_pypads_original_" + fn_name)
        else:
            fn = getattr(ctx, fn_name)
        hooks = get_hooked_fns(fn, mapping)
        if len(hooks) > 0:
            _wrap_method_helper(fn=fn, hooks=hooks, mapping=mapping, ctx=ctx)
    else:
        warning(ctx + " is no class or module. Couldn't access " + fn_name + " on it.")


active = False


def extend_import_module():
    """
    Function to add the custom import logic to the python importlib execution
    :return:
    """
    path_finder = [i for i in range(len(sys.meta_path)) if
                   "_frozen_importlib_external.PathFinder" in str(sys.meta_path[i])]
    sys.meta_path.insert(path_finder.pop(), PyPadsFinder())


def activate_tracking(mod_globals=None):
    """
    Function to duck punch all objects defined in the mapping files. This should at best be called before importing
    any libraries.
    :param mod_globals: globals() object used to duckpunch already loaded classes
    :return:
    """
    global active
    if not active:
        active = True

        extend_import_module()
        for i in set(mapping.reference.rsplit('.', 1)[0] for mapping in get_implementations() if
                     mapping.reference.rsplit('.', 1)[0] in sys.modules
                     and mapping.reference.rsplit('.', 1)[0] not in punched_module):
            spec = importlib.util.find_spec(i)
            loader = PyPadsLoader(spec)
            module = loader.load_module(i)
            loader.exec_module(module)
            sys.modules[i] = module
            warning(i + " was imported before PyPads. PyPads has to be imported before importing tracked libraries."
                        " Otherwise it can only try to wrap classes on global level.")
            if mod_globals:
                for k, l in mod_globals.items():
                    if isinstance(l, ModuleType) and i in str(l):
                        mod_globals[k] = module
                    elif inspect.isclass(l) and i in str(l) and hasattr(module, l.__name__):
                        if k not in mod_globals:
                            warning(i + " was imported before PyPads, but couldn't be modified on globals.")
                        else:
                            info("Modded " + i + " after importing it. This might fail.")
                            mod_globals[k] = getattr(module, l.__name__)
