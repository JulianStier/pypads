class Repository:

    def __init__(self, *args, name, **kwargs):
        """
        This class abuses mlflow experiments as arbitrary stores.
        :param args:
        :param name: Name of the repository experiment.
        :param kwargs:
        """
        # get the repo or create new where datasets are stored
        self._name = name
        from pypads.app.pypads import get_current_pads
        self.pads = get_current_pads()
        repo = self.pads.mlf.get_experiment_by_name(name)

        if repo is None:
            repo = self.pads.mlf.get_experiment(self.pads.mlf.create_experiment(name))
        self._repo = repo

    def get_object(self, run_id=None, uid=None):
        """
        Gets a persistent object to store to.
        :param uid: Optional uid of object. This allows only for one run storing the object with uid.
        :param run_id: Optional run_id of object. This is the id of the run in which the object should be stored.
        :return:
        """
        return RepositoryObject(self, run_id, uid)

    def context(self, run_id=None):
        """
        Activates the repository context by setting an intermediate run.
        :param run_id: Id of the run to log into. If none is given a new one is created
        :return:
        """

        if run_id:
            return self.pads.api.intermediate_run(experiment_id=self.id, run_id=run_id)
        else:
            return self.pads.api.intermediate_run(experiment_id=self.id)

    @property
    def name(self):
        return self._name

    @property
    def repo(self):
        return self._repo

    @property
    def id(self):
        return self._repo.experiment_id


class RepositoryObject:

    def __init__(self, repository, run_id, uid):
        """
        This is a representation of an object in the repository. It is stored as a run into mlflow. It can be identified
        by either a run_id or by a uid.
        :param repository:
        :param run_id:
        :param uid:
        """
        self.repository = repository
        from pypads.app.pypads import get_current_pads
        self.pads = get_current_pads()

        self.run_id = run_id
        if uid:
            runs = self.pads.mlf.search_runs(experiment_ids=self.repository.id,
                                             filter_string="tags.`pypads_unique_uid` = \"" + uid + "\"")
            if len(runs) > 0:
                self.run_id = runs.pop().info.run_id

        if self.run_id is None:
            self.run_id = self.pads.mlf.create_run(experiment_id=self.repository.id).info.run_id

        if uid:
            self.set_tag("pypads_unique_uid", uid,
                         "Unique id of the object. This might be a hash for a dataset or similar.")

    def log_mem_artifact(self, *args, **kwargs):
        """
        Activates the repository context and stores an artifact from memory into it.
        :param args:
        :param run_id: Id of the run to log into. If none is given a new one is created
        :param kwargs:
        :return:
        """
        with self.repository.context(self.run_id) as ctx:
            self.pads.api.log_mem_artifact(*args, **kwargs)

    def log_artifact(self, *args, **kwargs):
        """
        Activates the repository context and stores an artifact into it.
        :param args:
        :param run_id: Id of the run to log into. If none is given a new one is created
        :param kwargs:
        :return:
        """
        with self.repository.context(self.run_id) as ctx:
            self.pads.api.log_artifact(*args, **kwargs)

    def log_param(self, *args, **kwargs):
        """
        Activates the repository context and stores an parameter into it.
        :param args:
        :param run_id: Id of the run to log into. If none is given a new one is created
        :param kwargs:
        :return:
        """
        with self.repository.context(self.run_id) as ctx:
            self.pads.api.log_param(*args, **kwargs)

    def log_metric(self, *args, **kwargs):
        """
        Activates the repository context and stores an metric into it.
        :param args:
        :param run_id: Id of the run to log into. If none is given a new one is created
        :param kwargs:
        :return:
        """
        with self.repository.context(self.run_id) as ctx:
            self.pads.api.log_metric(*args, **kwargs)

    def set_tag(self, *args, **kwargs):
        """
        Activates the repository context and stores an tag into it.
        :param args:
        :param run_id: Id of the run to log into. If none is given a new one is created
        :param kwargs:
        :return:
        """
        with self.repository.context(self.run_id) as ctx:
            self.pads.api.set_tag(*args, **kwargs)


class SchemaRepository(Repository):

    def __init__(self, *args, **kwargs):
        """
        Repository holding all the relevant schema information
        :param args:
        :param kwargs:
        """
        super().__init__(*args, name="pypads_schemata", **kwargs)
