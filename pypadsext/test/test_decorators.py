from pypads.test.sklearn.base_sklearn_test import BaseSklearnTest, sklearn_pipeline_experiment


class PyPadrePadsTest(BaseSklearnTest):
    def test_pipeline(self):
        """
        This example will track the experiment exection with the default configuration.
        :return:
        """
        # --------------------------- setup of the tracking ---------------------------
        # Activate tracking of pypads
        from pypadsext.base import PyPadrePads
        tracker = PyPadrePads()

        import timeit
        t = timeit.Timer(sklearn_pipeline_experiment)
        print(t.timeit(1))

        # --------------------------- asserts ---------------------------
        # TODO
        # !-------------------------- asserts ---------------------------
