# -*- coding: utf-8 -*-
"""
Thai Trade Export Data Scraper (High-Performance, Resilient & Colab-Optimized)
Target: MOC Trade Report API (https://tradereport.moc.go.th/api/exportharmonizecountries)

Enhancements:
- Month-by-Month Structured Pipeline (Clear progress, tiny memory footprint).
- Session Warm-up & Handshake (Establishes valid cookies to prevent WAF 403/500 blocks).
- Multi-Attempt Exponential Retry per query (Prevents transient network errors).
- Live Real-time Terminal & Colab Logging (Shows exact year, month, HS code, records, and speed).
- Crash-Safe Auto-Resume (Remembers completed months & queries even if Colab disconnects).
- Dimension Enrichment (2, 4, 8, 11 digits HS Codes, Units, and CIA Country metadata).
"""

import os
import sys
import time
import ssl
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
import urllib3
from urllib3.util import Retry

# Suppress SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SSLAdapter(HTTPAdapter):
    """
    Custom SSL adapter that allows legacy TLS connection (SECLEVEL=1)
    and handles unexpected server EOF resets on older government servers.
    """
    def init_poolmanager(self, *args, **kwargs):
        ctx = urllib3.util.ssl_.create_urllib3_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        except Exception:
            pass
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

# Attempt to import tqdm for progress bar
try:
    from tqdm.auto import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Ensure UTF-8 output encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --- Setup Colab & Console Logging ---
class FlushStreamHandler(logging.StreamHandler):
    """Forces immediate unbuffered output in Google Colab and terminals."""
    def emit(self, record):
        super().emit(record)
        self.flush()

# Clean root handlers
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("trade_export_scraper.log", encoding="utf-8"),
        FlushStreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("TradeScraper")
logging.getLogger("urllib3").setLevel(logging.ERROR)

# --- Environment & Helper Functions ---
def is_colab() -> bool:
    """Check if the code is running in a Google Colab environment."""
    return "google.colab" in sys.modules

def display_df(df: pd.DataFrame, rows: int = 5):
    """Displays a DataFrame cleanly in both Colab and Terminal."""
    if is_colab():
        try:
            from IPython.display import display as ipy_display
            ipy_display(df.head(rows))
            return
        except Exception:
            pass
    print(df.head(rows).to_string())

# Mount Google Drive automatically if running in Colab
if is_colab():
    try:
        from google.colab import drive
        logger.info("Running in Google Colab. Mounting Google Drive...")
        drive.mount("/gdrive")
    except Exception as e:
        logger.warning(f"Google Drive mount notice: {e}")

# --- Configuration Class ---
class Config:
    # Base directories based on environment
    if is_colab():
        BASE_DIR = "/gdrive/My Drive/Food-Export"
    else:
        BASE_DIR = "./data"  # Local folder fallback

    # File Paths for Dimension Datasets
    DIM_COUNTRY_PATH = os.path.join(BASE_DIR, "Dim_COUNTRY_REGION_CIA.csv")
    DIM_HS_CODE_PATH = os.path.join(BASE_DIR, "Dim_HS Code.csv")
    DIM_UNIT_PATH = os.path.join(BASE_DIR, "Dim_Unit.csv")

    # Target Scraping Scope
    RESULT_NAME = "food_hs_07_08_20_export_2015_2026"
    YEARS = list(range(2015, 2027))                  # 2015 to 2026
    MONTHS = list(range(1, 13))                      # 1 to 12
    HS_CODE_PREFIXES = ["07", "08", "20"]            # Targets Chapter 07, 08, 20 (Veg, Fruit, Prep)

    # Network & Concurrency Settings (Tuned for MOC Server Stability)
    MAX_WORKERS = 3          # Concurrent parallel workers
    REQUEST_DELAY = 0.15     # Delay between requests (0.15s)
    REQUEST_TIMEOUT = 25     # HTTP Timeout (25s)
    MAX_RETRIES_PER_QUERY = 3 # Retries per item
    RESUME_CHECKPOINT = True # Auto-Resume from previous run

# --- Scraper & Processor Class ---
class TradeExportScraper:
    BASE_URL = "https://tradereport.moc.go.th/api/exportharmonizecountries"
    HOME_URL = "https://tradereport.moc.go.th"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://tradereport.moc.go.th/TradeThai/CustomsHarmonizeExportCountry",
        "Origin": "https://tradereport.moc.go.th",
        "Connection": "close"
    }

    def __init__(self, config: Config):
        self.config = config
        self.file_lock = threading.Lock()
        self._thread_local = threading.local()

    def _create_session(self) -> requests.Session:
        """Creates a requests session with SSLAdapter and warm-up cookies."""
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)
        retry_strategy = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = SSLAdapter(
            max_retries=retry_strategy,
            pool_connections=self.config.MAX_WORKERS * 2,
            pool_maxsize=self.config.MAX_WORKERS * 2
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Warm-up session to receive initial session cookies
        try:
            session.get(self.HOME_URL, timeout=10, verify=False)
        except Exception:
            pass

        return session

    def _get_session(self) -> requests.Session:
        if not hasattr(self._thread_local, "session"):
            self._thread_local.session = self._create_session()
        return self._thread_local.session

    def load_and_preprocess_dimensions(self) -> pd.DataFrame:
        """Loads and cleans dimension datasets. Returns the filtered HS code list."""
        logger.info("Loading dimension datasets...")

        for path_name, path in [
            ("Dim Country", self.config.DIM_COUNTRY_PATH),
            ("Dim HS Code", self.config.DIM_HS_CODE_PATH),
            ("Dim Unit", self.config.DIM_UNIT_PATH)
        ]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Critical Dimension file is missing: {path}")

        self.dim_country = pd.read_csv(self.config.DIM_COUNTRY_PATH)
        self.dim_hs_code = pd.read_csv(self.config.DIM_HS_CODE_PATH)
        self.dim_unit = pd.read_csv(self.config.DIM_UNIT_PATH)

        logger.info("Preprocessing HS Codes and Unit Dimensions...")

        # Pad codes to ensure exact-digit matches
        self.dim_hs_code["HS_2 Digit"] = self.dim_hs_code["HS_2 Digit"].astype(str).str.zfill(2)
        self.dim_hs_code["HS_4 Digit"] = self.dim_hs_code["HS_4 Digit"].astype(str).str.zfill(4)
        self.dim_hs_code["HS_8 Digit"] = self.dim_hs_code["HS_8 Digit"].astype(str).str.zfill(8)
        self.dim_hs_code["HS_11 Digit"] = self.dim_hs_code["HS_11 Digit"].astype(str).str.zfill(11)
        self.dim_unit["HS_11 Digit"] = self.dim_unit["HS_11 Digit"].astype(str).str.zfill(11)

        # Drop duplicate HS Codes
        self.dim_hs_code = self.dim_hs_code.drop_duplicates(subset=["HS_11 Digit"])

        # Filter strictly for HS Codes starting with specified prefix(es)
        prefixes = self.config.HS_CODE_PREFIXES
        if isinstance(prefixes, list):
            prefixes = tuple(prefixes)

        filtered_hs_df = self.dim_hs_code[self.dim_hs_code["HS_11 Digit"].str.startswith(prefixes)].copy()
        logger.info(f"Filtered to {len(filtered_hs_df)} HS codes starting with prefix(es) {prefixes}.")

        return filtered_hs_df

    def fetch_single_query(self, year: int, month: int, hs_code: str) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
        """Fetches trade export data for a single (year, month, hs_code) with internal retries."""
        params = {
            "limit": 0,
            "year": year,
            "month": month,
            "hs_code": hs_code
        }

        last_err = None
        for attempt in range(1, self.config.MAX_RETRIES_PER_QUERY + 1):
            try:
                session = self._get_session()
                response = session.get(self.BASE_URL, params=params, timeout=self.config.REQUEST_TIMEOUT)

                if response.status_code == 200:
                    if not response.text or not response.text.strip():
                        return None, None

                    try:
                        data = response.json()
                    except Exception as e:
                        last_err = f"JSONDecodeError: {e}"
                        time.sleep(1.0 * attempt)
                        continue

                    if data and isinstance(data, list) and len(data) > 0:
                        df = pd.DataFrame(data)
                        df["hs_code_query"] = hs_code
                        df["query_year"] = year
                        df["query_month"] = month
                        return df, None
                    else:
                        # Legitimate empty result (No trade transactions for this commodity in this month)
                        return None, None
                elif response.status_code in (500, 502, 503, 504, 429):
                    last_err = f"HTTP {response.status_code}"
                    time.sleep(1.5 * attempt)
                    continue
                else:
                    return None, {"year": year, "month": month, "hs_code": hs_code, "error": f"HTTP {response.status_code}"}

            except Exception as e:
                last_err = str(e)
                time.sleep(1.0 * attempt)

        err_msg = last_err or "Max retries exceeded"
        logger.warning(f"⚠️ [Error] Year: {year}, Month: {month:02d}, HS: {hs_code} -> {err_msg}")
        return None, {"year": year, "month": month, "hs_code": hs_code, "error": err_msg}

    def fetch_trade_data(self, hs_df: pd.DataFrame) -> Tuple[List[pd.DataFrame], List[Dict[str, Any]]]:
        """
        Month-by-Month Concurrently fetches trade export data across defined years, months, and HS codes
        with Auto-Resume Checkpointing and real-time live console tracking.
        """
        output_dir = os.path.join(self.config.BASE_DIR, "result")
        os.makedirs(output_dir, exist_ok=True)

        checkpoint_csv = os.path.join(output_dir, f"checkpoint_{self.config.RESULT_NAME}.csv")
        checked_log_path = os.path.join(output_dir, f"checked_queries_{self.config.RESULT_NAME}.txt")
        failed_csv_path = os.path.join(output_dir, f"failed_queries_{self.config.RESULT_NAME}.csv")

        hs_codes = hs_df["HS_11 Digit"].tolist()
        total_months = len(self.config.YEARS) * len(self.config.MONTHS)
        total_planned = total_months * len(hs_codes)

        logger.info(f"Total planned queries: {total_planned:,} ({len(self.config.YEARS)} years x {len(self.config.MONTHS)} months x {len(hs_codes)} HS codes)")

        # Load completed queries from tracking log (Auto-Resume)
        completed_keys: Set[str] = set()
        if self.config.RESUME_CHECKPOINT and os.path.exists(checked_log_path):
            try:
                with open(checked_log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        key = line.strip()
                        if key:
                            completed_keys.add(key)
                if completed_keys:
                    logger.info(f"Auto-Resume: Found {len(completed_keys):,} previously completed queries. Skipping them!")
            except Exception as e:
                logger.warning(f"Could not read tracking log: {e}")

        all_dfs = []
        error_logs = []
        overall_with_data = 0
        overall_empty = 0
        overall_errors = 0
        month_idx = 0

        # Load existing data from checkpoint if resuming
        if os.path.exists(checkpoint_csv) and os.path.getsize(checkpoint_csv) > 0:
            try:
                existing_df = pd.read_csv(checkpoint_csv)
                if not existing_df.empty:
                    all_dfs.append(existing_df)
                    logger.info(f"Loaded {len(existing_df):,} existing records from checkpoint CSV.")
            except Exception as e:
                logger.warning(f"Could not read existing checkpoint CSV: {e}")

        # Month-by-Month Execution Loop
        start_overall = time.time()
        for y in self.config.YEARS:
            for m in self.config.MONTHS:
                month_idx += 1
                month_str = f"{y}-{m:02d}"

                # Filter pending HS codes for this specific month
                month_pending_hs = [
                    hs for hs in hs_codes
                    if f"{y}_{m:02d}_{hs}" not in completed_keys
                ]

                if not month_pending_hs:
                    # Month already 100% completed
                    continue

                logger.info(f"\n--- [{month_idx}/{total_months}] Processing Period: {month_str} ({len(month_pending_hs)} pending HS codes) ---")
                month_start = time.time()
                month_data_count = 0
                month_empty_count = 0
                month_err_count = 0

                # Multi-threaded execution for this month
                with ThreadPoolExecutor(max_workers=self.config.MAX_WORKERS) as executor:
                    future_to_hs = {
                        executor.submit(self.fetch_single_query, y, m, hs): hs
                        for hs in month_pending_hs
                    }

                    pbar = tqdm(
                        total=len(month_pending_hs),
                        desc=f"[{month_str}]",
                        unit="code",
                        leave=False
                    ) if HAS_TQDM else None

                    for future in as_completed(future_to_hs):
                        hs = future_to_hs[future]
                        query_key = f"{y}_{m:02d}_{hs}"

                        try:
                            df_res, err = future.result()

                            if df_res is not None and not df_res.empty:
                                all_dfs.append(df_res)
                                month_data_count += 1
                                overall_with_data += 1

                                # Real-time append to checkpoint CSV
                                with self.file_lock:
                                    exists = os.path.exists(checkpoint_csv) and os.path.getsize(checkpoint_csv) > 0
                                    df_res.to_csv(checkpoint_csv, mode="a", header=not exists, index=False, encoding="utf-8-sig")

                            elif err is not None:
                                error_logs.append(err)
                                month_err_count += 1
                                overall_errors += 1
                            else:
                                month_empty_count += 1
                                overall_empty += 1

                            # Append to crash-safe tracking log
                            if err is None:
                                completed_keys.add(query_key)
                                with self.file_lock:
                                    with open(checked_log_path, "a", encoding="utf-8") as f:
                                        f.write(f"{query_key}\n")

                        except Exception as exc:
                            error_logs.append({"year": y, "month": m, "hs_code": hs, "error": str(exc)})
                            month_err_count += 1
                            overall_errors += 1

                        if pbar:
                            pbar.update(1)
                            pbar.set_postfix({
                                "Data": month_data_count,
                                "Empty": month_empty_count,
                                "Err": month_err_count
                            })

                        if self.config.REQUEST_DELAY > 0:
                            time.sleep(self.config.REQUEST_DELAY)

                    if pbar:
                        pbar.close()

                month_elapsed = time.time() - month_start
                logger.info(
                    f"Completed {month_str} in {month_elapsed:.1f}s | "
                    f"With Data: {month_data_count} | Empty: {month_empty_count} | Errors: {month_err_count}"
                )

        # Save persistent failed queries if any
        if error_logs:
            df_err = pd.DataFrame(error_logs)
            df_err.to_csv(failed_csv_path, index=False, encoding="utf-8-sig")
            logger.warning(f"Saved {len(error_logs)} failed queries to: {failed_csv_path}")

        return all_dfs, error_logs

    def enrich_data(self, combined_df: pd.DataFrame, hs_df: pd.DataFrame) -> pd.DataFrame:
        """Enriches the collected raw data by merging it with country, unit, and HS code dimensions."""
        logger.info("Enriching trade data with dimension metadata...")

        # 1. Merge with basic HS code segments (2, 4, 8, 11 digits)
        combined_df = pd.merge(
            combined_df,
            hs_df[["HS_2 Digit", "HS_4 Digit", "HS_8 Digit", "HS_11 Digit"]],
            left_on="hs_code_query",
            right_on="HS_11 Digit",
            how="left"
        )

        # Clear redundant columns if they exist
        hs_desc_cols = [
            "HS_11 Digit", "HS 11 Digit EN_Des", "HS 11 Digit TH_Des",
            "HS 8 Digit TH_Des", "HS 8 Digit EN_Des", "HS 4 Digit EN_Des", "HS 2 Digit EN_Des"
        ]
        redundant_cols = ["Unit_Name_x", "Unit_Name_y", "Alpha-2", "COUNTRY_NAME CIA", "REGION_CODE CIA"]
        cols_to_drop = [c for c in hs_desc_cols if c in combined_df.columns and c != "HS_11 Digit"]
        cols_to_drop += [c for c in redundant_cols if c in combined_df.columns]
        combined_df = combined_df.drop(columns=cols_to_drop, errors="ignore")

        # 2. Merge with detailed HS Code description columns
        desc_cols_to_merge = [c for c in hs_desc_cols if c in self.dim_hs_code.columns]
        combined_df = pd.merge(
            combined_df,
            self.dim_hs_code[desc_cols_to_merge],
            on="HS_11 Digit",
            how="left"
        )

        # 3. Merge with Unit names
        if "Unit_Name" in self.dim_unit.columns:
            combined_df = pd.merge(
                combined_df,
                self.dim_unit[["HS_11 Digit", "Unit_Name"]],
                on="HS_11 Digit",
                how="left"
            )

        # 4. Determine country joining column dynamically
        if "country_code" in combined_df.columns:
            if "COUNTRY_CODE CIA" in self.dim_country.columns:
                country_join_col = "COUNTRY_CODE CIA"
            elif "Alpha-2" in self.dim_country.columns:
                country_join_col = "Alpha-2"
            else:
                country_join_col = self.dim_country.columns[0]

            keep_cols = list(set([country_join_col, "Alpha-2", "COUNTRY_NAME CIA", "REGION_CODE CIA"]))
            keep_cols = [c for c in keep_cols if c in self.dim_country.columns]

            combined_df = pd.merge(
                combined_df,
                self.dim_country[keep_cols],
                left_on="country_code",
                right_on=country_join_col,
                how="left"
            )

            if country_join_col != "country_code" and country_join_col in combined_df.columns:
                if "Alpha-2" in combined_df.columns:
                    combined_df = combined_df.drop(columns=[country_join_col], errors="ignore")

        logger.info("Data enrichment complete.")
        return combined_df

    def save_results(self, combined_df: pd.DataFrame):
        """Saves final enriched dataset to CSV."""
        output_dir = os.path.join(self.config.BASE_DIR, "result")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{self.config.RESULT_NAME}.csv")

        logger.info(f"Saving final dataset ({len(combined_df):,} records) to: {output_path}")
        combined_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info("File saved successfully!")

# --- Execution Entry Point ---
def main():
    config = Config()
    scraper = TradeExportScraper(config)

    total_start = time.time()
    try:
        # 1. Load dimension data
        hs_df = scraper.load_and_preprocess_dimensions()

        # 2. Extract from API with live tracking & auto-resume
        raw_data_list, error_logs = scraper.fetch_trade_data(hs_df)

        if not raw_data_list:
            logger.error("No trade data was retrieved. Program finished.")
            return

        combined_trade_df = pd.concat(raw_data_list, ignore_index=True).drop_duplicates()
        logger.info(f"Successfully retrieved {len(combined_trade_df):,} total records.")

        # 3. Enrich data with dimensions
        final_df = scraper.enrich_data(combined_trade_df, hs_df)

        # 4. Display preview
        logger.info("Sample preview of enriched data:")
        display_df(final_df, rows=5)

        # 5. Save final result
        scraper.save_results(final_df)

        # 6. Post-Run Summary Report
        elapsed_total = time.time() - total_start
        print("\n" + "=" * 80, flush=True)
        print("TRADE DATA SCRAPING PIPELINE COMPLETED!", flush=True)
        print(f"Total Enriched Records : {len(final_df):,}", flush=True)
        print(f"Total Time Elapsed     : {elapsed_total:.1f} seconds ({elapsed_total/60:.2f} minutes)", flush=True)
        if error_logs:
            print(f"Failed Queries Logged  : {len(error_logs):,} (See failed_queries_*.csv)", flush=True)
            print("\nPreview of First 5 Errors:")
            display_df(pd.DataFrame(error_logs), rows=5)
        else:
            print("Status                 : 100% SUCCESS (0 errors)", flush=True)
        print("=" * 80 + "\n", flush=True)

    except Exception as e:
        logger.critical(f"Execution failed due to unhandled exception: {e}", exc_info=True)

if __name__ == "__main__":
    main()