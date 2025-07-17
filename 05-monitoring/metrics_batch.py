import argparse
import datetime
import io
import json
import logging
import os
import random
import time
import uuid
from calendar import month
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

pg_password = os.environ.get("POSTGRES_PASSWORD")

create_metrics_table_statement = """
create table if not exists taxi_metrics(
    timestamp timestamp,
    dataset_type varchar(20),
    metric_name varchar(50),
    metric_value float,
    additional_info jsonb
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


def load_and_preprocess_data(file_path, year, month):
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

    # Convert to datetime and sort
    data["lpep_pickup_datetime"] = pd.to_datetime(data["lpep_pickup_datetime"])

    data = data[
        (data["lpep_pickup_datetime"].dt.year == year) & 
        (data["lpep_pickup_datetime"].dt.month == month)
    ]

    data = data.sort_values("lpep_pickup_datetime")

    log.info(f"Data shape after preprocessing: {data.shape}")
    log.info(f"Date range: {data['lpep_pickup_datetime'].min().date()} to {data['lpep_pickup_datetime'].max().date()}")
    return data


def process_daily_metrics(data):
    """Process metrics for each day in the dataset."""
    # range of dates from first to last
    date_range = pd.date_range(
        data["lpep_pickup_datetime"].min().date(),
        data["lpep_pickup_datetime"].max().date()
    )

    day_one = date_range[0]
    reference_data = data[data["lpep_pickup_datetime"].dt.date == day_one.date()]

    all_metrics_data = []

    log.info(f"Processing metrics for {len(date_range)} days")

    for day in date_range:
        current_day_data = data[data["lpep_pickup_datetime"].dt.date == day.date()]

        if not current_day_data.empty and len(current_day_data) > 10:
            try:
                daily_metrics = reports_and_metrics(reference_data, current_day_data)

                for metric_name, metric_value, additional_info in daily_metrics:
                    additional_info = json.loads(additional_info)
                    additional_info["processing_date"] = day.date().isoformat()

                    all_metrics_data.append((
                        metric_name,
                        metric_value,
                        json.dumps(additional_info),
                        day.date()
                    ))

                log.info(f"Processed metrics for {day.date()}")

            except Exception as e:
                log.error(f"Failed to process metrics for {day.date()}: {e}")
        else:
            log.warning(f"Insufficient data for {day.date()} ({len(current_day_data)} rows)")

    return all_metrics_data


def reports_and_metrics(reference_data, current_data):
    #ws = Workspace("workspace")
    #try:
    #    project = ws.get_project("NYC Taxi Data Quality Project")
    #except (ValueError, Exception):
    #    project = ws.create_project("NYC Taxi Data Quality Project")
    #    project.description = "My project description"
    #    project.save()

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
    quantile_metric = result["metrics"][0]["result"]
    missing_metric = result["metrics"][1]["result"]

    log.info(f"Quantile value: {quantile_metric}")
    log.info(f"Missing values - trip_type: {missing_metric}")

    metrics_data = [
        ("fare_amount_quantile", quantile_metric["current"]["value"], json.dumps(quantile_metric)),
        ("trip_type_missing", missing_metric["current"]["number_of_missing_values"], json.dumps(missing_metric)),
    ]
    return metrics_data


def prep_db_and_save_metrics(metrics_data):
    """Prepare database and save metrics to PostgreSQL."""
    with psycopg.connect(
        f"host=localhost port=5432 user=postgres password={pg_password}", autocommit=True
    ) as conn:
        res = conn.execute("SELECT 1 FROM pg_database WHERE datname='test'")
        if len(res.fetchall()) == 0:
            conn.execute("create database test;")

    with psycopg.connect(
        f"host=localhost port=5432 dbname=test user=postgres password={pg_password}", autocommit=True
    ) as conn:
        conn.execute(create_metrics_table_statement)

        with conn.cursor() as curr:
            save_metrics_to_postgresql(curr, metrics_data)


def save_metrics_to_postgresql(curr, metrics_data):
    """Save Evidently metrics to PostgreSQL with date support."""
    for metric_name, metric_value, additional_info, processing_date in metrics_data:
        # so we use time from the data, not actual time
        timestamp = datetime.datetime.combine(processing_date, datetime.time())
        timestamp = pytz.timezone("Asia/Tbilisi").localize(timestamp)

        curr.execute(
            "insert into taxi_metrics(timestamp, dataset_type, metric_name, metric_value, additional_info) values (%s, %s, %s, %s, %s)",
            (timestamp, "validation", metric_name, metric_value, additional_info),
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process green taxi data for monitoring"
    )
    parser.add_argument(
        "--year", type=int, default=2024, help="Year of data to process"
    )
    parser.add_argument("--month", type=int, default=3, help="Month of data to process")
    args = parser.parse_args()

    data_path = download_data(args.year, args.month)
    data = load_and_preprocess_data(data_path, args.year, args.month)

    metrics_data = process_daily_metrics(data)

    prep_db_and_save_metrics(metrics_data)

    log.info(f"Completed processing {len(metrics_data)} metrics entries")