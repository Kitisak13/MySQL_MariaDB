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
from bs4 import BeautifulSoup

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

THAI_MONTHS = {
    'ม.ค.': '01', 'ก.พ.': '02', 'มี.ค.': '03', 'เม.ย.': '04',
    'พ.ค.': '05', 'มิ.ย.': '06', 'ก.ค.': '07', 'ส.ค.': '08',
    'ก.ย.': '09', 'ต.ค.': '10', 'พ.ย.': '11', 'ธ.ค.': '12'
}

def to_buddhist_date(iso_date: str) -> str:
    """Converts 'YYYY-MM-DD' to 'DD/MM/YYYY+543'."""
    parts = iso_date.split("-")
    if len(parts) == 3:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{day:02d}/{month:02d}/{year + 543}"
    return iso_date

def parse_thai_date(thai_str: str) -> Optional[str]:
    """Converts '1 ก.ย. 2569' to '2026-09-01'."""
    parts = thai_str.strip().split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = int(THAI_MONTHS.get(parts[1], 9))
            year = int(parts[2]) - 543
            return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, TypeError):
            return None
    return None

class DITPriceDownloader:
    """
    High-performance, resilient, and parallelized DIT Price Downloader
    with Dual-Source Architecture (DIT Live Portal + MOC Open Data API),
    Auto-Resume Checkpoints, and Multi-Pass Retries.
    """
    PORTAL_BASE_URL = "https://pricelist.dit.go.th"
    BASE_URL = "https://dataapi.moc.go.th"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    def __init__(
        self,
        max_workers: int = 4,
        retry_count: int = 5,
        backoff_factor: float = 1.2,
        timeout: Tuple[int, int] = (5, 20),
        rate_limit_delay: float = 0.05
    ):
        self.max_workers = max_workers
        self.retry_count = retry_count
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.file_lock = threading.Lock()
        self._thread_local = threading.local()

        # Load portal product catalog mapping
        self.portal_map = self._load_portal_map()

    def _load_portal_map(self) -> Dict[str, Dict[str, Any]]:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        map_path = os.path.join(base_dir, "master_data", "dit_portal_product_map.json")
        if os.path.exists(map_path):
            try:
                with open(map_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load portal map from {map_path}: {e}")
        return {}

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
        """Fetches product master catalog from portal or MOC API."""
        if self.portal_map:
            records = list(self.portal_map.values())
            return pd.DataFrame(records)

        url = f"{self.PORTAL_BASE_URL}/getdata.php"
        session = self._get_session()
        records = []
        try:
            for ptype in [1, 2]:
                tname = "ขายปลีก" if ptype == 1 else "ขายส่ง"
                r = session.get(url, params={"ID": ptype, "TYPE": "dit"}, timeout=self.timeout)
                for g in r.json():
                    gid = g["group_id"]
                    gname = g["group_name"]
                    r_p = session.get(url, params={"ID": gid, "TYPE": "product"}, timeout=self.timeout)
                    for p in r_p.json():
                        records.append({
                            "product_id": p["product_id"],
                            "product_name": p["product_name"],
                            "type_id": ptype,
                            "category_name": tname,
                            "group_id": gid,
                            "group_name": gname
                        })
            if records:
                return pd.DataFrame(records)
        except Exception as e:
            logger.warning(f"Error fetching from DIT portal: {e}")

        # Fallback to MOC Open Data API
        moc_url = f"{self.BASE_URL}/gis-products"
        try:
            r = session.get(moc_url, timeout=self.timeout)
            if r.status_code == 200:
                df = pd.DataFrame(r.json())
                if not df.empty and ("product_id" in df.columns):
                    return df.dropna(subset=["product_id"]).reset_index(drop=True)
        except Exception as e:
            logger.error(f"Failed to fetch product catalog from MOC API: {e}")

        return pd.DataFrame()

    def _fetch_from_portal(
        self, product_id: str, from_date: str, to_date: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Fetches price history from DIT Live Production Portal (pricelist.dit.go.th).
        Extremely reliable, high-speed, and directly queried from DIT database.
        """
        # Determine type_id and group_id
        meta = self.portal_map.get(product_id)
        if meta:
            type_id = meta["type_id"]
            group_id = meta["group_id"]
            p_name = meta.get("product_name", "")
            cat_name = meta.get("category_name", "")
        else:
            # Prefix heuristics
            type_id = 1 if product_id.startswith("P") else 2
            group_id = product_id[:3] + "000"
            p_name = ""
            cat_name = "ขายปลีก" if type_id == 1 else "ขายส่ง"

        from_thai = to_buddhist_date(from_date)
        to_thai = to_buddhist_date(to_date)

        url = f"{self.PORTAL_BASE_URL}/exportexcel.php"
        params = {
            "settime": "day",
            "from": from_thai,
            "to": to_thai,
            "type": type_id,
            "group": group_id,
            "name": product_id
        }

        session = self._get_session()
        response = session.get(url, params=params, timeout=self.timeout)

        if response.status_code != 200:
            return None, f"HTTP {response.status_code}"

        if not response.content or len(response.content) < 100:
            return None, "Empty response"

        soup = BeautifulSoup(response.content.decode("utf-8", "ignore"), "html.parser")
        rows = soup.find_all("tr")

        if len(rows) <= 1:
            # 0 price records for this product during the period (legitimate empty)
            return None, None

        parsed_data = []
        for tr in rows[1:]:
            tds = [td.text.strip().replace(",", "") for td in tr.find_all("td")]
            if len(tds) >= 7:
                # Format: ['วันที่', 'ประเภท', 'สินค้า', 'หน่วย', 'ราคา ต่ำสุด', 'ราคา สูงสุด', 'ราคาเฉลี่ย']
                iso_d = parse_thai_date(tds[0])
                if not iso_d:
                    continue

                min_str = tds[4] if tds[4] and tds[4] != "-" else None
                max_str = tds[5] if tds[5] and tds[5] != "-" else None
                avg_str = tds[6] if tds[6] and tds[6] != "-" else None

                p_min = float(min_str) if min_str else None
                p_max = float(max_str) if max_str else None
                p_avg = float(avg_str) if avg_str else None

                # Calculate avg if missing
                if p_avg is None and p_min is not None and p_max is not None:
                    p_avg = round((p_min + p_max) / 2.0, 2)
                elif p_avg is None:
                    p_avg = p_min if p_min is not None else p_max

                parsed_data.append({
                    "date": iso_d,
                    "product_id": product_id,
                    "product_name": tds[2] or p_name,
                    "category_name": tds[1] or cat_name,
                    "unit": tds[3],
                    "price_min": p_min,
                    "price_max": p_max,
                    "price_avg": p_avg
                })

        if parsed_data:
            return pd.DataFrame(parsed_data), None
        return None, None

    def _fetch_from_moc_api(
        self, product_id: str, from_date: str, to_date: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Fallback to MOC Open Data API."""
        url = f"{self.BASE_URL}/gis-product-prices"
        params = {"product_id": product_id, "from_date": from_date, "to_date": to_date}

        session = self._get_session()
        response = session.get(url, params=params, timeout=self.timeout)

        if response.status_code == 200:
            if not response.text or not response.text.strip():
                return None, "Empty body"
            try:
                data = response.json()
            except Exception as e:
                return None, f"JSONDecodeError: {e}"

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
                    return None, None
            return None, "Unexpected JSON structure"
        return None, f"HTTP {response.status_code}"

    def fetch_product_price(
        self, product_id: str, from_date: str, to_date: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
        """
        Fetches price history for a single product_id with dual-source fallback.
        """
        last_error = None
        for attempt in range(1, self.retry_count + 1):
            # Attempt 1: DIT Production Portal
            try:
                df, err = self._fetch_from_portal(product_id, from_date, to_date)
                if df is not None:
                    return df, None
                if err is None:
                    # Legitimate empty: product had no price recorded
                    return None, None
                last_error = f"Portal: {err}"
            except Exception as e:
                last_error = f"Portal error: {e}"

            # Attempt 2: MOC Open Data API fallback
            try:
                df, err = self._fetch_from_moc_api(product_id, from_date, to_date)
                if df is not None:
                    return df, None
                if err is None:
                    return None, None
                last_error += f" | MOC API: {err}"
            except Exception as e:
                last_error += f" | MOC API error: {e}"

            time.sleep(self.backoff_factor * attempt)

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
        - Real-time incremental CSV saving
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

            logger.info(f"--- [Pass {pass_num}/{max_passes}] Fetching {len(pending_ids)} products (Workers: {self.max_workers}) ---")
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
                    time.sleep(2.0)
            else:
                logger.info(f"Pass {pass_num}: All target products completed successfully.")
                pending_ids = []

        # Compile final dataframe from checkpoint or memory
        if checkpoint_csv and os.path.exists(checkpoint_csv) and os.path.getsize(checkpoint_csv) > 0:
            df_final = pd.read_csv(checkpoint_csv).drop_duplicates()
        elif combined_dfs:
            df_final = pd.concat(combined_dfs, ignore_index=True).drop_duplicates()
        else:
            df_final = pd.DataFrame()

        df_errs = pd.DataFrame(final_errors) if final_errors else pd.DataFrame()
        return df_final, df_errs
