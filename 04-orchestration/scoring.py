import argparse
import logging
import pickle
from pathlib import Path

import pandas as pd
from sklearn.metrics import mean_squared_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

categorical = ["PULocationID", "DOLocationID"]


def get_model():
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
    log(f"Standard Deviation: {y_pred.std():.2f}")
    return y_pred


def save_results(df, y_pred, year, month):
    output_file = f"yellow_tripdata_{year:04d}-{month:02d}.parquet"
    df_result = pd.DataFrame()
    df_result["prediction"] = y_pred
    df_result["ride_id"] = f"{year:04d}/{month:02d}_" + df.index.astype("str")

    log(f"Sampling top 3:\n{df_result.head(3)}")

    df_result.to_parquet(
        output_file,
        engine="pyarrow",
        compression=None,
        index=False,
    )
    log(f"Export DF Size: {Path(output_file).stat().st_size / 1024 / 1024:.02f} MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--month", type=int, default=3)
    args = parser.parse_args()
