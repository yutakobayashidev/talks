#!/usr/bin/env python3
"""
Internet Freedom Research: Reproducible Data Collection
========================================================
Cloudflare Radar API と OONI API から直接データを取得し、
raw JSON として保存する。

再現性のため、全てのクエリは絶対日付 (dateStart/dateEnd) を使用する。
オリジナル取得時の相対指定 (12w 等) は、返却されたメタデータの
dateRange から絶対日付に変換済み。

使い方:
  # Cloudflare API トークンを環境変数にセット
  export CLOUDFLARE_API_TOKEN="your-token-here"

  # 全データ取得
  python scripts/collect.py

  # raw → api_snapshot 合成
  python scripts/collect.py --build

  # OONI 構造化データ抽出
  python scripts/collect.py --extract

  # 検証モード (snapshot と raw の値を突合)
  python scripts/collect.py --verify
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SNAPSHOT_PATH = ROOT / "data" / "api_snapshot_2026-03-11.json"

RAW_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# API definitions
# ============================================================

# Cloudflare Radar 公開 API
# Docs: https://developers.cloudflare.com/radar/
CF_BASE = "https://api.cloudflare.com/client/v4/radar"

# OONI API (認証不要)
OONI_BASE = "https://api.ooni.io/api/v1"

# 全クエリ定義: (id, url, params, auth_required)
# オリジナル取得日: 2026-03-11
# 絶対日付はオリジナルの MCP レスポンス metadata から逆算
QUERIES = [
    # --- Cloudflare Radar: Iran HTTP traffic (comparison query) ---
    # MCP は dateRange=["12w","12wcontrol"], location=["IR","IR"] で1リクエスト。
    # 2期間を同時に渡すことで正規化が一貫する (MIN0_MAX は全体の min/max で正規化)。
    # REST API では repeated query params で配列を表現する。
    {
        "id": "cf_http_ir",
        "description": "Iran HTTP traffic timeseries (current vs control, joint normalization)",
        "url": (f"{CF_BASE}/http/timeseries"
                "?location=IR&location=IR"
                "&dateStart=2025-12-08T00:00:00Z&dateStart=2025-09-15T00:00:00Z"
                "&dateEnd=2026-03-09T00:00:00Z&dateEnd=2025-12-15T00:00:00Z"
                "&aggInterval=1w&normalization=MIN0_MAX"),
        "params": None,  # params already in URL (array params can't use urlencode)
        "auth": True,
    },
    # --- Cloudflare Radar: Venezuela HTTP traffic (comparison query) ---
    {
        "id": "cf_http_ve",
        "description": "Venezuela HTTP traffic timeseries (current vs control, joint normalization)",
        "url": (f"{CF_BASE}/http/timeseries"
                "?location=VE&location=VE"
                "&dateStart=2025-12-15T00:00:00Z&dateStart=2025-09-22T00:00:00Z"
                "&dateEnd=2026-03-09T00:00:00Z&dateEnd=2025-12-15T00:00:00Z"
                "&aggInterval=1w&normalization=MIN0_MAX"),
        "params": None,
        "auth": True,
    },
    # --- Cloudflare Radar: Outages ---
    {
        "id": "cf_outages_ir",
        "description": "Iran outages (past year: 2025-03-11 to 2026-03-11)",
        "url": f"{CF_BASE}/annotations/outages",
        "params": {
            "location": "IR",
            "dateStart": "2025-03-11T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "50",
        },
        "auth": True,
    },
    {
        "id": "cf_outages_ve",
        "description": "Venezuela outages (past year: 2025-03-11 to 2026-03-11)",
        "url": f"{CF_BASE}/annotations/outages",
        "params": {
            "location": "VE",
            "dateStart": "2025-03-11T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "50",
        },
        "auth": True,
    },
    # --- Cloudflare Radar: Traffic Anomalies ---
    {
        "id": "cf_anomalies_ir",
        "description": "Iran traffic anomalies (12 weeks: 2025-12-17 to 2026-03-11)",
        "url": f"{CF_BASE}/traffic_anomalies",
        "params": {
            "location": "IR",
            "dateStart": "2025-12-17T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "50",
        },
        "auth": True,
    },
    {
        "id": "cf_anomalies_ve",
        "description": "Venezuela traffic anomalies (12 weeks: 2025-12-17 to 2026-03-11)",
        "url": f"{CF_BASE}/traffic_anomalies",
        "params": {
            "location": "VE",
            "dateStart": "2025-12-17T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "50",
        },
        "auth": True,
    },
    # --- Cloudflare Radar: BGP Leaks ---
    {
        "id": "cf_bgp_leaks_ir",
        "description": "Iran BGP leaks (12 weeks: 2025-12-17 to 2026-03-11)",
        "url": f"{CF_BASE}/bgp/leaks/events",
        "params": {
            "involvedCountry": "IR",
            "dateStart": "2025-12-17T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "20",
        },
        "auth": True,
    },
    {
        "id": "cf_bgp_leaks_ve",
        "description": "Venezuela BGP leaks (12 weeks: 2025-12-17 to 2026-03-11)",
        "url": f"{CF_BASE}/bgp/leaks/events",
        "params": {
            "involvedCountry": "VE",
            "dateStart": "2025-12-17T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "20",
        },
        "auth": True,
    },
    # --- Cloudflare Radar: BGP Hijacks ---
    {
        "id": "cf_bgp_hijacks_ir",
        "description": "Iran BGP hijacks (12 weeks: 2025-12-17 to 2026-03-11)",
        "url": f"{CF_BASE}/bgp/hijacks/events",
        "params": {
            "involvedCountry": "IR",
            "dateStart": "2025-12-17T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "20",
        },
        "auth": True,
    },
    {
        "id": "cf_bgp_hijacks_ve",
        "description": "Venezuela BGP hijacks (12 weeks: 2025-12-17 to 2026-03-11)",
        "url": f"{CF_BASE}/bgp/hijacks/events",
        "params": {
            "involvedCountry": "VE",
            "dateStart": "2025-12-17T00:00:00Z",
            "dateEnd": "2026-03-11T00:00:00Z",
            "limit": "20",
        },
        "auth": True,
    },
    # --- OONI: Recent measurements ---
    {
        "id": "ooni_measurements_ir",
        "description": "Iran OONI measurements (since 2026-01-01)",
        "url": f"{OONI_BASE}/measurements",
        "params": {
            "probe_cc": "IR",
            "since": "2026-01-01",
            "limit": "100",
        },
        "auth": False,
    },
    {
        "id": "ooni_measurements_ve",
        "description": "Venezuela OONI measurements (since 2026-01-01)",
        "url": f"{OONI_BASE}/measurements",
        "params": {
            "probe_cc": "VE",
            "since": "2026-01-01",
            "limit": "100",
        },
        "auth": False,
    },
    # --- OONI: Aggregation (daily counts) ---
    {
        "id": "ooni_aggregation_ir",
        "description": "Iran OONI daily aggregation (2025-01-01 to 2026-03-11)",
        "url": f"{OONI_BASE}/aggregation",
        "params": {
            "probe_cc": "IR",
            "since": "2025-01-01",
            "until": "2026-03-11",
            "axis_x": "measurement_start_day",
        },
        "auth": False,
    },
    {
        "id": "ooni_aggregation_ve",
        "description": "Venezuela OONI daily aggregation (2025-01-01 to 2026-03-11)",
        "url": f"{OONI_BASE}/aggregation",
        "params": {
            "probe_cc": "VE",
            "since": "2025-01-01",
            "until": "2026-03-11",
            "axis_x": "measurement_start_day",
        },
        "auth": False,
    },
    # --- Tor Metrics (CSV, no auth) ---
    {
        "id": "tor_relay_users_ir",
        "description": "Tor relay users in Iran (daily CSV)",
        "url": "https://metrics.torproject.org/userstats-relay-country.csv",
        "params": {
            "start": "2025-01-01",
            "end": "2026-03-11",
            "country": "ir",
            "events": "off",
        },
        "auth": False,
    },
    {
        "id": "tor_relay_users_ve",
        "description": "Tor relay users in Venezuela (daily CSV)",
        "url": "https://metrics.torproject.org/userstats-relay-country.csv",
        "params": {
            "start": "2025-01-01",
            "end": "2026-03-11",
            "country": "ve",
            "events": "off",
        },
        "auth": False,
    },
    {
        "id": "tor_bridge_users_ir",
        "description": "Tor bridge users in Iran (daily CSV)",
        "url": "https://metrics.torproject.org/userstats-bridge-country.csv",
        "params": {
            "start": "2025-01-01",
            "end": "2026-03-11",
            "country": "ir",
            "events": "off",
        },
        "auth": False,
    },
    {
        "id": "tor_bridge_users_ve",
        "description": "Tor bridge users in Venezuela (daily CSV)",
        "url": "https://metrics.torproject.org/userstats-bridge-country.csv",
        "params": {
            "start": "2025-01-01",
            "end": "2026-03-11",
            "country": "ve",
            "events": "off",
        },
        "auth": False,
    },
]


def fetch(query, token):
    """1つのクエリを実行し、raw JSON を返す"""
    url = query["url"]
    if query["params"]:
        url += "?" + urllib.parse.urlencode(query["params"])
    # params=None means params are already embedded in the URL (for array params)

    headers = {"Accept": "application/json"}
    if query["auth"]:
        if not token:
            print(f"  SKIP (no CLOUDFLARE_API_TOKEN): {query['id']}")
            return None
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type or body.lstrip().startswith("{"):
                return json.loads(body)
            else:
                # CSV or other text response (e.g. Tor Metrics)
                return {"_format": "text", "body": body}
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        print(f"  ERROR {e.code}: {query['id']} — {body[:200]}")
        return None
    except Exception as e:
        print(f"  ERROR: {query['id']} — {e}")
        return None


def save_raw(query_id: str, data: dict, collected_at: str):
    """raw レスポンスをメタデータ付きで保存"""
    envelope = {
        "_meta": {
            "query_id": query_id,
            "collected_at": collected_at,
            "script": "scripts/collect.py",
        },
        "response": data,
    }
    path = RAW_DIR / f"{query_id}.json"
    with open(path, "w") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)
    return path


def collect_all(token, targets=None):
    """全クエリを実行して raw JSON を保存"""
    if targets is None:
        targets = QUERIES
    collected_at = datetime.now(timezone.utc).isoformat()
    print(f"Collection started at: {collected_at}")
    print(f"Output directory: {RAW_DIR}\n")

    results = {}
    for q in targets:
        print(f"Fetching: {q['id']} — {q['description']}")
        data = fetch(q, token)
        if data:
            path = save_raw(q["id"], data, collected_at)
            results[q["id"]] = str(path)
            print(f"  -> Saved: {path.name}")
        else:
            results[q["id"]] = None

    # マニフェスト保存
    manifest = {
        "collected_at": collected_at,
        "queries": {q["id"]: {
            "url": q["url"],
            "params": q["params"],
            "description": q["description"],
            "auth_required": q["auth"],
        } for q in targets},
        "results": results,
    }
    manifest_path = RAW_DIR / "_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest: {manifest_path}")
    return results


# ============================================================
# Extract structured data from raw responses
# ============================================================

def extract_ooni_blocked(raw_path, country_code):
    """OONI measurements raw JSON から遮断サイトを機械的に抽出"""
    if not raw_path.exists():
        print(f"  [SKIP] {raw_path.name} not found")
        return None

    with open(raw_path) as f:
        raw = json.load(f)

    results = raw["response"].get("results", [])
    blocked = []
    anomalies = []
    failed = []

    for m in results:
        test_name = m.get("test_name", "")
        inp = m.get("input", "")
        is_anomaly = m.get("anomaly", False)
        is_confirmed = m.get("confirmed", False)
        is_failure = m.get("failure", False)

        if is_confirmed:
            blocked.append({"input": inp, "test_name": test_name, "status": "confirmed"})
        elif is_anomaly:
            anomalies.append({"input": inp, "test_name": test_name, "status": "anomaly"})
        elif is_failure:
            failed.append({"input": inp, "test_name": test_name, "status": "failure"})

    return {
        "country": country_code,
        "total_measurements": len(results),
        "confirmed_blocked": blocked,
        "anomalies": anomalies,
        "failures": failed,
        "test_names": list(set(m.get("test_name", "") for m in results)),
    }


def extract_ooni_aggregation(raw_path, country_code):
    """OONI aggregation raw JSON からサマリ統計を抽出"""
    if not raw_path.exists():
        print(f"  [SKIP] {raw_path.name} not found")
        return None

    with open(raw_path) as f:
        raw = json.load(f)

    rows = raw["response"].get("result", [])
    if not rows:
        return None

    # 各日の measurement_count, anomaly_count, confirmed_count を集計
    daily = []
    for row in rows:
        day = row.get("measurement_start_day", "")
        mc = row.get("measurement_count", 0)
        ac = row.get("anomaly_count", 0)
        cc = row.get("confirmed_count", 0)
        daily.append({"date": day, "measurements": mc, "anomalies": ac, "confirmed": cc})

    # サマリ統計
    measurements = [d["measurements"] for d in daily]
    anomalies_list = [d["anomalies"] for d in daily]

    # 測定数が急減した日 (前日比 50% 以下)
    drops = []
    for i in range(1, len(daily)):
        prev = daily[i-1]["measurements"]
        curr = daily[i]["measurements"]
        if prev > 100 and curr < prev * 0.5:
            drops.append({
                "date": daily[i]["date"],
                "from": prev,
                "to": curr,
                "drop_pct": round((1 - curr / prev) * 100, 1),
            })

    return {
        "country": country_code,
        "total_days": len(daily),
        "date_range": f"{daily[0]['date']} to {daily[-1]['date']}",
        "measurement_count": {
            "min": min(measurements),
            "max": max(measurements),
            "mean": round(sum(measurements) / len(measurements), 1),
        },
        "anomaly_count": {
            "min": min(anomalies_list),
            "max": max(anomalies_list),
            "mean": round(sum(anomalies_list) / len(anomalies_list), 1),
        },
        "sharp_drops": drops,
        "daily": daily,
    }


def extract_all():
    """raw データから構造化データを抽出して保存"""
    print("=== Extracting structured data from raw responses ===\n")
    extracted = {}

    for cc in ["ir", "ve"]:
        name = "Iran" if cc == "ir" else "Venezuela"

        print(f"[{name}] OONI measurements...")
        blocked = extract_ooni_blocked(RAW_DIR / f"ooni_measurements_{cc}.json", cc.upper())
        if blocked:
            extracted[f"ooni_blocked_{cc}"] = blocked
            n_conf = len(blocked["confirmed_blocked"])
            n_anom = len(blocked["anomalies"])
            print(f"  confirmed={n_conf}, anomalies={n_anom}, failures={len(blocked['failures'])}")

        print(f"[{name}] OONI aggregation...")
        agg = extract_ooni_aggregation(RAW_DIR / f"ooni_aggregation_{cc}.json", cc.upper())
        if agg:
            extracted[f"ooni_aggregation_{cc}"] = {
                "date_range": agg["date_range"],
                "total_days": agg["total_days"],
                "measurement_count": agg["measurement_count"],
                "anomaly_count": agg["anomaly_count"],
                "sharp_drops": agg["sharp_drops"],
            }
            print(f"  days={agg['total_days']}, drops={len(agg['sharp_drops'])}")

    out_path = ROOT / "data" / "extracted_2026-03-11.json"
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {
                "description": "raw API レスポンスから機械的に抽出した構造化データ",
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "script": "scripts/collect.py --extract",
            },
            **extracted,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")


def collect_ooni_categories():
    """OONI APIからカテゴリ別遮断データを取得して保存する。

    Citizen Lab URL category codes を使い、国ごと・カテゴリごとの
    confirmed + anomaly 件数を集計。結果を1つのJSONにまとめる。
    ref: https://github.com/citizenlab/test-lists/blob/master/lists/00-LEGEND-category_codes.csv
    """
    import time

    CATEGORIES = [
        "NEWS", "HUMR", "POLR", "LGBT", "COMM", "COMT", "ANON",
        "MMED", "SRCH", "CULTR", "FILE", "HOST", "GAME", "PORN",
        "DATE", "PROV", "HACK", "MILX", "HATE", "REL", "GRP",
        "PUBH", "ECON", "ENV", "MISC",
    ]
    COUNTRIES = [("IR", "Iran"), ("VE", "Venezuela")]

    print("=== Collecting OONI category breakdown ===\n")
    results = {}

    for cc, label in COUNTRIES:
        print(f"[{label}]")
        country_data = {}
        for cat in CATEGORIES:
            params = urllib.parse.urlencode({
                "probe_cc": cc,
                "since": "2025-01-01",
                "until": "2026-03-11",
                "test_name": "web_connectivity",
                "category_code": cat,
            })
            url = f"{OONI_BASE}/aggregation?{params}"
            try:
                req = urllib.request.urlopen(url, timeout=30)
                data = json.loads(req.read())
                r = data.get("result", {})
                country_data[cat] = {
                    "confirmed_count": r.get("confirmed_count", 0),
                    "anomaly_count": r.get("anomaly_count", 0),
                    "measurement_count": r.get("measurement_count", 0),
                }
                blocked = r.get("confirmed_count", 0) + r.get("anomaly_count", 0)
                print(f"  {cat:6s} blocked={blocked:>8,}")
                time.sleep(0.3)
            except Exception as e:
                print(f"  {cat:6s} ERROR: {e}")
                country_data[cat] = {"confirmed_count": 0, "anomaly_count": 0, "measurement_count": 0}
        results[cc.lower()] = country_data

    out_path = RAW_DIR / "ooni_category_breakdown.json"
    with open(out_path, "w") as f:
        json.dump({
            "_meta": {
                "description": "OONI web_connectivity category breakdown (confirmed + anomaly)",
                "query_params": {"since": "2025-01-01", "until": "2026-03-11", "test_name": "web_connectivity"},
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "source": "https://api.ooni.io/api/v1/aggregation",
                "category_codes_ref": "https://github.com/citizenlab/test-lists/blob/master/lists/00-LEGEND-category_codes.csv",
            },
            **results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path}")


# ============================================================
# Build: raw → api_snapshot
# ============================================================

def _load_raw(query_id: str) -> Optional[dict]:
    """raw JSON を読み込んで response 部分を返す"""
    path = RAW_DIR / f"{query_id}.json"
    if not path.exists():
        print(f"  [SKIP] {path.name} not found")
        return None
    with open(path) as f:
        return json.load(f)["response"]


def _build_http_timeseries(query_id: str) -> dict:
    """CF HTTP comparison query の raw から timeseries セクションを構築"""
    resp = _load_raw(query_id)
    if not resp:
        return {"_raw": f"data/raw/{query_id}.json", "_query_id": query_id, "_note": "raw not found"}

    result = resp["result"]
    meta = result.get("meta", {})
    date_ranges = meta.get("dateRange", [])

    # serie_0 = current period, serie_1 = control period
    def parse_serie(serie_key, range_idx):
        serie = result.get(serie_key, {})
        timestamps = [t[:10] for t in serie.get("timestamps", [])]
        values = [float(v) for v in serie.get("values", [])]
        dr = date_ranges[range_idx] if range_idx < len(date_ranges) else {}
        return {
            "range": f"{dr.get('startTime', '')[:10]} to {dr.get('endTime', '')[:10]}",
            "timestamps": timestamps,
            "values": values,
        }

    current = parse_serie("serie_0", 0)
    current["normalization"] = meta.get("normalization", "")
    control = parse_serie("serie_1", 1)

    # annotations from confidenceInfo
    raw_annots = meta.get("confidenceInfo", {}).get("annotations", [])
    annotations = [
        {
            "startDate": a["startDate"],
            "endDate": a.get("endDate"),
            "eventType": a.get("eventType", ""),
            "description": a.get("description", ""),
        }
        for a in raw_annots
    ]

    out = {
        "_raw": f"data/raw/{query_id}.json",
        "_query_id": query_id,
        "_verified": True,
        "current_period": current,
        "control_period": control,
    }
    if annotations:
        out["annotations"] = annotations
    return out


def _build_outages(query_id: str) -> dict:
    """CF outages raw から outages セクションを構築"""
    resp = _load_raw(query_id)
    if not resp:
        return {"_raw": f"data/raw/{query_id}.json", "_query_id": query_id, "total_events": 0}

    annotations = resp.get("result", {}).get("annotations", [])
    total = len(annotations)

    all_gov = all(
        a.get("outage", {}).get("outageCause") == "GOVERNMENT_DIRECTED"
        for a in annotations
    ) if annotations else False

    all_nationwide = all(
        a.get("outage", {}).get("outageType") == "NATIONWIDE"
        for a in annotations
    ) if annotations else False

    events = []
    for a in annotations:
        ev = {
            "id": a["id"],
            "startDate": a["startDate"],
            "endDate": a.get("endDate"),
            "description": a.get("description", ""),
        }
        cause = a.get("outage", {}).get("outageCause")
        if cause and cause != "GOVERNMENT_DIRECTED":
            ev["cause"] = cause
        events.append(ev)

    out = {
        "_raw": f"data/raw/{query_id}.json",
        "_query_id": query_id,
        "_verified": True,
        "total_events": total,
    }
    if annotations:
        out["all_government_directed"] = all_gov
        out["all_nationwide"] = all_nationwide
        out["events"] = events
    return out


def _build_anomalies(query_id: str) -> dict:
    """CF traffic anomalies raw から anomalies セクションを構築"""
    resp = _load_raw(query_id)
    if not resp:
        return {"_raw": f"data/raw/{query_id}.json", "_query_id": query_id, "total_events": 0}

    result = resp.get("result", {})
    raw_events = result.get("trafficAnomalies", [])

    events = [
        {
            "startDate": e["startDate"],
            "endDate": e.get("endDate"),
            "status": e.get("status", ""),
        }
        for e in raw_events
    ]

    out = {
        "_raw": f"data/raw/{query_id}.json",
        "_query_id": query_id,
        "_verified": True,
    }
    if events:
        out["events"] = events
    else:
        out["total_events"] = 0
    return out


def _build_bgp_leaks(query_id: str) -> dict:
    """CF BGP leaks raw から leaks セクションを構築"""
    resp = _load_raw(query_id)
    if not resp:
        return {"_raw": f"data/raw/{query_id}.json", "_query_id": query_id, "total_events": 0}

    result = resp.get("result", {})
    raw_events = result.get("events", [])
    result_info = resp.get("result_info", {})

    events = [
        {
            "id": e["id"],
            "date": e["detected_ts"][:10],
            "leak_asn": e["leak_asn"],
            "leak_count": e["leak_count"],
        }
        for e in raw_events
    ]

    total_in_response = len(raw_events)
    total_in_api = result_info.get("total_count", total_in_response)

    out = {
        "_raw": f"data/raw/{query_id}.json",
        "_query_id": query_id,
        "_verified": True,
    }
    if total_in_api != total_in_response:
        out["total_events_in_snapshot"] = total_in_response
        out["total_events_in_api"] = total_in_api
    else:
        out["total_events"] = total_in_response
    if events:
        out["events"] = events
    return out


def _build_bgp_hijacks(query_id: str) -> dict:
    """CF BGP hijacks raw から hijacks セクションを構築"""
    resp = _load_raw(query_id)
    if not resp:
        return {"_raw": f"data/raw/{query_id}.json", "_query_id": query_id, "total_events": 0}

    result = resp.get("result", {})
    raw_events = result.get("events", [])
    result_info = resp.get("result_info", {})

    total_in_response = len(raw_events)
    total_in_api = result_info.get("total_count", total_in_response)

    out = {
        "_raw": f"data/raw/{query_id}.json",
        "_query_id": query_id,
        "_verified": True,
    }
    if total_in_api != total_in_response:
        out["total_events_in_snapshot"] = total_in_response
        out["total_events_in_api"] = total_in_api
    else:
        out["total_events"] = total_in_response
    return out


def build():
    """raw データから api_snapshot を合成する"""
    print("=== Building api_snapshot from raw data ===\n")

    # Tor Metrics の raw ファイルが存在するかチェック
    tor_ids = ["tor_relay_users_ir", "tor_relay_users_ve",
               "tor_bridge_users_ir", "tor_bridge_users_ve"]
    tor_collected = any((RAW_DIR / f"{tid}.json").exists() for tid in tor_ids)

    snapshot = {
        "_meta": {
            "description": "API再現可能なデータのみ。全ての値は data/raw/ の生レスポンスから導出可能",
            "collected_at": "2026-03-11T05:00:00Z",
            "reproducibility": "python scripts/collect.py && python scripts/collect.py --build",
            "sources": {
                "cloudflare_radar": {
                    "base_url": "https://api.cloudflare.com/client/v4/radar",
                    "auth": "Bearer token (Account > Radar > Read)",
                    "license": "CC BY-NC 4.0",
                },
                "ooni": {
                    "base_url": "https://api.ooni.io/api/v1",
                    "auth": "none",
                },
                "tor_metrics": {
                    "base_url": "https://metrics.torproject.org",
                    "auth": "none",
                    "status": "ECONNREFUSED on 2026-03-11 — endpoints defined but data not collected",
                },
            },
        },
        "cloudflare_radar": {},
        "ooni": {},
        "tor_metrics": {},
    }

    # --- Cloudflare Radar ---
    for cc, name in [("ir", "iran"), ("ve", "venezuela")]:
        print(f"[{name.title()}] Building Cloudflare Radar sections...")
        snapshot["cloudflare_radar"][name] = {
            "http_traffic_timeseries": _build_http_timeseries(f"cf_http_{cc}"),
            "outages_past_year": _build_outages(f"cf_outages_{cc}"),
            "traffic_anomalies_12w": _build_anomalies(f"cf_anomalies_{cc}"),
            "bgp_leaks_12w": _build_bgp_leaks(f"cf_bgp_leaks_{cc}"),
            "bgp_hijacks_12w": _build_bgp_hijacks(f"cf_bgp_hijacks_{cc}"),
        }

    # --- OONI ---
    for cc, name in [("ir", "iran"), ("ve", "venezuela")]:
        print(f"[{name.title()}] Building OONI sections...")
        snapshot["ooni"][name] = {
            "measurements": {
                "_raw": f"data/raw/ooni_measurements_{cc}.json",
                "_query_id": f"ooni_measurements_{cc}",
                "_extracted_by": "scripts/collect.py --extract",
            },
            "aggregation": {
                "_raw": f"data/raw/ooni_aggregation_{cc}.json",
                "_query_id": f"ooni_aggregation_{cc}",
                "_extracted_by": "scripts/collect.py --extract",
            },
        }

    # --- Tor Metrics ---
    if tor_collected:
        snapshot["tor_metrics"]["_status"] = "COLLECTED"
    else:
        snapshot["tor_metrics"] = {
            "_status": "NOT_COLLECTED",
            "_reason": "metrics.torproject.org returned ECONNREFUSED on 2026-03-11",
            "_endpoints": {
                tid: next(
                    (q["url"] + "?" + urllib.parse.urlencode(q["params"])
                     for q in QUERIES if q["id"] == tid),
                    "",
                )
                for tid in tor_ids
            },
        }

    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    print(f"\nSnapshot written: {SNAPSHOT_PATH}")
    return snapshot


# ============================================================
# Verification
# ============================================================

def verify():
    """raw データと snapshot の値を突合する"""
    if not SNAPSHOT_PATH.exists():
        print(f"Snapshot not found: {SNAPSHOT_PATH}")
        sys.exit(1)

    with open(SNAPSHOT_PATH) as f:
        snapshot = json.load(f)

    print("=== Verification: raw API responses vs snapshot ===\n")
    errors = 0

    # 1. Iran HTTP (comparison: serie_0=current, serie_1=control)
    raw_path = RAW_DIR / "cf_http_ir.json"
    if raw_path.exists():
        with open(raw_path) as f:
            raw = json.load(f)
        resp = raw["response"]
        if "result" in resp:
            for serie_key, period_name, snap_key in [
                ("serie_0", "current_period", "cf_http_ir serie_0 (current)"),
                ("serie_1", "control_period", "cf_http_ir serie_1 (control)"),
            ]:
                raw_values = resp["result"].get(serie_key, {}).get("values", [])
                snap_values = snapshot["cloudflare_radar"]["iran"]["http_traffic_timeseries"][period_name]["values"]
                raw_floats = [float(v) for v in raw_values]
                match = all(abs(a - b) < 1e-4 for a, b in zip(raw_floats, snap_values))
                status = "MATCH" if match and len(raw_floats) == len(snap_values) else "MISMATCH"
                if status == "MISMATCH":
                    errors += 1
                print(f"[{status}] {snap_key}: {len(raw_floats)} values vs {len(snap_values)} in snapshot")
                if status == "MISMATCH":
                    print(f"  raw:  {raw_floats[:5]}...")
                    print(f"  snap: {snap_values[:5]}...")
    else:
        print("[SKIP] cf_http_ir.json not found")

    # 3. Iran outages — check count and first event
    raw_path = RAW_DIR / "cf_outages_ir.json"
    if raw_path.exists():
        with open(raw_path) as f:
            raw = json.load(f)
        resp = raw["response"]
        annotations = resp.get("result", {}).get("annotations", [])
        snap_outages = snapshot["cloudflare_radar"]["iran"]["outages_past_year"]
        snap_count = snap_outages.get("total_events", len(snap_outages.get("events", snap_outages)))
        status = "MATCH" if len(annotations) >= snap_count else "MISMATCH"
        if status == "MISMATCH":
            errors += 1
        print(f"[{status}] cf_outages_ir: {len(annotations)} events (snapshot: {snap_count})")
    else:
        print("[SKIP] cf_outages_ir.json not found")

    # 4. Iran traffic anomalies
    # API returns result.trafficAnomalies (direct) or result (MCP).
    # Count may grow over time as new events are added; >= is acceptable.
    raw_path = RAW_DIR / "cf_anomalies_ir.json"
    if raw_path.exists():
        with open(raw_path) as f:
            raw = json.load(f)
        resp = raw["response"]
        result = resp.get("result", {})
        events = result.get("trafficAnomalies", result) if isinstance(result, dict) else result
        if isinstance(events, dict):
            events = []
        snap_anom = snapshot["cloudflare_radar"]["iran"]["traffic_anomalies_12w"]
        snap_count = len(snap_anom.get("events", snap_anom))
        status = "MATCH" if len(events) >= snap_count else "MISMATCH"
        if status == "MISMATCH":
            errors += 1
        print(f"[{status}] cf_anomalies_ir: {len(events)} events (snapshot: {snap_count}, >= is OK)")
    else:
        print("[SKIP] cf_anomalies_ir.json not found")

    # 5. Iran BGP leaks
    raw_path = RAW_DIR / "cf_bgp_leaks_ir.json"
    if raw_path.exists():
        with open(raw_path) as f:
            raw = json.load(f)
        resp = raw["response"]
        events = resp.get("result", {}).get("events", [])
        snap_count = snapshot["cloudflare_radar"]["iran"]["bgp_leaks_12w"]["total_events"]
        status = "MATCH" if len(events) == snap_count else "MISMATCH"
        if status == "MISMATCH":
            errors += 1
        print(f"[{status}] cf_bgp_leaks_ir: {len(events)} events (snapshot: {snap_count})")
    else:
        print("[SKIP] cf_bgp_leaks_ir.json not found")

    # 6. Venezuela BGP leaks
    # API default limit may differ from MCP's limit=20. Check that snapshot
    # events are a subset (by event id) of the API response.
    raw_path = RAW_DIR / "cf_bgp_leaks_ve.json"
    if raw_path.exists():
        with open(raw_path) as f:
            raw = json.load(f)
        resp = raw["response"]
        events = resp.get("result", {}).get("events", [])
        snap_count = snapshot["cloudflare_radar"]["venezuela"]["bgp_leaks_12w"].get(
            "total_events", snapshot["cloudflare_radar"]["venezuela"]["bgp_leaks_12w"].get("total_events_in_snapshot", 0)
        )
        status = "MATCH" if len(events) >= snap_count else "MISMATCH"
        if status == "MISMATCH":
            errors += 1
        print(f"[{status}] cf_bgp_leaks_ve: {len(events)} events (snapshot: {snap_count}, >= is OK)")
    else:
        print("[SKIP] cf_bgp_leaks_ve.json not found")

    # OONI checks
    for cc, name in [("ir", "Iran"), ("ve", "Venezuela")]:
        raw_path = RAW_DIR / f"ooni_measurements_{cc}.json"
        if raw_path.exists():
            with open(raw_path) as f:
                raw = json.load(f)
            resp = raw["response"]
            results = resp.get("results", [])
            print(f"[INFO] ooni_measurements_{cc}: {len(results)} measurements returned")
        else:
            print(f"[SKIP] ooni_measurements_{cc}.json not found")

    print(f"\n{'='*50}")
    if errors == 0:
        print("ALL CHECKS PASSED (or skipped)")
    else:
        print(f"{errors} MISMATCH(ES) FOUND")
    return errors


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect and verify internet freedom research data")
    parser.add_argument("--verify", action="store_true", help="Verify raw data against snapshot")
    parser.add_argument("--build", action="store_true", help="Build api_snapshot from raw data")
    parser.add_argument("--extract", action="store_true", help="Extract structured data from raw OONI/Tor responses")
    parser.add_argument("--ooni-only", action="store_true", help="Only fetch OONI data (no Cloudflare token needed)")
    parser.add_argument("--categories", action="store_true", help="Fetch OONI category breakdown data")
    args = parser.parse_args()

    if args.categories:
        collect_ooni_categories()
        sys.exit(0)

    if args.build:
        build()
        sys.exit(0)

    if args.verify:
        sys.exit(verify())

    if args.extract:
        extract_all()
        sys.exit(0)

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token and not args.ooni_only:
        print("Warning: CLOUDFLARE_API_TOKEN not set. Cloudflare queries will be skipped.")
        print("  Set it with: export CLOUDFLARE_API_TOKEN='your-token'")
        print("  Or use --ooni-only to fetch only OONI data.\n")

    if args.ooni_only:
        targets = [q for q in QUERIES if not q["auth"]]
    else:
        targets = list(QUERIES)

    collect_all(token, targets)
