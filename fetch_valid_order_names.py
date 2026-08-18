import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleads import errors
import pandas as pd
import shutil
import datetime
import pytz
import csv
import gspread
import tempfile
import os
import gzip
import json
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleads import errors
import logging
logging.basicConfig(level=logging.DEBUG)
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')

def fetch_valid_order_ids(sheet_url,sheet_id):
    creds_json = json.loads(GOOGLE_CREDENTIALS_JSON)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(sheet_url)
    worksheet = spreadsheet.get_worksheet_by_id(sheet_id)
    all_rows = worksheet.get_all_values()
    data_rows = all_rows[1:]
    valid_order_id = []
    for row in data_rows:
        order_name = row[0].strip()
        valid_order_id.append(order_name) 
    return valid_order_id

