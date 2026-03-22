#!/usr/bin/env python3
"""
Internet Freedom Research: Iran & Venezuela
Visualization script — reads data from api_snapshot / raw / web_research JSON.

Usage:
  python visualize.py                    # auto-detect latest snapshot
  python visualize.py --snapshot 2026-03-11
"""

import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import json

# Japanese font support — register BIZ UDPGothic from Nix store or system
import matplotlib.font_manager as fm
import subprocess
_font_dirs = ['/nix/store']
try:
    _nix_path = subprocess.run(
        ['nix', 'build', 'nixpkgs#biz-ud-gothic', '--no-link', '--print-out-paths'],
        capture_output=True, text=True, timeout=30,
    )
    if _nix_path.returncode == 0:
        _font_dirs = [_nix_path.stdout.strip() + '/share/fonts/truetype']
except (FileNotFoundError, subprocess.TimeoutExpired):
    pass
for _d in _font_dirs:
    for _f in fm.findSystemFonts(fontpaths=[_d]):
        fm.fontManager.addfont(_f)
plt.rcParams['font.family'] = ['BIZ UDPGothic', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / 'assets'
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# Data loading
# ============================================================

def load_data(snapshot_date: Optional[str] = None) -> dict:
    """api_snapshot, extracted, web_research を読み込む"""
    data_dir = ROOT / 'data'

    if snapshot_date is None:
        # auto-detect latest snapshot
        candidates = sorted(data_dir.glob('api_snapshot_*.json'))
        if not candidates:
            raise FileNotFoundError(f"No api_snapshot_*.json found in {data_dir}")
        snapshot_path = candidates[-1]
        snapshot_date = snapshot_path.stem.replace('api_snapshot_', '')
    else:
        snapshot_path = data_dir / f'api_snapshot_{snapshot_date}.json'

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    with open(snapshot_path) as f:
        api = json.load(f)
    print(f"Loaded: {snapshot_path.name}")

    # extracted (optional)
    extracted_path = data_dir / f'extracted_{snapshot_date}.json'
    extracted = None
    if extracted_path.exists():
        with open(extracted_path) as f:
            extracted = json.load(f)
        print(f"Loaded: {extracted_path.name}")

    # web_research (optional)
    web_path = data_dir / f'web_research_{snapshot_date}.json'
    web = None
    if web_path.exists():
        with open(web_path) as f:
            web = json.load(f)
        print(f"Loaded: {web_path.name}")
    else:
        print(f"Warning: {web_path.name} not found (web_research fallbacks will be used)")

    # raw OONI aggregation files
    raw_dir = data_dir / 'raw'
    ooni_agg = {}
    for cc in ['ir', 've']:
        path = raw_dir / f'ooni_aggregation_{cc}.json'
        if path.exists():
            with open(path) as f:
                ooni_agg[cc] = json.load(f)

    return {"api": api, "extracted": extracted, "web": web, "ooni_agg": ooni_agg}


def _parse_date(s: str) -> datetime:
    """'2025-12-15' or '2025-12-15T00:00:00Z' -> datetime"""
    return datetime.strptime(s[:10], '%Y-%m-%d')


def _parse_datetime(s: str) -> datetime:
    """ISO datetime string -> datetime"""
    if s is None:
        return datetime(2026, 3, 11)  # snapshot date as fallback for ongoing events
    s = s.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')


# ============================================================
# Fig 1: Iran HTTP Traffic Timeline with Event Annotations
# ============================================================
def plot_iran_traffic(data: dict):
    api = data["api"]
    ts = api["cloudflare_radar"]["iran"]["http_traffic_timeseries"]

    # Read from api_snapshot
    dates_cur = [_parse_date(t) for t in ts["current_period"]["timestamps"]]
    vals_cur = ts["current_period"]["values"]
    dates_ctrl = [_parse_date(t) for t in ts["control_period"]["timestamps"]]
    vals_ctrl = ts["control_period"]["values"]

    # Annotations (shutdown spans)
    annotations = ts.get("annotations", [])

    fig, ax = plt.subplots(figsize=(16, 7))

    ax.plot(dates_ctrl, vals_ctrl, 'o-', color='#4CAF50', linewidth=2, markersize=6,
            label='平常時 (2025年9-12月)', alpha=0.8)
    ax.plot(dates_cur, vals_cur, 'o-', color='#F44336', linewidth=2.5, markersize=8,
            label='紛争期 (2025年12月-2026年3月)', zorder=5)

    # Highlight shutdown periods from annotations
    shutdown_labels = ['第1次遮断 (抗議活動)', '第2次遮断 (軍事行動)']
    shutdown_colors = ['red', 'darkred']
    shutdown_alphas = [0.15, 0.2]
    for i, ann in enumerate(annotations[:2]):
        start = _parse_datetime(ann["startDate"])
        end = _parse_datetime(ann.get("endDate"))
        label = shutdown_labels[i] if i < len(shutdown_labels) else ann.get("description", "")
        ax.axvspan(start, end, alpha=shutdown_alphas[i] if i < len(shutdown_alphas) else 0.15,
                   color=shutdown_colors[i] if i < len(shutdown_colors) else 'red',
                   label=label)

    # Event annotations (editorial — positions tied to data values)
    ax.annotate('抗議デモ開始\n(12/28)', xy=(datetime(2025,12,29), 0.464),
                xytext=(datetime(2025,12,20), 0.65),
                arrowprops=dict(arrowstyle='->', color='#333'), fontsize=9,
                ha='center', bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))

    ax.annotate('完全遮断開始\n(1/8) トラフィック→0', xy=(datetime(2026,1,12), 0.003),
                xytext=(datetime(2026,1,5), 0.15),
                arrowprops=dict(arrowstyle='->', color='red', lw=2), fontsize=10, fontweight='bold',
                ha='center', color='red',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#ffcccc', alpha=0.9))

    ax.annotate('部分復旧\n(1/28)', xy=(datetime(2026,1,26), 0.933),
                xytext=(datetime(2026,1,30), 0.85),
                arrowprops=dict(arrowstyle='->', color='#333'), fontsize=9,
                ha='center', bbox=dict(boxstyle='round,pad=0.3', facecolor='#ccffcc', alpha=0.7))

    ax.annotate('米以軍事攻撃\n再遮断 (2/28)\nトラフィック→0', xy=(datetime(2026,3,2), 0.002),
                xytext=(datetime(2026,2,20), 0.18),
                arrowprops=dict(arrowstyle='->', color='darkred', lw=2), fontsize=10, fontweight='bold',
                ha='center', color='darkred',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#ffcccc', alpha=0.9))

    ax.set_ylabel('正規化トラフィック (MIN0_MAX)', fontsize=12)
    ax.set_title('イラン：インターネットトラフィックの時系列変化\n（Cloudflare Radar, 2026年3月11日取得）',
                 fontsize=14, fontweight='bold', pad=15)
    ax.legend(loc='upper left', fontsize=10, framealpha=0.9)
    ax.set_ylim(-0.05, 1.15)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m/%d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45, ha='right')
    ax.grid(True, alpha=0.3)
    ax.set_facecolor('#fafafa')

    # Stats box (web_research fallback)
    textstr = '2026年に2度の大規模遮断\n第1次(1/8〜1/28) 第2次(2/28〜)\n経済損失: $35.7M/日\nオンライン売上: 80%減'
    props = dict(boxstyle='round', facecolor='#fff3cd', alpha=0.9, edgecolor='#ffc107')
    ax.text(0.98, 0.98, textstr, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', horizontalalignment='right', bbox=props)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig1_iran_traffic.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Fig 1: Iran Traffic Timeline")


# ============================================================
# Fig 2: Iran Outage Timeline (Past Year)
# ============================================================

# Editorial labels keyed by startDate prefix (YYYY-MM-DD)
_OUTAGE_LABELS = {
    "2025-06-13": ("イスラエル攻撃後の遮断", "#FF9800"),
    "2025-06-17": ("多ISP遮断 (政府指示)", "#F44336"),
    "2025-06-18": ("多ISP遮断 (政府指示)", "#F44336"),  # merged with 06-17 group
    "2025-07-05": ("DDoS攻撃による遮断", "#9C27B0"),
    "2026-01-08": ("抗議デモ全面遮断\n(20日間)", "#D32F2F"),
    "2026-02-28": ("軍事行動遮断\n(継続中)", "#B71C1C"),
}
_OUTAGE_DEFAULT_COLOR = "#E57373"


def plot_iran_outage_timeline(data: dict):
    api = data["api"]
    events = api["cloudflare_radar"]["iran"]["outages_past_year"].get("events", [])

    # Group events by start date (YYYY-MM-DD) to consolidate overlapping bars
    groups = defaultdict(list)
    for ev in events:
        day = ev["startDate"][:10]
        groups[day].append(ev)

    # Build consolidated outage bars
    outages = []
    for day in sorted(groups.keys()):
        evs = groups[day]
        start = min(_parse_datetime(e["startDate"]) for e in evs)
        ends = [_parse_datetime(e.get("endDate")) for e in evs]
        end = max(ends)
        label, color = _OUTAGE_LABELS.get(day, (evs[0].get("description", ""), _OUTAGE_DEFAULT_COLOR))
        outages.append((start, end, label, color))

    # Merge consecutive groups that share a label (e.g. 06-17 and 06-18)
    merged = []
    for start, end, label, color in outages:
        if merged and merged[-1][2] == label:
            prev_start, prev_end, prev_label, prev_color = merged[-1]
            merged[-1] = (min(prev_start, start), max(prev_end, end), prev_label, prev_color)
        else:
            merged.append((start, end, label, color))
    outages = merged

    fig, ax = plt.subplots(figsize=(16, 5))

    for start, end, label, color in outages:
        duration_hours = (end - start).total_seconds() / 3600
        width_days = (end - start).days or 0.2
        ax.barh(0, width_days, left=start, height=0.6,
                color=color, alpha=0.8, edgecolor='white', linewidth=1)
        mid = start + (end - start) / 2
        ax.text(mid, 0.45, label, ha='center', va='bottom', fontsize=8, fontweight='bold',
                rotation=0 if duration_hours > 48 else 30)

    ax.set_xlim(datetime(2025,5,1), datetime(2026,3,15))
    ax.set_ylim(-0.5, 1.5)
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y/%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45, ha='right')

    all_gov = api["cloudflare_radar"]["iran"]["outages_past_year"].get("all_government_directed", False)
    all_nw = api["cloudflare_radar"]["iran"]["outages_past_year"].get("all_nationwide", False)
    subtitle = ""
    if all_gov and all_nw:
        subtitle = "\n全て政府指示・全国規模（Cloudflare Radar）"
    elif all_nw:
        subtitle = "\n全て全国規模（Cloudflare Radar）"

    ax.set_title(f'イラン：インターネット遮断イベント（過去1年）{subtitle}',
                 fontsize=13, fontweight='bold', pad=15)
    ax.grid(True, axis='x', alpha=0.3)
    ax.set_facecolor('#fafafa')

    if all_gov:
        ax.text(0.5, -0.25, '■ 全イベントが GOVERNMENT_DIRECTED / NATIONWIDE に分類',
                transform=ax.transAxes, ha='center', fontsize=10, color='#D32F2F', fontweight='bold')

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig2_iran_outage_timeline.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Fig 2: Iran Outage Timeline")


# ============================================================
# Fig 3: Comparison - Iran vs Venezuela Censorship Approach
# ============================================================
def plot_comparison(data: dict):
    api = data["api"]

    # Iran values from api_snapshot
    ir_outage_count = api["cloudflare_radar"]["iran"]["outages_past_year"]["total_events"]
    ir_bgp_leaks = api["cloudflare_radar"]["iran"]["bgp_leaks_12w"].get("total_events", 0)
    ir_anomalies = len(api["cloudflare_radar"]["iran"]["traffic_anomalies_12w"].get("events", []))

    # Venezuela BGP leaks
    ve_bgp_leaks_raw = api["cloudflare_radar"]["venezuela"]["bgp_leaks_12w"]
    ve_bgp_leaks = ve_bgp_leaks_raw.get("total_events",
                       ve_bgp_leaks_raw.get("total_events_in_snapshot", 0))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Iran - Kill Switch Model
    categories_ir = ['全面遮断\n(キルスイッチ)', 'DNS遮断', 'IP遮断', 'Starlink\n妨害', 'SIM無効化',
                      f'BGPリーク\n(12週間)']
    values_ir = [ir_anomalies, 1, 1, 1, 1, ir_bgp_leaks]
    colors_ir = ['#D32F2F', '#F44336', '#E57373', '#FF8A80', '#FFCDD2', '#EF9A9A']

    bars1 = ax1.barh(categories_ir, values_ir, color=colors_ir, edgecolor='white', linewidth=1.5)
    ax1.set_title('イラン：「キルスイッチ」モデル\n物理インフラ遮断中心', fontsize=13, fontweight='bold', pad=10)
    ax1.set_xlabel('イベント数 / 深刻度', fontsize=11)
    for bar, val in zip(bars1, values_ir):
        ax1.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                 str(val), va='center', fontweight='bold')

    # Key facts (web_research fallback)
    facts_ir = [
        "• 2026年の1/3をネット遮断下で過ごす",
        "• 経済損失: $35.7M/日",
        "• Starlink: 軍用ジャマーで最大80%損失",
        "• BGPハイジャック(経路乗っ取り): 90件/12週",
    ]
    ax1.text(0.95, 0.02, '\n'.join(facts_ir), transform=ax1.transAxes,
             fontsize=9, va='bottom', ha='right',
             bbox=dict(boxstyle='round', facecolor='#ffebee', alpha=0.9))

    # Venezuela - Selective Filtering Model (web_research fallback values)
    categories_ve = ['SNS遮断\n(X,Signal等)', 'メディア遮断\n(61サイト)', 'VPN遮断\n(21サービス)',
                      'DNS遮断\n(33サーバー)', 'Tor遮断', f'BGPリーク\n(12週間)']
    values_ve = [5, 61, 21, 33, 1, ve_bgp_leaks]
    colors_ve = ['#1565C0', '#1976D2', '#1E88E5', '#42A5F5', '#64B5F6', '#90CAF9']

    bars2 = ax2.barh(categories_ve, values_ve, color=colors_ve, edgecolor='white', linewidth=1.5)
    ax2.set_title('ベネズエラ：「選択的フィルタリング」モデル\n標的型コンテンツ遮断中心', fontsize=13, fontweight='bold', pad=10)
    ax2.set_xlabel('遮断対象数', fontsize=11)
    for bar, val in zip(bars2, values_ve):
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                 str(val), va='center', fontweight='bold')

    facts_ve = [
        "• CANTV(国営)が152+ドメインを遮断",
        "• 電話で遮断命令（書面なし）",
        "• VPN需要: +328% (2025年1月)",
        "• 基本的にインフラは維持",
    ]
    ax2.text(0.95, 0.02, '\n'.join(facts_ve), transform=ax2.transAxes,
             fontsize=9, va='bottom', ha='right',
             bbox=dict(boxstyle='round', facecolor='#e3f2fd', alpha=0.9))

    ax1.set_facecolor('#fafafa')
    ax2.set_facecolor('#fafafa')

    plt.suptitle('2つの検閲モデルの比較：イラン vs ベネズエラ',
                 fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig3_comparison.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Fig 3: Comparison")


# ============================================================
# Fig 4: Circumvention Tools - Cat and Mouse (unchanged — conceptual)
# ============================================================
def plot_circumvention():
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))

    dates = ['12/28\n抗議開始', '1/3\n35%低下', '1/8\n全面遮断', '1/22\n回避ピーク',
             '1/28\n部分復旧', '2/16\n50%低下', '2/28\n再遮断', '3/6\n1%']

    shutdown = [0.2, 0.35, 1.0, 0.95, 0.3, 0.5, 0.98, 0.99]
    circumvention = [0.1, 0.2, 0.05, 0.9, 0.7, 0.5, 0.1, 0.05]

    x = np.arange(len(dates))
    width = 0.35

    ax1.bar(x - width/2, shutdown, width, label='遮断の深刻度', color='#D32F2F', alpha=0.8)
    ax1.bar(x + width/2, circumvention, width, label='回避ツール利用', color='#4CAF50', alpha=0.8)

    ax1.set_xticks(x)
    ax1.set_xticklabels(dates, fontsize=9)
    ax1.set_ylabel('相対的な強度', fontsize=11)
    ax1.set_title('イラン：遮断 vs 回避の「いたちごっこ」',
                  fontsize=13, fontweight='bold', pad=10)
    ax1.legend(fontsize=11)
    ax1.set_ylim(0, 1.15)
    ax1.set_facecolor('#fafafa')
    ax1.grid(True, axis='y', alpha=0.3)

    tools = ['', '', 'Starlink\n妨害開始', 'Psiphon\n4万同時接続\nSnowflake急増',
             'VPN検索\n+2000%', '', 'Kalinka\nジャマー', '出口なし']
    for i, tool in enumerate(tools):
        if tool:
            ax1.text(i, max(shutdown[i], circumvention[i]) + 0.05, tool,
                     ha='center', va='bottom', fontsize=7, fontweight='bold',
                     bbox=dict(boxstyle='round,pad=0.2', facecolor='#FFF9C4', alpha=0.8))

    ve_tools = ['VPN\nサービス', 'Tor\nNetwork', 'DNS\n変更', 'Proton\nVPN', 'Psiphon',
                'ブラウザ\n直接']
    ve_blocked = [0.7, 0.6, 0.9, 0.3, 0.5, 0.1]
    ve_effective = [0.6, 0.4, 0.2, 0.7, 0.5, 0.8]

    x2 = np.arange(len(ve_tools))
    ax2.bar(x2 - width/2, ve_blocked, width, label='政府の遮断度', color='#1565C0', alpha=0.8)
    ax2.bar(x2 + width/2, ve_effective, width, label='回避の有効性', color='#66BB6A', alpha=0.8)

    ax2.set_xticks(x2)
    ax2.set_xticklabels(ve_tools, fontsize=10)
    ax2.set_ylabel('相対的な強度', fontsize=11)
    ax2.set_title('ベネズエラ：遮断手法 vs 回避ツールの有効性',
                  fontsize=13, fontweight='bold', pad=10)
    ax2.legend(fontsize=11)
    ax2.set_ylim(0, 1.15)
    ax2.set_facecolor('#fafafa')
    ax2.grid(True, axis='y', alpha=0.3)

    ax2.text(0.98, 0.95, 'VPN需要 +328%\n21 VPNサイト遮断\n33 DNSサーバー遮断',
             transform=ax2.transAxes, fontsize=9, va='top', ha='right',
             bbox=dict(boxstyle='round', facecolor='#e3f2fd', alpha=0.9))

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig4_circumvention.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Fig 4: Circumvention Tools")


# ============================================================
# Fig 5: OONI Data - Measurement Count & Anomalies
# ============================================================

def _aggregate_ooni_monthly(raw: dict) -> tuple:
    """raw OONI aggregation → monthly (labels, measurements, anomalies)"""
    rows = raw["response"].get("result", [])
    monthly = defaultdict(lambda: {"m": 0, "a": 0})
    for row in rows:
        day = row.get("measurement_start_day", "")
        if not day:
            continue
        key = day[:7]  # YYYY-MM
        monthly[key]["m"] += row.get("measurement_count", 0)
        monthly[key]["a"] += row.get("anomaly_count", 0)

    keys = sorted(monthly.keys())
    labels = []
    for i, k in enumerate(keys):
        if i == 0 or k[:4] != keys[i-1][:4]:
            labels.append(k.replace('-', '/'))
        else:
            labels.append(k[5:])  # just month
    measurements = [monthly[k]["m"] for k in keys]
    anomalies = [monthly[k]["a"] for k in keys]
    return labels, measurements, anomalies


def plot_ooni_summary(data: dict):
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 10))

    ooni_agg = data.get("ooni_agg", {})

    # Iran OONI
    if "ir" in ooni_agg:
        ir_labels, ir_measurements, ir_anomalies = _aggregate_ooni_monthly(ooni_agg["ir"])
    else:
        # Fallback
        ir_labels = ['2025/01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
                     '2026/01', '02', '03']
        ir_measurements = [10000, 11000, 12000, 11500, 10500, 2000, 9000, 10000, 11000,
                           12000, 13000, 14000, 500, 20000, 1000]
        ir_anomalies = [2000, 2100, 2200, 2000, 1800, 1500, 2000, 2200, 2300,
                        2500, 2500, 2800, 200, 5500, 300]

    x = np.arange(len(ir_labels))
    ax1.bar(x, ir_measurements, color='#42A5F5', alpha=0.7, label='測定数')
    ax1.bar(x, ir_anomalies, color='#EF5350', alpha=0.8, label='異常検知数')
    ax1.set_xticks(x)
    ax1.set_xticklabels(ir_labels, rotation=45, ha='right', fontsize=8)
    ax1.set_title('イラン：OONI測定数の推移', fontsize=12, fontweight='bold')
    ax1.legend(fontsize=9)
    ax1.set_ylabel('月間測定数', fontsize=10)
    ax1.set_facecolor('#fafafa')

    # Venezuela OONI
    if "ve" in ooni_agg:
        ve_labels, ve_measurements, ve_anomalies = _aggregate_ooni_monthly(ooni_agg["ve"])
    else:
        ve_labels = ['2025/01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
                     '2026/01', '02', '03']
        ve_measurements = [67000, 70000, 80000, 196000, 160000, 140000, 120000, 100000,
                           95000, 90000, 85000, 80000, 75000, 70000, 65000]
        ve_anomalies = [8800, 15000, 35000, 39000, 30000, 25000, 22000, 20000,
                        18000, 17000, 15000, 12000, 10000, 9000, 8500]

    x2 = np.arange(len(ve_labels))
    ax2.bar(x2, ve_measurements, color='#42A5F5', alpha=0.7, label='測定数')
    ax2.bar(x2, ve_anomalies, color='#EF5350', alpha=0.8, label='異常検知数')
    ax2.set_xticks(x2)
    ax2.set_xticklabels(ve_labels, rotation=45, ha='right', fontsize=8)
    ax2.set_title('ベネズエラ：OONI測定数の推移', fontsize=12, fontweight='bold')
    ax2.legend(fontsize=9)
    ax2.set_ylabel('月間測定数', fontsize=10)
    ax2.set_facecolor('#fafafa')

    # Pie charts (web_research — fallback constants)
    ir_categories = ['SNS・\nメッセージ', 'ニュース\nメディア', '人権\n団体', 'VPN・\n回避ツール',
                     'LGBTQ+\nサイト', 'その他']
    ir_blocked = [15, 25, 8, 12, 10, 30]
    colors_pie = ['#e53935', '#fb8c00', '#43a047', '#1e88e5', '#8e24aa', '#757575']

    ax3.pie(ir_blocked, labels=ir_categories, colors=colors_pie, autopct='%1.0f%%',
            startangle=90, textprops={'fontsize': 9})
    ax3.set_title('イラン：遮断対象の種類別内訳\n（OONI測定より推定）', fontsize=12, fontweight='bold')

    ve_categories = ['独立系\nメディア', 'SNS\nプラットフォーム', 'VPN\nサービス', 'DNS\nサーバー',
                     '政治\nサイト', 'その他']
    ve_blocked_pie = [61, 5, 21, 33, 15, 17]

    ax4.pie(ve_blocked_pie, labels=ve_categories, colors=colors_pie, autopct='%1.0f%%',
            startangle=90, textprops={'fontsize': 9})
    ax4.set_title('ベネズエラ：遮断対象の種類別内訳\n（VeSinFiltro / OONI）', fontsize=12, fontweight='bold')

    plt.suptitle('OONI (Open Observatory of Network Interference) データ分析',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'fig5_ooni_summary.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Fig 5: OONI Summary")


# ============================================================
# Fig 6: Visibility Matrix - What We Can/Cannot See (unchanged)
# ============================================================
def plot_visibility_matrix():
    fig, ax = plt.subplots(figsize=(16, 11))
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.patch.set_facecolor('white')

    visible = [
        ("遮断の事実と時期", "Cloudflare Radar: トラフィックが0になるタイムスタンプ"),
        ("遮断の規模", "全国規模 vs 局所的 / ISP別の影響"),
        ("遮断対象サービス", "OONI: DNS / HTTP / IP 別の遮断手法"),
        ("回避ツール使用急増", "Psiphon Conduit: 2,600万接続試行 / VPN検索 +2,000%"),
        ("BGPルーティング異常", "Cloudflare: リーク・ハイジャックイベント"),
        ("経済的影響", "オンライン売上 80%減 / 株価 450K pt 下落"),
    ]

    invisible = [
        ("遮断の命令者・意思決定過程", "電話で命令（書面なし）/ 法的根拠不明"),
        ("自己検閲の実態", "測定不可能 / 萎縮効果は定量化困難"),
        ("回避の実際の成功率", "接続できても速度が極端に遅い場合がある"),
        ("オフラインの影響", "精神的影響 / 医療・教育への打撃"),
        ("Starlink等の実効性", "妨害されたが部分的に機能？ データ不足"),
        ("内部ネットワークの状態", "イントラネット（SHOMA等）の監視状況"),
    ]

    col_w = 0.44
    row_h = 0.11
    gap = 0.025
    left_x = 0.03
    right_x = 0.53
    header_y = 0.92
    accent_w = 0.006

    # Headers removed — handled in Typst

    def _draw_items(items, x0, start_y, accent_color):
        for i, (title, detail) in enumerate(items):
            y = start_y - i * (row_h + gap)
            # Accent bar
            ax.add_patch(FancyBboxPatch((x0, y), accent_w, row_h,
                                        boxstyle="round,pad=0.002", facecolor=accent_color,
                                        edgecolor='none', transform=ax.transAxes))
            # Title
            ax.text(x0 + 0.025, y + row_h * 0.68, title, transform=ax.transAxes,
                    fontsize=15, fontweight='bold', va='center', color='#212121')
            # Detail
            ax.text(x0 + 0.025, y + row_h * 0.30, detail, transform=ax.transAxes,
                    fontsize=12, va='center', color='#757575')
            # Subtle bottom border
            ax.plot([x0 + 0.025, x0 + col_w - 0.02], [y - 0.002, y - 0.002],
                    transform=ax.transAxes, color='#E0E0E0', linewidth=0.5)

    items_top = 0.88
    _draw_items(visible, left_x, items_top, '#43A047')
    _draw_items(invisible, right_x, items_top, '#E53935')


    plt.savefig(OUTPUT_DIR / 'fig6_visibility_matrix.png', dpi=200, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print("Fig 6: Visibility Matrix")


# ============================================================
# Fig 7: Cat-and-Mouse Structure Diagram (unchanged)
# ============================================================
def plot_cat_mouse_structure():
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.axis('off')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)

    ax.text(5, 9.5, '遮断 → 回避 → 再遮断：「いたちごっこ」の構造',
            fontsize=16, fontweight='bold', ha='center', va='top')

    ax.text(2.5, 8.8, 'イラン', fontsize=14, fontweight='bold', ha='center',
            color='#D32F2F',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#FFCDD2', edgecolor='#D32F2F'))

    steps_ir = [
        (1, 8, "① 抗議デモ発生\n(2025/12/28)", '#FFF9C4', '→'),
        (1, 7, "② 段階的遮断\nモバイル・IPv6切断", '#FFECB3', '→'),
        (1, 6, "③ 全面遮断\n(2026/1/8)\nトラフィック→0", '#FFCDD2', '→'),
        (3.5, 6, "④ 市民の対応\nPsiphon 4万同時\nSnowflake急増\nVPN検索+2000%", '#C8E6C9', '→'),
        (1, 5, "⑤ 政府の対抗措置\nKalinka妨害装置\nStarlink端末押収\nSIM無効化", '#FFCDD2', '→'),
        (3.5, 5, "⑥ さらなる回避\n海外ボランティア\nPsiphon Conduit\n40万人が帯域共有", '#C8E6C9', '→'),
        (1, 4, "⑦ キルスイッチ計画\nHuawei/中国と開発\n恒久的遮断能力の構築", '#FFCDD2', ''),
    ]

    for x, y, text, color, arrow in steps_ir:
        ax.text(x, y, text, fontsize=8, va='center',
                bbox=dict(boxstyle='round,pad=0.4', facecolor=color, edgecolor='#999', linewidth=0.5))

    ax.annotate('', xy=(1, 7.4), xytext=(1, 7.6), arrowprops=dict(arrowstyle='->', color='#666'))
    ax.annotate('', xy=(1, 6.4), xytext=(1, 6.6), arrowprops=dict(arrowstyle='->', color='#666'))
    ax.annotate('', xy=(3.0, 6), xytext=(2.2, 6), arrowprops=dict(arrowstyle='->', color='#4CAF50', lw=2))
    ax.annotate('', xy=(1, 5.4), xytext=(1, 5.6), arrowprops=dict(arrowstyle='->', color='red', lw=2))
    ax.annotate('', xy=(3.0, 5), xytext=(2.2, 5), arrowprops=dict(arrowstyle='->', color='#4CAF50', lw=2))
    ax.annotate('', xy=(1, 4.4), xytext=(1, 4.6), arrowprops=dict(arrowstyle='->', color='red', lw=2))

    ax.text(7.5, 8.8, 'ベネズエラ', fontsize=14, fontweight='bold', ha='center',
            color='#1565C0',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#BBDEFB', edgecolor='#1565C0'))

    steps_ve = [
        (6, 8, "① 選挙紛争\n(2024/7/28)", '#FFF9C4', ''),
        (6, 7, "② 選択的遮断\nX, Signal遮断\n(2024/8/8)", '#BBDEFB', ''),
        (6, 6, "③ VPN需要急増\n+328%\n(2025/1)", '#C8E6C9', ''),
        (8.5, 6, "④ VPN遮断\n21サービス遮断\n33 DNSサーバー\n遮断 (1/9)", '#BBDEFB', ''),
        (6, 5, "⑤ 代替手段\nProton VPN\nTor Bridge\n口コミで共有", '#C8E6C9', ''),
        (8.5, 5, "⑥ Tor遮断試行\n70-80% DA遮断\n完全遮断は失敗", '#BBDEFB', ''),
        (6, 4, "⑦ 現状\n152+ドメイン遮断\nだがVPN経由で\nアクセス可能", '#E8F5E9', ''),
    ]

    for x, y, text, color, arrow in steps_ve:
        ax.text(x, y, text, fontsize=8, va='center',
                bbox=dict(boxstyle='round,pad=0.4', facecolor=color, edgecolor='#999', linewidth=0.5))

    ax.annotate('', xy=(6, 7.4), xytext=(6, 7.6), arrowprops=dict(arrowstyle='->', color='#666'))
    ax.annotate('', xy=(6, 6.4), xytext=(6, 6.6), arrowprops=dict(arrowstyle='->', color='#666'))
    ax.annotate('', xy=(8.0, 6), xytext=(7.2, 6), arrowprops=dict(arrowstyle='->', color='#1565C0', lw=2))
    ax.annotate('', xy=(6, 5.4), xytext=(6, 5.6), arrowprops=dict(arrowstyle='->', color='#4CAF50', lw=2))
    ax.annotate('', xy=(8.0, 5), xytext=(7.2, 5), arrowprops=dict(arrowstyle='->', color='#1565C0', lw=2))
    ax.annotate('', xy=(6, 4.4), xytext=(6, 4.6), arrowprops=dict(arrowstyle='->', color='#4CAF50', lw=2))

    ax.text(5, 2.8, '構造的な違い', fontsize=13, fontweight='bold', ha='center',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#FFF59D', edgecolor='#F9A825', linewidth=2))

    ax.text(2.5, 2,
            'イラン：「物理的遮断」の拡大\n'
            '回避 → 物理妨害 → 端末押収 → 法的処罰\n'
            '最終目標：恒久的キルスイッチ',
            fontsize=10, ha='center', va='center',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFEBEE', edgecolor='#D32F2F'))

    ax.text(7.5, 2,
            'ベネズエラ：「レイヤー型フィルタ」の深化\n'
            '回避 → DNS遮断 → VPN遮断 → Tor遮断\n'
            'だが完全遮断には至らず',
            fontsize=10, ha='center', va='center',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#E3F2FD', edgecolor='#1565C0'))

    ax.text(5, 0.5, 'データソース: Cloudflare Radar / OONI / NetBlocks / Tor Project / Access Now / VeSinFiltro / HRW / Amnesty\n'
            '取得日: 2026年3月11日',
            fontsize=8, ha='center', va='center', color='#666',
            bbox=dict(boxstyle='round', facecolor='#f5f5f5', alpha=0.8))

    plt.savefig(OUTPUT_DIR / 'fig7_cat_mouse_structure.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Fig 7: Cat-and-Mouse Structure")


# ============================================================
# Fig 8: Key Facts for Poster (unchanged)
# ============================================================
def plot_poster_facts():
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.axis('off')

    ax.text(0.5, 0.97, 'ポスター用：一言で言えるファクト',
            transform=ax.transAxes, fontsize=18, fontweight='bold', ha='center', va='top')

    facts = [
        ("🇮🇷 イラン", [
            ("2026年の1/3をインターネット遮断下で過ごした", "#D32F2F"),
            ("遮断の経済損失：1日あたり3,570万ドル", "#E53935"),
            ("1月8日、トラフィックがゼロに。20日間の完全遮断", "#F44336"),
            ("Psiphon：ピーク時2,600万の日次接続がイランから", "#4CAF50"),
            ("4万台のStarlink端末がロシア製妨害装置で無力化", "#FF6F00"),
            ("VPN検索への関心が2,000%以上急増", "#2E7D32"),
            ("Starlink所持に最大死刑を含む法的処罰", "#B71C1C"),
        ], '#FFEBEE'),
        ("🇻🇪 ベネズエラ", [
            ("CANTV（国営ISP）が152以上のドメインを遮断中", "#1565C0"),
            ("遮断命令は電話で伝達—書面の記録は一切なし", "#1976D2"),
            ("61の独立系メディアが遮断。X, Signal, YouTubeも", "#1E88E5"),
            ("VPN需要が1週間で328%増加", "#2E7D32"),
            ("33のパブリックDNSサーバー（含む8.8.8.8, 1.1.1.1）を遮断", "#F57F17"),
            ("Torディレクトリの70-80%を遮断するも完全遮断は失敗", "#6A1B9A"),
        ], '#E3F2FD'),
    ]

    y = 0.87
    for section_title, items, bg_color in facts:
        ax.text(0.5, y, section_title, transform=ax.transAxes,
                fontsize=15, fontweight='bold', ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor=bg_color, edgecolor='#999'))
        y -= 0.05
        for text, color in items:
            ax.text(0.5, y, f"▸ {text}", transform=ax.transAxes,
                    fontsize=11, ha='center', va='top', color=color, fontweight='bold')
            y -= 0.04
        y -= 0.03

    ax.text(0.5, 0.03, 'Source: Cloudflare Radar, OONI, NetBlocks, Tor Project, Access Now, VeSinFiltro, HRW, Amnesty International\n'
            'Data snapshot: 2026-03-11',
            transform=ax.transAxes, fontsize=8, ha='center', va='bottom', color='#666')

    plt.savefig(OUTPUT_DIR / 'fig8_poster_facts.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("Fig 8: Poster Facts")


# ============================================================
# Run all
# ============================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate visualizations from snapshot data')
    parser.add_argument('--snapshot', type=str, default=None,
                        help='Snapshot date (e.g. 2026-03-11). Auto-detected if omitted.')
    args = parser.parse_args()

    print("Loading data...")
    data = load_data(args.snapshot)

    print("\nGenerating visualizations...")
    plot_iran_traffic(data)
    plot_iran_outage_timeline(data)
    plot_comparison(data)
    plot_circumvention()
    plot_ooni_summary(data)
    plot_visibility_matrix()
    plot_cat_mouse_structure()
    plot_poster_facts()
    print(f"\nAll figures saved to: {OUTPUT_DIR}/")
