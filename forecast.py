#!/usr/bin/env python3
"""
7 天走势预测 - 自动信号脚本

作用：
1. 抓取公开行情页面的近期文字，用方向词做倾向打分，写入 forecast.json 的 auto 段；
2. 记录最近核对时间 checkedAt，并计算人工判断已过去多少天；
3. 绝不修改人工判断（trend / changePct / advice / drivers / confidence）——
   自动打分只用于「核对」，与人工判断不一致时由页面提示谨慎参考。

设计原则：
- 抓取失败不写文件，保留上一次结果，绝不因为网络问题把判断改成中性；
- 没有稳定数据源的品类（不锈钢、塑料、玻璃、轮胎、电池等）auto 保持 null；
- auto 的置信度上限 0.6，页面上与人工判断分开显示。
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FORECAST_PATH = os.path.join(SCRIPT_DIR, 'forecast.json')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

# 每个大类的稳定行情页（优先取「最新」内容，不写死日期）
PAGES = {
    '废铜': [
        'https://m.mysteel.com/hot/424076.html',
        'https://www.mysteel.com/hot/1622551.html',
    ],
    '废铝': [
        'https://www.mysteel.com/hot/1622491.html',
        'https://www.mysteel.com/hot/1103476.html',
    ],
    '废铁': [
        'https://feigang.mysteel.com/',
        'https://www.mysteel.com/hot/1667594.html',
    ],
    '废纸': [
        'https://m.zgfeipin.cn/expo_10009_1/',
    ],
}

# 句子必须命中这些词，才算与该大类相关，避免把别的品种算进来
KEYWORDS = {
    '废铜': ['废铜', '铜价', '光亮铜', '黄杂铜', '铜厂'],
    '废铝': ['废铝', '铝价', '铝线', '生铝', '熟铝', '铝合金'],
    '废铁': ['废钢', '废铁', '重废', '钢厂', '铁水'],
    '废纸': ['废纸', '黄板纸', '国废', '纸厂', '废报纸', '书本纸'],
}

UP_WORDS = ['上涨', '上调', '提涨', '涨价', '反弹', '紧缺', '缺货', '去库',
            '库存下降', '库存减少', '惜售', '停机', '减产', '备货', '支撑', '看涨']
DOWN_WORDS = ['下跌', '下调', '跌价', '回落', '走弱', '累库', '库存增加',
              '过剩', '压价', '疲弱', '抛售', '看空', '亏损', '承压']


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        enc = r.headers.get('content-encoding', '').lower()
    if enc == 'gzip':
        import gzip
        raw = gzip.decompress(raw)
    elif enc == 'deflate':
        import zlib
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    for cs in ('utf-8', 'gbk', 'gb18030'):
        try:
            return raw.decode(cs)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'ignore')


def plain(html):
    html = re.sub(r'<script[\s\S]*?</script>', ' ', html, flags=re.I)
    html = re.sub(r'<style[\s\S]*?</style>', ' ', html, flags=re.I)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&')
    return re.sub(r'\s+', ' ', html)


def score_text(text, cat):
    keys = KEYWORDS.get(cat, [])
    sents = [s for s in re.split(r'[。！？;；]', text) if any(k in s for k in keys)]
    up = down = 0
    hits = []
    for s in sents:
        u = sum(s.count(w) for w in UP_WORDS)
        d = sum(s.count(w) for w in DOWN_WORDS)
        if u or d:
            up += u
            down += d
            if (u or d) and len(hits) < 3:
                hits.append(s.strip()[:70])
    total = up + down
    if total < 3:
        return None
    raw = (up - down) / max(1, total)
    trend = 'up' if raw > 0.2 else ('down' if raw < -0.2 else 'flat')
    conf = round(min(0.6, 0.3 + abs(raw) * 0.5), 2)
    return {'trend': trend, 'score': round(raw, 2), 'up': up, 'down': down,
            'sentences': len(sents), 'confidence': conf, 'samples': hits}


def main():
    if not os.path.exists(FORECAST_PATH):
        print('缺少 forecast.json，跳过')
        return 0
    with open(FORECAST_PATH, encoding='utf-8') as f:
        fc = json.load(f)

    now = datetime.now(timezone(timedelta(hours=8)))
    changed = False
    summary = []

    for cat, urls in PAGES.items():
        if cat not in fc.get('categories', {}):
            continue
        texts = []
        for u in urls:
            try:
                texts.append(plain(fetch(u)))
            except Exception as e:
                print('  抓取失败 %s %s: %s' % (cat, u, e))
        if not texts:
            print('  %s 全部源不可用，保留上次结果' % cat)
            summary.append('%s: 抓取失败' % cat)
            continue
        r = score_text(' '.join(texts), cat)
        if not r:
            print('  %s 样本不足（相关语句太少），保留上次结果' % cat)
            summary.append('%s: 样本不足' % cat)
            continue
        r['checkedAt'] = now.strftime('%Y-%m-%dT%H:%M:%S+08:00')
        old = fc['categories'][cat].get('auto') or {}
        if old.get('trend') != r['trend'] or old.get('up') != r['up'] or old.get('down') != r['down']:
            changed = True
        fc['categories'][cat]['auto'] = r
        summary.append('%s: %s(+%d/-%d)' % (cat, r['trend'], r['up'], r['down']))
        print('  %s → %s  上% d 下% d  相关句 %d' % (cat, r['trend'], r['up'], r['down'], r['sentences']))

    if not changed:
        print('自动信号无变化', '; '.join(summary))

    # 人工判断过期天数
    try:
        gen = datetime.strptime(fc['generatedAt'][:19], '%Y-%m-%dT%H:%M:%S')
        fc['staleDays'] = max(0, (now.replace(tzinfo=None) - gen).days)
    except Exception:
        fc['staleDays'] = 0

    # 同一天内且自动信号无变化时不写文件，避免每天多次无意义的提交；
    # 跨天则更新核对时间，页面能看到「今天核对过」
    today = now.strftime('%Y-%m-%d')
    old = fc.get('checkedAt', '')
    if not changed and old[:10] == today:
        print('今日已核对且信号无变化，不写入')
        return 0

    fc['checkedAt'] = now.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    with open(FORECAST_PATH, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('已更新 forecast.json：', '; '.join(summary) or '仅更新时间')
    return 0


if __name__ == '__main__':
    sys.exit(main())
