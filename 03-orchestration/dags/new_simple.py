from __future__ import annotations

import logging

import mlflow
from airflow.sdk import dag, task


@dag
def new_simple_dag():
    @task
    def my_task():
        log = logging.getLogger("airflow.task")

        # Get MLflow version and configuration info
        log.info("=== MLflow Doctor Output ===")
        mlflow.doctor()

        # Get MLflow version
        log.info("MLflow version: %s", mlflow.__version__)

        # Get tracking URI
        tracking_uri = mlflow.get_tracking_uri()
        log.info("MLflow tracking URI: %s", tracking_uri)

        # Get artifact URI for default experiment
        try:
            experiment = mlflow.get_experiment_by_name("Default")
            if experiment:
                log.info(
                    "Default experiment artifact location: %s",
                    experiment.artifact_location,
                )
        except mlflow.MlflowException as e:
            log.info("Could not get default experiment: %s", e)

        # Try to create a test experiment to verify connectivity
        try:
            experiment_name = "airflow-test-experiment"
            experiment_id = mlflow.create_experiment(experiment_name)
            log.info(
                "Successfully created test experiment '%s' with ID: %s",
                experiment_name,
                experiment_id,
            )

            # Clean up the test experiment
            mlflow.delete_experiment(experiment_id)
            log.info("Cleaned up test experiment")
        except mlflow.MlflowException as e:
            log.info("Test experiment creation failed: %s", e)

        return {
            "mlflow_version": mlflow.__version__,
            "tracking_uri": tracking_uri,
            "doctor_executed": True,
        }

    my_task()


dag_instance = new_simple_dag()