"""InsureDesk — Migrate companies: add 12 new + update portal_urls.

Run this once to update the existing database.
"""
from __future__ import annotations

import sqlite3
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\user\Desktop\InsureDesk\insuredesk.db"

NEW_COMPANIES = [
    ("MSIG Malaysia", "MSIG", "msig", "https://www.msig.com.my"),
    ("Liberty General Insurance", "Liberty", "liberty", "https://www.libertygeneral.com.my"),
    ("Berjaya Sompo Insurance", "Sompo", "berjaya_sompo", "https://www.berjayasompo.com.my"),
    ("RHB Insurance", "RHB", "rhb", "https://www.rhbgroup.com/insurance"),
    ("MCIS Insurance", "MCIS", "mcis", "https://www.mcis.com.my"),
    ("Generali Malaysia", "Generali", "generali", "https://www.generali.com.my"),
    ("Chubb Insurance Malaysia", "Chubb", "chubb", "https://www.chubb.com/my"),
    ("AIG Malaysia", "AIG", "aig", "https://www.aig.com.my"),
    ("AmMetLife Insurance", "AmMetLife", "ammetlife", "https://www.ammetlife.com"),
    ("Sun Life Malaysia", "Sun Life", "sunlife", "https://www.sunlifemalaysia.com"),
    ("Manulife Insurance Malaysia", "Manulife", "manulife", "https://www.manulife.com.my"),
    ("OAC (Overseas Assurance Corp)", "OAC", "oac", "https://www.oac.com.my"),
]

# Portal URLs for existing companies
UPDATE_URLS = {
    "Great Eastern": "https://www.greateasternlife.com/my",
    "Allianz Malaysia": "https://www.allianz.com.my",
    "Zurich Malaysia": "https://www.zurich.com.my",
    "AIA Malaysia": "https://www.aia.com.my",
    "Etiqa Malaysia": "https://www.etiqa.com.my",
    "Prudential Malaysia": "https://www.prudential.com.my",
    "Tokio Marine": "https://www.tokiomarine.com.my",
    "AXA Malaysia": "https://www.axa.com.my",
    "Hong Leong Assurance": "https://www.hla.com.my",
    "Takaful Malaysia": "https://www.takaful-malaysia.com.my",
}


def _uuid() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Update portal_url for existing companies
    updated = 0
    for name, url in UPDATE_URLS.items():
        cur.execute(
            "UPDATE companies SET portal_url = ? WHERE name = ? AND (portal_url IS NULL OR portal_url = '')",
            (url, name),
        )
        if cur.rowcount > 0:
            updated += cur.rowcount
            print(f"  [OK] Updated: {name} -> {url}")

    # 2. Insert new companies
    inserted = 0
    for name, short, adapter, url in NEW_COMPANIES:
        cur.execute("SELECT id FROM companies WHERE short_name = ?", (short,))
        if cur.fetchone():
            print(f"  [SKIP] Exists: {name}")
            continue
        cur.execute(
            "INSERT INTO companies (id, name, short_name, portal_url, adapter_name, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (_uuid(), name, short, url, adapter),
        )
        inserted += 1
        print(f"  [OK] Inserted: {name} ({short})")

    conn.commit()
    conn.close()

    print(f"\nDone! {updated} updated, {inserted} inserted.")


if __name__ == "__main__":
    main()
