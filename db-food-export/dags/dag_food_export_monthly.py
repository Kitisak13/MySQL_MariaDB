"""
Airflow DAG: Monthly Food Export Ingestion & Incremental Sync
Author: Lead Data Engineer
Schedule: Runs on the 25th of every month at 02:00 UTC (MOC typically releases previous month trade data by 20th-25th)
"""

# discomment when deploy to cloud server

# from datetime import datetime, timedelta
# from airflow import DAG
# from airflow.operators.bash import BashOperator
# from airflow.operators.python import PythonOperator

# default_args = {
#     "owner": "data_engineering",
#     "depends_on_past": False,
#     "email_on_failure": True,
#     "email": ["admin@example.com"],
#     "retries": 3,
#     "retry_delay": timedelta(minutes=5),
# }

# with DAG(
#     dag_id="thailand_food_export_monthly_sync",
#     default_args=default_args,
#     description="Monthly automated ingestion of Thailand Food Export Data into MariaDB",
#     schedule_interval="0 2 25 * *",  # Every 25th of the month at 02:00 AM
#     start_date=datetime(2026, 8, 1),
#     catchup=False,
#     tags=["trade", "food_export", "mariadb", "etl"],
# ) as dag:

#     # Task 1: Run Auto Ingestion of latest released month
#     ingest_monthly_data = BashOperator(
#         task_id="ingest_monthly_data",
#         bash_command="python D:/MySQL/mysql/db-food-export/scripts/ingest_monthly.py --auto --workers 4",
#     )

#     # Task 2: Verify and Log Table Summary
#     verify_database_summary = BashOperator(
#         task_id="verify_database_summary",
#         bash_command="python D:/MySQL/mysql/db-food-export/scripts/verify_ingestion_summary.py",
#     )

#     ingest_monthly_data >> verify_database_summary
