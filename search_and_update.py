#!/usr/bin/env python3
"""
废品回收价格 - 自动更新脚本
从百度搜索获取批发价/市场价，更新 prices.json
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

# 数据源配置：我的钢铁网（m.mysteel.com）
SOURCES = [
    {
        "category": "废铜",
        "target": "1号光亮铜线",
        "url": "https://m.mysteel.com/hot/424076.html",
        "extract": "mysteel_scrap_copper",
        "reliable": True,
    },
    {
        "category": "废铝",
        "target": "铝线",
        "url": "https://m.mysteel.com/hot/424077.html",
        "extract": "mysteel_scrap_aluminum",
        "reliable": True,
    },
    {
        "category": "废铁",
        "target": "重废",
        "url": "https://m.mysteel.com/hot/424078.html",
        "extract": "mysteel_scrap_steel",
        "reliable": True,
    },
    {
        "category": "废不锈钢",
        "target": "304不锈钢",
        "url": "https://m.mysteel.com/hot/424079.html",
        "extract": "mysteel_scrap_stainless",
        "reliable": True,
    },
]

# 价格合理区间（元/kg）- 批发价/市场价
PRICE_RANGES = {
    "废铜": (80, 100),      # 批发价：80-100元/kg（光亮铜92元/kg，黄铜53元/kg）
    "废铝": (15, 25),       # 批发价：15-25元/kg
    "废铁": (2, 4),         # 批发价：2-4元/kg
    "废不锈钢": (8, 15),    # 批发价：8-15元/kg
    "废电池": (10, 30),     # 锂电池：10-30元/kg
    "废电线": (15, 35),     # 废电线：15-35元/kg
}

# 最大允许价格波动（20%）
MAX_PRICE_CHANGE = 0.20

def fetch_url(url):
    """获取网页内容"""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [WARN] 获取失败: {url} -> {e}")
        return ""

def search_baidu(query):
    """百度搜索"""
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.baidu.com/s?wd={encoded_query}"
    return fetch_url(url)

def extract_price_from_source(source):
    """从数据源提取价格（数字匹配）"""
    html = fetch_url(source["url"])
    if not html:
        return None
    
    # 去HTML标签，保留数字和分隔符
    text = re.sub(r'<[^>]+>', '|', html)
    text = re.sub(r'&[a-z]+;', '', text)
    
    # 提取所有价格数字（元/吨，范围10000-200000）
    prices = []
    for m in re.finditer(r'(\d{4,6})', text):
        price = int(m.group(1))
        if 50000 <= price <= 120000:  # 废铜价格范围
            prices.append(price)
    
    if not prices:
        return None
    
    # 根据 extract 类型选择价格
    extract_type = source.get("extract", "mysteel_scrap_copper")
    
    if extract_type.startswith("mysteel_"):
        # mysteel 数据：取第一个价格（通常是最低价）
        raw_price = prices[0]
    else:
        # 其他数据源：取第一个价格
        raw_price = prices[0]
    
    # 转为元/kg
    price = round(raw_price / 1000, 2)
    return price

def is_price_in_range(price, category):
    """检查价格是否在合理区间"""
    if category in PRICE_RANGES:
        min_price, max_price = PRICE_RANGES[category]
        return min_price <= price <= max_price
    return True

def update_prices_from_sources(prices):
    """从数据源更新价格"""
    updated = 0
    
    for source in SOURCES:
        category = source["category"]
        target = source["target"]
        reliable = source.get("reliable", False)
        print(f"\n[SRCH] {category} -> {target} - {source['url']}")
        price = extract_price_from_source(source)
        
        if price is None:
            print(f"  [WARN] 未提取到价格")
            continue
        
        print(f"  [OK] 提取到价格: {price}/kg")
        
        # 检查价格是否在合理区间
        if not is_price_in_range(price, category):
            print(f"  [SKIP] {price}/kg 不在 {category} 合理区间内 ({PRICE_RANGES[category]})")
            continue
        
        # 更新价格
        if category in prices.get("categories", {}):
            items = prices["categories"][category]
            if target in items:
                old = items[target]
                # 可靠数据源允许更大波动（50%）
                max_change = 0.50 if reliable else MAX_PRICE_CHANGE
                if old > 0 and abs(price - old) / old > max_change:
                    print(f"  [SKIP] {old} -> {price} 波动超过{max_change*100}%")
                    continue
                if abs(price - old) / max(old, 0.01) > 0.005:
                    items[target] = price
                    updated += 1
                    print(f"  [UPD] {target}: {old} -> {price}")
                else:
                    print(f"  [SKIP] {old} -> {price} 变化太小")
            else:
                print(f"  [SKIP] {target} 不在 {category} 品类中")
    
    return updated

def load_prices():
    """加载价格数据"""
    if PRICES_PATH.exists():
        with open(PRICES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updatedAt": "", "categories": {}}

def save_prices(data):
    """保存价格数据"""
    from datetime import timezone, timedelta
    tz = timezone(timedelta(hours=8))
    data["updatedAt"] = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存 {PRICES_PATH}")

def git_push(total_updated):
    """提交并推送 prices.json 到 GitHub"""
    try:
        subprocess.run(["git", "-C", str(SCRIPT_DIR), "add", "prices.json"],
                       check=True, capture_output=True, timeout=10)
        msg = f"[auto] 价格更新 {datetime.now().strftime('%m-%d %H:%M')} ({total_updated}项)"
        subprocess.run(["git", "-C", str(SCRIPT_DIR), "commit", "-m", msg],
                       check=True, capture_output=True, timeout=10)
        subprocess.run(["git", "-C", str(SCRIPT_DIR), "push"],
                       capture_output=True, timeout=30)
        print(f"[OK] Git: {msg}")
    except Exception as e:
        print(f"[WARN] Git: {e}")

def main():
    print("=" * 50)
    print("废品回收价格 - 自动更新（我的钢铁网批发价）")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    prices = load_prices()
    total = update_prices_from_sources(prices)
    
    print(f"\n[STAT] 共更新 {total} 个品类")
    
    if total > 0:
        save_prices(prices)
        git_push(total)
    else:
        print("[INFO] 无需更新")
    
    return 0

if __name__ == "__main__":
    exit(main())
