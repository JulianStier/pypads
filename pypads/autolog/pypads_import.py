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
from logging import warning, info
from os.path import expanduser
from types import ModuleType

import mlflow
from boltons.funcutils import wraps

punched_module = set()
mapping_files = glob.glob(expanduser("~") + ".pypads/bindings/**.json")
mapping_files.extend(
    glob.glob(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + "/bindings/resources/mapping/**.json"))

mappings = {}
for m in mapping_files:
    with open(m) as json_file:
        name = os.path.basename(json_file.name)
        mappings[name] = json.load(json_file)


class Mapping:

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
        # for name in dir(module):
        #     reference = getattr(module, name)
        #     if inspect.isclass(reference) and hasattr(reference, "mro"):
        #         try:
        #             overlap = set(reference.mro()[1:]) & punched_classes
        #             if bool(overlap):
        #                 # TODO maybe only for the first one
        #                 for o in overlap:
        #                     if reference not in punched_classes:
        #                         sub_classes.append(
        #                             (reference.__module__ + "." + reference.__qualname__, o.pypads_library,
        #                              o.pypads_alg, o.pypads_content, o.pypads_file))
        #         except Exception as e:
        #             debug("Skipping superclasses of " + str(reference) + ". " + str(e))

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


def new_method_proxy(func):
    """
    Proxy method for calling the non-punched function.
    :param func:
    :return:
    """

    def inner(self, *args):
        return func(self._pads_wrapped_instance, *args)

    return inner


def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])


def to_method_type(cls, self, original_method, wrapped_method):
    if inspect.ismethod(original_method):
        if hasattr(original_method, "__self__") and original_method.__self__ is cls:
            out = wrapped_method
        else:
            out = wrapped_method
    else:
        out = types.MethodType(wrapped_method, self)
    return out


def get_pypads_config():
    from pypads.base import get_current_pads
    from pypads.base import CONFIG_NAME
    pads = get_current_pads()
    run = pads.mlf.get_run(mlflow.active_run().info.run_id)
    if CONFIG_NAME in run.data.tags:
        return ast.literal_eval(run.data.tags[CONFIG_NAME])
    return {"events": {}}


def _wrap(wrappee, *args, **kwargs):
    if inspect.isclass(wrappee):
        _wrap_class(*args, **kwargs)

    elif inspect.isfunction(wrappee):
        _wrap_function(wrappee.__name__, *args, **kwargs)


def _wrap_module(module, mapping):
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


class CallCache:

    def __init__(self):
        self.cache = {}

    def add(self, identifier, reference):
        if identifier not in self.cache:
            self.cache[identifier] = set()
        self.cache[identifier].add(reference)

    def has(self, identifier, reference):
        return identifier in self.cache and reference in self.cache[identifier]

    def delete(self, identifier, reference):
        if identifier in self.cache:
            self.cache[identifier].remove(reference)
            if len(self.cache[identifier]):
                del self.cache[identifier]


call_cache = CallCache()


def _wrap_class(clazz, ctx, mapping):
    if not hasattr(clazz, "_pypads_wrapped") or (
            clazz is not getattr(clazz, "_pypads_wrapped") and issubclass(clazz, getattr(clazz, "_pypads_wrapped"))):
        if not mapping.hooks:
            content = mappings[mapping.file]
            if "default_hooks" in content:
                if "classes" in content["default_hooks"]:
                    if "fns" in content["default_hooks"]["classes"]:
                        mapping.hooks = content["default_hooks"]["classes"]["fns"]

        if hasattr(clazz.__init__, "__module__"):
            original_init = object.__getattribute__(clazz, "__init__")

            @wraps(clazz.__init__)
            def __init__(self, *args, **kwargs):
                entry = False
                if not call_cache.has(id(self), __init__.__name__):
                    call_cache.add(id(self), __init__.__name__)
                    entry = True
                    print("Pypads tracked class " + str(clazz) + " initialized.")
                original_init(self, *args, **kwargs)
                if entry:
                    call_cache.delete(id(self), __init__.__name__)

            try:
                setattr(clazz, "__init__", __init__)
            except Exception as e:
                warning(str(e))

        for k, v in mapping.hooks.items():
            for fn_name in v:
                _wrap_function(fn_name, clazz, mapping)

        reference_name = mapping.reference.rsplit('.', 1)[-1]
        setattr(clazz, "_pypads_mapping", mapping)
        setattr(clazz, "_pypads_wrapped", clazz)
        setattr(ctx, reference_name, clazz)


def get_class_that_defined_method(method):
    if inspect.ismethod(method):
        for cls in inspect.getmro(method.__self__.__class__):
            if cls.__dict__.get(method.__name__) is method:
                return cls
        method = method.__func__  # fallback to __qualname__ parsing
    if inspect.isfunction(method):
        cls = getattr(inspect.getmodule(method),
                      method.__qualname__.split('.<locals>', 1)[0].rsplit('.', 1)[0])
        if isinstance(cls, type):
            return cls
    return getattr(method, '__objclass__', None)  # handle special descriptor objects


def get_hooked_fns(fn, mapping):
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


NONE_OBJECT = object()


def _wrap_method_helper(fn, hook, params, stack, mapping, ctx, fn_type=None, last_element=False):
    if not fn_type or "staticmethod" in str(fn_type):
        @wraps(fn)
        def ctx_setter(*args, pypads_hooked_fn=hook,
                       pypads_hook_params=params, _pypads_mapped_by=mapping, _pypads_current_mapping=mapping, **kwargs):
            print("Static method or function " + str(ctx) + str(fn) + str(hook))

            # check for name collision
            if set([k for k, v in kwargs.items()]) & set(
                    [k for k, v in pypads_hook_params.items()]):
                warning("Hook parameter is overwriting a parameter in the standard "
                        "model call. This most likely will produce side effects.")

            entry = False
            if not call_cache.has(id(fn), pypads_hooked_fn.__name__):
                entry = True
                call_cache.add(id(fn), pypads_hooked_fn.__name__)
                out = pypads_hooked_fn(None, _pypads_wrappe=fn, _pypads_context=ctx,
                                       _pypads_item=fn.__name__, _pypads_fn_stack=stack, _pypads_mapped_by=mapping,
                                       *args,
                                       **{**kwargs, **pypads_hook_params})
            else:
                out = stack.pop()(*args, **kwargs)
            if entry:
                call_cache.delete(id(fn), pypads_hooked_fn.__name__)
            return out
    elif "function" in str(fn_type):
        @wraps(fn)
        def ctx_setter(self, *args, pypads_hooked_fn=hook,
                       pypads_hook_params=params, _pypads_mapped_by=mapping, _pypads_current_mapping=mapping, **kwargs):
            print("Method " + str(ctx) + str(fn) + str(hook))

            if self is not None and not len(stack) is 0 and not inspect.ismethod(stack[0]):
                methods = []
                for callback in stack:
                    methods.append(types.MethodType(callback, self))
                stack.clear()
                stack.extend(methods)

            # check for name collision
            if set([k for k, v in kwargs.items()]) & set(
                    [k for k, v in pypads_hook_params.items()]):
                warning("Hook parameter is overwriting a parameter in the standard "
                        "model call. This most likely will produce side effects.")

            entry = False
            if not call_cache.has(id(self), pypads_hooked_fn.__name__):
                entry = True
                call_cache.add(id(self), pypads_hooked_fn.__name__)
                out = pypads_hooked_fn(self, _pypads_wrappe=fn, _pypads_context=ctx,
                                       _pypads_item=fn.__name__, _pypads_fn_stack=stack, _pypads_mapped_by=mapping,
                                       *args,
                                       **{**kwargs, **pypads_hook_params})
            else:
                out = stack.pop()(*args, **kwargs)
            if entry:
                call_cache.delete(id(self), pypads_hooked_fn.__name__)
            return out
    else:
        @wraps(fn)
        def ctx_setter(cls, *args, pypads_hooked_fn=hook,
                       pypads_hook_params=params, _pypads_mapped_by=mapping, _pypads_current_mapping=mapping, **kwargs):
            print("Class method " + str(ctx) + str(fn) + str(hook))

            # check for name collision
            if set([k for k, v in kwargs.items()]) & set(
                    [k for k, v in pypads_hook_params.items()]):
                warning("Hook parameter is overwriting a parameter in the standard "
                        "model call. This most likely will produce side effects.")

            entry = False
            if not call_cache.has(id(cls), pypads_hooked_fn.__name__):
                entry = True
                call_cache.add(id(cls), pypads_hooked_fn.__name__)
                out = pypads_hooked_fn(_pypads_wrappe=fn, _pypads_context=ctx,
                                       _pypads_item=fn.__name__, _pypads_fn_stack=stack, _pypads_mapped_by=mapping,
                                       *args,
                                       **{**kwargs, **pypads_hook_params})
            else:
                out = stack.pop()(*args, **kwargs)
            if entry:
                call_cache.delete(id(cls), pypads_hooked_fn.__name__)
            return out

    if hasattr(fn, "__self__"):
        stack.append(types.MethodType(ctx_setter, fn.__self__))
    else:
        stack.append(ctx_setter)
    if last_element:
        setattr(ctx, "_pypads_mapping_" + fn.__name__, mapping)
        setattr(ctx, "_pypads_original_" + fn.__name__, fn)
        setattr(ctx, fn.__name__, stack.pop())


def _wrap_function(fn_name, ctx, mapping):
    if inspect.isclass(ctx):
        defining_class = None
        if not hasattr(ctx, "__dict__") or fn_name not in ctx.__dict__:
            mro = ctx.mro()
            for c in mro[1:]:
                defining_class = ctx
                if hasattr(ctx, "__dict__") and fn_name in defining_class.__dict__:
                    break
                defining_class = None
        else:
            defining_class = ctx

        if defining_class:

            if hasattr(defining_class, "_pypads_original_" + fn_name):
                fn = getattr(defining_class, "_pypads_original_" + fn_name)
            else:
                fn = getattr(defining_class, fn_name)

            if isinstance(fn, property):
                fn = fn.fget

            fn_stack = [fn]
            hooks = get_hooked_fns(fn, mapping)
            if len(hooks) > 0:
                for (hook, params) in hooks[:-1]:
                    _wrap_method_helper(fn=fn, hook=hook, params=params, stack=fn_stack, mapping=mapping, ctx=ctx,
                                        fn_type=type(defining_class.__dict__[fn.__name__]))

                (hook, params) = hooks[-1]
                _wrap_method_helper(fn=fn, hook=hook, params=params, stack=fn_stack, mapping=mapping, ctx=ctx,
                                    fn_type=type(defining_class.__dict__[fn.__name__]), last_element=True)
    elif hasattr(ctx, fn_name):
        if hasattr(ctx, "_pypads_original_" + fn_name):
            fn = getattr(ctx, "_pypads_original_" + fn_name)
        else:
            fn = getattr(ctx, fn_name)
        fn_stack = [fn]
        hooks = get_hooked_fns(fn, mapping)
        if len(hooks) > 0:
            for (hook, params) in hooks[:-1]:
                _wrap_method_helper(fn=fn, hook=hook, params=params, stack=fn_stack, mapping=mapping, ctx=ctx)

            (hook, params) = hooks[-1]
            _wrap_method_helper(fn=fn, hook=hook, params=params, stack=fn_stack, mapping=mapping, ctx=ctx,
                                last_element=True)
    else:
        warning(ctx + " is no class or module. Couldn't access " + fn_name + " on it.")


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
    extend_import_module()
    for i in set(mapping.reference.rsplit('.', 1)[0] for mapping in get_implementations() if
                 mapping.reference.rsplit('.', 1)[0] in sys.modules
                 and mapping.reference.rsplit('.', 1)[0] not in punched_module):
        spec = importlib.util.find_spec(i)
        loader = PyPadsLoader(spec.name, spec.origin)
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
