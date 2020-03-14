import time
from collections import OrderedDict
from logging import info

from pypads.logging_util import WriteFormats


class TimingDefined(Exception):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def timed(f):
    start = time.time()
    ret = f()
    elapsed = time.time() - start
    return ret, elapsed


def print_timings():
    from pypads.base import get_current_pads
    pads = get_current_pads()

    timings: OrderedDict = pads.cache.run_get("timings")
    out = ""
    for k, v in timings.items():
        out += v + "\n"
    pads.api.log_mem_artifact("timings", out, write_format=WriteFormats.text.text)


def add_run_time(name, time):
    from pypads.base import get_current_pads
    pads = get_current_pads()

    pads.api.register_post_fn("timings", print_timings)

    if not pads.cache.run_exists("timings"):
        pads.cache.run_add("timings", OrderedDict())

    timings: OrderedDict = pads.cache.run_get("timings")

    if name not in timings:
        value = ""
        # dashes
        for i in range(1, pads.call_tracker.call_depth()):
            value += "\t"
        timings[name] = value + " " + name + ": " + str(time)
        info(name + " done after: " + str(time) + "s")
    else:
        raise TimingDefined("Timing already defined for " + name)
