import os
import json
import requests

def build_portal_product_map():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    master_dir = os.path.join(base_dir, "master_data")
    os.makedirs(master_dir, exist_ok=True)
    out_path = os.path.join(master_dir, "dit_portal_product_map.json")

    base_url = "https://pricelist.dit.go.th/getdata.php"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    print("Fetching product mapping from DIT Portal (pricelist.dit.go.th)...")
    product_map = {}
    for ptype in [1, 2]:
        type_name = "ขายปลีก" if ptype == 1 else "ขายส่ง"
        r_groups = session.get(base_url, params={"ID": ptype, "TYPE": "dit"}, timeout=15)
        for g in r_groups.json():
            gid = g["group_id"]
            gname = g["group_name"]
            r_prods = session.get(base_url, params={"ID": gid, "TYPE": "product"}, timeout=15)
            for p in r_prods.json():
                pid = p["product_id"]
                pname = p["product_name"]
                product_map[pid] = {
                    "product_id": pid,
                    "product_name": pname,
                    "type_id": ptype,
                    "category_name": type_name,
                    "group_id": gid,
                    "group_name": gname
                }

    print(f"Total products mapped: {len(product_map)}")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(product_map, f, ensure_ascii=False, indent=2)
    print(f"Saved mapping to: {out_path}")
    return product_map

if __name__ == "__main__":
    build_portal_product_map()
