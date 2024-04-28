# UNIQLO Realtime Price and Inventory Tracker
***via phone notifications, so you'll always get the best price and before it's sold out***

This Python script monitors the prices, stock status, and quantities of UNIQLO products. It sends notifications to an ntfy.sh topic whenever there's a change in price, stock status, or quantity (if low on stock).

## Features

- Monitor prices of UNIQLO products
- Detect price changes and send notifications with the old and new prices, as well as the price difference
- Monitor stock status (in stock, low stock, out of stock)
- Send notifications when stock status changes
- Monitor quantity changes for low stock products and send notifications
- Configure notification topics and refresh interval through a YAML configuration file
- Interactively add or remove products to monitor using a dedicated ntfy.sh topic

## Requirements

- Python 3.x
- The following Python packages:
  - requests
  - PyYAML
  - tabulate

You can install the required packages using pip:

```bash
pip install requests PyYAML tabulate
```

## Setup

1. Clone or download the repository.
2. Create a new file called `config.yml` in the same directory as the script.
3. In `config.yml`, define the following configuration:

```yaml
refresh_time: <refresh_time_in_seconds>
ntfy_topic: <your_ntfy_topic>
ntfy_listen_topic: <your_ntfy_listen_topic>
```

- `refresh_time`: The interval (in seconds) at which the script should check for changes.
- `ntfy_topic`: The ntfy.sh topic where notifications will be sent.
- `ntfy_listen_topic`: The ntfy.sh topic where you can send requests to add or remove products to monitor.

4. Create a `products.json` file in the same directory as the script. This file will store the list of products you want to monitor.
5. Run the script:

```
python main.py
```

**Note:** Due to the highly customized preferences for clothing items that
each person would want to subscribe to, you will need to run this script on a
personal machine or cloud hosting server and select a private topic of your own
choice. All sensitive data will be maintained on that machine locally.

The script will start monitoring the products listed in `products.json` and send notifications to the specified `ntfy_topic` whenever there's a change in price, stock status, or quantity (if low on stock).

## Adding or Removing Products

You can interactively add or remove products to monitor by sending POST requests to the `ntfy_listen_topic` specified in your `config.yml` file.

### Using curl

To add a product:

```
curl -X POST '{{server}}/{{listen_topic}}' -H 'Content-Type:text/plain' -H 'Priority:min' -d '{{url}} name:{{name}}'
```

Replace `{{server}}` with your ntfy.sh server URL, `{{listen_topic}}` with your `ntfy_listen_topic`, `{{url}}` with the UNIQLO product URL, and `{{name}}` with the product name.

To remove a product:

```
curl -X POST '{{server}}/{{listen_topic}}' -H 'Content-Type:text/plain' -H 'Priority:min' -d 'remove: {{url}}'
```

Replace `{{server}}` with your ntfy.sh server URL, `{{listen_topic}}` with your `ntfy_listen_topic`, and `{{url}}` with the UNIQLO product URL you want to remove.

### Using API Tester (Android)

You can use the [API Tester](https://play.google.com/store/apps/details?id=apitester.org) app on
Android to send requests to the `ntfy_listen_topic`. This app works well with
the curl commands mentioned above. Be sure to set the content type to
`text/plain` and the priority to `min` when sending the requests. Use the
variables feature for easy substitution of values i.e., `{{server}}`,
`{{listen_topic}}`, `{{url}}`, and `{{name}}`.

### Using Web UI

Alternatively, you can use the web UI provided by ntfy.sh to publish messages to
the `ntfy_listen_topic`. Visit `ntfy.sh/{{listen_topic}}` or
`{{your_server}}/{{listen_topic}}` and send the following messages:

To remove a product:

```
remove: <uniqlo_url>
```

To add a product:

```
<uniqlo_url> name:<name_of_item_to_add>
```

Replace `<uniqlo_url>` with the UNIQLO product URL and `<name_of_item_to_add>` with the name of the product you want to add.

## Notification Format

The script sends notifications to the specified `ntfy_topic` with the following information:

- **Price change**: Includes the product name, old price, new price, and price difference.
- **Stock status change**: Includes the product name and the new stock status (low stock or out of stock). If the status is "low stock," the notification also includes the remaining quantity.
- **Quantity change (for low stock products)**: Includes the product name, old quantity, and new quantity.

The notifications are formatted with appropriate titles and tags for better visibility and filtering.

## Installing ntfy on Your Phone

Go to [ntfy.sh](https://ntfy.sh/) and install the ntfy app on your phone. The app is available for both Android and iOS devices.

## Subscribing to the ntfy_topic

1. Open the ntfy app on your phone.
2. Tap on the "Subscribe to Topic" button or the "+" icon (depending on the app version).
3. Enter the `ntfy_topic` value specified in your `config.yml` file.
4. Optionally, you can configure additional settings like notification sound, vibration, etc.
5. Tap "Subscribe" or "Save" to subscribe to the topic.

Now, whenever the script sends a notification to the specified `ntfy_topic`, you will receive it on your phone through the ntfy app.

**Note:** You can also subscribe to the topic using the ntfy web interface or other ntfy client applications. Visit [ntfy.sh](https://ntfy.sh/) for more information on subscribing to topics and managing your ntfy account.

With the ntfy app installed and subscribed to the correct topic, you'll receive real-time notifications from the UNIQLO Price and Stock Tracker script on your phone.
