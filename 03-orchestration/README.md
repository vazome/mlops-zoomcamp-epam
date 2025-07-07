Apache Airflow will be installed via `uv`

# Question 1. Select the Tool
Apache Airflow (local, K8S)
![image](https://github.com/user-attachments/assets/96650421-38e0-4035-b59e-0b4e988542ca)

# Question 2. Version
Version 3.0.2
![image](https://github.com/user-attachments/assets/a9a68ac9-5d49-4047-9e34-b7ab9cf15ba1)

# Question 3. Creating a pipeline
It took some time to create a pipeline, to ensure stability of airflow and mlflow.
[data_prediction_yellow.py](https://github.com/vazome/mlops-zoomcamp-epam/blob/c8e13024e7c2576494f6fdcb98f97d6e3e8608d2/03-orchestration/dags/data_prediction_yellow.py)
![image](https://github.com/user-attachments/assets/2e961d1f-bf11-4c88-92fc-acc080e28fb2)

**How many records did we load?**

We have loaded: **3,403,766** records.
![image](https://github.com/user-attachments/assets/3d641b80-328c-47f8-bec7-dee9ba425adf)

# Question 4. Data preparation
**What's the size of the result?**

The size of the result is: **3,316,216**.

As per screenshot above.

# Question 5. Train a model
**What's the intercept of the model?**

The intercept of the model is: **24.77**
![image](https://github.com/user-attachments/assets/dce5ad8a-4120-4cee-a807-5359a122ebce)

# Question 6. Register the model
