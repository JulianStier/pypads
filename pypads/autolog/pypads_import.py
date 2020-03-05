import inspect
import sys
import types
from functools import wraps
from importlib._bootstrap_external import PathFinder
from logging import warning, info, debug
# noinspection PyUnresolvedReferences
from multiprocessing import Value
from types import ModuleType

from pypads.autolog.mappings import AlgorithmMapping
from pypads.autolog.wrapping import wrap_module, wrap_class, wrap_function, punched_classes, punched_module


def _add_found_class(mapping):
    from pypads.base import get_current_pads
    return get_current_pads().mapping_registry.add_found_class(mapping)


def _get_algorithm_mappings():
    from pypads.base import get_current_pads
    return get_current_pads().mapping_registry.get_relevant_mappings()


def _add_inherited_mapping(clazz, super_class):
    if clazz not in punched_classes:
        found_mapping = AlgorithmMapping(
            clazz.__module__ + "." + clazz.__qualname__, super_class._pypads_mapping.library,
            super_class._pypads_mapping.algorithm, super_class._pypads_mapping.file, super_class._pypads_mapping.hooks)
        found_mapping.in_collection = super_class._pypads_mapping.in_collection
        _add_found_class(mapping=found_mapping)


def duck_punch_loader(spec):
    original_exec = spec.loader.exec_module

    @wraps(original_exec)
    def exec_module(self, module, execute=original_exec):
        out = execute(module)

        # History to check if a class inherits a wrapping intra-module
        mro_entry_history = {}

        # On execution of a module we search for relevant mappings
        # TODO we might want to make this configurable/improve performance. This looks at every imported class.
        for name in dir(module):
            reference = getattr(module, name)
            if inspect.isclass(reference) and hasattr(reference, "mro"):
                try:

                    # Look at the MRO and add classes to be punched which inherit from our punched classes
                    mro_ = reference.mro()[1:]
                    for entry in mro_:
                        if entry not in mro_entry_history.keys():
                            mro_entry_history[entry] = [reference]
                        else:
                            mro_entry_history[entry].append(reference)
                    overlap = set(mro_) & punched_classes
                    if bool(overlap):
                        # TODO maybe only for the first one
                        for o in overlap:
                            _add_inherited_mapping(reference, o)
                except Exception as e:
                    debug("Skipping superclasses of " + str(reference) + ". " + str(e))

        # TODO And every mapping.
        for mapping in _get_algorithm_mappings():
            if mapping.reference.startswith(module.__name__):
                if mapping.reference == module.__name__:
                    wrap_module(module, mapping)
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
                                wrap_class(obj, ctx, mapping)
                                if obj in mro_entry_history:
                                    for clazz in mro_entry_history[obj]:
                                        _add_inherited_mapping(clazz, obj)

                        elif inspect.isfunction(obj):
                            wrap_function(obj.__name__, ctx, mapping)
        return out

    spec.loader.exec_module = types.MethodType(exec_module, spec.loader)
    return spec


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
                # Find a valid importer for the given fullname on the meta_path
                importer = None
                while not spec:
                    importer = next(i)
                    if hasattr(importer, "find_spec"):
                        spec = importer.find_spec(fullname, path)

                # Use the importer as a real importer but wrap it in the PyPadsLoader
                if spec and importer:
                    return duck_punch_loader(spec)
            except StopIteration:
                pass


active = False
is_recursive = False


def extend_import_module():
    """
    Function to add the custom import logic to the python importlib execution
    :return:
    """
    path_finder = [i for i in range(len(sys.meta_path)) if
                   "_frozen_importlib_external.PathFinder" in str(sys.meta_path[i])]
    sys.meta_path.insert(path_finder.pop(), PyPadsFinder())


def activate_tracking(mod_globals=None, reload_modules=False):
    """
    Function to duck punch all objects defined in the mapping files. This should at best be called before importing
    any libraries.
    :param mod_globals: globals() object used to duckpunch already loaded classes
    :return:
    """
    global active
    if not active:
        active = True

        # Add our loader to the meta_path
        extend_import_module()

        # Try to punch if we already imported modules before starting to track
        from pypads.base import get_current_pads

        import sys
        if reload_modules:
            tmp_modules = sys.modules

            # reimport modules
            import importlib
            for module in tmp_modules:
                try:
                    importlib.reload(module)
                except:
                    pass
        else:
            import importlib
            # TODO cleanup the mapping reference rsplit checks
            for i in set(mapping.reference.rsplit('.', 1)[0] for mapping in
                         get_current_pads().mapping_registry.get_algorithms() if
                         mapping.reference.rsplit('.', 1)[0] in sys.modules
                         and mapping.reference.rsplit('.', 1)[0] not in punched_module):
                spec = importlib.util.find_spec(i)
                duck_punch_loader(spec)
                loader = spec.loader
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
