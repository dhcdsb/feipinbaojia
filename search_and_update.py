#!/usr/bin/env python3
"""
废品回收价格 - 搜索+更新一体化脚本
用 urllib 从 Bing 搜索最新价格，解析后更新 prices.json
"""
import urllib.request
import urllib.parse
import re
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PRICES_PATH = SCRIPT_DIR / "prices.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

KEYWORDS = [
    "废铜回收价格 元/吨 2026",
    "废铝回收价格 元/吨 2026",
    "废铁废钢回收价格 元/吨 2026",
    "废不锈钢回收价格 元/吨 2026",
    "废铜价格行情 今日",
    "废铝价格行情 今日",
]

COPPER_MAP = {
    "1号光亮铜线": "1号光亮铜线", "光亮铜线": "1号光亮铜线",
    "紫铜": "紫铜", "马达铜": "铜米", "铜米": "铜米",
    "黄铜": "黄铜", "H62黄铜": "黄铜",
    "铜管": "铜管", "紫铜管": "铜管",
    "铜排": "铜排", "杂铜": "杂铜", "铜屑": "铜屑",
}
ALUMINUM_MAP = {
    "铝线": "铝线", "光亮铝线": "铝线",
    "熟铝": "熟铝", "生铝": "生铝", "机生铝": "生铝",
    "铝合金": "铝合金", "铝合金门窗": "铝合金",
    "铝板": "铝板", "铝型材": "铝型材", "铝箔": "铝箔", "铝屑": "铝屑",
}
IRON_MAP = {
    "重废": "重废", "中废": "中废", "轻废": "轻废",
    "钢筋": "钢筋", "铸铁": "铸铁", "铁皮": "铁皮", "铁屑": "铁屑", "生铁": "生铁",
}
STAINLESS_MAP = {
    "316不锈钢": "316不锈钢", "304不锈钢": "304不锈钢",
    "201不锈钢": "201不锈钢", "不锈钢屑": "不锈钢屑", "杂不锈钢": "杂不锈钢",
}
CATEGORY_MAPS = {
    "废铜": COPPER_MAP, "废铝": ALUMINUM_MAP,
    "废铁": IRON_MAP, "废不锈钢": STAINLESS_MAP,
}


def bing_search(query):
    encoded = urllib.parse.quote(query)
    url = f"https://www.bing.com/search?q={encoded}&setlang=zh-CN"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [WARN] 搜索失败: {query} -> {e}")
        return ""


def extract_prices(html):
    """从HTML中提取中文价格信息"""
    # 去HTML标签
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    results = {}
    # 匹配：品类名 + 数字-数字（区间）
    for m in re.finditer(r'([\u4e00-\u9fa5]{2,8})\s*(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)', text):
        name, low, high = m.group(1), float(m.group(2)), float(m.group(3))
        avg = round((low + high) / 2, 2)
        if 100 <= avg <= 200000:  # 元/吨范围
            results[name] = round(avg / 1000, 4)  # 转元/kg
        elif 0.1 <= avg <= 200:  # 已经是元/kg
            results[name] = avg

    # 匹配：品类名 + 单个数字
    for m in re.finditer(r'([\u4e00-\u9fa5]{2,8})\s*(\d+(?:\.\d+)?)\s*元/吨', text):
        name, price = m.group(1), float(m.group(2))
        if 100 <= price <= 200000:
            results[name] = round(price / 1000, 4)

    return results


def apply_prices(prices, category, mapping, parsed):
    if category not in prices.get("categories", {}):
        return 0
    updated = 0
    items = prices["categories"][category]
    for raw_name, price in parsed.items():
        for key, target in mapping.items():
            if key in raw_name or raw_name in key:
                if target in items and price > 0:
                    old = items[target]
                    if abs(price - old) / max(old, 0.01) > 0.01:
                        items[target] = price
                        updated += 1
                        print(f"  [UPD] {raw_name} -> {target}: {old} -> {price}")
                break
    return updated


def load_prices():
    if PRICES_PATH.exists():
        with open(PRICES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updatedAt": "", "categories": {}}


def save_prices(data):
    from datetime import timezone, timedelta
    tz = timezone(timedelta(hours=8))
    data["updatedAt"] = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存 {PRICES_PATH}")


def main():
    print("=" * 50)
    print("废品回收价格 - 搜索+更新")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    prices = load_prices()
    all_parsed = {}

    for kw in KEYWORDS:
        print(f"\n[SRCH] {kw}")
        html = bing_search(kw)
        if not html:
            continue
        parsed = extract_prices(html)
        print(f"  提取到 {len(parsed)} 个价格")
        all_parsed.update(parsed)

    if not all_parsed:
        print("\n[ERR] 未搜到任何价格数据")
        return 1

    print(f"\n[STAT] 共搜到 {len(all_parsed)} 个品类:")
    for name, price in list(all_parsed.items())[:15]:
        print(f"   {name}: {price}/kg")

    total = 0
    for cat, mapping in CATEGORY_MAPS.items():
        total += apply_prices(prices, cat, mapping, all_parsed)

    print(f"\n[STAT] 共更新 {total} 个品类")
    save_prices(prices)

    if total > 0:
        # Git push
        try:
            subprocess.run(["git", "-C", str(SCRIPT_DIR), "add", "prices.json"],
                           check=True, capture_output=True, timeout=10)
            msg = f"[auto] 价格更新 {datetime.now().strftime('%m-%d %H:%M')} ({total}项)"
            subprocess.run(["git", "-C", str(SCRIPT_DIR), "commit", "-m", msg],
                           check=True, capture_output=True, timeout=10)
            subprocess.run(["git", "-C", str(SCRIPT_DIR), "push"],
                           capture_output=True, timeout=30)
            print(f"[OK] Git: {msg}")
        except Exception as e:
            print(f"[WARN] Git: {e}")

    return 0


if __name__ == "__main__":
    exit(main())
