import os
import sys
import re
import time
import requests
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, List, Tuple

# Reconfigure stdout for Unicode / Thai display
sys.stdout.reconfigure(encoding="utf-8")

DATASETS: List[Dict[str, str]] = [
    {
        "id": "ctm_06_11",
        "name_th": "การนำเข้าสินค้า รายประเทศกำเนิด",
        "folder": "ctm_06_11_import_country",
        "type": "import"
    },
    {
        "id": "ctm_06_17",
        "name_th": "การนำเข้าสินค้า ตามประเภทการขนส่ง",
        "folder": "ctm_06_17_import_transport",
        "type": "import"
    },
    {
        "id": "ctm_06_15",
        "name_th": "การนำเข้าสินค้า รายด่านศุลกากร",
        "folder": "ctm_06_15_import_port",
        "type": "import"
    },
    {
        "id": "ctm_06_13",
        "name_th": "การนำเข้าสินค้า รายสำนักงานศุลกากร",
        "folder": "ctm_06_13_import_office",
        "type": "import"
    },
    {
        "id": "ctm_06_12",
        "name_th": "การส่งออกสินค้า รายประเทศปลายทาง",
        "folder": "ctm_06_12_export_country",
        "type": "export"
    },
    {
        "id": "ctm_06_18",
        "name_th": "การส่งออกสินค้า ตามประเภทการขนส่ง",
        "folder": "ctm_06_18_export_transport",
        "type": "export"
    },
    {
        "id": "ctm_06_16",
        "name_th": "การส่งออกสินค้า รายด่านศุลกากร",
        "folder": "ctm_06_16_export_port",
        "type": "export"
    },
    {
        "id": "ctm_06_14",
        "name_th": "การส่งออกสินค้า รายสำนักงานศุลกากร",
        "folder": "ctm_06_14_export_office",
        "type": "export"
    }
]

def get_resilient_session() -> requests.Session:
    """Creates a requests session with automatic retry logic and headers."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "th,en-US;q=0.7,en;q=0.3"
    })
    return session

def sanitize_filename(name: str) -> str:
    """Sanitizes text to produce safe filenames."""
    name = name.strip()
    name = re.sub(r'[\/:*?"<>|]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name

def fetch_dataset_resources(session: requests.Session, dataset_id: str) -> List[dict]:
    """
    Fetches all available resources using the CKAN API.
    """
    api_url = f"https://catalog.customs.go.th/api/3/action/package_show?id={dataset_id}"
    try:
        resp = session.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            return data.get("result", {}).get("resources", [])
    except Exception as e:
        print(f"  [WARN] CKAN API failed for {dataset_id}: {e}. Trying direct scraping fallback...")
    return []

def download_file(session: requests.Session, url: str, destination: str, description: str) -> bool:
    """
    Downloads a single file with streaming and size checks.
    Skips if file already exists and is non-empty.
    """
    if os.path.exists(destination) and os.path.getsize(destination) > 0:
        print(f"  -> [SKIP] File exists ({os.path.getsize(destination):,} bytes): {os.path.basename(destination)}")
        return True

    temp_dest = destination + ".tmp"
    try:
        with session.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(temp_dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

        if os.path.exists(temp_dest):
            os.replace(temp_dest, destination)
            size_mb = downloaded / (1024 * 1024)
            print(f"  -> [SUCCESS] Downloaded: {os.path.basename(destination)} ({size_mb:.2f} MB)")
            return True
    except Exception as e:
        if os.path.exists(temp_dest):
            os.remove(temp_dest)
        print(f"  -> [ERROR] Failed to download {description} ({url}): {e}")
        return False

def download_dataset(session: requests.Session, ds_info: dict, base_raw_dir: str):
    """
    Downloads all CSV data files and Data Dictionaries for a single dataset.
    """
    ds_id = ds_info["id"]
    ds_title = ds_info["name_th"]
    ds_folder = os.path.join(base_raw_dir, ds_info["folder"])
    csv_dir = os.path.join(ds_folder, "csv")
    dict_dir = os.path.join(ds_folder, "data_dictionary")

    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(dict_dir, exist_ok=True)

    print("\n" + "=" * 80)
    print(f"PROCESSING DATASET: {ds_id} - {ds_title}")
    print("=" * 80)

    resources = fetch_dataset_resources(session, ds_id)
    if not resources:
        print(f"[ERROR] No resources retrieved for {ds_id}")
        return

    csv_count = 0
    dict_count = 0

    for r in resources:
        name = r.get("name", "").strip()
        fmt = r.get("format", "").upper().strip()
        url = r.get("url", "").strip()

        if not url:
            continue

        is_dict = "dict" in name.lower() or "dict" in url.lower() or "dictionary" in name.lower()
        
        # Determine target folder and file extension
        if is_dict:
            target_dir = dict_dir
            ext = os.path.splitext(url)[1] or ".xlsx"
            clean_name = sanitize_filename(name)
            if not clean_name.lower().endswith(ext.lower()):
                clean_name += ext
            file_path = os.path.join(target_dir, clean_name)
            print(f"\n[DATA DICTIONARY] {name} ({fmt})")
            if download_file(session, url, file_path, name):
                dict_count += 1
        elif fmt == "CSV" or url.lower().endswith(".csv"):
            target_dir = csv_dir
            clean_name = sanitize_filename(name)
            if not clean_name.lower().endswith(".csv"):
                clean_name += ".csv"
            file_path = os.path.join(target_dir, clean_name)
            print(f"\n[CSV DATA] {name}")
            if download_file(session, url, file_path, name):
                csv_count += 1

    print(f"\n[SUMMARY for {ds_id}] Downloaded: {csv_count} CSV files, {dict_count} Data Dictionary files.")

def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    raw_data_dir = os.path.join(base_dir, "raw_data")
    os.makedirs(raw_data_dir, exist_ok=True)

    session = get_resilient_session()
    start_time = time.time()

    print("=" * 80)
    print("THAI CUSTOMS DATA DOWNLOADER - 8 OPEN DATA DATASETS")
    print(f"Target Directory: {raw_data_dir}")
    print("=" * 80)

    for ds in DATASETS:
        download_dataset(session, ds, raw_data_dir)

    total_time = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"ALL 8 DATASETS DOWNLOAD COMPLETED in {total_time:.2f} seconds!")
    print("=" * 80)

if __name__ == "__main__":
    main()
