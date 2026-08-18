from googleads import ad_manager

def fetch_imp_clicks_and_goal(client, order_name):
    order_service = client.GetService('OrderService', version='v202602')
    line_item_service = client.GetService('LineItemService', version='v202602')

    # Get Order
    statement = (ad_manager.StatementBuilder()
                 .Where('name = :orderName')
                 .WithBindVariable('orderName', order_name)
                 .Limit(1))

    response = order_service.getOrdersByStatement(statement.ToStatement())

    if 'results' not in response:
        return None, None, None

    order = response['results'][0]
    order_id = order['id']

    impressions = order['totalImpressionsDelivered']
    clicks = order['totalClicksDelivered']

    # Fetch all line items under this order
    statement = (ad_manager.StatementBuilder()
                 .Where('orderId = :orderId')
                 .WithBindVariable('orderId', order_id))

    total_goal = 0

    while True:
        page = line_item_service.getLineItemsByStatement(statement.ToStatement())

        if 'results' in page:
            for line_item in page['results']:
                primary_goal = line_item['primaryGoal']
                if primary_goal:
                    total_goal += primary_goal['units']
                if 'secondaryGoals' in line_item and line_item['secondaryGoals']:
                    for secondary_goal in line_item['secondaryGoals']:
                        total_goal += secondary_goal['units']
        statement.offset += statement.limit

        if statement.offset >= page['totalResultSetSize']:
            break

    return impressions, clicks, total_goal
