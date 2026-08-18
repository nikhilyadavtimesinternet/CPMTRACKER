import datetime
from datetime import timedelta
import gzip
import shutil
import os
from googleads import ad_manager
from fetch_valid_order_names import fetch_valid_order_ids
import pytz
import csv
import json
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

def download_combined_report_by_name(client, order_names):
    print(f"Downloading report for orders: {order_names}")

    end_datetime = datetime.datetime.today()
    start_datetime = end_datetime - timedelta(days=92)
    print(end_datetime)

    report_downloader = client.GetDataDownloader(version='v202602')

    # Convert names into SQL-safe string list
    formatted_names = ",".join([f"'{name.strip()}'" for name in order_names])

    report_job = {
        'reportQuery': {
            'dimensions': ['ORDER_ID', 'ORDER_NAME'],
            'columns': [
                'AD_SERVER_IMPRESSIONS',
                'AD_SERVER_CLICKS',
                'AD_SERVER_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS',
                'UNIQUE_REACH'
            ],
            'statement': {
                'query': f'WHERE ORDER_NAME IN ({formatted_names})'
            },
            'dateRangeType': 'CUSTOM_DATE',
            'startDate': {
                'year': start_datetime.year,
                'month': start_datetime.month,
                'day': start_datetime.day
            },
            'endDate': {
                'year': end_datetime.year,
                'month': end_datetime.month,
                'day': end_datetime.day
            }
        }
    }

    try:
        report_job_id = report_downloader.WaitForReport(report_job)
    except Exception as e:
        print(f"[ERROR] Report generation failed: {e}")
        return None

    file_name = 'combined_report.csv.gz'
    csv_file = 'combined_report.csv'

    try:
        with open(file_name, 'wb') as f:
            report_downloader.DownloadReportToFile(report_job_id, 'CSV_DUMP', f)

        with gzip.open(file_name, 'rb') as f_in:
            with open(csv_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        print("Report saved:")
        return csv_file

    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        return None
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)
