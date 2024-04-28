# UNIQLO Price and Stock Tracker

This Python script monitors the prices, stock status, and quantities of UNIQLO
products listed in a configuration file. It sends notifications to an ntfy.sh
topic whenever there's a change in price, stock status, or quantity (if low on
stock).

## Features

- Monitor prices of UNIQLO products
- Detect price changes and send notifications with the old and new prices, as well as the price difference
- Monitor stock status (in stock, low stock, out of stock)
- Send notifications when stock status changes
- Monitor quantity changes for low stock products and send notifications
- Configure products to monitor, notification topic, and refresh interval through a YAML configuration file

## Requirements

- Python 3.x
- The following Python packages:
  - requests
  - PyYAML

You can install the required packages using pip:

```bash
pip install requests PyYAML
```

## Setup

1. Clone or download the repository.
2. Create a new file called `config.yml` in the same directory as the script.
3. In `config.yml`, define the following configuration:

```yaml
product_urls:
  <product_url_1>: <product_name_1>
  <product_url_2>: <product_name_2>
  # ... add more product URLs and names as needed
refresh_time: <refresh_time_in_seconds>
ntfy_topic: <your_ntfy_topic>
```

- `product_urls`: A dictionary where the keys are the UNIQLO product URLs, and the values are the corresponding product names.
- `refresh_time`: The interval (in seconds) at which the script should check for changes.
- `ntfy_topic`: The ntfy.sh topic where notifications will be sent.

4. Run the script:

```
python main.py
```

The script will start monitoring the configured products and send notifications
to the specified ntfy.sh topic whenever there's a change in price, stock status,
or quantity (if low on stock).

## Notification Format

The script sends notifications to the specified ntfy.sh topic with the following information:

- **Price change**: Includes the product name, old price, new price, and price difference.
- **Stock status change**: Includes the product name and the new stock status
  (low stock or out of stock). If the status is "low stock," the notification
  also includes the remaining quantity.
- **Quantity change (for low stock products)**: Includes the product name, old
  quantity, and new quantity.

The notifications are formatted with appropriate titles and tags for better visibility and filtering.
Sure, here are the instructions for installing ntfy on your phone and subscribing to the ntfy_topic:

## Installing ntfy on Your Phone

Go to [ntfy.sh](https://ntfy.sh/) and install the ntfy app on your phone. The app is available for both Android and iOS devices.

## Subscribing to the ntfy_topic

1. Open the ntfy app on your phone.
2. Tap on the "Subscribe to Topic" button or the "+" icon (depending on the app version).
3. Enter the `ntfy_topic` value specified in your `config.yml` file.
4. Optionally, you can configure additional settings like notification sound, vibration, etc.
5. Tap "Subscribe" or "Save" to subscribe to the topic.

Now, whenever the script sends a notification to the specified `ntfy_topic`, you will receive it on your phone through the ntfy app.

**Note:** You can also subscribe to the topic using the ntfy web interface or
other ntfy client applications. Visit [ntfy.sh](https://ntfy.sh/) for more
information on subscribing to topics and managing your ntfy account.

With the ntfy app installed and subscribed to the correct topic, you'll receive
real-time notifications from the UNIQLO Price and Stock Tracker script on your
phone.
