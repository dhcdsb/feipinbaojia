#!/usr/bin/env python3
"""
废品回收报价自动更新脚本
用法：python update_prices.py temp_prices.txt
从行情文本解析价格，更新 prices.json，并推送 Git
"""

import json
import re
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# 价格映射表：行情网站显示名称 → 我们的品类名
# ============================================================

COPPER_MAP = {
    "1号光亮铜线": "1号光亮铜线", "1#光亮铜线": "1号光亮铜线", "光亮铜线": "1号光亮铜线",
    "紫铜": "紫铜", "马达铜": "铜米", "通讯线铜米": "铜米",
    "黄铜": "黄铜", "H62黄铜": "黄铜", "62黄铜边料": "黄铜", "65黄铜边料": "黄铜",
    "铜管": "铜管", "紫铜管": "铜管",
    "铜排": "铜排", "磷铜边料": "铜排",
    "杂铜": "杂铜", "H59黄杂铜": "杂铜",
    "铜屑": "铜屑", "紫杂铜": "铜屑", "破碎紫铜": "紫铜",
}

ALUMINUM_MAP = {
    "铝线": "铝线", "割胶铝线": "铝线", "光亮铝线": "铝线",
    "熟铝": "熟铝",
    "生铝": "生铝", "大件生铝": "生铝", "小件生铝": "生铝", "机生铝": "生铝",
    "铝合金": "铝合金", "铝合金门窗": "铝合金",
    "铝板": "铝板", "1系废铝板料": "铝板",
    "铝型材": "铝型材", "型材白料": "铝型材", "型材废铝": "铝型材",
    "铝箔": "铝箔",
    "铝屑": "铝屑", "6系铝屑": "铝屑", "易拉罐": "铝屑",
}

IRON_MAP = {
    "重废": "重废", "中废": "中废", "轻废": "轻废",
    "钢筋": "钢筋", "铸铁": "铸铁", "铁皮": "铁皮", "铁屑": "铁屑", "生铁": "生铁",
}

STAINLESS_MAP = {
    "316不锈钢": "316不锈钢", "316回炉料": "316不锈钢", "316回炉边料": "316不锈钢",
    "304不锈钢": "304不锈钢", "304回炉料": "304不锈钢", "304回炉边料": "304不锈钢", "304边料": "304不锈钢",
    "201不锈钢": "201不锈钢", "201回炉料": "201不锈钢",
    "不锈钢屑": "不锈钢屑",
    "杂不锈钢": "杂不锈钢", "430回炉料": "杂不锈钢",
}

CATEGORY_MAPS = {
    "废铜": COPPER_MAP, "废铝": ALUMINUM_MAP,
    "废铁": IRON_MAP, "废不锈钢": STAINLESS_MAP,
}


def load_current_prices(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"updatedAt": "", "categories": {}}


def save_prices(path, data):
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    data["updatedAt"] = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存 {path}")
    return data


def parse_price_text(text):
    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line or len(line) < 4:
            continue
        if line.startswith('#') or line.startswith('-') or line.startswith('|') or line.startswith('>'):
            continue

        # 模式1: 名称 数字-数字（区间取均价）
        m = re.search(
            r'^(.+?)\s*[:：=＝]?\s*(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)',
            line
        )
        if m:
            name = m.group(1).strip().rstrip('：: =＝ ')
            if not re.search(r'[\u4e00-\u9fa5]', name):
                continue
            low, high = float(m.group(2)), float(m.group(3))
            avg = round((low + high) / 2, 2)
            if avg >= 100: avg = round(avg / 1000, 2)
            if avg > 500: continue
            result[name] = avg
            continue

        # 模式2: 名称 单个数字
        m = re.search(r'^(.+?)\s*[:：=＝]?\s*(\d+(?:\.\d+)?)\s*$', line)
        if m:
            name = m.group(1).strip().rstrip('：: =＝ ')
            if not re.search(r'[\u4e00-\u9fa5]', name):
                continue
            price = float(m.group(2))
            if price >= 100: price = round(price / 1000, 2)
            if price > 500 or price <= 0: continue
            result[name] = price

    return result


def apply_mapped_prices(prices, category, mapping, parsed):
    if category not in prices["categories"]:
        return 0
    updated = 0
    items = prices["categories"][category]
    for raw_name, price in parsed.items():
        if raw_name in mapping:
            target = mapping[raw_name]
            if target in items:
                old = items[target]
                if abs(price - old) / max(old, 0.01) > 0.01:
                    items[target] = price
                    updated += 1
                    print(f"  [UPD] {raw_name} -> {target}: {old} -> {price}")
            continue
        for key, target in mapping.items():
            if key in raw_name or raw_name in key:
                if target in items:
                    old = items[target]
                    if abs(price - old) / max(old, 0.01) > 0.01:
                        items[target] = price
                        updated += 1
                        print(f"  [UPD] {raw_name} ~> {target}: {old} -> {price}")
                break
    return updated


def git_push(script_dir, total_updated):
    """提交并推送 prices.json 到 GitHub"""
    repo_dir = str(script_dir)
    try:
        subprocess.run(["git", "-C", repo_dir, "add", "prices.json"],
                       check=True, capture_output=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        print("[WARN] git add 失败")
        return

    commit_msg = f"[auto] 价格更新 {datetime.now().strftime('%m-%d %H:%M')} ({total_updated}项)"
    try:
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", commit_msg],
                       check=True, capture_output=True, timeout=10)
    except subprocess.CalledProcessError:
        # 可能没有变化
        print("[INFO] git commit: 无变化或已提交")
        return

    # 尝试 push
    for push_cmd in [["git", "-C", repo_dir, "push"],
                     ["git", "-C", repo_dir, "push", "--set-upstream", "origin", "main"]]:
        try:
            r = subprocess.run(push_cmd, capture_output=True, timeout=30)
            if r.returncode == 0:
                print(f"[OK] 已推送到 GitHub: {commit_msg}")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError):
            break

    print("[WARN] Git push 失败，请手动推送")


def main():
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    script_dir = Path(__file__).parent
    prices_path = script_dir / "prices.json"

    print("=" * 50)
    print("废品回收报价自动更新")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    prices = load_current_prices(prices_path)

    price_text = os.environ.get("PRICE_TEXT", "")
    if not price_text:
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if os.path.isfile(arg):
                with open(arg, 'r', encoding='utf-8') as f:
                    price_text = f.read()
                print(f"[DOC] 从文件读取: {arg}")
            else:
                price_text = " ".join(sys.argv[1:])
        elif not sys.stdin.isatty():
            try:
                price_text = sys.stdin.buffer.read().decode('utf-8')
            except:
                price_text = sys.stdin.read()

    if not price_text:
        print("[ERR] 未提供价格数据")
        sys.exit(1)

    print(f"\n[DOC] 收到 {len(price_text)} 字符行情数据")
    parsed = parse_price_text(price_text)
    print(f"[SRCH] 解析到 {len(parsed)} 个价格条目:")
    for name, price in list(parsed.items())[:20]:
        print(f"   {name}: {price}/kg")
    if len(parsed) > 20:
        print(f"   ... 共 {len(parsed)} 条")

    total_updated = 0
    for cat, mapping in CATEGORY_MAPS.items():
        updated = apply_mapped_prices(prices, cat, mapping, parsed)
        total_updated += updated

    print(f"\n[STAT] 共更新 {total_updated} 个品类价格")
    save_prices(prices_path, prices)

    if total_updated > 0:
        print("\n--- Git Push ---")
        git_push(script_dir, total_updated)

    return 0


if __name__ == "__main__":
    sys.exit(main())
