punch_dummy_mapping = {
    "default_hooks": {
        "modules": {
            "fns": {}
        },
        "classes": {
            "fns": {}
        },
        "fns": {}
    },
    "algorithms": [
        {
            "name": "punchtest",
            "other_names": [],
            "implementation": {
                "sklearn": "test_classes.dummy_classes.PunchDummy"
            },
            "hooks": {
                "pypads_dummy_hook": "always"
            }
        }],
    "metadata": {
        "author": "Thomas Weißgerber",
        "library": "pypads",
        "library_version": "0.0.1",
        "mapping_version": "0.1"
    }
}


def _get_punch_dummy_mapping():
    from pypads.autolog.mappings import MappingFile
    return MappingFile("punch_dummy", punch_dummy_mapping)


class PunchDummy:
    def something(self):
        pass


class PunchDummy2(PunchDummy):
    def __init__(self, value):
        self._value = value

    @property
    def value(self):
        return self._value
