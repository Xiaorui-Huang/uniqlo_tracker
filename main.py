import argparse
import logging
import json
import os
import threading
import requests
import time
import yaml
import re
from urllib.parse import quote, urlparse, parse_qs
from tabulate import tabulate


# https://docs.ntfy.sh/publish


def setup_logger():
    logger = logging.getLogger("uniqlo_monitor")
    logger.setLevel(logging.INFO)

    # Create a file handler
    file_handler = logging.FileHandler("uniqlo_monitor.log")
    file_handler.setLevel(logging.INFO)

    # Create a console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Create a formatter and add it to the handlers
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def parse_product_url(url):
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)

    color_code = params.get("colorCode", [None])[0]
    size_code = params.get("sizeCode", [None])[0]
    return color_code, size_code


def get_api_url(url):
    region = "ca"
    language = "en"
    reg = re.compile(f"({region})\\/({language})([A-Za-z0-9\\-\\/]+)?")
    matches = reg.search(url)
    if not matches:
        return None
    base_api_url = "https://www.uniqlo.com/ca/api/commerce/v3/en/"
    uri = matches.group(3) or "/"
    product_reg = re.compile(r"products\/([\dA-Z\-]+)")
    product_matches = product_reg.search(uri)
    if product_matches:
        # PDP
        id = product_matches.group(1)
        api_url = base_api_url + "products/" + id
    else:
        # CMS
        api_url = base_api_url + "cms?path=" + quote(uri)
    return api_url


# https://www.uniqlo.com/ca/api/commerce/v3/en/products/E463985-000
def get_info_from_api(
    api_url, color_code, size_code
) -> tuple[float, str, int, bool, str, str]:
    """
    returns a tuple with the following values:
        price: float
        statusLocalized: str
        quantity: int
        is_promo: bool
        color_name: str
        size_name: str
        image_url: str | None
    """
    response = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code != 200:
        logger.error(
            f"Failed to get product data for {api_url} from API. Status code: {response.status_code}"
        )
        return None

    product_dict = response.json()["result"]["items"][0]
    images = product_dict["images"]["main"]
    display_color = re.sub("[^0-9]", "", color_code)
    color_size_list = product_dict["l2s"]
    for variant in color_size_list:
        if (variant["color"]["code"] == color_code or color_code is None) and (
            variant["size"]["code"] == size_code or size_code is None
        ):
            prices = variant["prices"]
            # prices are either base or promo
            price = (
                float(prices["promo"]["value"])
                if prices["promo"]
                else float(prices["base"]["value"])
            )

            # variant["stock"]["transitStatus"] might be insteresting
            # actual name is at response.json()["result"]["items"][0]["name"]
            return {
                "price": price,
                "statusCode": variant["stock"]["statusCode"],
                "statusLocalized": variant["stock"]["statusLocalized"],
                "quantity": variant["stock"]["quantity"],
                "is_promo": bool(prices["promo"]),
                "color_name": variant["color"]["name"]
                if color_code is not None
                else "",
                "size_name": variant["size"]["name"] if size_code is not None else "",
                "image_url": next(
                    filter(
                        lambda image_dict: image_dict["colorCode"] == display_color,
                        images,
                    ),
                    {"url": ""},
                )["url"],
            }


def get_info(url):
    api_url = get_api_url(url)
    color_code, size_code = parse_product_url(url)
    return get_info_from_api(api_url, color_code, size_code)


def send_ntfy_notification(
    title, message, topic, product_info=None, priority=3, tags=None, show_image=False
):
    headers = {}

    headers["Title"] = title
    if product_info:
        headers["Click"] = product_info["url"]
    headers["Priority"] = str(priority)

    if tags:
        headers["Tags"] = tags

    if show_image and product_info["image_url"]:
        headers["Attach"] = product_info["image_url"]

    r = requests.post(f"{args.server}/{topic}", data=message, headers=headers)
    if r.status_code != 200:
        logger.error(f"Failed to send notification: {r.text}")


def main():
    product_history = {}
    for url, product_name in product_urls.items():
        info = get_info(url)

        if not info:
            # try again once
            info = get_info(url)
            if not info:
                logger.error(f"Unable to retrieve price for {url}")
            continue

        info["product_name"] = product_name
        info["url"] = url

        if info:
            product_history[url] = info
        else:
            logger.error(f"Unable to retrieve price for {url}")

    if not args.carry_on:
        for product in product_history.values():
            title = f"{product['product_name']} Added"
            priority = 3
            tags = None
            msg = f"Price: {product['price']}, Quantity: {product['quantity']}, {product['color_name']}, {product['size_name']}"
            if product["is_promo"]:
                msg += " (on promo)"

            if product["statusCode"] == "LOW_STOCK":
                title = f"{product['product_name']} is LOW on stock"
                priority = 4
                tags = "warning"
                if product["quantity"] <= 3:
                    title = f"{product['product_name']} is ALMOST OUT of stock"
                    priority = 5
                    tags = "rotating_light"

            if product["statusCode"] == "STOCK_OUT":
                title = f"{product['product_name']} is OUT OF STOCK"
                priority = 4
                tags = "skull"

            send_ntfy_notification(
                title,
                msg,
                topic,
                product,
                priority=priority,
                tags=tags,
                show_image=True,
            )

    while True:
        # add in any new products to the product_history
        with new_products_lock:
            for url, product_name in new_products_working_queue.items():
                info = get_info(url)
                if not info:
                    continue
                info["product_name"] = product_name
                info["url"] = url
                product_history[url] = info

            # clear the working queue after adding to product_history
            new_products_working_queue.clear()

        # check for updates
        for url, old_info in product_history.items():
            new_info = get_info(url)

            if not new_info:
                # try again once
                new_info = get_info(url)
                if not new_info:
                    logger.error(f"Unable to retrieve updated info for {url}")
                    continue

            new_info["product_name"] = old_info["product_name"]
            new_info["url"] = url

            # check price
            if new_info["price"] != old_info["price"]:
                price_diff = new_info["price"] - old_info["price"]
                msg = f"""The price for {new_info['product_name']} has changed
    Old price: {old_info['price']}
    New price: {new_info['price']}
    Price difference: {price_diff}"""
                promo_str = " (ON PROMO)" if new_info["is_promo"] else ""
                send_ntfy_notification(
                    f"Price change for {new_info['product_name']}{promo_str}",
                    msg,
                    topic,
                    new_info,
                    priority=4,
                    tags="tada",
                )

            # check stock status
            if new_info["statusCode"] != old_info["statusCode"]:
                if new_info["statusCode"] == "LOW_STOCK":
                    send_ntfy_notification(
                        f"{new_info['product_name']} is LOW on stock",
                        f"Price: {new_info['price']}, Quantity: {new_info['quantity']}, {new_info['color_name']}, {new_info['size_name']}",
                        topic,
                        new_info,
                        priority=4,
                        tags="warning"
                        if old_info["statusCode"] == "IN_STOCK"
                        else "up,tada",
                        show_image=True,
                    )
                elif new_info["statusCode"] == "STOCK_OUT":
                    send_ntfy_notification(
                        f"{new_info['product_name']} is OUT OF STOCK",
                        " ",
                        topic,
                        new_info,
                        priority=4,
                        tags="skull",
                    )

            # check quantity if low stock
            if new_info["statusCode"] == "LOW_STOCK":
                if old_info["quantity"] > new_info["quantity"]:
                    title = f"{new_info['product_name']} - Quantity change"
                    msg = f"Qunaity is down from {old_info['quantity']} to {new_info['quantity']} at Price: {new_info['price']}"
                    priority = 3
                    tags = "small_red_triangle_down	"
                    if new_info["quantity"] <= 3:
                        title = f"{new_info['product_name']} - ALMOST OUT OF STOCK"
                        priority = 5
                        tags = "rotating_light"
                    send_ntfy_notification(
                        title, msg, topic, new_info, priority=priority, tags=tags
                    )
                elif old_info["quantity"] < new_info["quantity"]:
                    send_ntfy_notification(
                        f"{new_info['product_name']} - Quantity change",
                        f"Qunaity is up from {old_info['quantity']} to {new_info['quantity']} at Price: {new_info['price']}",
                        topic,
                        new_info,
                        tags="up",
                    )

            new_info["quantity_change"] = (
                f"{old_info['quantity']} -> {new_info['quantity']}"
                if old_info["quantity"] != new_info["quantity"]
                else None
            )
            product_history[url] = new_info

        product_data = [
            [
                info["product_name"],
                (info["quantity"], info["quantity_change"]),
                info["color_name"],
                info["size_name"],
                info["url"],
            ]
            for info in product_history.values()
        ]
        product_data.sort(key=lambda x: x[1][0])
        for i, (_, (quantity, change), *_) in enumerate(product_data):
            product_data[i][1] = change if change is not None else str(quantity)

        logger.info(
            "\n"
            + tabulate(
                product_data,
                headers=["Product Name", "Quantity", "Color", "Size", "URL"],
                tablefmt="outline",
            )
        )

        time.sleep(refresh_time)


def listen_to_ntfy(server, topic):
    global new_products, new_products_working_queue
    while True:
        try:
            response = requests.get(f"{server}/{topic}/raw", stream=True)
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if "www.uniqlo.com" in line_str and "name:" in line_str:
                        # Split the line into URL and product name

                        url, product_name = line_str.split("name:", 1)
                        url = url.strip()
                        # add https:// if it's not there
                        url = "https://www.uniqlo.com" + url.split("www.uniqlo.com")[1]
                        product_name = product_name.strip()

                        with new_products_lock:
                            new_products_working_queue[url] = product_name

                        new_products[url] = product_name
                        json.dump(
                            new_products, open("new_products.json", "w"), indent=4
                        )

        except requests.exceptions.RequestException as e:
            logger.error(f"Server error: {e}")
            logger.info("Retrying in 5 seconds")
            time.sleep(5)
            continue
        break


if __name__ == "__main__":
    logger = setup_logger()
    parser = argparse.ArgumentParser(description="Monitor Uniqlo products")
    parser.add_argument(
        "-c",
        "--carry_on",
        action="store_true",
        default=False,
        help="Continue monitoring",
    )
    parser.add_argument(
        "-s", "--server", type=str, default="https://ntfy.sh", help="Ntfy server URL"
    )
    args = parser.parse_args()

    with open("config.yml", "r") as f:
        config = yaml.safe_load(f)

    product_urls = config["product_urls"]
    if os.path.exists("new_products.json"):
        product_urls.update(json.load(open("new_products.json", "r")))
    refresh_time = config["refresh_time"]
    topic = config["ntfy_topic"]

    new_products = dict()
    new_products_working_queue = dict()
    new_products_lock = threading.Lock()

    listen_thread = threading.Thread(target=listen_to_ntfy, args=(args.server, topic))
    listen_thread.daemon = True
    listen_thread.start()

    main()

    listen_thread.join()
