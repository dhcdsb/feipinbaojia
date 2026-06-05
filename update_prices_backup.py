#!/usr/bin/env python3
"""
搴熷搧鍥炴敹鎶ヤ环鑷姩鏇存柊鑴氭湰
鐢ㄦ硶锛歱ython update_prices.py temp_prices.txt
浠庤鎯呮枃鏈В鏋愪环鏍硷紝鏇存柊 prices.json锛屽苟鎺ㄩ€?Git
"""

import json
import re
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# 浠锋牸鏄犲皠琛細琛屾儏缃戠珯鏄剧ず鍚嶇О 鈫?鎴戜滑鐨勫搧绫诲悕
# ============================================================

COPPER_MAP = {
    "1鍙峰厜浜摐绾?: "1鍙峰厜浜摐绾?, "1#鍏変寒閾滅嚎": "1鍙峰厜浜摐绾?, "鍏変寒閾滅嚎": "1鍙峰厜浜摐绾?,
    "绱摐": "绱摐", "椹揪閾?: "閾滅背", "閫氳绾块摐绫?: "閾滅背",
    "榛勯摐": "榛勯摐", "H62榛勯摐": "榛勯摐", "62榛勯摐杈规枡": "榛勯摐", "65榛勯摐杈规枡": "榛勯摐",
    "閾滅": "閾滅", "绱摐绠?: "閾滅",
    "閾滄帓": "閾滄帓", "纾烽摐杈规枡": "閾滄帓",
    "鏉傞摐": "鏉傞摐", "H59榛勬潅閾?: "鏉傞摐",
    "閾滃睉": "閾滃睉", "绱潅閾?: "閾滃睉", "鐮寸绱摐": "绱摐",
}

ALUMINUM_MAP = {
    "閾濈嚎": "閾濈嚎", "鍓茶兌閾濈嚎": "閾濈嚎", "鍏変寒閾濈嚎": "閾濈嚎",
    "鐔熼摑": "鐔熼摑",
    "鐢熼摑": "鐢熼摑", "澶т欢鐢熼摑": "鐢熼摑", "灏忎欢鐢熼摑": "鐢熼摑", "鏈虹敓閾?: "鐢熼摑",
    "閾濆悎閲?: "閾濆悎閲?, "閾濆悎閲戦棬绐?: "閾濆悎閲?,
    "閾濇澘": "閾濇澘", "1绯诲簾閾濇澘鏂?: "閾濇澘",
    "閾濆瀷鏉?: "閾濆瀷鏉?, "鍨嬫潗鐧芥枡": "閾濆瀷鏉?, "鍨嬫潗搴熼摑": "閾濆瀷鏉?,
    "閾濈當": "閾濈當",
    "閾濆睉": "閾濆睉", "6绯婚摑灞?: "閾濆睉", "鏄撴媺缃?: "閾濆睉",
}

IRON_MAP = {
    "閲嶅簾": "閲嶅簾", "涓簾": "涓簾", "杞诲簾": "杞诲簾",
    "閽㈢瓔": "閽㈢瓔", "閾搁搧": "閾搁搧", "閾佺毊": "閾佺毊", "閾佸睉": "閾佸睉", "鐢熼搧": "鐢熼搧",
}

STAINLESS_MAP = {
    "316涓嶉攬閽?: "316涓嶉攬閽?, "316鍥炵倝鏂?: "316涓嶉攬閽?, "316鍥炵倝杈规枡": "316涓嶉攬閽?,
    "304涓嶉攬閽?: "304涓嶉攬閽?, "304鍥炵倝鏂?: "304涓嶉攬閽?, "304鍥炵倝杈规枡": "304涓嶉攬閽?, "304杈规枡": "304涓嶉攬閽?,
    "201涓嶉攬閽?: "201涓嶉攬閽?, "201鍥炵倝鏂?: "201涓嶉攬閽?,
    "涓嶉攬閽㈠睉": "涓嶉攬閽㈠睉",
    "鏉備笉閿堥挗": "鏉備笉閿堥挗", "430鍥炵倝鏂?: "鏉備笉閿堥挗",
}

PAPER_MAP = {
    "A4绾?: "A4绾?, "A4鎵撳嵃绾?: "A4绾?, "鎵撳嵃绾?: "A4绾?,
    "鎶ョ焊": "鎶ョ焊", "搴熸姤绾?: "鎶ョ焊",
    "绾哥": "绾哥", "绾告澘": "绾哥", "榛勭焊鏉?: "绾哥", "鐡︽绾?: "绾哥",
    "涔︽湰绾?: "涔︽湰绾?, "涔︽湰": "涔︽湰绾?, "搴熶功鏈?: "涔︽湰绾?,
    "鑺辩焊": "鑺辩焊",
    "鏉傜焊": "鏉傜焊", "搴熺焊": "鏉傜焊",
    "鐧界焊": "A4绾?, "閾滅増绾?: "A4绾?,
}

PLASTIC_MAP = {
    "ABS": "ABS", "ABS濉戞枡": "ABS", "ABS鑳跺ご": "ABS",
    "PP": "PP", "PP濉戞枡": "PP", "PP鑳跺ご": "PP",
    "PE": "PE", "PE濉戞枡": "PE", "HDPE": "PE", "LDPE": "PE",
    "PVC": "PVC", "PVC濉戞枡": "PVC",
    "PET": "PET", "PET濉戞枡": "PET", "PET鐡剁墖": "PET",
    "鏉傚鏂?: "鏉傚鏂?,
    "PC": "ABS", "灏奸緳": "PE",
}

GLASS_MAP = {
    "閽㈠寲鐜荤拑": "閽㈠寲鐜荤拑",
    "骞虫澘鐜荤拑": "骞虫澘鐜荤拑", "娴硶鐜荤拑": "骞虫澘鐜荤拑",
    "纰庣幓鐠?: "纰庣幓鐠?, "鐜荤拑纰庣墖": "纰庣幓鐠?,
    "鐜荤拑鐡?: "鐜荤拑鐡?, "閰掔摱": "鐜荤拑鐡?,
}

TIRE_MAP = {
    "宸ョ▼鑳?: "宸ョ▼鑳?, "宸ョ▼杞儙": "宸ョ▼鑳?, "澶у瀷杞儙": "宸ョ▼鑳?,
    "閽笣鑳?: "閽笣鑳?, "閽笣杞儙": "閽笣鑳?,
    "灏奸緳鑳?: "灏奸緳鑳?, "灏奸緳杞儙": "灏奸緳鑳?,
    "鑷杞﹁儙": "鑷杞﹁儙", "鑷杞﹁疆鑳?: "鑷杞﹁儙",
}

BATTERY_MAP = {
    "闀嶆阿鐢垫睜": "闀嶆阿鐢垫睜",
    "閿傜數姹?: "閿傜數姹?, "涓夊厓閿傜數姹?: "閿傜數姹?, "纾烽吀閾侀攤鐢垫睜": "閿傜數姹?,
    "閾呴吀鐢垫睜": "閾呴吀鐢垫睜", "閾呰搫鐢垫睜": "閾呴吀鐢垫睜", "搴熸棫閾呴吀鐢垫睜": "閾呴吀鐢垫睜",
    "骞茬數姹?: "骞茬數姹?, "纰辨€х數姹?: "骞茬數姹?,
}

OTHER_MAP = {
    "搴熺數瀛愭澘": "搴熺數瀛愭澘", "鐢靛瓙鏉?: "搴熺數瀛愭澘", "鐢佃矾鏉?: "搴熺數瀛愭澘", "绾胯矾鏉?: "搴熺數瀛愭澘", "PCB鏉?: "搴熺數瀛愭澘",
    "搴熺數鏈?: "搴熺數鏈?, "鐢垫満": "搴熺數鏈?, "椹揪": "搴熺數鏈?,
    "搴熺數绾?: "搴熺數绾?, "鐢电嚎": "搴熺數绾?, "鐢电紗": "搴熺數绾?,
    "搴熷鐢?: "搴熷鐢?, "瀹剁數": "搴熷鐢?, "鏃у鐢?: "搴熷鐢?,
    "鏉傛枡": "鏉傛枡",
}

CATEGORY_MAPS = {
    "搴熼摐": COPPER_MAP, "搴熼摑": ALUMINUM_MAP,
    "搴熼搧": IRON_MAP, "搴熶笉閿堥挗": STAINLESS_MAP,
    "搴熺焊": PAPER_MAP, "搴熷鏂?: PLASTIC_MAP,
    "搴熺幓鐠?: GLASS_MAP, "搴熻疆鑳?: TIRE_MAP,
    "搴熺數姹?: BATTERY_MAP, "鍏朵粬": OTHER_MAP,
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
    print(f"[OK] 宸蹭繚瀛?{path}")
    return data


# 浠锋牸鍚堢悊鍖洪棿锛堝厓/kg锛?
PRICE_RANGES = {
    "搴熼摐": (30, 100),
    "搴熼摑": (10, 30),
    "搴熼搧": (1, 5),
    "搴熶笉閿堥挗": (3, 25),
    "搴熺焊": (0.5, 3),
    "搴熷鏂?: (1, 10),
    "搴熺幓鐠?: (0.1, 1),
    "搴熻疆鑳?: (0.5, 3),
    "搴熺數姹?: (5, 30),
    "鍏朵粬": (1, 30),
}

def is_price_in_range(price, category):
    """妫€鏌ヤ环鏍兼槸鍚﹀湪鍚堢悊鍖洪棿"""
    if category in PRICE_RANGES:
        min_price, max_price = PRICE_RANGES[category]
        return min_price <= price <= max_price
    return True  # 鏈煡鍝佺被涓嶆鏌?

def parse_price_text(text):
    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line or len(line) < 4:
            continue
        if line.startswith('#') or line.startswith('-') or line.startswith('|') or line.startswith('>'):
            continue

        # 妯″紡1: 鍚嶇О 鏁板瓧-鏁板瓧锛堝尯闂村彇鍧囦环锛?
        m = re.search(
            r'^(.+?)\s*[:锛?锛漖?\s*(\d+(?:\.\d+)?)\s*[-~鍒拌嚦]\s*(\d+(?:\.\d+)?)',
            line
        )
        if m:
            name = m.group(1).strip().rstrip('锛? =锛?')
            if not re.search(r'[\u4e00-\u9fa5]', name):
                continue
            low, high = float(m.group(2)), float(m.group(3))
            avg = round((low + high) / 2, 2)
            if avg >= 100: avg = round(avg / 1000, 2)
            if avg > 500: continue
            result[name] = avg
            continue

        # 妯″紡2: 鍚嶇О 鍗曚釜鏁板瓧
        m = re.search(r'^(.+?)\s*[:锛?锛漖?\s*(\d+(?:\.\d+)?)\s*$', line)
        if m:
            name = m.group(1).strip().rstrip('锛? =锛?')
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
        # 妫€鏌ヤ环鏍兼槸鍚﹀湪鍚堢悊鍖洪棿
        if not is_price_in_range(price, category):
            print(f"  [SKIP] {raw_name}: {price}/kg 涓嶅湪 {category} 鍚堢悊鍖洪棿鍐?)
            continue
        
        if raw_name in mapping:
            target = mapping[raw_name]
            if target in items:
                old = items[target]
                if abs(price - old) / max(old, 0.01) > 0.005:
                    items[target] = price
                    updated += 1
                    print(f"  [UPD] {raw_name} -> {target}: {old} -> {price}")
            continue
        for key, target in mapping.items():
            if key in raw_name or raw_name in key:
                if target in items:
                    old = items[target]
                    if abs(price - old) / max(old, 0.01) > 0.005:
                        items[target] = price
                        updated += 1
                        print(f"  [UPD] {raw_name} ~> {target}: {old} -> {price}")
                break
    return updated


def git_push(script_dir, total_updated):
    """鎻愪氦骞舵帹閫?prices.json 鍒?GitHub"""
    repo_dir = str(script_dir)
    try:
        subprocess.run(["git", "-C", repo_dir, "add", "prices.json"],
                       check=True, capture_output=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        print("[WARN] git add 澶辫触")
        return

    commit_msg = f"[auto] 浠锋牸鏇存柊 {datetime.now().strftime('%m-%d %H:%M')} ({total_updated}椤?"
    try:
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", commit_msg],
                       check=True, capture_output=True, timeout=10)
    except subprocess.CalledProcessError:
        # 鍙兘娌℃湁鍙樺寲
        print("[INFO] git commit: 鏃犲彉鍖栨垨宸叉彁浜?)
        return

    # 灏濊瘯 push
    for push_cmd in [["git", "-C", repo_dir, "push"],
                     ["git", "-C", repo_dir, "push", "--set-upstream", "origin", "main"]]:
        try:
            r = subprocess.run(push_cmd, capture_output=True, timeout=30)
            if r.returncode == 0:
                print(f"[OK] 宸叉帹閫佸埌 GitHub: {commit_msg}")
                return
        except (subprocess.TimeoutExpired, FileNotFoundError):
            break

    print("[WARN] Git push 澶辫触锛岃鎵嬪姩鎺ㄩ€?)


def main():
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    script_dir = Path(__file__).parent
    prices_path = script_dir / "prices.json"

    print("=" * 50)
    print("搴熷搧鍥炴敹鎶ヤ环鑷姩鏇存柊")
    print(f"鏃堕棿: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    prices = load_current_prices(prices_path)

    price_text = os.environ.get("PRICE_TEXT", "")
    if not price_text:
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if os.path.isfile(arg):
                with open(arg, 'r', encoding='utf-8') as f:
                    price_text = f.read()
                print(f"[DOC] 浠庢枃浠惰鍙? {arg}")
            else:
                price_text = " ".join(sys.argv[1:])
        elif not sys.stdin.isatty():
            try:
                price_text = sys.stdin.buffer.read().decode('utf-8')
            except:
                price_text = sys.stdin.read()

    if not price_text:
        print("[ERR] 鏈彁渚涗环鏍兼暟鎹?)
        sys.exit(1)

    print(f"\n[DOC] 鏀跺埌 {len(price_text)} 瀛楃琛屾儏鏁版嵁")
    parsed = parse_price_text(price_text)
    print(f"[SRCH] 瑙ｆ瀽鍒?{len(parsed)} 涓环鏍兼潯鐩?")
    for name, price in list(parsed.items())[:20]:
        print(f"   {name}: {price}/kg")
    if len(parsed) > 20:
        print(f"   ... 鍏?{len(parsed)} 鏉?)

    total_updated = 0
    for cat, mapping in CATEGORY_MAPS.items():
        updated = apply_mapped_prices(prices, cat, mapping, parsed)
        total_updated += updated

    print(f"\n[STAT] 鍏辨洿鏂?{total_updated} 涓搧绫讳环鏍?)
    save_prices(prices_path, prices)

    if total_updated > 0:
        print("\n--- Git Push ---")
        git_push(script_dir, total_updated)

    return 0


if __name__ == "__main__":
    sys.exit(main())

