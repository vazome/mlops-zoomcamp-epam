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
        "year": Param(
            2024,
            type="integer",
            minimum=2009,
            maximum=2030,
            title="Year",
            description="Year of the data to train on (NYC taxi data)",
        ),
        "month": Param(
            1,
            type="integer",
            minimum=1,
            maximum=12,
            title="Month",
            description="Month of the data to train on (1-12)",
        ),
    },
    render_template_as_native_obj=True,
)
def upload_to_s3_test():
    @task(multiple_outputs=True)
    def get_params(**context):
        log = logging.getLogger("airflow.task")
        params = context["params"]
        year = params["year"]
        month = params["month"]
        log.info("Extracted parameters: year=%s, month=%s", year, month)
        return {"year": year, "month": month}

    @task
    def save_objects_to_s3():
        log = logging.getLogger("airflow.task")
        hook =  S3Hook(aws_conn_id="S3")
        conn = Connection.get_connection_from_secrets("S3")
        bucket_name = conn.extra_dejson.get('bucket_name') #get('service_config', {}).get('s3', {}).
        hook.load_string(
                    string_data='Hello, S3!',
                    key='test.txt',
                    bucket_name=bucket_name
                )
        log.info(f"Uploaded to s3://{bucket_name}/test.txt")

    # Define task instances and dependencies
    params = get_params()
    save_to_s3 = save_objects_to_s3()


# Instantiate the DAG
dag_instance = upload_to_s3_test()

if __name__ == "__main__":
    dag_instance.test()