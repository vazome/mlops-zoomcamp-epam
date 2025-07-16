import argparse
import datetime
import io
import logging
import random
import time
import uuid
from pathlib import Path

import pandas as pd
import psycopg
import pytz
import requests
from evidently import ColumnMapping
from evidently.metric_preset import DataDriftPreset, DataQualityPreset
from evidently.metrics import (
    ColumnDriftMetric,
    ColumnMissingValuesMetric,
    ColumnQuantileMetric,
    DatasetDriftMetric,
    DatasetMissingValuesMetric,
)
from evidently.renderers.html_widgets import WidgetSize
from evidently.report import Report
from evidently.ui.dashboards import (
    CounterAgg,
    DashboardPanelCounter,
    DashboardPanelPlot,
    PanelValue,
    PlotType,
    ReportFilter,
)
from evidently.ui.workspace import Workspace
from joblib import dump, load
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


SEND_TIMEOUT = 10
rand = random.Random()

create_table_statement = """
drop table if exists dummy_metrics;
create table dummy_metrics(
    timestamp timestamp,
    value1 integer,
    value2 varchar,
    value3 float
)
"""


def download_data(year, month):
    """Download green taxi data for the specified year and month."""
    file_name = f"green_tripdata_{year:04d}-{month:02d}.parquet"
    save_path = f"./data/{file_name}"

    # Check if file already exists
    if Path(save_path).exists():
        log.info(f"File {save_path} already exists, skipping download")
        return save_path

    # Create data directory if it doesn't exist
    Path("./data").mkdir(exist_ok=True)

    url = f"https://d37ci6vzurychx.cloudfront.net/trip-data/{file_name}"
    log.info(f"Downloading {file_name} from {url}")

    resp = requests.get(url, stream=True)
    resp.raise_for_status()

    with open(save_path, "wb") as handle:
        for data in tqdm(
            resp.iter_content(),
            desc=f"{file_name}",
            postfix=f"save to {save_path}",
            total=int(resp.headers.get("Content-Length", 0)),
        ):
            handle.write(data)

    log.info(f"Downloaded {file_name} to {save_path}")
    return save_path


def load_and_preprocess_data(file_path):
    """Load and preprocess green taxi data."""
    log.info(f"Loading data from {file_path}")
    data = pd.read_parquet(file_path)

    # Create target
    data["duration_min"] = data.lpep_dropoff_datetime - data.lpep_pickup_datetime
    data.duration_min = data.duration_min.apply(
        lambda td: float(td.total_seconds()) / 60,
    )

    # Filter out outliers
    data = data[(data.duration_min >= 0) & (data.duration_min <= 60)]
    data = data[(data.passenger_count > 0) & (data.passenger_count <= 8)]

    log.info(f"Data shape after preprocessing: {data.shape}")
    return data


def train_model(train_data, num_features, cat_features):
    """Train linear regression model."""
    target = "duration_min"
    num_features = ["passenger_count", "trip_distance", "fare_amount", "total_amount"]
    cat_features = ["PULocationID", "DOLocationID"]

    log.info("Training linear regression model")
    model = LinearRegression()
    model.fit(train_data[num_features + cat_features], train_data[target])

    # Save model
    Path("models").mkdir(exist_ok=True)
    with open("models/lin_reg.bin", "wb") as f_out:
        dump(model, f_out)

    log.info("Model trained and saved to models/lin_reg.bin")
    return model


def generate_predictions(model, data):
    """Generate predictions for the data."""
    num_features = ["passenger_count", "trip_distance", "fare_amount", "total_amount"]
    cat_features = ["PULocationID", "DOLocationID"]

    predictions = model.predict(data[num_features + cat_features])
    data["prediction"] = predictions

    log.info(f"Generated predictions for {len(data)} samples")
    return data


def reports_and_metrics(reference_data, current_data):
    ws = Workspace("workspace")

    try:
        project = ws.get_project("NYC Taxi Data Quality Project")
    except (ValueError, Exception):
        # If project doesn't exist or there's an error, create a new one
        project = ws.create_project("NYC Taxi Data Quality Project")
        project.description = "My project description"
        project.save()

    num_features = ["passenger_count", "trip_distance", "fare_amount", "total_amount"]
    cat_features = ["PULocationID", "DOLocationID"]

    column_mapping = ColumnMapping(
        target="fare_amount",
        numerical_features=num_features,
        categorical_features=cat_features,
    )

    report = Report(
        metrics=[
            ColumnQuantileMetric(column_name="fare_amount", quantile=0.5),
            ColumnMissingValuesMetric(column_name="trip_type"),
        ]
    )

    report.run(
        reference_data=reference_data,
        current_data=current_data,
        column_mapping=column_mapping,
    )

    result = report.as_dict()

    quntile_metric = result["metrics"][0]["result"]
    trip_type_metric = result["metrics"][1]["result"]
    
    log.info(f"Quantile value: {quntile_metric}")
    log.info(f"Missing values - trip_type: {trip_type_metric}")
    # prediction_drift = result["metrics"][0]["result"]["drift_score"]
    # num_drifted_columns = result["metrics"][1]["result"]["number_of_drifted_columns"]
    # missing_values_share = result["metrics"][2]["result"]["current"][
    #    "share_of_missing_values"
    # ]

    # log.info(f"Prediction drift score: {prediction_drift:.4f}")
    # log.info(f"Number of drifted columns: {num_drifted_columns}")
    # log.info(f"Share of missing values: {missing_values_share:.4f}")


def prep_db():
    with psycopg.connect(
        "host=localhost port=5432 user=postgres password=example", autocommit=True
    ) as conn:
        res = conn.execute("SELECT 1 FROM pg_database WHERE datname='test'")
        if len(res.fetchall()) == 0:
            conn.execute("create database test;")
        with psycopg.connect(
            "host=localhost port=5432 dbname=test user=postgres password=example"
        ) as conn:
            conn.execute(create_table_statement)


def calculate_dummy_metrics_postgresql(curr):
    value1 = rand.randint(0, 1000)
    value2 = str(uuid.uuid4())
    value3 = rand.random()

    curr.execute(
        "insert into dummy_metrics(timestamp, value1, value2, value3) values (%s, %s, %s, %s)",
        (datetime.datetime.now(pytz.timezone("Europe/London")), value1, value2, value3),
    )


def connect_pg():
    prep_db()
    last_send = datetime.datetime.now() - datetime.timedelta(seconds=10)
    with psycopg.connect(
        "host=localhost port=5432 dbname=test user=postgres password=example",
        autocommit=True,
    ) as conn:
        for i in range(0, 100):
            with conn.cursor() as curr:
                calculate_dummy_metrics_postgresql(curr)

            new_send = datetime.datetime.now()
            seconds_elapsed = (new_send - last_send).total_seconds()
            if seconds_elapsed < SEND_TIMEOUT:
                time.sleep(SEND_TIMEOUT - seconds_elapsed)
            while last_send < new_send:
                last_send = last_send + datetime.timedelta(seconds=10)
            log.info("data sent")


if __name__ == "__main__":
    # CLI Argument Parsing
    parser = argparse.ArgumentParser(
        description="Process green taxi data for monitoring"
    )
    parser.add_argument(
        "--year", type=int, default=2024, help="Year of data to process"
    )
    parser.add_argument("--month", type=int, default=3, help="Month of data to process")
    args = parser.parse_args()

    # Download and load data
    data_path = download_data(args.year, args.month)
    data = load_and_preprocess_data(data_path)

    # Split data for training and validation
    train_data = data[:30000]
    val_data = data[30000:]

    ## Train model and generate predictions
    #model = train_model(train_data)
    #train_data = generate_predictions(model, train_data)
    #val_data = generate_predictions(model, val_data)
#
    ## Evaluate model
    #target = "duration_min"
    #train_mae = mean_absolute_error(train_data[target], train_data["prediction"])
    #val_mae = mean_absolute_error(val_data[target], val_data["prediction"])
#
    #log.info(f"Training MAE: {train_mae:.4f}")
    #log.info(f"Validation MAE: {val_mae:.4f}")
#
    ## Save reference data
    #val_data.to_parquet("data/reference.parquet")
    #log.info("Reference data saved to data/reference.parquet")
#
    ## Run Evidently report

    result = reports_and_metrics(train_data, val_data)

    # Set up column mapping for dashboard
    num_features = ["passenger_count", "trip_distance", "fare_amount", "total_amount"]
    cat_features = ["PULocationID", "DOLocationID"]

    column_mapping = ColumnMapping(
        target=None,
        prediction="prediction",
        numerical_features=num_features,
        categorical_features=cat_features,
    )