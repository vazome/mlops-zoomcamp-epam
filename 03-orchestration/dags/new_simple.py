from __future__ import annotations

from airflow.sdk import dag, task


@dag
def new_simple_dag():
    @task
    def my_task():
        pass

    my_task()

dag_instance = new_simple_dag()