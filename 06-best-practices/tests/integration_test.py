import os
import sys
from datetime import datetime

# Add parent directory to path so we can import batch
import batch
import pandas as pd

S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL', 'http://localhost:4566')

options = {
    'client_kwargs': {
        'endpoint_url': S3_ENDPOINT_URL
    },
    'key': os.getenv('AWS_ACCESS_KEY_ID', 'test'),
    'secret': os.getenv('AWS_SECRET_ACCESS_KEY', 'test'),
}


def dt(day, hour, minute=0):
    return datetime(2023, 1, day, hour, minute)


def create_test_data():
    data = [
        (None, None, dt(1, 1), dt(1, 10)),
        (1, 1, dt(1, 2), dt(1, 10)),
        (1, None, dt(1, 2, 0), dt(1, 2, 59)),
        (3, 4, dt(1, 2, 0), dt(2, 2, 1)),      
    ]

    columns = ["PULocationID", "DOLocationID", "tpep_pickup_datetime", "tpep_dropoff_datetime"]
    df_input = pd.DataFrame(data, columns=columns)
    return df_input

input_file = batch.get_input_path(2023, 1)
output_file = batch.get_output_path(2023, 1)


def test_integration():
    # Step 1: Create and save test data to S3
    df_input = create_test_data()
    
    # Save test data to S3
    df_input.to_parquet(
        input_file,
        engine='pyarrow',
        compression=None,
        index=False,
        storage_options=options
    )
    print(f"Test data saved to {input_file}")
    
    # Step 2: Run the batch script using os.system
    command = f"AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test S3_ENDPOINT_URL={S3_ENDPOINT_URL} INPUT_FILE_PATTERN=\"s3://nyc-duration/in/{{year:04d}}-{{month:02d}}.parquet\" OUTPUT_FILE_PATTERN=\"s3://nyc-duration/out/{{year:04d}}-{{month:02d}}.parquet\" python batch.py --year 2023 --month 1"
    
    result = os.system(command)
    print(f"Batch script executed with return code: {result}")
    
    # Step 3: Read the results from S3
    df_result = pd.read_parquet(output_file, storage_options=options)
    print(f"Results read from {output_file}")
    
    # Step 4: Calculate the sum of predicted durations
    sum_predicted = df_result['predicted_duration'].sum()
    print(f"Sum of predicted durations: {sum_predicted}")
    
    return sum_predicted


if __name__ == "__main__":
    sum_duration = test_integration()
