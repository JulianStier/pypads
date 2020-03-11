from pypads.functions.loggers.base_logger import LoggingFunction


# def parameter_search(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback, **kwargs):
#     from pypads.base import get_current_pads
#     from pypadsext.base import PyPadrePads
#     pads: PyPadrePads = get_current_pads()
#     pads.cache.add("parameter_search", self)
#
#     result = _pypads_callback(*args, **kwargs)
#     pads.cache.pop("parameter_search")
#     return result
#
#
# def parameter_search_executor(self, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
#                               **kwargs):
#     from pypads.base import get_current_pads
#     from pypadsext.base import PyPadrePads
#
#     pads: PyPadrePads = get_current_pads()
#     if pads.cache.exists("parameter_search"):
#         with pads.api.intermediate_run():
#             out = _pypads_callback(*args, **kwargs)
#         return out
#     else:
#         return _pypads_callback(*args, **kwargs)


class ParameterSearch(LoggingFunction):

    def __pre__(self, ctx, *args, **kwargs):
        from pypads.base import get_current_pads
        from pypadsext.base import PyPadrePads
        pads: PyPadrePads = get_current_pads()
        pads.cache.add("parameter_search", ctx)

    def __post__(self, ctx, *args, **kwargs):
        from pypads.base import get_current_pads
        from pypadsext.base import PyPadrePads
        pads: PyPadrePads = get_current_pads()

        pads.cache.pop("parameter_search")


class ParameterSearchExecutor(LoggingFunction):

    def call_wrapped(self, ctx, *args, _pypads_wrappe, _pypads_context, _pypads_mapped_by, _pypads_callback,
                     _kwargs, **_pypads_hook_params):
        from pypads.base import get_current_pads
        from pypadsext.base import PyPadrePads
        pads: PyPadrePads = get_current_pads()

        if pads.cache.exists("parameter_search"):
            with pads.api.intermediate_run():
                out = _pypads_callback(*args, **_kwargs)
            return out
        else:
            return _pypads_callback(*args, **_kwargs)
