import logging
import os
import queue
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

# --- Background stock update queue ---
_stock_queue = queue.Queue()
MAX_RETRIES = 3


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
    """Start the background sync and stock worker threads. Call once at app startup."""
    t = threading.Thread(target=_background_sync, daemon=True)
    t.start()

    w = threading.Thread(target=_stock_worker, daemon=True)
    w.start()

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


def _batch_update_stock(updates):
    """Send a batch stock update to WooCommerce. updates = {product_id: new_qty}."""
    url = f"{_base_url()}/wp-json/wc/v3/products/batch"
    payload = {
        "update": [
            {"id": pid, "stock_quantity": qty}
            for pid, qty in updates.items()
        ]
    }
    resp = requests.post(url, auth=_auth(), json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _stock_worker():
    """Background worker: collects queued stock updates and sends them in batches."""
    while True:
        # Block until the first item arrives
        first = _stock_queue.get()
        updates = {first[0]: first[1]}

        # Drain any additional items that arrived in the meantime
        time.sleep(0.1)
        while not _stock_queue.empty():
            try:
                pid, qty = _stock_queue.get_nowait()
                updates[pid] = qty
            except queue.Empty:
                break

        # Send batch to WooCommerce with retries
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                _batch_update_stock(updates)
                logger.info("Stock batch update OK — %d products", len(updates))
                break
            except Exception:
                logger.exception(
                    "Stock batch update failed (attempt %d/%d, %d products)",
                    attempt, MAX_RETRIES, len(updates),
                )
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** attempt)


def queue_stock_update(product_id, new_quantity):
    """Update local cache immediately and queue the WooCommerce API call."""
    with _lock:
        product = _products_by_id.get(product_id)
        if product:
            product["stock_quantity"] = new_quantity

    _stock_queue.put((product_id, new_quantity))
