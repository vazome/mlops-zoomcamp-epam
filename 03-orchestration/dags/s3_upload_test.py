#!/usr/bin/env python
# coding: utf-8

import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import pandas as pd
import xgboost as xgb
from airflow.decorators import dag, task
from airflow.models.connection import Connection
from airflow.models.param import Param
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import root_mean_squared_error

MODELS_FOLDER = Path("models")
MODELS_FOLDER.mkdir(exist_ok=True)
PREPROCESSOR_PATH = MODELS_FOLDER / "preprocessor.b"
RUN_ID_PATH = Path("run_id.txt")

MAX_DURATION_MIN = 60
MIN_DURATION_MIN = 1

default_args = {"owner": "airflow", "start_date": datetime.now(timezone.utc), "retries": 0}

@dag(
    dag_id="upload_to_s3_test",
    default_args=default_args,
    schedule=None,  # Manual trigger only
    catchup=False,
    start_date=datetime.now(timezone.utc),
    tags=["mlops", "taxi-prediction", "xgboost"],
    params={
        "name": Param(
            "Hello",
            type="string",
            title="Name",
            description="Name of the file to upload to S3",
        ),
        "contents": Param(
            "Hi! I'm a test file",
            type="string",
            title="Contents",
            description="Contents of the file to upload to S3",
        ),
    },
    render_template_as_native_obj=True,
)
def upload_to_s3_test():
    @task(multiple_outputs=True)
    def get_params(**context):
        log = logging.getLogger("airflow.task")
        params = context["params"]
        name = params["name"]
        contents = params["contents"]
        log.info("Extracted parameters: name=%s, contents=%s", name, contents)
        return {"name": name, "contents": contents}

    @task
    def save_objects_to_s3(name: str, contents: str):
        log = logging.getLogger("airflow.task")
        hook =  S3Hook(aws_conn_id="S3")
        conn = Connection.get_connection_from_secrets("S3")
        bucket_name = conn.extra_dejson.get('bucket_name') #get('service_config', {}).get('s3', {}).
        hook.load_string(
                    string_data=f"{contents}",
                    key=f"{name}.txt",
                    bucket_name=bucket_name
                )
        log.info(f"Uploaded to s3://{bucket_name}/{name}.txt")

    # Define task instances and dependencies
    params = get_params()
    save_to_s3 = save_objects_to_s3(name=params["name"], contents=params["contents"])


# Instantiate the DAG
dag_instance = upload_to_s3_test()

if __name__ == "__main__":
    dag_instance.test()