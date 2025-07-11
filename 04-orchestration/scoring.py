import argparse
import logging
import pickle
import urllib.request
from ast import arg
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

categorical = ["PULocationID", "DOLocationID"]

def get_model():
    if Path("model.bin").exists():
        with open("model.bin", "rb") as f_in:
            dv, model = pickle.load(f_in)
    else:
        with urllib.request.urlopen(
            "https://github.com/DataTalksClub/mlops-zoomcamp/raw/refs/heads/main/cohorts/2025/04-deployment/homework/model.bin",
            ) as f_in, open("model.bin", "wb") as f_out:
            f_out.write(f_in.read())

        with open("model.bin", "rb") as f_in:
            dv, model = pickle.load(f_in)

    return dv, model


def read_data(filename):
    df = pd.read_parquet(filename)

    df["duration"] = df.tpep_dropoff_datetime - df.tpep_pickup_datetime
    df["duration"] = df.duration.dt.total_seconds() / 60

    df = df[(df.duration >= 1) & (df.duration <= 60)].copy()

    df[categorical] = df[categorical].fillna(-1).astype("int").astype("str")

    return df


def prediction(dv, df, model):
    dicts = df[categorical].to_dict(orient="records")
    X_val = dv.transform(dicts)
    y_pred = model.predict(X_val)
    log.info(f"Mean: {y_pred.mean():.2f}")
    log.info(f"Standard Deviation: {y_pred.std():.2f}")
    return y_pred


def save_results(df, y_pred, year, month):
    df_result = pd.DataFrame()
    df_result["prediction"] = y_pred
    df_result["ride_id"] = f"{year:04d}/{month:02d}_" + df.index.astype("str")

    log.info(f"Sampling top 3:\n{df_result.head(3)}")

    df_result.to_parquet(
        file_name,
        engine="pyarrow",
        compression=None,
        index=False,
    )
    log.info(f"Export DF Size: {Path(file_name).stat().st_size / 1024 / 1024:.02f} MB")

if __name__ == "__main__":
    # CLI Argument Parsing
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--month", type=int, default=3)
    args = parser.parse_args()

    # Download and Save file name construction
    file_name = f"yellow_tripdata_{args.year:04d}-{args.month:02d}.parquet"

    # Execution
    dv, model = get_model()
    df = read_data(f"https://d37ci6vzurychx.cloudfront.net/trip-data/{file_name}")
    y_pred = prediction(dv, df, model)
    save_results(df, y_pred, args.year, args.month)
