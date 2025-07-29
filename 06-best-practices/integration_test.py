import os
import sys
from datetime import datetime

import batch
import pandas as pd

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:4566")

options = {
    "client_kwargs": {"endpoint_url": S3_ENDPOINT_URL},
    "key": os.getenv("AWS_ACCESS_KEY_ID", "test"),
    "secret": os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
}


def dt(hour, minute, second=0):
    return datetime(2023, 1, 1, hour, minute, second)


def create_test_data():
    data = [
        (None, None, dt(1, 1), dt(1, 10)),
        (1, 1, dt(1, 2), dt(1, 10)),
        (1, None, dt(1, 2, 0), dt(1, 2, 59)),
        (3, 4, dt(1, 2, 0), dt(2, 2, 1)),
    ]

    columns = [
        "PULocationID",
        "DOLocationID",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
    ]
    df_input = pd.DataFrame(data, columns=columns)
    return df_input


input_file = batch.get_input_path(2023, 1)
output_file = batch.get_output_path(2023, 1)


def test_integration():
    df_input = create_test_data()

    df_input.to_parquet(
        input_file,
        engine="pyarrow",
        compression=None,
        index=False,
        storage_options=options,
    )
    print(f"Test data saved to {input_file}")

    command = (
        f"AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test "
        f"S3_ENDPOINT_URL={S3_ENDPOINT_URL} "
        f'INPUT_FILE_PATTERN="s3://nyc-duration/in/{{year:04d}}-{{month:02d}}.parquet" '
        f'OUTPUT_FILE_PATTERN="s3://nyc-duration/out/{{year:04d}}-{{month:02d}}.parquet" '
        f"python batch.py --year 2023 --month 1"
    )

    os.system(command)

    df_result = pd.read_parquet(output_file, storage_options=options)
    print(f"Results read from {output_file}")

    sum_predicted = df_result["predicted_duration"].sum()
    print(f"Sum of predicted durations: {sum_predicted}")

    return sum_predicted


if __name__ == "__main__":
    sum_duration = test_integration()
