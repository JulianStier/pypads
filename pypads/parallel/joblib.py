import os
import time
from functools import wraps
from typing import List

from pypads.util import is_package_available

if is_package_available("joblib"):
    import joblib

    original_delayed = joblib.delayed


    @wraps(original_delayed)
    def punched_delayed(fn):
        """Decorator used to capture the arguments of a function."""

        @wraps(fn)
        def wrapped_function(*args, _pypads=None, _pypads_active_run_id=None, _pypads_tracking_uri=None,
                             _pypads_affected_modules=None, _pypads_triggering_process=None, **kwargs):
            from pypads.parallel.util import _pickle_tuple, _cloudpickle_tuple
            from pypads import logger
            if _pypads:
                # noinspection PyUnresolvedReferences
                import pypads.pypads
                import mlflow

                is_new_process = not pypads.pypads.current_pads
                if is_new_process:
                    import pypads

                    # reactivate this run in the foreign process
                    mlflow.set_tracking_uri(_pypads_tracking_uri)
                    mlflow.start_run(run_id=_pypads_active_run_id, nested=True)

                    # TODO pickling _pypads takes a long time
                    start_time = time.time()
                    logger.debug("Init Pypads in:" + str(time.time() - start_time))
                    pypads.pypads.current_pads = _pypads

                    _pypads.activate_tracking(reload_warnings=False, affected_modules=_pypads_affected_modules,
                                              clear_imports=True)

                    def clear_mlflow():
                        """
                        Don't close run. This function clears the run which was reactivated from the stack to stop a closing of it.
                        :return:
                        """
                        if len(mlflow.tracking.fluent._active_run_stack) == 1:
                            mlflow.tracking.fluent._active_run_stack.pop()

                    import atexit
                    atexit.register(clear_mlflow)

                from pickle import loads

                start_time = time.time()
                a, b = loads(args[0])
                logger.debug("Loading args from pickle in:" + str(time.time() - start_time))
                from cloudpickle import loads as c_loads
                start_time = time.time()
                wrapped_fn = c_loads(args[1])[0]
                logger.debug("Loading punched function from pickle in:" + str(time.time() - start_time))

                args = a
                kwargs = b

                logger.info("Started wrapped function on process: " + str(os.getpid()))

                out = wrapped_fn(*args, **kwargs)
                if is_new_process:
                    return out, _pypads.cache
                else:
                    return out
            else:
                return fn(*args, **kwargs)

        def delayed_function(*args, **kwargs):
            from pypads.parallel.util import _pickle_tuple, _cloudpickle_tuple
            from pypads.autolog.wrapping.module_wrapping import punched_module_names
            import mlflow
            run = mlflow.active_run()
            if run:
                # TODO only if this is going to be a process and not a thread (how can we know?)
                pickled_params = (_pickle_tuple(args, kwargs), _cloudpickle_tuple(fn))
                args = pickled_params
                from pypads.pypads import get_current_pads

                kwargs = {"_pypads": get_current_pads(), "_pypads_active_run_id": run.info.run_id,
                          "_pypads_tracking_uri": mlflow.get_tracking_uri(),
                          "_pypads_affected_modules": punched_module_names, "_pypads_triggering_process": os.getpid()}
            return wrapped_function, args, kwargs

        try:
            import functools
            delayed_function = functools.wraps(fn)(delayed_function)
        except AttributeError:
            " functools.wraps fails on some callable objects "
        return delayed_function


    setattr(joblib, "delayed", punched_delayed)

    # original_dispatch = joblib.Parallel._dispatch
    #
    # def _dispatch(self, *args, **kwargs):
    #     print(self._backend)
    #     out = original_dispatch(self, *args, **kwargs)
    #     return out
    #
    # joblib.Parallel._dispatch = _dispatch

    original_call = joblib.Parallel.__call__


    @wraps(original_call)
    def joblib_call(self, *args, **kwargs):
        from pypads.caches import PypadsCache
        from pypads import logger
        logger.remove()
        out = original_call(self, *args, **kwargs)
        if isinstance(out, List):
            real_out = []
            for entry in out:
                if isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[1], PypadsCache):
                    real_out.append(entry[0])
                    cache = entry[1]
                    from pypads.pypads import get_current_pads
                    pads = get_current_pads()
                    pads.cache.merge(cache)
                else:
                    real_out.append(entry)
            out = real_out
        return out


    setattr(joblib.Parallel, "__call__", joblib_call)
