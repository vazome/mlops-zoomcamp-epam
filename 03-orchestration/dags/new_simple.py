from __future__ import annotations

import logging

import mlflow
from airflow.sdk import dag, task


@dag
def new_simple_dag():
    @task
    def my_task():
        log = logging.getLogger("airflow.task")
        mlflow.doctor()
        pass

    my_task()

dag_instance = new_simple_dag()