#!/usr/bin/env python
# coding: utf-8

import pickle
from datetime import datetime
from pathlib import Path

import mlflow
import pandas as pd
import xgboost as xgb
from airflow.decorators import dag, task
from airflow.models.param import Param
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import root_mean_squared_error

mlflow.set_tracking_uri("http://mlflow:5000")
mlflow.set_experiment("nyc-taxi-experiment")

models_folder = Path("models")
models_folder.mkdir(exist_ok=True)

default_args = {"owner": "airflow", "start_date": datetime(2023, 1, 1), "retries": 1}


@dag(
    dag_id="data_prediction",
    default_args=default_args,
    schedule=None,  # Manual trigger only
    catchup=False,
    start_date=datetime(2023, 1, 1),
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
    render_template_as_native_obj=True,  # Ensures params are passed as native types, not strings
)
def data_prediction_dag():
    @task
    def read_dataframe(year: int, month: int):
        url = f"https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_{year}-{month:02d}.parquet"
        df = pd.read_parquet(url)

        df["duration"] = df.lpep_dropoff_datetime - df.lpep_pickup_datetime
        df.duration = df.duration.apply(lambda td: td.total_seconds() / 60)

        df = df[(df.duration >= 1) & (df.duration <= 60)]

        categorical = ["PULocationID", "DOLocationID"]
        df[categorical] = df[categorical].astype(str)

        df["PU_DO"] = df["PULocationID"] + "_" + df["DOLocationID"]

        return df

    @task
    def create_X(df, dv=None):
        categorical = ["PU_DO"]
        numerical = ["trip_distance"]
        dicts = df[categorical + numerical].to_dict(orient="records")

        if dv is None:
            dv = DictVectorizer(sparse=True)
            X = dv.fit_transform(dicts)
        else:
            X = dv.transform(dicts)

        return X, dv

    @task
    def train_model(X_train, y_train, X_val, y_val, dv):
        with mlflow.start_run() as run:
            train = xgb.DMatrix(X_train, label=y_train)
            valid = xgb.DMatrix(X_val, label=y_val)

            best_params = {
                "learning_rate": 0.09585355369315604,
                "max_depth": 30,
                "min_child_weight": 1.060597050922164,
                "objective": "reg:linear",
                "reg_alpha": 0.018060244040060163,
                "reg_lambda": 0.011658731377413597,
                "seed": 42,
            }

            mlflow.log_params(best_params)

            booster = xgb.train(
                params=best_params,
                dtrain=train,
                num_boost_round=30,
                evals=[(valid, "validation")],
                early_stopping_rounds=50,
            )

            y_pred = booster.predict(valid)
            rmse = root_mean_squared_error(y_val, y_pred)
            mlflow.log_metric("rmse", rmse)

            with open("models/preprocessor.b", "wb") as f_out:
                pickle.dump(dv, f_out)
            mlflow.log_artifact("models/preprocessor.b", artifact_path="preprocessor")

            mlflow.xgboost.log_model(booster, artifact_path="models_mlflow")

            return run.info.run_id

    @task
    def run_training(**context):
        params = context["params"]
        year = params["year"]
        month = params["month"]

        print(f"Training model with data from {year}-{month:02d}")

        df_train = read_dataframe(year=year, month=month)

        next_year = year if month < 12 else year + 1
        next_month = month + 1 if month < 12 else 1
        df_val = read_dataframe(year=next_year, month=next_month)

        X_train, dv = create_X(df_train)
        X_val, _ = create_X(df_val, dv)

        target = "duration"
        y_train = df_train[target].values
        y_val = df_val[target].values

        run_id = train_model(X_train, y_train, X_val, y_val, dv)
        print(f"MLflow run_id: {run_id}")
        # Log the file as MLflow artifact
        with open("run_id.txt", "w") as f:
            f.write(run_id)
        with mlflow.start_run(run_id=run_id):
            mlflow.log_artifact("run_id.txt", artifact_path="outputs")

        return run_id

    # Define the task flow within the DAG
    training_task = run_training()

    return training_task


# Allow us to execute via Airflow Scheduler
dag_instance = data_prediction_dag()

# Allow us to execute via bash
if __name__ == "__main__":
    dag_instance.test()