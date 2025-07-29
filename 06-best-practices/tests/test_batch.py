from datetime import datetime

import pandas as pd
from batch import prepare_data


def dt(hour, minute, second=0):
    return datetime(2023, 1, 1, hour, minute, second)


def test_prepare_data():
    data = [
        (None, None, dt(1, 1), dt(1, 10)),
        (1, 1, dt(1, 2), dt(1, 10)),
        (1, None, dt(1, 2, 0), dt(1, 2, 59)),
        (3, 4, dt(1, 2, 0), dt(2, 2, 1)),      
    ]

    columns = ["PULocationID", "DOLocationID", "tpep_pickup_datetime", "tpep_dropoff_datetime"]
    df = pd.DataFrame(data, columns=columns)
    categorical = ["PULocationID", "DOLocationID"]
    
    actual_result = prepare_data(df, categorical)
    
    expected_data = [
        ("-1", "-1", 9.0),
        ("1", "1", 8.0),
    ]
    expected_columns = ["PULocationID", "DOLocationID", "duration"]
    expected_result = pd.DataFrame(expected_data, columns=expected_columns)
    
    actual_dicts = actual_result[expected_columns].to_dict("records")
    expected_dicts = expected_result.to_dict("records")
    
    assert len(actual_dicts) == len(expected_dicts)
    
    for actual, expected in zip(actual_dicts, expected_dicts):
        assert actual["PULocationID"] == expected["PULocationID"]
        assert actual["DOLocationID"] == expected["DOLocationID"]
