import logging
import os
import threading
import time

import requests

logger = logging.getLogger(__name__)

# --- Cache state ---
_lock = threading.Lock()
_products = []  # list of product dicts
_products_by_id = {}  # id -> product dict
_last_sync = 0
_ready = threading.Event()  # set after first successful sync

SYNC_INTERVAL = int(os.environ.get("WOO_SYNC_INTERVAL", 300))  # default 5 min


def _base_url():
    return os.environ["WOOCOMMERCE_URL"].rstrip("/")


def _auth():
    return (os.environ["WOOCOMMERCE_KEY"], os.environ["WOOCOMMERCE_SECRET"])


def _fetch_all_products():
    """Fetch all managed-stock products from WooCommerce (publish + private)."""
    url = f"{_base_url()}/wp-json/wc/v3/products"
    raw = []

    for status in ("publish", "private"):
        page = 1
        while True:
            resp = requests.get(
                url,
                auth=_auth(),
                params={"per_page": 100, "page": page, "status": status},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            raw.extend(data)
            page += 1

    result = []
    for p in raw:
        if p.get("manage_stock"):
            result.append({
                "id": p["id"],
                "name": p["name"],
                "stock_quantity": p.get("stock_quantity") or 0,
                "image": p["images"][0]["src"] if p.get("images") else None,
                "sku": p.get("sku", ""),
            })

    result.sort(key=lambda x: x["stock_quantity"], reverse=True)
    return result


def _sync():
    """Sync products from WooCommerce into the local cache."""
    global _products, _products_by_id, _last_sync
    try:
        products = _fetch_all_products()
        with _lock:
            _products = products
            _products_by_id = {p["id"]: p for p in products}
            _last_sync = time.time()
        _ready.set()
        logger.info("WooCommerce sync OK — %d products", len(products))
    except Exception:
        logger.exception("WooCommerce sync failed")
        # Keep serving stale cache if we have one
        if _products:
            return
        # No data at all yet — don't set _ready so get_products() will retry inline
        raise


def _background_sync():
    """Background thread: sync on a fixed interval."""
    while True:
        _sync()
        time.sleep(SYNC_INTERVAL)


def start_sync():
    """Start the background sync thread. Call once at app startup."""
    t = threading.Thread(target=_background_sync, daemon=True)
    t.start()
    # Wait up to 15s for the first sync so the app doesn't serve empty pages
    _ready.wait(timeout=15)


# --- Public API ---


def get_products(force_refresh=False):
    """Return cached product list. If force_refresh, sync inline first."""
    if force_refresh:
        try:
            _sync()
        except Exception:
            pass  # fall through to whatever cache we have

    # If cache is empty (app just started, background not ready yet), try inline
    if not _products:
        try:
            _sync()
        except Exception:
            pass

    with _lock:
        return list(_products)


def get_product(product_id):
    """Return a single product from cache. Falls back to API if not cached."""
    with _lock:
        cached = _products_by_id.get(product_id)
        if cached:
            return dict(cached)

    # Not in cache (new product or cache empty) — fetch directly
    url = f"{_base_url()}/wp-json/wc/v3/products/{product_id}"
    resp = requests.get(url, auth=_auth(), timeout=30)
    resp.raise_for_status()
    p = resp.json()
    return {
        "id": p["id"],
        "name": p["name"],
        "stock_quantity": p.get("stock_quantity") or 0,
        "image": p["images"][0]["src"] if p.get("images") else None,
        "sku": p.get("sku", ""),
    }


def update_stock(product_id, new_quantity):
    """Update stock in WooCommerce and patch the local cache immediately."""
    url = f"{_base_url()}/wp-json/wc/v3/products/{product_id}"
    resp = requests.put(
        url,
        auth=_auth(),
        json={"stock_quantity": new_quantity},
        timeout=30,
    )
    resp.raise_for_status()

    # Patch cache in-place instead of invalidating
    with _lock:
        product = _products_by_id.get(product_id)
        if product:
            product["stock_quantity"] = new_quantity

    return resp.json()
