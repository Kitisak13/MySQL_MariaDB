import os
import sys
import time
import json
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Attempt to import tqdm for progress bar
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("DITDownloader")
logging.getLogger("urllib3").setLevel(logging.ERROR)

class DITPriceDownloader:
    """
    High-performance, resilient, and parallelized DIT Price API Downloader
    with Auto-Resume Checkpoints and Multi-Pass Retries.
    """
    BASE_URL = "https://dataapi.moc.go.th"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def __init__(
        self,
        max_workers: int = 3,
        retry_count: int = 5,
        backoff_factor: float = 1.5,
        timeout: Tuple[int, int] = (5, 45),
        rate_limit_delay: float = 0.1
    ):
        self.max_workers = max_workers
        self.retry_count = retry_count
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.file_lock = threading.Lock()
        self._thread_local = threading.local()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)
        retry_strategy = Retry(total=0, raise_on_status=False)
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.max_workers * 2,
            pool_maxsize=self.max_workers * 2
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get_session(self) -> requests.Session:
        if not hasattr(self._thread_local, "session"):
            self._thread_local.session = self._create_session()
        return self._thread_local.session

    def get_product_list(self) -> pd.DataFrame:
        """Fetches product master catalog from /gis-products."""
        url = f"{self.BASE_URL}/gis-products"
        logger.info("Fetching master product catalog from DIT API...")

        for attempt in range(1, self.retry_count + 1):
            try:
                response = self._get_session().get(url, timeout=self.timeout)
                if response.status_code == 200:
                    data = response.json()
                    df = pd.DataFrame(data)
                    if not df.empty and ("product_id" in df.columns):
                        df = df.dropna(subset=["product_id"]).reset_index(drop=True)
                        df = df[df["product_id"] != "product_id"].reset_index(drop=True)
                    logger.info(f"Successfully retrieved {len(df)} products from DIT API.")
                    return df
                else:
                    logger.warning(f"Attempt {attempt}: Status {response.status_code}")
            except Exception as e:
                logger.warning(f"Attempt {attempt}: Error ({e})")
            time.sleep(self.backoff_factor * attempt)

        logger.error("Failed to fetch product catalog from API.")
        return pd.DataFrame()

    def fetch_product_price(
        self, product_id: str, from_date: str, to_date: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
        """Fetches price history for a single product_id."""
        url = f"{self.BASE_URL}/gis-product-prices"
        params = {
            "product_id": product_id,
            "from_date": from_date,
            "to_date": to_date
        }

        last_error = None
        for attempt in range(1, self.retry_count + 1):
            try:
                response = self._get_session().get(url, params=params, timeout=self.timeout)

                if response.status_code == 200:
                    if not response.text or not response.text.strip():
                        last_error = "Empty response body (0 bytes)"
                        time.sleep(self.backoff_factor * (1.5 ** (attempt - 1)))
                        continue

                    try:
                        data = response.json()
                    except json.JSONDecodeError as e:
                        last_error = f"JSONDecodeError: {e}"
                        time.sleep(self.backoff_factor * (1.5 ** (attempt - 1)))
                        continue

                    if isinstance(data, dict):
                        price_list = data.get("price_list")
                        if price_list and len(price_list) > 0:
                            df = pd.DataFrame(price_list)
                            df["product_id"] = data.get("product_id", product_id)
                            df["product_name"] = data.get("product_name", "")
                            df["category_name"] = data.get("category_name", "")
                            df["group_name"] = data.get("group_name", "")
                            df["unit"] = data.get("unit", "")
                            return df, None
                        else:
                            # Legitimate case: product has no price recorded for this period
                            return None, None
                    else:
                        last_error = f"Unexpected JSON structure: {type(data)}"
                elif response.status_code in (400, 403, 404):
                    last_error = f"HTTP {response.status_code}: Client Error"
                    break
                else:
                    last_error = f"HTTP {response.status_code}"

            except Exception as e:
                last_error = str(e)

            time.sleep(self.backoff_factor * (1.5 ** (attempt - 1)))

        error_record = {
            "product_id": product_id,
            "error_detail": last_error or "Unknown error",
            "from_date": from_date,
            "to_date": to_date
        }
        return None, error_record

    def fetch_all_prices(
        self,
        product_ids: List[str],
        from_date: str,
        to_date: str,
        max_passes: int = 3,
        checkpoint_csv: Optional[str] = None,
        checked_log_path: Optional[str] = None,
        resume: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Concurrently fetches prices for all product_ids with:
        - Auto-Resume Checkpointing (skips already checked IDs)
        - Real-time incremental saving
        - Multi-pass failed ID retries
        """
        completed_ids = set()

        # Step 1: Check for existing tracking log for auto-resume
        if resume and checked_log_path and os.path.exists(checked_log_path):
            try:
                with open(checked_log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        pid = line.strip()
                        if pid:
                            completed_ids.add(pid)
                if completed_ids:
                    logger.info(f"Auto-Resume: Found {len(completed_ids)} completed products in tracking log.")
            except Exception as e:
                logger.warning(f"Could not read tracking log: {e}")

        # Fallback: check checkpoint CSV if tracking log is empty
        if resume and not completed_ids and checkpoint_csv and os.path.exists(checkpoint_csv) and os.path.getsize(checkpoint_csv) > 0:
            try:
                cp_df = pd.read_csv(checkpoint_csv)
                if not cp_df.empty and "product_id" in cp_df.columns:
                    completed_ids = set(cp_df["product_id"].astype(str).unique())
                    logger.info(f"Auto-Resume: Found {len(completed_ids)} products in checkpoint CSV.")
            except Exception as e:
                logger.warning(f"Could not read checkpoint CSV: {e}")

        pending_ids = [pid for pid in product_ids if pid not in completed_ids]

        if not pending_ids:
            logger.info("All products have already been processed in checkpoint! Loading cached data...")
            if checkpoint_csv and os.path.exists(checkpoint_csv) and os.path.getsize(checkpoint_csv) > 0:
                return pd.read_csv(checkpoint_csv), pd.DataFrame()
            return pd.DataFrame(), pd.DataFrame()

        logger.info(f"Targeting {len(pending_ids)} remaining products (Skipping {len(completed_ids)} already checked)...")

        combined_dfs = []
        final_errors = []

        for pass_num in range(1, max_passes + 1):
            if not pending_ids:
                break

            logger.info(f"--- [Pass {pass_num}/{max_passes}] Fetching {len(pending_ids)} products ---")
            pass_failed_ids = []
            pass_errors = []

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_id = {
                    executor.submit(self.fetch_product_price, p_id, from_date, to_date): p_id
                    for p_id in pending_ids
                }

                iterator = as_completed(future_to_id)
                if HAS_TQDM:
                    iterator = tqdm(iterator, total=len(pending_ids), desc=f"Pass {pass_num}")

                for future in iterator:
                    p_id = future_to_id[future]
                    try:
                        df_res, err = future.result()
                        if df_res is not None and not df_res.empty:
                            combined_dfs.append(df_res)
                            # Real-time incremental CSV append
                            if checkpoint_csv:
                                with self.file_lock:
                                    exists = os.path.exists(checkpoint_csv) and os.path.getsize(checkpoint_csv) > 0
                                    df_res.to_csv(checkpoint_csv, mode="a", header=not exists, index=False, encoding="utf-8")
                        elif err is not None:
                            pass_failed_ids.append(p_id)
                            pass_errors.append(err)

                        # Crash-safe tracking log append
                        if err is None and checked_log_path:
                            with self.file_lock:
                                with open(checked_log_path, "a", encoding="utf-8") as f:
                                    f.write(f"{p_id}\n")

                    except Exception as exc:
                        pass_failed_ids.append(p_id)
                        pass_errors.append({"product_id": p_id, "error_detail": str(exc), "from_date": from_date, "to_date": to_date})

                    if self.rate_limit_delay > 0:
                        time.sleep(self.rate_limit_delay)

            if pass_failed_ids:
                logger.warning(f"Pass {pass_num}: {len(pass_failed_ids)} items failed.")
                pending_ids = pass_failed_ids
                if pass_num == max_passes:
                    final_errors.extend(pass_errors)
                else:
                    time.sleep(3.0)
            else:
                logger.info(f"Pass {pass_num}: All target products completed successfully.")
                pending_ids = []

        # Compile final dataframe from memory or checkpoint
        if checkpoint_csv and os.path.exists(checkpoint_csv) and os.path.getsize(checkpoint_csv) > 0:
            df_final = pd.read_csv(checkpoint_csv).drop_duplicates()
        elif combined_dfs:
            df_final = pd.concat(combined_dfs, ignore_index=True).drop_duplicates()
        else:
            df_final = pd.DataFrame()

        df_errs = pd.DataFrame(final_errors) if final_errors else pd.DataFrame()
        return df_final, df_errs
