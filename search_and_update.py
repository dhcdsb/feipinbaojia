#!/usr/bin/env python3
"""
废品回收价格 - 自动更新脚本
从多个数据源获取废品价格，更新 prices.json 并推送 Git

数据源：
1. 我的钢铁网 (Mysteel) - 废铜价格
2. 上海有色网 (SMM) - 废铜、废铝、废不锈钢价格
"""
import urllib.request
import re
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PRICES_PATH = SCRIPT_DIR / "prices.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 数据源：品类、目标品名、关键词、价格范围(元/吨)
SOURCES = [
    # 我的钢铁网数据源
    {"category": "废铜", "target": "1号光亮铜线", "keyword": "光亮铜", "range": (50000, 120000)},
    {"category": "废铜", "target": "黄铜",       "keyword": "黄杂铜", "range": (30000, 80000)},
    # 关键词必须具体到品名：原来写"废铝"会把任意含废铝字样的行（甚至标题行）
    # 的中间价当成铝线价写进 prices.json，与下面 SMM 的铝线条目互相覆盖。
    {"category": "废铝", "target": "铝线",       "keyword": "铝线",   "range": (10000, 30000)},
    
    # SMM数据源 - 废铝
    {"category": "废铝", "target": "铝线",       "keyword": "割胶铝线", "range": (18000, 25000), "source": "smm_aluminum"},
    {"category": "废铝", "target": "熟铝",       "keyword": "熟铝",   "range": (15000, 25000), "source": "smm_aluminum"},
    {"category": "废铝", "target": "生铝",       "keyword": "生铝",   "range": (12000, 22000), "source": "smm_aluminum"},
    {"category": "废铝", "target": "铝合金",     "keyword": "铝合金", "range": (12000, 22000), "source": "smm_aluminum"},
    {"category": "废铝", "target": "铝板",       "keyword": "铝板",   "range": (15000, 25000), "source": "smm_aluminum"},
    {"category": "废铝", "target": "铝型材",     "keyword": "铝型材", "range": (15000, 25000), "source": "smm_aluminum"},
    
    # SMM数据源 - 废不锈钢
    {"category": "废不锈钢", "target": "304不锈钢", "keyword": "304废不锈钢边料", "range": (8000, 15000), "source": "smm_stainless"},
    {"category": "废不锈钢", "target": "316不锈钢", "keyword": "316废不锈钢回炉料", "range": (18000, 25000), "source": "smm_stainless"},
    {"category": "废不锈钢", "target": "201不锈钢", "keyword": "201废不锈钢回炉料", "range": (3000, 8000), "source": "smm_stainless"},
]

# SMM数据源URL
SMM_URLS = {
    "smm_aluminum": "https://hq.smm.cn/h5/scrap-aluminum-price-chart",
    "smm_stainless": "https://hq.smm.cn/h5/scrap-stainless-steel-price",
}

MAX_CHANGE = 1.00  # 最大允许波动 100%
WARN_CHANGE = 0.20  # 超过 20% 打印警告

TABLE_URL = "https://m.mysteel.com/hot/424076.html"

# 价格合理区间（元/kg）
PRICE_RANGES = {
    "废铜": (50, 110),
    "废铝": (10, 30),
    "废不锈钢": (3, 25),
}


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Encoding": "gzip, deflate",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            content_encoding = r.headers.get('content-encoding', '').lower()

            # 按响应头解压（站点可能返回 gzip 或 deflate）
            try:
                if 'gzip' in content_encoding:
                    import gzip
                    raw = gzip.decompress(raw)
                elif 'deflate' in content_encoding:
                    import zlib
                    try:
                        raw = zlib.decompress(raw)
                    except zlib.error:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            except Exception as e:
                print(f"  [WARN] 解压失败，尝试按原始字节解析: {e}")

            # Try different encodings
            for encoding in ['utf-8', 'gb2312', 'gbk', 'gb18030']:
                try:
                    text = raw.decode(encoding)
                    # Check if we got valid Chinese characters
                    if '价格' in text or '废铜' in text or '废铝' in text:
                        return text
                except UnicodeDecodeError:
                    continue

            # Fallback
            return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [WARN] {type(e).__name__}: {e}")
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


def extract_smm_prices(html):
    """从SMM页面提取价格数据（元/吨）"""
    # SMM格式：名称价格范围均价涨跌单位日期
    # 如：上海废铜价格89900 - 9000089950-700元/吨2026-06-11
    # 注意：SMM页面使用markdown格式链接 [名称](url)
    results = {}
    
    # 去HTML标签
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&[a-z]+;', '', text)
    # 去除markdown链接格式，保留链接文本
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 去除URL中的数字（避免干扰价格解析）
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'\s+', ' ', text)
    
    # 匹配：中文名称 + 数字范围 + 均价 + 涨跌 + 元/吨 + 日期
    # 格式1：上海废铜价格 89900 - 90000 89950 -700 元/吨 2026-06-11 (有空格)
    # 格式2：上海废铜价格89900 - 9000089950-700元/吨2026-06-11 (无空格)
    # 尝试两种格式
    
    # 格式1：有空格
    pattern1 = r'([\u4e00-\u9fa5A-Za-z0-9]+价格[\u4e00-\u9fa5A-Za-z0-9]*?)\s+(\d{5})\s*-\s*(\d{5})\s+(\d{5})\s+([+-]?\d+)\s+元/吨\s+(\d{4}-\d{2}-\d{2})'
    # 格式2：无空格
    pattern2 = r'([\u4e00-\u9fa5A-Za-z0-9]+价格[\u4e00-\u9fa5A-Za-z0-9]*?)\s*(\d{5})\s*-\s*(\d{5})(\d{5})([+-]?\d+)\s*元/吨\s*(\d{4}-\d{2}-\d{2})'
    
    for pattern in [pattern1, pattern2]:
        for m in re.finditer(pattern, text):
            name = m.group(1).strip()
            low = int(m.group(2))
            high = int(m.group(3))
            mid = int(m.group(4))
            change = int(m.group(5))
            date = m.group(6)
            
            results[name] = {
                "low": low,
                "high": high,
                "mid": mid,
                "change": change,
                "date": date
            }
    
    return results


def load_prices():
    if PRICES_PATH.exists():
        with open(PRICES_PATH, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {"updatedAt": "", "categories": {}}


def save_prices(data):
    tz = timezone(timedelta(hours=8))
    # 写盘前对比旧文件，把"变动前的价"记进 prev，页面才有涨跌可看。
    # 没变的项沿用原来的 prev（不能覆盖成当前价，否则涨跌会被抹平）。
    old = load_prices()
    old_cats = old.get("categories") or {}
    prev = dict(old.get("prev") or {})
    changed = 0
    for cat, items in (data.get("categories") or {}).items():
        for item, price in items.items():
            o = (old_cats.get(cat) or {}).get(item)
            try:
                o = float(o); p = float(price)
            except (TypeError, ValueError):
                continue
            if abs(o - p) < 1e-9:
                continue
            prev.setdefault(cat, {})[item] = round(o, 2)
            changed += 1
    if prev:
        data["prev"] = prev
    if old.get("prevNote"):
        data["prevNote"] = old["prevNote"]
    data["updatedAt"] = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    if changed:
        print(f"[PREV] {changed} 项变动前的价已记入 prev")
    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存 {PRICES_PATH}")


def git_push(n):
    # GitHub Actions 里由 workflow 统一提交，脚本自带 push 需跳过，
    # 否则会与 workflow 的提交冲突（detached HEAD / 重复 commit）。
    if os.environ.get("SKIP_GIT_PUSH") == "1":
        print("[INFO] SKIP_GIT_PUSH=1，跳过脚本内 git push（交给 CI 提交）")
        return
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

    # 存储SMM数据
    smm_data = {}
    
    # 获取SMM数据
    for source_key, url in SMM_URLS.items():
        print(f"\n[SMM] 获取 {source_key} 数据...")
        smm_html = fetch(url)
        if not smm_html:
            print(f"  [WARN] 获取失败（网络或反爬）")
            continue
        # SMM 对未登录用户用 lock 图标遮住价格，静态抓取拿不到数字。
        # 明确提示，避免误以为脚本解析逻辑坏了。
        if 'lock.png' in smm_html or 'user.smm.cn/login' in smm_html:
            print(f"  [WARN] 该源价格被登录墙锁定（需登录 SMM 账号），已跳过")
            continue
        smm_prices = extract_smm_prices(smm_html)
        smm_data[source_key] = smm_prices
        print(f"  [OK] 提取到 {len(smm_prices)} 条数据")
        for name, v in smm_prices.items():
            print(f"    {name}: {v['low']}-{v['high']} (均价 {v['mid']})")

    for src in SOURCES:
        cat, target, keyword = src["category"], src["target"], src["keyword"]
        lo, hi = src["range"]
        source = src.get("source", "mysteel")
        print(f"\n[SRCH] {cat} -> {target} (关键词: {keyword}, 来源: {source})")

        price_per_ton = None
        
        if source == "mysteel":
            # 从我的钢铁网表格中查找匹配的品名
            for name, v in table.items():
                if keyword in name:
                    price_per_ton = v["mid"]
                    print(f"  [MATCH] {name} -> 中间价 {price_per_ton} 元/吨")
                    break
        else:
            # 从SMM数据中查找匹配的品名
            if source in smm_data:
                for name, v in smm_data[source].items():
                    if keyword in name:
                        price_per_ton = v["mid"]
                        print(f"  [MATCH] {name} -> 均价 {price_per_ton} 元/吨")
                        break

        if price_per_ton is None:
            print("  [WARN] 未找到匹配数据")
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
                change_pct = abs(price_per_kg - old) / max(old, 0.01)
                if old > 0 and change_pct > MAX_CHANGE:
                    print(f"  [SKIP] {old} -> {price_per_kg} 波动过大 ({change_pct*100:.1f}%)")
                    continue
                if change_pct > WARN_CHANGE:
                    print(f"  [WARN] {old} -> {price_per_kg} 波动较大 ({change_pct*100:.1f}%)，仍然更新")
                if change_pct > 0.005:
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
