#!/usr/bin/env python3
"""
app.py の非API関数を全パステスト（Streamlit・API呼び出しなし）
"""

import json
import re
import tempfile
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# テスト対象の関数をインライン定義（app.py からコピー）
# Streamlit を一切起動しないために独立して定義する
# ─────────────────────────────────────────────

_PRICE_INPUT        = 3.00  / 1_000_000
_PRICE_OUTPUT       = 15.00 / 1_000_000
_PRICE_CACHE_WRITE  = 3.75  / 1_000_000
_PRICE_CACHE_READ   = 0.30  / 1_000_000
_JPY_RATE           = 150


def calculate_cost(stats):
    return (
        stats.get("input_tokens", 0)           * _PRICE_INPUT
        + stats.get("output_tokens", 0)         * _PRICE_OUTPUT
        + stats.get("cache_creation_tokens", 0) * _PRICE_CACHE_WRITE
        + stats.get("cache_read_tokens", 0)     * _PRICE_CACHE_READ
    )


def stats_from_usage(usage):
    return {
        "input_tokens":          usage.input_tokens,
        "output_tokens":         usage.output_tokens,
        "cache_creation_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_tokens":     getattr(usage, "cache_read_input_tokens", 0),
    }


def fmt_cost(usd):
    return f"${usd:.4f}（約{usd * _JPY_RATE:.0f}円）"


def load_cost_log(path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def save_cost_log(log, path):
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def split_script_by_episode(script):
    lines = script.split('\n')
    episodes = []
    current_title = None
    current_lines = []
    for line in lines:
        if re.match(r'^#\s+第\d+話', line.strip()):
            if current_lines and any(l.strip() for l in current_lines):
                episodes.append({'title': current_title or '全話', 'content': '\n'.join(current_lines).strip()})
            current_title = line.strip().lstrip('#').strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines and any(l.strip() for l in current_lines):
        episodes.append({'title': current_title or '全話', 'content': '\n'.join(current_lines).strip()})
    return episodes if episodes else [{'title': '全話', 'content': script}]


def min_chars_per_block(video_duration):
    for minutes, chars in [(120, 2500), (90, 2000), (60, 1500), (45, 1200),
                            (30, 900), (20, 700), (15, 600)]:
        if f"{minutes}分" in video_duration:
            return chars
    return 400


def parse_outline_blocks(outline_text):
    blocks = []
    current_title = ""
    current_lines = []
    episode_header = ""
    for line in outline_text.split('\n'):
        s = line.strip()
        if re.match(r'^# ', s) and '第' in s:
            if current_title and current_lines:
                blocks.append({'title': current_title, 'episode_header': episode_header, 'content': '\n'.join(current_lines)})
                current_title = ""
                current_lines = []
            episode_header = s
        elif re.match(r'^## \[', s):
            if current_title and current_lines:
                blocks.append({'title': current_title, 'episode_header': episode_header, 'content': '\n'.join(current_lines)})
            current_title = s
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_title and current_lines:
        blocks.append({'title': current_title, 'episode_header': episode_header, 'content': '\n'.join(current_lines)})
    return blocks


def try_parse_json(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError("JSONが見つかりませんでした")
    raw = match.group()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r',(\s*[}\]])', r'\1', raw)
    cleaned = re.sub(r'}\s*\n(\s*)\{', r'},\n\1{', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for sep in ('}\n    }', '},\n    {', '},\n  {', '},\n{', '},'):
        pos = cleaned.rfind(sep)
        if pos > 0:
            truncated = cleaned[:pos + 1]
            open_b = truncated.count('[') - truncated.count(']')
            open_c = truncated.count('{') - truncated.count('}')
            repaired = truncated + ']' * max(0, open_b) + '}' * max(0, open_c)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                continue
    raise ValueError("JSONパース失敗")


def extract_script_only(script_text):
    lines = script_text.split('\n')
    if not any('|' in line for line in lines):
        return script_text
    result = []
    current_section = ""
    for line in lines:
        s = line.strip()
        if s.startswith('## ') or s.startswith('# '):
            current_section = s.lstrip('#').strip()
            result.append(f"\n【{current_section}】\n")
        elif re.match(r'^\|[-|: ]+\|$', s):
            continue
        elif s.startswith('|'):
            cells = [c.strip() for c in s.split('|')[1:-1]]
            if len(cells) >= 2:
                script_cell = cells[1]
                if script_cell in ('演者のセリフ', 'セリフ'):
                    continue
                if script_cell:
                    result.append(script_cell)
        elif s and not s.startswith('|'):
            result.append(line)
    return '\n'.join(result)


# ─────────────────────────────────────────────
# テストランナー
# ─────────────────────────────────────────────

_passed = 0
_failed = 0


def ok(name):
    global _passed
    _passed += 1
    print(f"  ✅ PASS  {name}")


def fail(name, detail=""):
    global _failed
    _failed += 1
    print(f"  ❌ FAIL  {name}")
    if detail:
        print(f"          {detail}")


def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ─────────────────────────────────────────────
# 1. calculate_cost
# ─────────────────────────────────────────────
section("1. calculate_cost")

try:
    c = calculate_cost({"input_tokens": 1_000_000, "output_tokens": 0})
    assert abs(c - 3.00) < 0.0001, f"expected 3.00 got {c}"
    ok("入力のみ 1M tokens = $3.00")
except Exception as e:
    fail("入力のみ 1M tokens = $3.00", str(e))

try:
    c = calculate_cost({"input_tokens": 0, "output_tokens": 1_000_000})
    assert abs(c - 15.00) < 0.0001, f"expected 15.00 got {c}"
    ok("出力のみ 1M tokens = $15.00")
except Exception as e:
    fail("出力のみ 1M tokens = $15.00", str(e))

try:
    c = calculate_cost({"cache_creation_tokens": 1_000_000})
    assert abs(c - 3.75) < 0.0001, f"expected 3.75 got {c}"
    ok("キャッシュ書き込み 1M = $3.75")
except Exception as e:
    fail("キャッシュ書き込み 1M = $3.75", str(e))

try:
    c = calculate_cost({"cache_read_tokens": 1_000_000})
    assert abs(c - 0.30) < 0.0001, f"expected 0.30 got {c}"
    ok("キャッシュ読み込み 1M = $0.30")
except Exception as e:
    fail("キャッシュ読み込み 1M = $0.30", str(e))

try:
    c = calculate_cost({})
    assert c == 0.0
    ok("空の stats = $0.00")
except Exception as e:
    fail("空の stats = $0.00", str(e))

try:
    stats = {"input_tokens": 130_000, "output_tokens": 15_000,
             "cache_creation_tokens": 0, "cache_read_tokens": 0}
    c = calculate_cost(stats)
    expected = 130_000 * _PRICE_INPUT + 15_000 * _PRICE_OUTPUT
    assert abs(c - expected) < 0.00001
    ok(f"通常モード典型値 = ${c:.4f}")
except Exception as e:
    fail("通常モード典型値", str(e))

try:
    stats = {"input_tokens": 7_000, "output_tokens": 15_000,
             "cache_creation_tokens": 123_000, "cache_read_tokens": 0}
    c = calculate_cost(stats)
    expected = 7_000 * _PRICE_INPUT + 15_000 * _PRICE_OUTPUT + 123_000 * _PRICE_CACHE_WRITE
    assert abs(c - expected) < 0.00001
    ok(f"構成案生成（キャッシュ書き込み）= ${c:.4f}")
except Exception as e:
    fail("構成案生成（キャッシュ書き込み）", str(e))

try:
    stats = {"input_tokens": 7_000, "output_tokens": 3_000,
             "cache_creation_tokens": 0, "cache_read_tokens": 123_000}
    c = calculate_cost(stats)
    expected = 7_000 * _PRICE_INPUT + 3_000 * _PRICE_OUTPUT + 123_000 * _PRICE_CACHE_READ
    assert abs(c - expected) < 0.00001
    ok(f"ブロック生成（キャッシュ読み込み）= ${c:.4f}")
except Exception as e:
    fail("ブロック生成（キャッシュ読み込み）", str(e))


# ─────────────────────────────────────────────
# 2. stats_from_usage
# ─────────────────────────────────────────────
section("2. stats_from_usage")

class MockUsage:
    def __init__(self, inp, out, cw=0, cr=0):
        self.input_tokens = inp
        self.output_tokens = out
        self.cache_creation_input_tokens = cw
        self.cache_read_input_tokens = cr

try:
    s = stats_from_usage(MockUsage(100, 200, 50, 30))
    assert s["input_tokens"] == 100
    assert s["output_tokens"] == 200
    assert s["cache_creation_tokens"] == 50
    assert s["cache_read_tokens"] == 30
    ok("全フィールド正常変換")
except Exception as e:
    fail("全フィールド正常変換", str(e))

try:
    class MinimalUsage:
        input_tokens = 500
        output_tokens = 800
    s = stats_from_usage(MinimalUsage())
    assert s["cache_creation_tokens"] == 0
    assert s["cache_read_tokens"] == 0
    ok("キャッシュフィールドなしでも0になる")
except Exception as e:
    fail("キャッシュフィールドなしでも0になる", str(e))


# ─────────────────────────────────────────────
# 3. fmt_cost
# ─────────────────────────────────────────────
section("3. fmt_cost")

try:
    s = fmt_cost(0.0)
    assert "$0.0000" in s and "0円" in s
    ok("$0 → $0.0000（約0円）")
except Exception as e:
    fail("$0", str(e))

try:
    s = fmt_cost(1.0)
    assert "$1.0000" in s and "150円" in s
    ok("$1.00 → 約150円")
except Exception as e:
    fail("$1.00", str(e))

try:
    s = fmt_cost(0.0821)
    assert "0.0821" in s
    ok("小数4桁表示")
except Exception as e:
    fail("小数4桁表示", str(e))


# ─────────────────────────────────────────────
# 4. load_cost_log / save_cost_log
# ─────────────────────────────────────────────
section("4. load_cost_log / save_cost_log")

with tempfile.TemporaryDirectory() as tmpdir:
    log_path = Path(tmpdir) / "cost_log.json"

    try:
        result = load_cost_log(log_path)
        assert result == []
        ok("ファイルなしで空リストを返す")
    except Exception as e:
        fail("ファイルなしで空リストを返す", str(e))

    try:
        entries = [
            {"date": "2026-05-05", "time": "10:00", "label": "テスト", "cost": 0.05, "mode": "通常モード"},
            {"date": "2026-05-05", "time": "11:00", "label": "テスト2", "cost": 0.12, "mode": "高精度（台本生成）"},
        ]
        save_cost_log(entries, log_path)
        assert log_path.exists()
        ok("ファイルに書き込める")
    except Exception as e:
        fail("ファイルに書き込める", str(e))

    try:
        loaded = load_cost_log(log_path)
        assert len(loaded) == 2
        assert loaded[0]["label"] == "テスト"
        assert loaded[1]["cost"] == 0.12
        ok("書き込んだ内容を正しく読み込める")
    except Exception as e:
        fail("書き込んだ内容を正しく読み込める", str(e))

    try:
        # 壊れたJSONファイル
        log_path.write_text("{ broken json }", encoding="utf-8")
        result = load_cost_log(log_path)
        assert result == []
        ok("壊れたJSONでも空リストを返す（クラッシュしない）")
    except Exception as e:
        fail("壊れたJSONでも空リストを返す", str(e))


# ─────────────────────────────────────────────
# 5. コストログの日付別集計ロジック
# ─────────────────────────────────────────────
section("5. 日付別集計ロジック")

try:
    log = [
        {"date": "2026-05-03", "time": "09:00", "label": "A", "cost": 0.10, "mode": "通常モード"},
        {"date": "2026-05-04", "time": "14:00", "label": "B", "cost": 0.20, "mode": "高精度（構成案）"},
        {"date": "2026-05-04", "time": "14:30", "label": "C", "cost": 0.15, "mode": "高精度（台本生成）"},
        {"date": "2026-05-05", "time": "10:00", "label": "D", "cost": 0.08, "mode": "通常モード"},
    ]
    by_date = defaultdict(list)
    for e in log:
        by_date[e["date"]].append(e)
    dates = sorted(by_date.keys(), reverse=True)

    assert dates == ["2026-05-05", "2026-05-04", "2026-05-03"]
    ok("日付の降順ソート")
except Exception as e:
    fail("日付の降順ソート", str(e))

try:
    day_total_0504 = sum(e["cost"] for e in by_date["2026-05-04"])
    assert abs(day_total_0504 - 0.35) < 0.0001
    ok("同日の費用合計が正しい")
except Exception as e:
    fail("同日の費用合計が正しい", str(e))

try:
    grand_total = sum(e["cost"] for e in log)
    assert abs(grand_total - 0.53) < 0.0001
    ok("累計合計が正しい")
except Exception as e:
    fail("累計合計が正しい", str(e))


# ─────────────────────────────────────────────
# 6. split_script_by_episode
# ─────────────────────────────────────────────
section("6. split_script_by_episode")

try:
    script = "テスト台本\nセリフです。"
    eps = split_script_by_episode(script)
    assert len(eps) == 1
    assert eps[0]["title"] == "全話"
    ok("話数マーカーなし → 全話1件")
except Exception as e:
    fail("話数マーカーなし → 全話1件", str(e))

try:
    script = """# 第1話 オープニング
セリフ1

# 第2話 クロージング
セリフ2"""
    eps = split_script_by_episode(script)
    assert len(eps) == 2
    assert eps[0]["title"] == "第1話 オープニング"
    assert eps[1]["title"] == "第2話 クロージング"
    ok("2話分割 → 2件")
except Exception as e:
    fail("2話分割 → 2件", str(e))

try:
    script = "# 第1話\nA\n# 第2話\nB\n# 第3話\nC\n# 第4話\nD\n# 第5話\nE"
    eps = split_script_by_episode(script)
    assert len(eps) == 5
    ok("5話分割 → 5件")
except Exception as e:
    fail("5話分割 → 5件", str(e))

try:
    script = "空白のみ\n  \n  "
    eps = split_script_by_episode(script)
    assert len(eps) == 1
    ok("空白のみのコンテンツでも落ちない")
except Exception as e:
    fail("空白のみのコンテンツでも落ちない", str(e))


# ─────────────────────────────────────────────
# 7. min_chars_per_block
# ─────────────────────────────────────────────
section("7. min_chars_per_block")

cases = [
    ("120分（約36,000文字）", 2500),
    ("90分（約27,000文字）", 2000),
    ("60分（約18,000文字）", 1500),
    ("45分（約13,500文字）", 1200),
    ("30分（約9,000文字）", 900),
    ("20分（約6,000文字）", 700),
    ("15分（約4,500文字）", 600),
    ("7分（約2,100文字）", 400),
    ("3分（約900文字）", 400),
]
for dur, expected in cases:
    try:
        result = min_chars_per_block(dur)
        assert result == expected, f"got {result}"
        ok(f"{dur} → {expected}文字")
    except Exception as e:
        fail(f"{dur} → {expected}文字", str(e))


# ─────────────────────────────────────────────
# 8. parse_outline_blocks
# ─────────────────────────────────────────────
section("8. parse_outline_blocks")

try:
    outline = """## [1] オープニング
内容A

## [2] 問題提起
内容B

## [3] クロージング
内容C"""
    blocks = parse_outline_blocks(outline)
    assert len(blocks) == 3
    assert blocks[0]["title"] == "## [1] オープニング"
    assert blocks[2]["title"] == "## [3] クロージング"
    ok("単話3ブロック分割")
except Exception as e:
    fail("単話3ブロック分割", str(e))

try:
    outline = """# 第1話
## [1] 第1話オープニング
内容

# 第2話
## [2] 第2話オープニング
内容"""
    blocks = parse_outline_blocks(outline)
    assert len(blocks) == 2
    assert blocks[0]["episode_header"] == "# 第1話"
    assert blocks[1]["episode_header"] == "# 第2話"
    ok("複数話のエピソードヘッダーが正しく付与される")
except Exception as e:
    fail("複数話のエピソードヘッダー", str(e))

try:
    blocks = parse_outline_blocks("")
    assert blocks == []
    ok("空の構成案 → 空リスト")
except Exception as e:
    fail("空の構成案 → 空リスト", str(e))

try:
    outline = "## [なし] ブロック\n内容"
    blocks = parse_outline_blocks(outline)
    assert len(blocks) == 1  # ## [ で始まれば何でも有効なブロック
    assert blocks[0]["title"] == "## [なし] ブロック"
    ok("## [任意文字] でも有効なブロックとして扱う")
except Exception as e:
    fail("## [任意文字] でも有効なブロック", str(e))


# ─────────────────────────────────────────────
# 9. try_parse_json
# ─────────────────────────────────────────────
section("9. try_parse_json")

try:
    result = try_parse_json('{"title": "テスト", "slides": []}')
    assert result["title"] == "テスト"
    ok("正常なJSON")
except Exception as e:
    fail("正常なJSON", str(e))

try:
    result = try_parse_json('前文\n{"title": "埋め込み"}\n後文')
    assert result["title"] == "埋め込み"
    ok("前後にテキストがある場合も抽出できる")
except Exception as e:
    fail("前後にテキストがある場合", str(e))

try:
    result = try_parse_json('{"title": "末尾カンマ", "slides": [],}')
    assert result["title"] == "末尾カンマ"
    ok("trailing comma を自動修復")
except Exception as e:
    fail("trailing comma を自動修復", str(e))

try:
    try_parse_json("JSONがない文字列")
    fail("JSONなし → ValueError が発生するべき")
except ValueError:
    ok("JSONなし → ValueError が正しく発生")
except Exception as e:
    fail("JSONなし → ValueError", str(e))


# ─────────────────────────────────────────────
# 10. extract_script_only
# ─────────────────────────────────────────────
section("10. extract_script_only")

try:
    plain = "これはテーブルなしの台本です。\nセリフが続きます。"
    result = extract_script_only(plain)
    assert result == plain
    ok("テーブルなし台本はそのまま返す")
except Exception as e:
    fail("テーブルなし台本はそのまま返す", str(e))

try:
    table = """## オープニング
| 映像/テロップ指示 | 演者のセリフ | 演技/効果音の指示 |
|---|---|---|
| [Bロール] | こんにちは！ | [カメラ目線] |
| [テロップ] | よろしくお願いします。 | [笑顔で] |"""
    result = extract_script_only(table)
    assert "こんにちは！" in result
    assert "よろしくお願いします。" in result
    assert "[Bロール]" not in result
    assert "[カメラ目線]" not in result
    ok("3列テーブルからセリフ列だけ抽出")
except Exception as e:
    fail("3列テーブルからセリフ列だけ抽出", str(e))

try:
    table = """## セクション1
| 映像 | 演者のセリフ | 演技 |
|---|---|---|
| A | セリフA | B |
---
## セクション2
| 映像 | 演者のセリフ | 演技 |
|---|---|---|
| C | セリフC | D |"""
    result = extract_script_only(table)
    assert "セリフA" in result
    assert "セリフC" in result
    assert "【セクション1】" in result
    assert "【セクション2】" in result
    ok("セクション見出しが【】付きで挿入される")
except Exception as e:
    fail("セクション見出しが【】付きで挿入される", str(e))


# ─────────────────────────────────────────────
# 11. コストログの通し連携テスト
# ─────────────────────────────────────────────
section("11. コストログ連携テスト（通常→高精度→累計）")

with tempfile.TemporaryDirectory() as tmpdir:
    path = Path(tmpdir) / "cost_log.json"
    log = []

    def add_entry(label, cost, mode):
        log.append({"date": datetime.now().strftime("%Y-%m-%d"),
                    "time": datetime.now().strftime("%H:%M"),
                    "label": label, "cost": cost, "mode": mode})
        save_cost_log(log, path)

    try:
        # 通常モード生成
        s1 = {"input_tokens": 130_000, "output_tokens": 12_000,
              "cache_creation_tokens": 0, "cache_read_tokens": 0}
        add_entry("テスト商品", calculate_cost(s1), "通常モード")
        ok("通常モード: コスト記録")
    except Exception as e:
        fail("通常モード: コスト記録", str(e))

    try:
        # 構成案生成
        s2 = {"input_tokens": 7_000, "output_tokens": 4_000,
              "cache_creation_tokens": 95_000, "cache_read_tokens": 0}
        add_entry("構成案：テスト商品", calculate_cost(s2), "高精度（構成案）")
        ok("高精度モード: 構成案コスト記録")
    except Exception as e:
        fail("高精度モード: 構成案コスト記録", str(e))

    try:
        # ブロック生成 × 10回累積
        accum = 0.0
        for i in range(10):
            sb = {"input_tokens": 7_000, "output_tokens": 2_500,
                  "cache_creation_tokens": 0, "cache_read_tokens": 95_000}
            accum += calculate_cost(sb)
        add_entry("台本生成：テスト商品_高精度", accum, "高精度（台本生成）")
        ok(f"高精度モード: ブロック10回累積コスト記録 = ${accum:.4f}")
    except Exception as e:
        fail("高精度モード: ブロック10回累積", str(e))

    try:
        loaded = load_cost_log(path)
        assert len(loaded) == 3
        total = sum(e["cost"] for e in loaded)
        assert total > 0
        ok(f"ファイルから3件読み込み・累計 = ${total:.4f}（約{total*150:.0f}円）")
    except Exception as e:
        fail("ファイルから3件読み込み", str(e))

    try:
        by_date = defaultdict(list)
        for e in loaded:
            by_date[e["date"]].append(e)
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in by_date
        assert len(by_date[today]) == 3
        ok(f"今日({today})のエントリが3件ある")
    except Exception as e:
        fail("日付別グルーピング", str(e))


# ─────────────────────────────────────────────
# 結果サマリー
# ─────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  結果: {_passed} PASS  /  {_failed} FAIL  /  計 {_passed + _failed} テスト")
print(f"{'='*50}\n")

if _failed > 0:
    exit(1)
