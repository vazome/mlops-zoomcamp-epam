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
from airflow.models.param import Param
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

    @task
    def create_x(df, dv=None):
        log = logging.getLogger("airflow.task")
        log.info("Creating feature matrix X.")
        categorical = ["PU_DO"]
        numerical = ["trip_distance"]
        dicts = df[categorical + numerical].to_dict(orient="records")

        if dv is None:
            log.info("No DictVectorizer provided, fitting a new one.")
            dv = DictVectorizer(sparse=True)
            x = dv.fit_transform(dicts)
        else:
            log.info("Using existing DictVectorizer to transform data.")
            x = dv.transform(dicts)

        log.info("Feature matrix shape: %s", x.shape)
        return {"x": x, "dv": dv}

    @task
    def train_model(x_train, y_train, x_val, y_val, dv):
        log = logging.getLogger("airflow.task")
        log.info("Starting model training.")
        mlflow.set_tracking_uri("http://mlflow:5000")
        log.info("Set MLflow tracking URI.")
        mlflow.set_experiment("nyc-taxi-experiment")
        log.info("Set MLflow experiment.")
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
    params = {"year": "{{ params.year }}", "month": "{{ params.month }}"}
    year = params["year"]
    month = params["month"]

    # Read training and validation data
    df_train = read_dataframe(year=year, month=month)
    next_year = year if month < 12 else year + 1
    next_month = month + 1 if month < 12 else 1
    df_val = read_dataframe(year=next_year, month=next_month)

    # Create feature matrices
    train_x_dict = create_x(df_train)
    x_train = train_x_dict["x"]
    dv = train_x_dict["dv"]
    val_x_dict = create_x(df_val, dv=dv)
    x_val = val_x_dict["x"]

    # Extract target
    target = "duration"
    y_train = df_train[target].to_numpy()
    y_val = df_val[target].to_numpy()

    # Train model
    run_id = train_model(x_train, y_train, x_val, y_val, dv)

# Instantiate the DAG
dag_instance = data_prediction_dag()

if __name__ == "__main__":
    dag_instance.test()