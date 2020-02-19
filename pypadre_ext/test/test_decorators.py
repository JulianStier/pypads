import unittest
import os


class PypadsEXT(unittest.TestCase):

    def test_dataset(self):
        """
        This example will track the dataset created by the decorated function
        """
        # --------------------------- setup of the tracking ---------------------------
        # Activate tracking of pypads
        from pypadre_ext.pypads_padre import PyPadsEXT
        tracker = PyPadsEXT()

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

        @tracker.dataset(name=ds_name, metadata={"attributes": columns_wine, "target": columns_wine[-1]})
        def load_iris():
            from sklearn.datasets import load_iris
            return load_iris()

        data = load_iris()

        # --------------------------- asserts ---------------------------
        import mlflow
        datasets_repo = mlflow.get_experiment_by_name("datasets")
        datasets = tracker.mlf.list_run_infos(datasets_repo.experiment_id)

        def get_name(run_info):
            tags = tracker.mlf.list_artifacts(run_info.run_id, path='../tags')
            for tag in tags:
                if '/name' in tag.path:
                    with open(os.path.normpath(os.path.join(run_info.artifact_uri.replace('file://',''),tag.path)), 'r') as f:
                        name = f.read()
                    return name
        ds_names = [ get_name(ds) for ds in datasets]
        assert ds_name in ds_names

        # !-------------------------- asserts ---------------------------
        # End the mlflow run opened by PyPads
        mlflow.end_run()

    def test_splitter(self):
        # --------------------------- setup of the tracking ---------------------------
        # Activate tracking of pypads
        from pypadre_ext.pypads_padre import PyPadsEXT
        tracker = PyPadsEXT()

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

        @tracker.dataset(name=ds_name, metadata={"attributes": columns_wine, "target": columns_wine[-1]})
        def load_iris():
            from sklearn.datasets import load_iris
            return load_iris()

        @tracker.splitter(dataset=ds_name)
        def splitter(data, training=0.6):
            import numpy as np
            idx = np.arange(data.shape[0])
            cut = int(len(idx)*training)
            targets = data[:,-1][cut:]
            return 0, idx[:cut], idx[cut:], targets

        data = load_iris()

        num, train_idx, test_idx = splitter(data)

        # --------------------------- asserts ---------------------------
        import mlflow
        datasets_repo = mlflow.get_experiment_by_name("datasets")
        datasets = tracker.mlf.list_run_infos(datasets_repo.experiment_id)

        def get_name(run_info):
            tags = tracker.mlf.list_artifacts(run_info.run_id, path='../tags')
            for tag in tags:
                if '/name' in tag.path:
                    with open(os.path.normpath(os.path.join(run_info.artifact_uri.replace('file://', ''), tag.path)),
                              'r') as f:
                        name = f.read()
                    return name

        ds_names = [get_name(ds) for ds in datasets]
        assert ds_name in ds_names

        # !-------------------------- asserts ---------------------------
        # End the mlflow run opened by PyPads
        mlflow.end_run()