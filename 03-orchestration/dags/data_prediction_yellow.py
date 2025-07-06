#!/usr/bin/env python
# coding: utf-8

import base64
import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import xgboost as xgb
from airflow.decorators import dag, task
from airflow.models.param import Param
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import root_mean_squared_error

MODELS_FOLDER = Path("/tmp/models")
MODELS_FOLDER.mkdir(exist_ok=True)
PREPROCESSOR_PATH = MODELS_FOLDER / "preprocessor.b"
RUN_ID_PATH = Path("run_id.txt")
MLFLOW_TRACKING_URI = "http://ec2-16-170-162-168.eu-north-1.compute.amazonaws.com:5000"

default_args = {"owner": "airflow", "start_date": datetime.now(timezone.utc), "retries": 0}

@dag(
    dag_id="data_prediction_yellow",
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
def data_prediction_dag():
    @task(multiple_outputs=True)
    def get_params(**context):
        log = logging.getLogger("airflow.task")
        params = context["params"]
        year = params["year"]
        month = params["month"]
        log.info("Extracted parameters: year=%s, month=%s", year, month)
        return {"year": year, "month": month}

    @task(multiple_outputs=True)
    def calculate_dates(year: int, month: int):
        log = logging.getLogger("airflow.task")
        next_year = year if month < 12 else year + 1
        next_month = month + 1 if month < 12 else 1
        log.info("Calculated dates: next_year=%s, next_month=%s", next_year, next_month)
        return {"next_year": next_year, "next_month": next_month}

    @task
    def read_dataframe(year: int, month: int):
        log = logging.getLogger("airflow.task")
        log.info("Reading data for %s-%02d", year, month)

        url = f"https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{year}-{month:02d}.parquet"
        df = pd.read_parquet(url)
        log.info("Initial dataframe length: %s", len(df))

        df["duration"] = df.tpep_dropoff_datetime  - df.tpep_pickup_datetime
        df.duration = df.duration.dt.total_seconds() / 60

        df = df[(df.duration >= 1) & (df.duration <= 60)]
        log.info("Filtered dataframe shape: %s", df.shape)

        categorical = ["PULocationID", "DOLocationID"]
        df[categorical] = df[categorical].astype(str)

        memory_usage_bytes = df.memory_usage(deep=True).sum()
        memory_usage_mb = memory_usage_bytes / (1024 * 1024)
        log.info("usage: %.2f MB (%d bytes)", memory_usage_mb, memory_usage_bytes)

        return df

    @task(multiple_outputs=True)
    def create_x(df):
        log = logging.getLogger("airflow.task")
        log.info("Creating feature matrix X.")

        dv = DictVectorizer()
        categories = ["PULocationID", "DOLocationID"]
        target = "duration"

        df[categories] = df[categories].astype(str)
        df_train = df[categories].to_dict(orient="records")

        x_train = dv.fit_transform(df_train)
        y_train = df_train[target].to_numpy()

        # Serialize as bytes and encode to base64
        x_pickled = base64.b64encode(pickle.dumps(x_train)).decode('utf-8')
        y_pickled = base64.b64encode(pickle.dumps(y_train)).decode('utf-8')

        return {"x_train": x_pickled, "y_train": y_pickled}

    @task
    def train_model(x_train, y_train):
        log = logging.getLogger("airflow.task")
        log.info("Starting model training.")
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        log.info("Set MLflow tracking URI.")
        mlflow.set_experiment("nyc-taxi-experiment")
        log.info("Set MLflow experiment.")

        #root_mean_squared_error(y_train, y_pred)

        # Deserialize the inputs
        x_train = pickle.loads(base64.b64decode(x_train.encode('utf-8')))
        y_train = pickle.loads(base64.b64decode(y_train.encode('utf-8')))

        with mlflow.start_run() as run:
            log.info("Started MLflow run with ID: %s", run.info.run_id)

            lr = LinearRegression()
            lr.fit(x_train, y_train)
            log.info("Model intercept value: %s", lr.intercept_)
            #y_pred = lr.predict(x_train)
            log.info("Logging model")
            mlflow.sklearn.log_model(
                sk_model=lr,
                artifact_path="model",
                registered_model_name="nyc-taxi-yellow-prediction",
            )
            return run.info.run_id

    # Define task instances and dependencies
    params = get_params()
    dates = calculate_dates(year=params["year"], month=params["month"])

    # Read training and validation data
    df_train = read_dataframe(year=params["year"], month=params["month"])

    # Create feature matrices
    train_x_dict = create_x(df_train)
    x_train = train_x_dict["x_train"]
    y_train = train_x_dict["y_train"]

    # Train model
    run_id = train_model(x_train, y_train)

# Instantiate the DAG
dag_instance = data_prediction_dag()

if __name__ == "__main__":
    dag_instance.test()