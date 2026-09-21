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
from oauth2client.service_account import ServiceAccountCredentials
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------- Config ----------------
spreadsheet_id = "1080823886"          # gid of the target tab/worksheet
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')
sheet_url = 'https://docs.google.com/spreadsheets/d/1u68QXESgLIlfDHzSY_9QVCd9pFIk-sCqiSBB9IERz9g/edit?gid=1080823886#gid=1080823886'
OUTPUT_COLUMN = 'AK'  # column to write "total_predicted_units" into
MAX_WORKERS = 8       # number of orders to process in parallel.
                      # Ad Manager doesn't publish a hard concurrency limit,
                      # but stay conservative (5-10) to avoid rate limiting.
# -----------------------------------------


def get_line_item_delivery_forecast(client, line_item_ids):
    line_item_ids = [int(x) for x in line_item_ids]
    forecast_service = client.GetService('ForecastService', version='v202602')

    total_delivered = 0
    total_predicted = 0

    def accumulate(forecasts):
        nonlocal total_delivered, total_predicted
        for f in forecasts or []:
            total_delivered += int(getattr(f, 'deliveredUnits', 0) or 0)
            total_predicted += int(getattr(f, 'predictedDeliveryUnits', 0) or 0)

    try:
        # Single batched call for ALL line items at once.
        forecast = forecast_service.getDeliveryForecastByIds(
            line_item_ids,
            {'ignoredLineItemIds': []}
        )
        accumulate(forecast.lineItemDeliveryForecasts)

    except Exception as e:
        # Batch failed (often due to one expired/invalid line item) —
        # fall back to per-item calls only in that case.
        print(f"Batch forecast failed ({e}); falling back to per-item calls.")

        for line_item_id in line_item_ids:
            try:
                forecast = forecast_service.getDeliveryForecastByIds(
                    [line_item_id],
                    {'ignoredLineItemIds': []}
                )
                accumulate(forecast.lineItemDeliveryForecasts)

            except Exception as inner_e:
                if 'END_DATE_TIME_IS_IN_PAST' in str(inner_e):
                    print(f"Skipping expired line item: {line_item_id}")
                else:
                    print(f"Failed for {line_item_id}: {inner_e}")

    data = {
        'line_item_ids': line_item_ids,
        'total_delivered_units': total_delivered,
        'total_predicted_units': total_predicted
    }

    print("\nCombined Forecast")
    print("=" * 50)
    print(f"Total Delivered : {total_delivered:,}")
    print(f"Total Predicted : {total_predicted:,}")

    return data


def get_order_id_by_name(client, order_name):
    order_service = client.GetService('OrderService', version='v202602')

    statement = (
        ad_manager.StatementBuilder(version='v202602')
        .Where('name = :name')
        .WithBindVariable('name', order_name)
    )

    response = order_service.getOrdersByStatement(statement.ToStatement())
    orders = getattr(response, 'results', [])

    if not orders:
        print(f"No order found with name: {order_name}")
        return None

    order = orders[0]
    print(f"Found Order '{order.name}' -> ID: {order.id}")
    return order.id


def get_line_items_for_order(client, order_id):
    line_item_service = client.GetService(
        'LineItemService',
        version='v202602'
    )

    line_items = []

    statement = (
        ad_manager.StatementBuilder(version='v202602')
        .Where(
            'orderId = :orderId '
            'AND status IN (:statusDelivering, :statusPaused) '
            'AND lineItemType != :bulk'
        )
        .WithBindVariable('orderId', int(order_id))
        .WithBindVariable('statusDelivering', 'DELIVERING')
        .WithBindVariable('statusPaused', 'PAUSED')
        .WithBindVariable('bulk', 'BULK')
        .OrderBy('id', ascending=True)
    )

    while True:
        response = line_item_service.getLineItemsByStatement(
            statement.ToStatement()
        )

        results = getattr(response, 'results', []) or []
        line_items.extend(results)

        if len(results) < statement.limit:
            break

        statement.offset += statement.limit

    print(f"Found {len(line_items)} line items.")

    return line_items


def get_forecasts_for_order(client, order_name):

    order_id = get_order_id_by_name(client, order_name)

    if order_id is None:
        return None

    line_items = get_line_items_for_order(client, order_id)

    if not line_items:
        print(f"No line items found for order ID {order_id}.")
        return None

    print(
        f"\nFound {len(line_items)} line item(s) "
        f"for order '{order_name}'."
    )
    line_item_ids = [li.id for li in line_items]
    return get_line_item_delivery_forecast(
        client,
        line_item_ids
    )


def get_order_names_from_sheet(sheet_url, spreadsheet_id, GOOGLE_CREDENTIALS_JSON, skip_header=True):
    creds_json = json.loads(GOOGLE_CREDENTIALS_JSON)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    
    gs_client  = gspread.authorize(creds)
    sh = gs_client.open_by_url(sheet_url)

    if spreadsheet_id is not None:
        worksheet = sh.get_worksheet_by_id(int(spreadsheet_id))
    else:
        worksheet = sh.sheet1

    col_a_values = worksheet.col_values(1)  # Column A = index 1

    if skip_header and col_a_values:
        col_a_values = col_a_values[1:]

    order_names = [name.strip() for name in col_a_values if name and name.strip()]

    print(f"Found {len(order_names)} order name(s) in column A.")
    return order_names


def _process_one_order(row_num, order_name, output_column):
    thread_client = ad_manager.AdManagerClient.LoadFromString(f"""
   ad_manager:
    application_name: {os.getenv('APPLICATION_NAME')}
    network_code: {os.getenv('NETWORK_CODE')}
    client_id: {os.getenv('CLIENT_ID')}
    client_secret: {os.getenv('CLIENT_SECRET')}
    refresh_token: {os.getenv('REFRESH_TOKEN')}
  """)

    print(f"\n{'=' * 70}")
    print(f"Row {row_num} | Order: {order_name}")
    print('=' * 70)

    result = get_forecasts_for_order(thread_client, order_name)
    predicted_units = result['total_predicted_units'] if result else 0

    return {
        'range': f'{output_column}{row_num}',
        'values': [[predicted_units]]
    }


def update_predicted_units_in_sheet(client, sheet_url, spreadsheet_id, GOOGLE_CREDENTIALS_JSON,
                                     skip_header=True, output_column=OUTPUT_COLUMN,
                                     max_workers=MAX_WORKERS):
    creds_json = json.loads(GOOGLE_CREDENTIALS_JSON)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    
    gs_client  = gspread.authorize(creds)
    sheet = gs_client.open_by_url(sheet_url)
    worksheet = sheet.get_worksheet_by_id(spreadsheet_id)

    col_a_values = worksheet.col_values(1)  # Column A

    start_row = 2 if skip_header else 1
    rows_to_process = col_a_values[start_row - 1:]

    # Build (row_num, order_name) pairs, skipping blanks up front.
    jobs = [
        (start_row + offset, order_name.strip())
        for offset, order_name in enumerate(rows_to_process)
        if order_name and order_name.strip()
    ]

    updates = []  # batch of {'range': '<col><row>', 'values': [[value]]}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_row = {
            executor.submit(_process_one_order, row_num, order_name, output_column): row_num
            for row_num, order_name in jobs
        }

        for future in as_completed(future_to_row):
            row_num = future_to_row[future]
            try:
                updates.append(future.result())
            except Exception as e:
                print(f"Row {row_num} failed: {e}")
                updates.append({
                    'range': f'{output_column}{row_num}',
                    'values': [[0]]
                })

    if updates:
        worksheet.batch_update(updates)
        print(f"\nUpdated {len(updates)} row(s) in column {output_column}.")
    else:
        print("\nNo rows updated.")

    return updates
