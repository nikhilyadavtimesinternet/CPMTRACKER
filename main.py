from fetch_valid_order_names import fetch_valid_order_ids
from googleads import ad_manager
from update_sheet_from_report import update_sheet_from_report
import gspread
import tempfile
import os
import gzip
import pandas as pd
import shutil
import datetime
import pytz
import csv
import json
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from oauth2client.service_account import ServiceAccountCredentials
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
print("NETWORK_CODE :", os.getenv('NETWORK_CODE'))
print("APPLICATION_NAME:", os.getenv('APPLICATION_NAME'))
print("CLIENT_ID:", os.getenv('CLIENT_ID'))
print("CLIENT_SECRET:", os.getenv('CLIENT_SECRET'))
print("REFRESH_TOKEN:", os.getenv('REFRESH_TOKEN'))
from impressions_clicks_of_order import download_combined_report_by_name
from Update_predicted_adunits_sheet import update_predicted_units_in_sheet
OUTPUT_COLUMN = 'AK' 

sheet_url = "https://docs.google.com/spreadsheets/d/1u68QXESgLIlfDHzSY_9QVCd9pFIk-sCqiSBB9IERz9g/edit?gid=1080823886#gid=1080823886"
sheet_id=1080823886
client = ad_manager.AdManagerClient.LoadFromString(f"""
   ad_manager:
    application_name: {os.getenv('APPLICATION_NAME')}
    network_code: {os.getenv('NETWORK_CODE')}
    client_id: {os.getenv('CLIENT_ID')}
    client_secret: {os.getenv('CLIENT_SECRET')}
    refresh_token: {os.getenv('REFRESH_TOKEN')}
  """)

if __name__ == '__main__':
    order_names = fetch_valid_order_ids(sheet_url, sheet_id)
    report_file = download_combined_report_by_name(client, order_names) 
    print(report_file)

    if report_file:
        update_sheet_from_report(client, sheet_url, sheet_id, report_file)
        update_predicted_units_in_sheet(
        client,
        sheet_url,
        sheet_id,
        GOOGLE_CREDENTIALS_JSON,
        skip_header=True,
        output_column=OUTPUT_COLUMN
    )
         
            
    
    
