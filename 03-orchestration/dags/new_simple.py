from __future__ import annotations

import logging

from airflow.sdk import dag, task


@dag
def new_simple_dag():
    @task
    def my_task():
        log = logging.getLogger("airflow.task")
        log.info("Reading data")
        pass

    my_task()

dag_instance = new_simple_dag()