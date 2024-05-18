import argparse
import logging
import json
from logging.handlers import RotatingFileHandler
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

    # Create a rotating file handler
    file_handler = RotatingFileHandler(
        "uniqlo_monitor.log", maxBytes=1024 * 1024, backupCount=10
    )
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
    color_display_code = params.get("colorDisplayCode", [None])[0]
    size_display_code = params.get("sizeDisplayCode", [None])[0]
    if color_display_code is None:
        color_display_code = re.sub("[^0-9]", "", color_code) if color_code else None

    if size_display_code is None:
        size_display_code = re.sub("[^0-9]", "", size_code) if size_code else None

    return color_display_code, size_display_code


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


def get_response(api_url, max_retries=3, retry_delay=5):
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get(
                api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10
            )
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            retries += 1
            if retries == max_retries:
                raise e
            else:
                time.sleep(retry_delay)
                print(
                    f"Retrying in {retry_delay} seconds... (Attempt {retries}/{max_retries})"
                )


# https://www.uniqlo.com/ca/api/commerce/v3/en/products/E463985-000
def get_info_from_api(
    api_url, color_display_code, size_display_code
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
    try:
        response = get_response(api_url)
    except requests.RequestException as e:
        logger.error(f"Failed to get response from API: {e}")
        return None

    product_dict = response.json()["result"]["items"][0]
    color_code_prefix = (
        re.sub("[^A-Za-z]", "", product_dict["colors"][0]["code"])
        if color_display_code
        else None
    )
    size_code_prefix = (
        re.sub("[^A-Za-z]", "", product_dict["sizes"][0]["code"])
        if size_display_code
        else None
    )

    images = product_dict["images"]["main"]
    color_size_list = product_dict["l2s"]
    for variant in color_size_list:
        if (
            variant["color"]["displayCode"] == color_display_code
            or color_display_code is None
        ) and (
            variant["size"]["displayCode"] == size_display_code
            or size_display_code is None
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
            return (
                {
                    "price": price,
                    "statusCode": variant["stock"]["statusCode"],
                    "statusLocalized": variant["stock"]["statusLocalized"],
                    "quantity": variant["stock"]["quantity"],
                    "is_promo": bool(prices["promo"]),
                    "color_name": variant["color"]["name"]
                    if color_display_code is not None
                    else "",
                    "size_name": variant["size"]["name"]
                    if size_display_code is not None
                    else "",
                    "image_url": next(
                        filter(
                            lambda image_dict: image_dict["colorCode"]
                            == color_display_code,
                            images,
                        ),
                        {"url": ""},
                    )["url"],
                    "name": product_dict["name"],
                },
                color_code_prefix,
                size_code_prefix,
            )
    return None


def get_info(url, max_retries=5):
    api_url = get_api_url(url)
    color_display_code, size_display_code = parse_product_url(url)

    result = None
    for _ in range(max_retries):
        result = get_info_from_api(api_url, color_display_code, size_display_code)
        if result is not None:
            break

    if result is None:  # if result is still None after max_retries
        return None

    info, color_code_prefix, size_code_prefix = result

    modified_url = url.split("?", 1)[0]

    def next_delimiter(url):
        return "&" if "?" in url else "?"

    if color_display_code is not None:
        modified_url += f"{next_delimiter(modified_url)}colorCode={color_code_prefix}{color_display_code}"
        # modified_url += f"{next_delimiter(modified_url)}colorDisplayCode={color_display_code}"

    if size_display_code is not None:
        modified_url += f"{next_delimiter(modified_url)}sizeCode={size_code_prefix}{size_display_code}"
        # modified_url += f"{next_delimiter(modified_url)}sizeDisplayCode={size_display_code}"

    return info, modified_url


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


def notify_product_added(product):
    product_full_name = (
        f"{product['name']} ({product['color_name']}) - {product['nickname']}"
    )
    title = f"{product_full_name} Added"
    priority = 3
    tags = None
    price_str = f"{product['price']}" + (" (Sale)" if product["is_promo"] else "")
    msg = f"Price: {price_str}, Quantity: {product['quantity']}, {product['color_name']}, {product['size_name']}"

    if product["statusCode"] == "LOW_STOCK":
        title = f"{product_full_name} is LOW on stock"
        priority = 4
        tags = "warning"
        if product["quantity"] <= 3:
            title = f"{product_full_name} is ALMOST OUT of stock"
            priority = 5
            tags = "rotating_light"

    if product["statusCode"] == "STOCK_OUT":
        title = f"{product_full_name} is OUT OF STOCK"
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


def initialize_product_history():
    for url, nickname in product_urls.items():
        res = get_info(url)
        if not res:
            logger.error(f"Unable to retrieve price for {url}")
            continue
        info, url = res

        info["nickname"] = nickname
        info["url"] = url

        if info:
            with product_history_lock:
                product_history[url] = info
        else:
            logger.error(f"Unable to retrieve price for {url}")

    if not args.carry_on:
        with product_history_lock:
            for product in product_history.values():
                notify_product_added(product)


def process_new_products(info, url, nickname):
    # add in any new products to the product_history
    if not info:
        return
    info["nickname"] = nickname
    info["url"] = url
    with product_history_lock:
        product_history[url] = info
    notify_product_added(info)


def main():
    with product_urls_lock:
        initialize_product_history()

    while True:
        # check for updates
        with product_history_lock:
            for url, old_info in product_history.items():
                res = get_info(url)
                if not res:
                    logger.error(f"Unable to retrieve updated info for {url}")
                    continue
                new_info, url = res

                new_info["nickname"] = old_info["nickname"]
                new_info["url"] = url

                price_str = (
                    f"{new_info['price']}" + " (Sale)" if new_info["is_promo"] else ""
                )
                product_full_name = f"{new_info['name']} ({new_info['color_name']}) - {new_info['nickname']}"

                # check price
                if new_info["price"] != old_info["price"]:
                    price_diff = new_info["price"] - old_info["price"]
                    msg = f"""
    Old price: {old_info['price']}
    New price: {new_info['price']}
    Price difference: {price_diff}"""
                    send_ntfy_notification(
                        f"Price change for {product_full_name}",
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
                            f"{product_full_name} is LOW on stock",
                            f"Price: {price_str}, Quantity: {new_info['quantity']}, {new_info['color_name']}, {new_info['size_name']}",
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
                            f"{product_full_name} is OUT OF STOCK",
                            " ",
                            topic,
                            new_info,
                            priority=4,
                            tags="skull",
                        )

                # check quantity if low stock
                if new_info["statusCode"] == "LOW_STOCK":
                    if old_info["quantity"] > new_info["quantity"]:
                        title = f"{product_full_name} - Quantity change"
                        msg = f"Qunaity is down from {old_info['quantity']} to {new_info['quantity']} at Price: {price_str}"
                        priority = 3
                        tags = "small_red_triangle_down	"
                        if new_info["quantity"] <= 3:
                            title = f"{product_full_name} - ALMOST OUT OF STOCK"
                            priority = 5
                            tags = "rotating_light"
                        send_ntfy_notification(
                            title, msg, topic, new_info, priority=priority, tags=tags
                        )
                    elif old_info["quantity"] < new_info["quantity"]:
                        send_ntfy_notification(
                            f"{product_full_name} - Quantity change",
                            f"Qunaity is up from {old_info['quantity']} to {new_info['quantity']} at Price: {price_str}",
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

                new_info["price_change"] = (
                    f"{old_info['price']} -> {new_info['price']}"
                    if old_info["price"] != new_info["price"]
                    else None
                )

            product_data = [
                [
                    info["nickname"],
                    info["name"],
                    (info["quantity"], info["quantity_change"]),
                    (info["price"], info["price_change"]),
                    "Yes" if info["is_promo"] else "",
                    info["color_name"],
                    info["size_name"],
                    info["url"],
                ]
                for info in product_history.values()
            ]
        quantity_idx = 2
        product_data.sort(key=lambda x: x[quantity_idx][0])
        for i, (_, _, (quantity, change), (price, price_change), *_) in enumerate(
            product_data
        ):
            product_data[i][quantity_idx] = (
                change if change is not None else str(quantity)
            )
            product_data[i][quantity_idx + 1] = (
                price_change if price_change is not None else str(price)
            )

        logger.info(
            "\n"
            + tabulate(
                product_data,
                headers=[
                    "Nickname",
                    "Name",
                    "Stock",
                    "Price",
                    "Sale",
                    "Color",
                    "Size",
                    "URL",
                ],
                tablefmt="outline",
            )
        )

        time.sleep(refresh_time)


def parse_uniqlo_url(url):
    return "https://www.uniqlo.com" + url.split("www.uniqlo.com")[1]


def listen_to_ntfy(server, topic):
    while True:
        try:
            response = requests.get(f"{server}/{topic}/raw", stream=True)
            for line in response.iter_lines():
                if line and "www.uniqlo.com" in (line_str := line.decode("utf-8")):
                    if "remove:" in line_str:
                        is_removed = False
                        url = line_str.replace("remove:", "").strip()
                        url = parse_uniqlo_url(url)

                        res = get_info(url)
                        if res:
                            _, url = res

                        with product_urls_lock:
                            if url in product_urls:
                                del product_urls[url]
                                json.dump(
                                    product_urls, open("products.json", "w"), indent=4
                                )
                                is_removed = True

                        with product_history_lock:
                            if url in product_history:
                                del product_history[url]
                                is_removed = True

                        logger.info(
                            f"Removed product: {url}"
                            if is_removed
                            else f"Product not found: {url}"
                        )
                    elif "name:" in line_str:
                        url, nickname = line_str.split("name:", 1)
                        url = parse_uniqlo_url(url.strip())
                        nickname = nickname.strip()

                        res = get_info(url)
                        if not res:
                            logger.error(
                                f"Unable to retrieve product info for {url}. You can try again or there might be an issue with the product URL or Uniqlo API."
                            )
                            continue
                        info, url = res

                        if url in product_urls or url in product_history:
                            logger.info(f"Product already exists: {url}")
                            continue

                        process_new_products(info, url, nickname)

                        with product_urls_lock:
                            product_urls[url] = nickname
                            json.dump(
                                product_urls, open("products.json", "w"), indent=4
                            )
                        logger.info(f"Added product: {url} - {nickname}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Server error: {e}")
            logger.info("Retrying in 5 seconds")
            time.sleep(5)
            continue
        except Exception as e:
            logger.error(f"General Error in listener: {e}")
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

    product_urls = json.load(open("products.json", "r"))
    refresh_time = config["refresh_time"]
    topic = config["ntfy_topic"]
    listen_topic = config["ntfy_listen_topic"]

    product_history = dict()
    product_history_lock = threading.Lock()
    product_urls_lock = threading.Lock()

    listen_thread = threading.Thread(
        target=listen_to_ntfy, args=(args.server, listen_topic)
    )
    listen_thread.daemon = True
    listen_thread.start()

    main()

    listen_thread.join()
