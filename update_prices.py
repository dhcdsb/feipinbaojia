#!/usr/bin/env python3
"""
废品回收报价自动更新脚本
用法：python update_prices.py
从行情网站抓取最新价格，更新 prices.json，并推送 commit
"""

import json
import re
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# 价格映射表：行情网站显示名称 → 我们的品类名
# 单位统一为 元/kg（抓到的 元/吨 会除以 1000）
# ============================================================

# 废铜映射
COPPER_MAP = {
    "1号光亮铜线": "1号光亮铜线",
    "1#光亮铜线": "1号光亮铜线",
    "光亮铜线": "1号光亮铜线",
    "紫铜": "紫铜",
    "马达铜": "铜米",      # 马达铜 ≈ 铜米
    "黄铜": "黄铜",
    "H62黄铜": "黄铜",
    "62黄铜边料": "黄铜",
    "铜管": "铜管",
    "紫铜管": "铜管",
    "铜排": "铜排",
    "杂铜": "杂铜",
    "H59黄杂铜": "杂铜",
    "铜屑": "铜屑",
    "紫杂铜": "铜屑",
}

# 废铝映射
ALUMINUM_MAP = {
    "铝线": "铝线",
    "割胶铝线": "铝线",
    "光亮铝线": "铝线",
    "熟铝": "熟铝",
    "生铝": "生铝",
    "大件生铝": "生铝",
    "小件生铝": "生铝",
    "铝合金": "铝合金",
    "铝板": "铝板",
    "1系废铝板料": "铝板",
    "铝型材": "铝型材",
    "型材白料": "铝型材",
    "铝箔": "铝箔",
    "铝屑": "铝屑",
    "6系铝屑": "铝屑",
    "易拉罐": "铝屑",
}

# 废铁映射
IRON_MAP = {
    "重废": "重废",
    "中废": "中废",
    "轻废": "轻废",
    "钢筋": "钢筋",
    "铸铁": "铸铁",
    "铁皮": "铁皮",
    "铁屑": "铁屑",
    "生铁": "生铁",
}

# 废不锈钢映射
STAINLESS_MAP = {
    "316不锈钢": "316不锈钢",
    "316": "316不锈钢",
    "304不锈钢": "304不锈钢",
    "304": "304不锈钢",
    "201不锈钢": "201不锈钢",
    "201": "201不锈钢",
    "不锈钢屑": "不锈钢屑",
    "杂不锈钢": "杂不锈钢",
}

# 大类映射
CATEGORY_MAPS = {
    "废铜": COPPER_MAP,
    "废铝": ALUMINUM_MAP,
    "废铁": IRON_MAP,
    "废不锈钢": STAINLESS_MAP,
}


def load_current_prices(path):
    """加载现有 prices.json"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"updatedAt": "", "categories": {}}


def save_prices(path, data):
    """保存 prices.json"""
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    data["updatedAt"] = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已保存 {path}")
    return data


def parse_price_text(text):
    """
    从行情文本中提取价格信息
    每行格式: 品类名 空格/冒号/等号 价格
    价格可以是单个数字或 数字-数字（取均价）
    返回: {品类名: 价格(元/kg)}
    """
    result = {}

    for line in text.split('\n'):
        line = line.strip()
        if not line or len(line) < 4:
            continue

        # 跳过纯标题行、表格头等
        if line.startswith('#') or line.startswith('-') or line.startswith('|') or line.startswith('>'):
            continue

        # 模式1: 名称 数字-数字（区间取均价）
        m = re.search(
            r'^(.+?)\s*[:：=＝]?\s*(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)',
            line
        )
        if m:
            name = m.group(1).strip().rstrip('：: =＝ ')
            # 名称必须包含中文
            if not re.search(r'[\u4e00-\u9fa5]', name):
                continue
            low = float(m.group(2))
            high = float(m.group(3))
            avg = round((low + high) / 2, 2)
            if avg >= 100:
                avg = round(avg / 1000, 2)
            if avg > 500:
                continue
            result[name] = avg
            continue

        # 模式2: 名称 单个数字（最后一段是数字）
        m = re.search(
            r'^(.+?)\s*[:：=＝]?\s*(\d+(?:\.\d+)?)\s*$',
            line
        )
        if m:
            name = m.group(1).strip().rstrip('：: =＝ ')
            if not re.search(r'[\u4e00-\u9fa5]', name):
                continue
            price = float(m.group(2))
            if price >= 100:
                price = round(price / 1000, 2)
            if price > 500 or price <= 0:
                continue
            result[name] = price

    return result


def apply_mapped_prices(prices, category, mapping, parsed):
    """将解析的价格映射到品类"""
    if category not in prices["categories"]:
        return 0

    updated = 0
    items = prices["categories"][category]

    for raw_name, price in parsed.items():
        # 直接匹配
        if raw_name in mapping:
            target = mapping[raw_name]
            if target in items:
                old = items[target]
                # 只有价格变化超过1%才更新
                if abs(price - old) / max(old, 0.01) > 0.01:
                    items[target] = price
                    updated += 1
                    print(f"  [UPD] {raw_name} → {target}: {old} → {price}")
            continue

        # 模糊匹配
        for key, target in mapping.items():
            if key in raw_name or raw_name in key:
                if target in items:
                    old = items[target]
                    if abs(price - old) / max(old, 0.01) > 0.01:
                        items[target] = price
                        updated += 1
                        print(f"  [UPD] {raw_name} ~> {target}: {old} → {price}")
                break

    return updated


def merge_prices(base, updates):
    """合并价格更新（深合并）"""
    for cat, items in updates.items():
        if cat not in base["categories"]:
            base["categories"][cat] = {}
        base["categories"][cat].update(items)
    return base


def main():
    # Fix Windows encoding
    import io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    script_dir = Path(__file__).parent
    prices_path = script_dir / "prices.json"

    print("=" * 50)
    print("废品回收报价自动更新")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 加载现有价格
    prices = load_current_prices(prices_path)

    # 这里从文件、stdin 或环境变量读取价格文本
    price_text = os.environ.get("PRICE_TEXT", "")
    if not price_text:
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            # 如果是文件路径，从文件读取
            if os.path.isfile(arg):
                with open(arg, 'r', encoding='utf-8') as f:
                    price_text = f.read()
                print(f"[DOC] 从文件读取: {arg}")
            else:
                price_text = " ".join(sys.argv[1:])
        elif not sys.stdin.isatty():
            # 从 stdin 读取（用 buffer 绕过编码问题）
            try:
                price_text = sys.stdin.buffer.read().decode('utf-8')
            except:
                price_text = sys.stdin.read()

    if not price_text:
        print("[ERR] 未提供价格数据。用法:")
        print("   python update_prices.py <行情文本>")
        print("   或设置 PRICE_TEXT 环境变量")
        print("   或通过管道传入: echo '...' | python update_prices.py")
        sys.exit(1)

    # 解析价格
    print(f"\n[DOC] 收到 {len(price_text)} 字符行情数据")
    parsed = parse_price_text(price_text)
    print(f"[SRCH] 解析到 {len(parsed)} 个价格条目:")
    for name, price in list(parsed.items())[:20]:
        print(f"   {name}: ¥{price}/kg")
    if len(parsed) > 20:
        print(f"   ... 共 {len(parsed)} 条")

    # 应用映射
    total_updated = 0
    for cat, mapping in CATEGORY_MAPS.items():
        updated = apply_mapped_prices(prices, cat, mapping, parsed)
        total_updated += updated

    print(f"\n[STAT] 共更新 {total_updated} 个品类价格")

    # 保存
    save_prices(prices_path, prices)

    return 0


if __name__ == "__main__":
    sys.exit(main())

