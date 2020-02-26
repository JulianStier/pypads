import os
import unittest


class PyPadrePadsTest(unittest.TestCase):

    def test_dataset(self):
        """
        This example will track the concepts created by the decorated function
        """
        # --------------------------- setup of the tracking ---------------------------
        # Activate tracking of pypads
        from pypadsext.base import PyPadrePads
        tracker = PyPadrePads()

        cwd = os.getcwd()
        columns_wine = [
            "Fixed acidity.",
            "Volatile acidity.",
            "Citric acid.",
            "Residual sugar.",
            "Chlorides.",
            "Free sulfur dioxide.",
            "Total sulfur dioxide.",
            "Density.",
            "pH.",
            "Sulphates.",
            "Alcohol.",
            "Quality"]

        ds_name = "winequality_red"

        @tracker.decorators.dataset(name=ds_name, columns=columns_wine, target=[-1])
        def load_wine():
            import numpy as np
            name = "/winequality-red.csv"
            data = np.loadtxt(cwd + name, delimiter=';', usecols=range(12))
            return data

        data = load_wine()

        # --------------------------- asserts ---------------------------
        import mlflow
        datasets_repo = mlflow.get_experiment_by_name("datasets")
        datasets = tracker.mlf.list_run_infos(datasets_repo.experiment_id)

        def get_name(run_info):
            tags = tracker.mlf.list_artifacts(run_info.run_id, path='../tags')
            for tag in tags:
                if '/pypads.dataset' in tag.path:
                    with open(os.path.normpath(os.path.join(run_info.artifact_uri.replace('file://', ''), tag.path)),
                              'r') as f:
                        name = f.read()
                    return name

        ds_names = [get_name(ds) for ds in datasets]
        assert ds_name in ds_names

        # !-------------------------- asserts ---------------------------
        # End the mlflow run opened by PyPads
        mlflow.end_run()

    def test_custom_splitter(self):
        # --------------------------- setup of the tracking ---------------------------
        # Activate tracking of pypads
        from pypadsext.base import PyPadrePads
        tracker = PyPadrePads()

        @tracker.decorators.dataset(name="iris")
        def load_iris():
            from sklearn.datasets import load_iris
            return load_iris()

        @tracker.decorators.splitter(default=False)
        def splitter(data, training=0.6):
            import numpy as np
            idx = np.arange(data.shape[0])
            cut = int(len(idx) * training)
            return idx[:cut], idx[cut:]

        data = load_iris()

        train_idx, test_idx = splitter(data.data, training=0.7)

        # --------------------------- asserts ---------------------------
        import mlflow
        # !-------------------------- asserts ---------------------------
        # End the mlflow run opened by PyPads
        mlflow.end_run()

    def test_default_splitter_with_no_params(self):
        # --------------------------- setup of the tracking ---------------------------
        # Activate tracking of pypads
        from pypadsext.base import PyPadrePads
        tracker = PyPadrePads()

        @tracker.decorators.dataset(name="iris")
        def load_iris():
            from sklearn.datasets import load_iris
            return load_iris()

        @tracker.decorators.splitter(default=True)
        def splitter():
            return

        data = load_iris()

        train_idx, test_idx, val_idx = splitter(data)

        # --------------------------- asserts ---------------------------
        import mlflow
        # !-------------------------- asserts ---------------------------
        # End the mlflow run opened by PyPads
        mlflow.end_run()
