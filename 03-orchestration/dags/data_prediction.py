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
from airflow.models.connection import Connection
from airflow.models.param import Param
from airflow.models.xcom import BaseXCom
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import root_mean_squared_error

RUN_ID_PATH = Path("run_id.txt")
MLFLOW_TRACKING_URI = "http://mlflow.mlflow.svc.cluster.local:5000"
MAX_DURATION_MIN = 60
MIN_DURATION_MIN = 1

default_args = {"owner": "airflow", "start_date": datetime.now(timezone.utc), "retries": 0}

@dag(
    dag_id="data_prediction",
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
        url = f"https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_{year}-{month:02d}.parquet"
        df = pd.read_parquet(url)
        log.info("Initial dataframe shape: %s", df.shape)

        df["duration"] = df.lpep_dropoff_datetime - df.lpep_pickup_datetime
        df.duration = df.duration.apply(lambda td: td.total_seconds() / 60)

        df = df[(df.duration >= MIN_DURATION_MIN) & (df.duration <= MAX_DURATION_MIN)]
        log.info("Filtered dataframe shape: %s", df.shape)

        categorical = ["PULocationID", "DOLocationID"]
        df[categorical] = df[categorical].astype(str)

        df["PU_DO"] = df["PULocationID"] + "_" + df["DOLocationID"]

        return df

#    @task
#    def save_objects_to_s3(name: str, contents: str):
#        """Save objects to S3 bucket. We may need it of XCOM fails"""
#        log = logging.getLogger("airflow.task")
#        hook =  S3Hook(aws_conn_id="S3")
#        conn = Connection.get_connection_from_secrets("S3")
#        bucket_name = conn.extra_dejson.get('bucket_name') #get('service_config', {}).get('s3', {}).
#        hook.load_string(
#                    string_data=f"{contents}",
#                    key=f"{name}.txt",
#                    bucket_name=bucket_name,
#                )
#        log.info(f"Uploaded to s3://{bucket_name}/{name}.txt")

    @task(multiple_outputs=True)
    def create_x(df, dv=None):
        log = logging.getLogger("airflow.task")
        log.info("Creating feature matrix X.")
        categorical = ["PU_DO"]
        numerical = ["trip_distance"]
        dicts = df[categorical + numerical].to_dict(orient="records")

        if dv is None:
            log.info("No DictVectorizer provided, fitting a new one.")
            dv = DictVectorizer(sparse=True)  # Use dense arrays directly so it is serializable
            x = dv.fit_transform(dicts)
        else:
            dv = pickle.loads(base64.b64decode(dv.encode('utf-8')))
            log.info("Using existing DictVectorizer to transform data.")
            x = dv.transform(dicts)
        x_pickled = base64.b64encode(pickle.dumps(x)).decode('utf-8')
        dv_pickled = base64.b64encode(pickle.dumps(dv)).decode('utf-8')

        log.info("Feature matrix shape: %s", x.shape)
        return {"x": x_pickled, "dv": dv_pickled}

    @task(multiple_outputs=True)
    def extract_target(df_train, df_val):
        log = logging.getLogger("airflow.task")
        log.info("Extracting target variable 'duration' from DataFrames.")
        target = "duration"
        #y_train = df_train[target].to_numpy()
        #y_val = df_val[target].to_numpy()
        #log.info("y_train shape: %s, y_val shape: %s", y_train.shape, y_val.shape)

        # Convert to Python lists for serialization - XCom compatibility
        y_train = df_train[target].to_list()
        y_val = df_val[target].to_list()
        log.info("y_train shape: %s, y_val shape: %s", len(y_train), len(y_val))
        return {"y_train": y_train, "y_val": y_val}

    @task
    def train_model(x_train, y_train, x_val, y_val, dv):
        log = logging.getLogger("airflow.task")
        log.info("Starting model training.")
        mlflow.autolog()
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        log.info("Set MLflow tracking URI.")
        mlflow.set_experiment("nyc-taxi-experiment")
        log.info("Set MLflow experiment.")

        # Deserialize the inputs, unnload and convert to NumPy arrays
        y_train = np.array(y_train)
        y_val = np.array(y_val)
        dv = pickle.loads(base64.b64decode(dv.encode('utf-8')))
        x_train = pickle.loads(base64.b64decode(x_train.encode('utf-8')))
        x_val = pickle.loads(base64.b64decode(x_val.encode('utf-8')))
        with mlflow.start_run() as run:
            log.info("Started MLflow run with ID: %s", run.info.run_id)
            train = xgb.DMatrix(x_train, label=y_train)
            valid = xgb.DMatrix(x_val, label=y_val)

            best_params = {
                "learning_rate": 0.09585355369315604,
                "max_depth": 30,
                "min_child_weight": 1.060597050922164,
                "objective": "reg:linear",
                "reg_alpha": 0.018060244040060163,
                "reg_lambda": 0.011658731377413597,
                "seed": 42,
            }

            log.info("Logging parameters: %s", best_params)
            mlflow.log_params(best_params)

            log.info("Training XGBoost model.")
            booster = xgb.train(
                params=best_params,
                dtrain=train,
                num_boost_round=30,
                evals=[(valid, "validation")],
                early_stopping_rounds=50,
            )
            log.info("Model training finished.")

            y_pred = booster.predict(valid)
            rmse = root_mean_squared_error(y_val, y_pred)
            log.info("Validation RMSE: %s", rmse)
            mlflow.log_metric("rmse", rmse)

            log.info("Saving and logging preprocessor artifact.")
            MODELS_FOLDER = Path("/tmp/models")
            MODELS_FOLDER.mkdir(exist_ok=True)
            PREPROCESSOR_PATH = MODELS_FOLDER / "preprocessor.b"
            with PREPROCESSOR_PATH.open("wb") as f_out:
                pickle.dump(dv, f_out)
            mlflow.log_artifact(str(PREPROCESSOR_PATH), artifact_path="preprocessor")
            log.info("Preprocessor artifact logged.")

            log.info("Logging XGBoost model.")
            mlflow.xgboost.log_model(booster, artifact_path="models_mlflow")
            log.info("XGBoost model logged.")

            with RUN_ID_PATH.open("w") as f:
                f.write(run.info.run_id)
            mlflow.log_artifact(str(RUN_ID_PATH), artifact_path="outputs")
            log.info("Logged run_id.txt as artifact.")

            return run.info.run_id

    # Define task instances and dependencies
    params = get_params()
    dates = calculate_dates(year=params["year"], month=params["month"])

    # Read training and validation data
    df_train = read_dataframe(year=params["year"], month=params["month"])
    df_val = read_dataframe(year=dates["next_year"], month=dates["next_month"])

    # Extract target variables
    target_dict = extract_target(df_train, df_val)
    y_train = target_dict["y_train"]
    y_val = target_dict["y_val"]

    # Create feature matrices
    train_x_dict = create_x(df_train)
    x_train = train_x_dict["x"]
    dv = train_x_dict["dv"]
    val_x_dict = create_x(df_val, dv=dv)
    x_val = val_x_dict["x"]

    # Train model
    run_id = train_model(x_train, y_train, x_val, y_val, dv)

# Instantiate the DAG
dag_instance = data_prediction_dag()

if __name__ == "__main__":
    dag_instance.test()