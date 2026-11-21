#!/usr/bin/env python3
"""
从 Mysteel 子站首页的「今日价格」表抓废铜 / 废铝报价。

为什么用这几个页面：
- 首页 HTML 里就是一张表（品名 / 地区 / 价格 / 涨跌 / 日期），
  不需要登录、不需要执行 JS，也不需要绕验证码；
- robots.txt 只禁止 *.js / *.css / 图片和带 ? 参数的地址，首页本身允许抓；
- 表格自带「涨跌」，可以直接算出上一期价，让站内的涨跌列有真实依据，
  而不是靠"我们自己上次调价"来推断。

只取公开页面上的公开报价，不碰会员内容，也不做高频请求。

用法：
    python fetch_mysteel.py            # 抓取并写入 prices.json
    python fetch_mysteel.py --dry-run  # 只打印，不写文件
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

SCRIPT_DIR = Path(__file__).parent
PRICES_PATH = SCRIPT_DIR / "prices.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# 首页地址 -> 对应大类（只用于日志）
SITES = {
    "feitong": "https://feitong.mysteel.com/",   # 废铜
    "feilv": "https://feilv.mysteel.com/",       # 废铝
}

# (站点, 表中品名关键字, 我们的品类, 我们的品项)
# 词表偏保守：只映射含义明确、不会串味的品名。
MAP = [
    ("feitong", "光亮铜", "废铜", "1号光亮铜线"),
    ("feilv", "光亮铝线", "废铝", "铝线"),
    ("feilv", "型材白料", "废铝", "铝型材"),
]

# 元/kg 合理区间，越界视为解析错误
RANGES = {
    "废铜": (20.0, 120.0),
    "废铝": (8.0, 35.0),
}
# 与站内现价偏差超过这个比例就跳过，避免把解析错的数字写进线上
MAX_DRIFT = 0.10
# 只要最近几天内的报价（首页偶尔残留几个月前的旧行）
FRESH_DAYS = 5


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def parse_today_price(html):
    """解析首页「今日价格」表，返回 [{name, region, price, change, date}]。"""
    i = html.find("today-price")
    if i < 0:
        return []
    seg = html[max(0, i - 200):i + 20000]
    rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", seg)
    out = []
    for r in rows:
        tds = re.findall(r"<td[^>]*>([\s\S]*?)</td>", r)
        if len(tds) < 4:
            continue
        cells = [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").strip() for x in tds]
        price_s = cells[2].replace(",", "")
        if not re.fullmatch(r"\d{4,6}(\.\d+)?", price_s):
            continue
        chg_s = cells[3].replace(",", "").replace("+", "").strip()
        try:
            change = float(chg_s) if chg_s not in ("", "-", "--") else 0.0
        except ValueError:
            change = None
        out.append({
            "name": cells[0],
            "region": cells[1],
            "price": float(price_s),
            "change": change,
            "date": cells[4] if len(cells) > 4 else "",
        })
    return out


def is_fresh(date_s, today, days=FRESH_DAYS):
    """'11-20' 这种 MM-DD，判断是不是最近 days 天内。"""
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", (date_s or "").strip())
    if not m:
        return False
    mo, dd = int(m.group(1)), int(m.group(2))
    for year in (today.year, today.year - 1):
        try:
            d = datetime(year, mo, dd).date()
        except ValueError:
            continue
        gap = (today - d).days
        if 0 <= gap <= days:
            return True
    return False


def load_prices():
    if PRICES_PATH.exists():
        with open(PRICES_PATH, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {"updatedAt": "", "categories": {}}


def main():
    dry = "--dry-run" in sys.argv
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz).date()
    data = load_prices()
    cats = data.get("categories") or {}
    prev = dict(data.get("prev") or {})

    fetched = {}
    for key, url in SITES.items():
        try:
            html = fetch(url)
            rows = parse_today_price(html)
            fetched[key] = rows
            print(f"[OK] {key}: {len(rows)} 行 ({url})")
        except Exception as e:
            fetched[key] = []
            print(f"[WARN] {key} 抓取失败: {e}")

    changed = 0
    for site, kw, cat, item in MAP:
        rows = [r for r in fetched.get(site, []) if kw in r["name"] and is_fresh(r["date"], today)]
        if not rows:
            print(f"[SKIP] {cat}/{item}: 没有近期报价")
            continue
        prices = [r["price"] for r in rows]
        base = round(median(prices) / 1000, 2)
        lo, hi = RANGES.get(cat, (0.0, 9999.0))
        if not (lo <= base <= hi):
            print(f"[SKIP] {cat}/{item}: {base} 超出合理区间 {lo}~{hi}")
            continue
        old = (cats.get(cat) or {}).get(item)
        if isinstance(old, (int, float)) and old > 0 and abs(base - old) / old > MAX_DRIFT:
            print(f"[SKIP] {cat}/{item}: {old} -> {base} 偏差 {(base-old)/old*100:+.1f}% 超过阈值")
            continue

        # 上一期价 = 现价 - 涨跌。用各地区的中位数，避免单个地区异常值带偏。
        bases = [r["price"] - (r["change"] or 0) for r in rows]
        prev_kg = round(median(bases) / 1000, 2)
        if prev_kg <= 0:
            prev_kg = base

        regions = "、".join(sorted({r["region"] for r in rows}))
        pct = (base - prev_kg) / prev_kg * 100 if prev_kg else 0
        print(f"[MAP] {cat}/{item}: {old} -> {base}  (上次 {prev_kg}, {pct:+.1f}%, {len(rows)} 地区: {regions})")

        if cats.get(cat) is None:
            cats[cat] = {}
        cats[cat][item] = base
        prev.setdefault(cat, {})[item] = prev_kg
        changed += 1

    if not changed:
        print("[INFO] 没有可写入的项目")
        return 0

    data["categories"] = cats
    data["prev"] = prev
    if data.get("prevNote"):
        pass
    else:
        data["prevNote"] = "prev 记录本站上一次的报价，价格变动时由更新脚本写入。"
    data["updatedAt"] = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")

    if dry:
        print("[DRY] 不写文件")
        return 0

    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[OK] 已更新 {changed} 项 -> {PRICES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
