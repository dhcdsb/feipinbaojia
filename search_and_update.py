#!/usr/bin/env python3
"""
废品回收价格 - 自动更新脚本
从我的钢铁网获取废铜/废铝价格，更新 prices.json 并推送 Git
"""
import urllib.request
import re
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PRICES_PATH = SCRIPT_DIR / "prices.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 数据源：品类、目标品名、关键词、价格范围(元/吨)
SOURCES = [
    {"category": "废铜", "target": "1号光亮铜线", "keyword": "光亮铜", "range": (50000, 120000)},
    {"category": "废铜", "target": "黄铜",       "keyword": "黄杂铜", "range": (30000, 80000)},
    {"category": "废铝", "target": "铝线",       "keyword": "废铝",   "range": (10000, 30000)},
]

# 价格合理区间（元/kg）
PRICE_RANGES = {
    "废铜": (50, 110),
    "废铝": (10, 30),
}

MAX_CHANGE = 0.20  # 最大允许波动 20%

TABLE_URL = "https://m.mysteel.com/hot/424076.html"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [WARN] {e}")
        return ""


def extract_table_prices(html):
    """从价格表格中提取所有品名的价格（元/吨）"""
    # 表格格式：品名 品位 最低价 最高价 中间价
    # 如：光亮铜 Cu：98% 91100 91300 91200
    results = {}
    # 去HTML标签
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&[a-z]+;', '', text)
    text = re.sub(r'\s+', ' ', text)

    # 匹配：中文品名 + 可选品位 + 3个数字
    for m in re.finditer(r'([\u4e00-\u9fa5A-Za-z0-9]+)\s+(?:Cu[：:]\s*[\d.%-]+\s+)?(\d{4,6})\s+(\d{4,6})\s+(\d{4,6})', text):
        name = m.group(1).strip()
        low, high, mid = int(m.group(2)), int(m.group(3)), int(m.group(4))
        results[name] = {"low": low, "high": high, "mid": mid}

    return results


def load_prices():
    if PRICES_PATH.exists():
        with open(PRICES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updatedAt": "", "categories": {}}


def save_prices(data):
    tz = timezone(timedelta(hours=8))
    data["updatedAt"] = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存 {PRICES_PATH}")


def git_push(n):
    try:
        subprocess.run(["git", "-C", str(SCRIPT_DIR), "add", "prices.json"],
                       check=True, capture_output=True, timeout=10)
        msg = f"[auto] 价格更新 {datetime.now().strftime('%m-%d %H:%M')} ({n}项)"
        subprocess.run(["git", "-C", str(SCRIPT_DIR), "commit", "-m", msg],
                       check=True, capture_output=True, timeout=10)
        subprocess.run(["git", "-C", str(SCRIPT_DIR), "push"],
                       capture_output=True, timeout=30)
        print(f"[OK] Git: {msg}")
    except Exception as e:
        print(f"[WARN] Git: {e}")


def main():
    print("=" * 50)
    print("废品回收价格 - 自动更新（我的钢铁网）")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    html = fetch(TABLE_URL)
    if not html:
        print("[ERR] 获取页面失败")
        return 1

    table = extract_table_prices(html)
    print(f"\n[TABLE] 从表格提取到 {len(table)} 个品名:")
    for name, v in table.items():
        print(f"  {name}: {v['low']}-{v['high']} (中间价 {v['mid']})")

    prices = load_prices()
    updated = 0

    for src in SOURCES:
        cat, target, keyword = src["category"], src["target"], src["keyword"]
        lo, hi = src["range"]
        print(f"\n[SRCH] {cat} -> {target} (关键词: {keyword})")

        # 从表格中查找匹配的品名
        price_per_ton = None
        for name, v in table.items():
            if keyword in name:
                price_per_ton = v["mid"]
                print(f"  [MATCH] {name} -> 中间价 {price_per_ton} 元/吨")
                break

        if price_per_ton is None:
            print("  [WARN] 表格中未找到")
            continue

        if not (lo <= price_per_ton <= hi):
            print(f"  [SKIP] {price_per_ton} 不在范围 {lo}-{hi}")
            continue

        price_per_kg = round(price_per_ton / 1000, 2)
        print(f"  [OK] {price_per_kg}/kg")

        if cat in PRICE_RANGES:
            plo, phi = PRICE_RANGES[cat]
            if not (plo <= price_per_kg <= phi):
                print(f"  [SKIP] 不在合理区间 ({plo}-{phi})")
                continue

        if cat in prices.get("categories", {}):
            items = prices["categories"][cat]
            if target in items:
                old = items[target]
                if old > 0 and abs(price_per_kg - old) / old > MAX_CHANGE:
                    print(f"  [SKIP] {old} -> {price_per_kg} 波动过大")
                    continue
                if abs(price_per_kg - old) / max(old, 0.01) > 0.005:
                    items[target] = price_per_kg
                    updated += 1
                    print(f"  [UPD] {target}: {old} -> {price_per_kg}")
                else:
                    print(f"  [SKIP] 变化太小")

    print(f"\n[STAT] 共更新 {updated} 个品类")
    if updated > 0:
        save_prices(prices)
        git_push(updated)
    else:
        print("[INFO] 无需更新")
    return 0


if __name__ == "__main__":
    exit(main())
