import smtplib
import requests
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleads import ad_manager
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
from googleads import errors
import logging
from oauth2client.service_account import ServiceAccountCredentials
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
from Impression_Clicks_of_order import fetch_imp_clicks_and_goal
OUTPUT_COLUMN = 'AK'  # column to write "total_predicted_units" into
MAX_WORKERS = 8  
def update_sheet_from_report(client,sheet_url, sheet_id, report_file):
    creds_json = json.loads(GOOGLE_CREDENTIALS_JSON)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    
    gs_client  = gspread.authorize(creds)
    sheet = gs_client.open_by_url(sheet_url)
    worksheet = sheet.get_worksheet_by_id(sheet_id)

    sheet_data = worksheet.get_all_values()

    # Map Column A → row index
    sheet_map = {}
    for i in range(1, len(sheet_data)):
        key = sheet_data[i][0].strip()
        sheet_map[key] = i

    df = pd.read_csv(report_file)

    # Prepare only I & J columns
    updates = []

    for _, row in df.iterrows():
        order_name = str(row['Dimension.ORDER_NAME']).strip()
        impressions,clicks,Gam_goal=fetch_imp_clicks_and_goal(client, order_name)
        viewable_imps=row.get('Column.AD_SERVER_ACTIVE_VIEW_VIEWABLE_IMPRESSIONS',0)
        reach=row.get('Column.UNIQUE_REACH',0)

        if order_name in sheet_map:
            idx = sheet_map[order_name] + 1  # sheet row number
            updates.append({
            'range': f'S{idx}:T{idx}',
            'values': [[impressions, clicks]]
        })

            updates.append({
            'range': f'AD{idx}',
            'values': [[viewable_imps]]
        })
            updates.append({
            'range': f'V{idx}',
            'values': [[reach]]
        })
            updates.append({
            'range': f'AI{idx}',
            'values': [[Gam_goal]]
    })


    #  Batch update only required cells
    if updates:
        worksheet.batch_update(updates)

    print(" Bulk update completed")
