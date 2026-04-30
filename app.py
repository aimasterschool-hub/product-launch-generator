#!/usr/bin/env python3
import os
import re
import json
import zipfile
import subprocess
from io import BytesIO
import streamlit as st
from pathlib import Path
from datetime import datetime
import anthropic
from tavily import TavilyClient
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from PIL import Image, ImageDraw, ImageFont

DESIGN_PRESETS = {
    "ダーク（黒背景・白文字）":   {"bg": "#1a1a1a", "title": "#ffffff", "content": "#e0e0e0", "accent": "#4a9eff"},
    "ホワイト（白背景・黒文字）": {"bg": "#ffffff", "title": "#1a1a1a", "content": "#333333", "accent": "#2563eb"},
    "ネイビー（紺背景・白文字）": {"bg": "#1e3a5f", "title": "#ffffff", "content": "#d0e8ff", "accent": "#ffd700"},
    "レッド（赤背景・白文字）":   {"bg": "#8b0000", "title": "#ffffff", "content": "#ffe0e0", "accent": "#ffcc00"},
    "グリーン（緑背景・白文字）": {"bg": "#1a4a2e", "title": "#ffffff", "content": "#d0ffd8", "accent": "#90ee90"},
}

SLIDE_FORMATS = {
    "横動画（16:9 / YouTube・一般動画）":  {"png": (1920, 1080), "pptx": (13.33, 7.5)},
    "正方形（1:1 / Instagram・note）":     {"png": (1080, 1080), "pptx": (10.0,  10.0)},
    "縦動画（9:16 / TikTok・Shorts・リール）": {"png": (1080, 1920), "pptx": (7.5,  13.33)},
}

SAMPLES_DIR = Path("samples")

PRESET_SIMPLE_KEYS = [
    "structure_type", "include_knowhow", "knowhow_theme", "knowhow_notes",
    "name", "category", "seller_name", "seller_profile",
    "interviewer_name", "interviewer_profile", "seller_authority",
    "catchcopy", "target_audience", "result1", "result2",
    "monthly_return", "ease_of_start",
    "voice1", "voice2", "voice3",
    "pain_points", "why_now",
    "third_party_type", "third_party_name", "third_party_points",
    "regular_price", "special_price", "limited_time", "limited_seats",
    "installment", "bonuses",
    "episode_structure", "closing_strength", "video_duration", "notes",
    "sales_flow_type", "sales_start_day", "consultation_method",
]


def load_preset_to_session(preset):
    for k in PRESET_SIMPLE_KEYS:
        if k in preset:
            st.session_state[f"f_{k}"] = preset[k]
    for i, v in enumerate(preset.get("strengths", ["", "", "", ""])):
        st.session_state[f"str_{i}"] = v
    voices = preset.get("voices", ["", "", ""])
    for i in range(3):
        st.session_state[f"f_voice{i+1}"] = voices[i] if i < len(voices) else ""
    for i, v in enumerate(preset.get("comment_includes", [True]*5)):
        st.session_state[f"comment_include_{i}"] = v
    for i, v in enumerate(preset.get("comment_prompts", [""]*5)):
        st.session_state[f"comment_{i}"] = v


def clear_form_state():
    """フォームの入力欄をデフォルト値にリセットする。保存済みプリセットは残る。

    st.form 内のウィジェットはキーを削除しても表示がリセットされないため、
    load_preset_to_session と同様にデフォルト値を明示的にセットする方式を使う。
    """
    # テキスト入力・テキストエリア → 空文字
    for k in [
        "knowhow_theme", "knowhow_notes",
        "name", "seller_name", "seller_profile",
        "interviewer_name", "interviewer_profile", "seller_authority",
        "catchcopy", "target_audience",
        "result1", "result2", "monthly_return", "ease_of_start",
        "voice1", "voice2", "voice3",
        "pain_points", "why_now",
        "third_party_name", "third_party_points",
        "consultation_method",
        "regular_price", "special_price",
        "limited_time", "limited_seats", "bonuses", "notes",
    ]:
        st.session_state[f"f_{k}"] = ""

    # 強み欄（str_0〜str_3）
    for i in range(4):
        st.session_state[f"str_{i}"] = ""

    # コメント促進パート
    for i in range(5):
        st.session_state[f"comment_{i}"] = ""
        st.session_state[f"comment_include_{i}"] = True

    # 各話テーマ
    for i in range(5):
        st.session_state[f"episode_theme_{i}"] = ""

    # チェックボックス
    st.session_state["f_include_knowhow"]    = False
    st.session_state["f_use_episode_themes"] = False

    # ラジオボタン
    st.session_state["f_structure_type"]  = "従来型"
    st.session_state["f_sales_flow_type"] = "直接販売型"

    # セレクトボックス（フォームの default と一致させる）
    st.session_state["f_category"]          = "FX・為替投資"
    st.session_state["f_third_party_type"]  = "なし"
    st.session_state["f_sales_start_day"]   = "翌日（1日後）"
    st.session_state["f_installment"]       = "なし"
    st.session_state["f_episode_structure"] = "1話完結"
    st.session_state["f_closing_strength"]  = "真摯・控えめ（押し付けない）"
    st.session_state["f_video_duration"]    = "7分（約2,100文字）"


OUTPUT_DIR   = Path("output")
PRESETS_FILE = Path("presets.json")
MODEL = "claude-opus-4-7"

# ── 成功台本の設計図（心理構造フレームワーク） ──────────────────────────────
SUCCESS_FRAMEWORK = """
## 成功するプロダクトローンチ台本の構成要素（心理設計の型）

台本を書く際は、以下の8要素と話数設計を必ず意識して構成してください。

### 8つの必須構成要素

1. **衝撃的なベネフィットの提示（フック）**
   - 冒頭で「元手1万円で月60万」「30日で資金2倍」など常識外れの数字を提示する
   - 視聴者が「え、本当に？」と思わず続きを見てしまうフックを作る

2. **現状の問題提起と危機の共有**
   - 「普通に働いても生活を守れない時代」「年金制度の破綻」「AIによる職の代替」など
   - 視聴者が漠然と抱える不安を言語化し、共通の危機感を顕在化させる

3. **ストーリー（挫折→運命的な発見→成功）**
   - 発信者自身の「どん底（借金・大損・失職など）」を正直に告白する
   - そこから這い上がった「運命的な発見」を語り、親近感と信頼を同時に構築する

4. **非常識なロジック（独自メカニズム）の提示**
   - 「97%の負け組の逆を突く」「AIとプロの嗅覚の融合」など
   - 他と明確に違う"勝ち筋"を説明し、「これなら自分でもできる」という希望を与える

5. **圧倒的な証拠（エビデンス）の提示**
   - 取引履歴・LINEのやり取り・教え子の成功事例を動画や画像で見せる
   - 「見せられる証拠がある」ことで疑念を払拭する

6. **ハードルの徹底排除**
   - 「2万円から開始可能」「スマホ1台で完結」「設定代行サポートあり」など
   - 視聴者が「自分には無理」と思う理由をすべて先回りして潰す

7. **価格崩しと価値の正当化**
   - 本来100万円以上の価値があると印象づけた上で、補助金・期間限定などの理由で
   - 手が届く価格（9.8万〜30万）まで下げる演出をする

8. **強力なクロージング（希少性×緊急性）**
   - 「先着100名」「3日間限定」「審査制」などの枠を設け、今すぐ動く理由を作る
   - 5年後の未来を想像させ、行動しない損失を意識させる

---

### 話数別・最適設計図

#### 第1話：衝撃とパラダイムシフト
- オープニング：圧倒的な実績を見せ「あなたの常識を覆す」と宣言
- 質問フック：「月60万稼ぐのに元手はいくら必要だと思いますか？」など思考を揺さぶる
- 独自システムの紹介：少額からの可能性を示す
- 社会背景の危機：「沈みゆく日本」という共通の敵を設定し投資の必要性を説く
- 自己紹介（挫折ストーリー）：負けの過去を共有して信頼を獲得
- 次回予告＋コメント促進：「勝てる理由の全貌を次回明かす」として引きを作る

#### 第2話：信頼構築とメカニズム解明
- 反響の共有：「コメントが殺到している」として社会的証明を演出
- ロジックの深掘り：「市場の歪みを拾う仕組み」「AI24時間監視」など勝てる理屈を解説
- 第三者の登場：開発者・専門家・実績ある教え子との対談で客観性を担保
- 不安の先回り解消（Q&A形式）：初心者でも可能な理由、税金、リスクを事前に回答
- 特典の予告：「自己資金がない方向けの秘策」などを次話の引きとして提示

#### 第3話：オファーと決断の促し
- フルパッケージの公開：メインシステム＋長期・短期・複利など人生設計全体を提示
- 豪華特典の提示：導入マニュアル・無期限サポート・限定セミナーなどで価値を最大化
- 価格提示：他商品との比較・開発費の大きさを語った後、限定価格を発表
- リスクリワードの強調：「参加費は1週間で回収できる」という実績を再提示
- クロージング：5年後の未来を想像させ、先行受付URLへ誘導

#### 特別編（ダウンセル／救済クロージング）
- ハードル再調整：「価格で諦めた方へ」として機能を絞ったライト版・分割払いを再提案
- 取りこぼしの回収：本編で決断できなかった層に最後のチャンスを提供
"""


def load_presets_from_file():
    if PRESETS_FILE.exists():
        try:
            return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_presets_to_file(presets):
    try:
        PRESETS_FILE.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_samples():
    SAMPLES_DIR.mkdir(exist_ok=True)
    samples = []
    files = []
    for pattern in ["*.txt", "*.rtf", "*.rtfd"]:
        files.extend(SAMPLES_DIR.glob(pattern))
    for file_path in sorted(set(files)):
        try:
            if file_path.suffix.lower() in (".rtf", ".rtfd"):
                result = subprocess.run(
                    ["textutil", "-convert", "txt", "-stdout", str(file_path)],
                    capture_output=True, text=True
                )
                content = result.stdout
            else:
                content = file_path.read_text(encoding="utf-8")
            if content.strip():
                samples.append({"filename": file_path.name, "content": content})
        except Exception:
            pass
    return samples


def build_system_prompt(samples):
    instruction_block = {
        "type": "text",
        "text": (
            "あなたはプロダクトローンチ用の台本を生成する専門家です。\n"
            "以下の【成功台本の設計図】と【サンプル台本】を両方参照して台本を作成してください。\n\n"
            "## 参照の優先度\n"
            "1. **成功台本の設計図**：心理構造・話数設計・各セクションの役割を理解する（構成の骨格）\n"
            "2. **サンプル台本**：実際の語り口・文体・リズム・言い回しを学ぶ（表現のスタイル）\n"
            "3. **商品情報**：具体的な数字・ストーリー・特徴を設計図に当てはめる\n\n"
            "## 分析のポイント\n"
            "- 設計図の8要素（フック・問題提起・ストーリー・ロジック・証拠・ハードル排除・価格崩し・クロージング）が\n"
            "  各話に適切に配置されているか確認する\n"
            "- サンプルのトーン・語彙・文章のリズムを踏襲する\n"
            "- 視聴者の心理変化（無関心→興味→信頼→欲求→行動）を各話の流れで設計する\n"
        ),
    }

    framework_block = {
        "type": "text",
        "text": SUCCESS_FRAMEWORK,
        "cache_control": {"type": "ephemeral"},
    }

    if not samples:
        instruction_block["text"] += "\nサンプルがないため、設計図のフレームワークとベストプラクティスに従って生成してください。"
        return [instruction_block, framework_block]

    samples_text = "\n\n".join(
        f"=== サンプル {i + 1}: {s['filename']} ===\n{s['content']}"
        for i, s in enumerate(samples)
    )
    samples_block = {
        "type": "text",
        "text": f"## 学習用サンプル台本\n\n{samples_text}",
        "cache_control": {"type": "ephemeral"},
    }
    return [instruction_block, framework_block, samples_block]


def build_user_prompt(info):
    strengths = [s for s in info.get("strengths", []) if s]
    strengths_str = "\n".join(f"  - {s}" for s in strengths) or "  （未入力）"

    voices = [v for v in info.get("voices", []) if v]
    voices_str = "\n".join(f"  - {v}" for v in voices) if voices else "  （なし）"

    structure_type = info.get("structure_type", "従来型")
    if structure_type == "従来型":
        structure_desc = "実績提示→商品説明→販売。インタビュー or 一人語り形式。"
    else:
        structure_desc = "無料ノウハウ・セミナー形式で価値提供→「時間・リスクが心配な方はこちら」と商品販売に自然につなぐフロントエンド型。"

    interviewer = info.get("interviewer_name", "").strip()
    dialogue_style = f"インタビュアー「{interviewer}」との対話形式" if interviewer else "一人語り（モノローグ）形式"

    comment_includes = info.get("comment_includes", [True] * 5)
    comment_prompts = info.get("comment_prompts", [])
    episode_structure = info.get("episode_structure", "1話完結")
    episode_count = int(episode_structure[0]) if episode_structure[0].isdigit() else 1

    include_knowhow = info.get("include_knowhow", False)
    knowhow_theme = info.get("knowhow_theme", "").strip()
    knowhow_notes = info.get("knowhow_notes", "").strip()

    lines = [
        "以下のプロダクト情報をもとに、サンプル台本のスタイルを踏襲した台本を生成してください。",
        "",
        "## 構成タイプ",
        f"**タイプ**: {structure_type}",
        f"**説明**: {structure_desc}",
        f"**話し方スタイル**: {dialogue_style}",
        "",
        "## フロントエンド型ノウハウパート",
    ]

    if include_knowhow and knowhow_theme:
        lines += [
            f"**ノウハウテーマ**: {knowhow_theme}",
            f"**補足メモ**: {knowhow_notes if knowhow_notes else 'なし'}",
            "このテーマについて視聴者にとって価値ある具体的なノウハウを台本の前半に組み込んでください。",
            "ノウハウ提供の後、自然に商品の紹介につなげてください。",
        ]
    elif include_knowhow:
        lines.append("商品カテゴリに合った価値あるノウハウを台本の前半に自動生成して組み込んでください。")
    else:
        lines.append("ノウハウパートは不要です。")

    lines += [
        "",
        "## 商品・基本情報",
        f"**商品名**: {info.get('name', '')}",
        f"**ジャンル**: {info.get('category', '')}",
        f"**販売者名**: {info.get('seller_name', '')}",
        f"**販売者のプロフィール**: {info.get('seller_profile', '')}",
        f"**インタビュアープロフィール**: {info.get('interviewer_profile', '')}",
        f"**販売者の権威・実績**: {info.get('seller_authority', '')}",
        f"**キャッチコピー**: {info.get('catchcopy', '')}",
        f"**ターゲット層**: {info.get('target_audience', '')}",
        f"**実績数値①（短期）**: {info.get('result1', '')}",
        f"**実績数値②（中〜長期）**: {info.get('result2', '')}",
        f"**月利 / 月収目安**: {info.get('monthly_return', '')}",
        f"**始めやすさの根拠**: {info.get('ease_of_start', '')}",
        "",
        "**商品の強み**:",
        strengths_str,
        "",
        "## 利用者の声（喜びの声）",
        voices_str,
        "",
        "## 社会背景・痛み訴求",
        f"**視聴者のペイン**: {info.get('pain_points', '')}",
        f"**なぜ今必要か（why now）**: {info.get('why_now', '')}",
        "",
        "## 第三者・信頼性",
        f"**第三者の種類**: {info.get('third_party_type', 'なし')}",
        f"**名前・肩書き**: {info.get('third_party_name', '')}",
        f"**裏付けポイント**: {info.get('third_party_points', '')}",
        "",
        "## 販売フロー",
    ]

    sales_flow = info.get("sales_flow_type", "直接販売型")
    lines.append(f"**販売フロータイプ**: {sales_flow}")
    if sales_flow == "直接販売型":
        start_day = info.get("sales_start_day", "翌日（1日後）")
        lines.append(f"**販売スタート日**: {start_day}")
        lines.append(f"クロージングでは、{start_day}から販売を開始することを明示し、視聴者に行動を促す緊迫感を持たせてください。")
    else:
        method = info.get("consultation_method", "").strip()
        if method:
            lines.append(f"**誘導先**: {method}")
        lines.append("クロージングでは商品への直接誘導ではなく、個別面談・相談への申し込みを促してください。「まずは無料で話しましょう」「個別でご相談ください」のようなトーンで、個別接触後に販売につなげる流れで台本を構成してください。")

    lines += [
        "",
        "## 価格・オファー",
        f"**定価**: {info.get('regular_price', '')}",
        f"**特別価格**: {info.get('special_price', '')}",
        f"**期間限定条件**: {info.get('limited_time', '')}",
        f"**先着・定員制限**: {info.get('limited_seats', '')}",
        f"**分割対応**: {info.get('installment', 'なし')}",
        f"**特典内容**: {info.get('bonuses', '')}",
        "",
        "## コメント促進パート（動画末尾）",
    ]

    any_comment = any(comment_includes[i] for i in range(episode_count))
    if not any_comment:
        lines.append("コメント促進パートは全話不要です。含めないでください。")
    else:
        for i in range(episode_count):
            include = comment_includes[i] if i < len(comment_includes) else True
            if not include:
                lines.append(f"**第{i+1}話のコメント促進**: 不要（含めないでください）")
            else:
                cp = comment_prompts[i].strip() if i < len(comment_prompts) else ""
                instruction = f"「{cp}」" if cp else "内容に合った質問を自動生成"
                lines.append(f"**第{i+1}話のコメント促進**: {instruction}")

    lines += [
        "",
        "## 構成オプション",
        f"**話数構成**: {episode_structure}",
        f"**1話あたりの動画の長さ**: {info.get('video_duration', '7分（約2,100文字）')}",
        f"**クロージングの強度**: {info.get('closing_strength', '標準')}",
    ]

    if info.get("use_episode_themes"):
        themes = info.get("episode_themes", [])
        specified = [(i+1, t) for i, t in enumerate(themes[:episode_count]) if t.strip()]
        if specified:
            lines.append("")
            lines.append("## 各話の内容指定")
            for num, theme in specified:
                lines.append(f"**第{num}話**: {theme}")
            lines.append("※ 内容が指定されている話は、その内容に沿って台本を作成してください。")

    lines += [
    ]

    if info.get("notes"):
        lines += ["", f"**追加メモ**: {info['notes']}"]

    lines += [
        "",
        "【出力形式の指示】",
        "- 【セクション名 - タイムコード】の見出しを使って構成を明示してください",
        "- 【ナレーション】【インタビュアー】【販売者】【SE】【映像】などの役割表記を適切に使ってください",
        "- サンプル台本と同じスタイル・語り口・構成で作成してください",
        "- 話数構成が指定されている場合は、その構成に合わせて台本を分けてください",
        "- コメント促進パートが必要な場合は各話の動画末尾に必ず含めてください",
        f"- 1話あたりの目標文字数を厳守してください（{info.get('video_duration', '7分（約2,100文字）')}）",
    ]
    return "\n".join(lines)


def try_parse_json(text):
    """テキストからJSONを抽出し、一般的な破損パターンを自動修復してパースする。"""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError("JSONが見つかりませんでした")
    raw = match.group()

    # ① そのままパース
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # ② よくある修正: trailing comma / 隣接オブジェクト間の欠落カンマ
    cleaned = re.sub(r',(\s*[}\]])', r'\1', raw)          # trailing comma
    cleaned = re.sub(r'}\s*\n(\s*)\{', r'},\n\1{', cleaned)  # } { → },{
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # ③ 末尾トランケーション修復: 最後の完全スライドで切り詰めて閉じ括弧を補完
    for sep in ('}\n    }', '},\n    {', '},\n  {', '},\n{', '},'):
        pos = cleaned.rfind(sep)
        if pos > 0:
            truncated = cleaned[:pos + 1]
            open_b = truncated.count('[') - truncated.count(']')
            open_c = truncated.count('{') - truncated.count('}')
            repaired = truncated
            repaired += ']' * max(0, open_b)
            repaired += '}' * max(0, open_c)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                continue

    raise ValueError(
        "スライドJSONの解析に失敗しました。\n"
        "台本が非常に長い場合、スライド数が多すぎてJSONが壊れることがあります。\n"
        "話数構成を減らすか台本を短くしてお試しください。"
    )


SLIDE_CHUNK_MAX_CHARS = 4500  # このサイズ以下に収まるよう台本を分割（約15分相当）


def split_script_into_chunks(script):
    """台本を話数・長さで分割してチャンクリストを返す。

    戻り値: [(episode_num, chunk_label, chunk_text), ...]
    - 第N話マーカーがあれば話数ごとに分割
    - 1チャンクが SLIDE_CHUNK_MAX_CHARS を超える場合は前半/後半/パートN でさらに分割
    """
    # ── 話数マーカーで分割 ──
    ep_pattern = re.compile(r'(?:^|\n)(【?第\s*(\d+)\s*話[^\n]*)', re.MULTILINE)
    ep_matches = list(ep_pattern.finditer(script))

    if len(ep_matches) >= 2:
        ep_texts = {}
        for i, m in enumerate(ep_matches):
            ep_num = int(m.group(2))
            start = m.start()
            end = ep_matches[i + 1].start() if i + 1 < len(ep_matches) else len(script)
            ep_texts[ep_num] = script[start:end].strip()
    else:
        ep_texts = {1: script}

    # ── 各話を長さでさらに分割 ──
    result = []
    for ep_num, ep_text in sorted(ep_texts.items()):
        ep_label_base = f"第{ep_num}話" if len(ep_texts) > 1 else "全体"

        if len(ep_text) <= SLIDE_CHUNK_MAX_CHARS:
            result.append((ep_num, ep_label_base, ep_text))
            continue

        # 段落単位で SLIDE_CHUNK_MAX_CHARS 以下のチャンクに分割
        paras = re.split(r'\n\n+', ep_text)
        chunks_text, cur, cur_len = [], [], 0
        for para in paras:
            if cur_len + len(para) > SLIDE_CHUNK_MAX_CHARS and cur:
                chunks_text.append('\n\n'.join(cur))
                cur, cur_len = [para], len(para)
            else:
                cur.append(para)
                cur_len += len(para)
        if cur:
            chunks_text.append('\n\n'.join(cur))

        n = len(chunks_text)
        part_labels = (
            ["前半", "後半"] if n == 2
            else [f"パート{j+1}" for j in range(n)]
        )
        for ci, chunk in enumerate(chunks_text):
            label = f"{ep_label_base} {part_labels[ci]}"
            result.append((ep_num, label, chunk))

    return result


def search_trends(tavily_api_key, category, product_name):
    """カテゴリと商品名に関連する最新トレンドをWeb検索して返す。"""
    try:
        client = TavilyClient(api_key=tavily_api_key)
        query = f"{category} {product_name} 最新トレンド 2025 日本"
        results = client.search(query=query, max_results=3, search_depth="basic")
        summaries = []
        for r in results.get("results", []):
            title = r.get("title", "")
            content = r.get("content", "")[:300]
            summaries.append(f"・{title}：{content}")
        return "\n".join(summaries) if summaries else ""
    except Exception:
        return ""


def generate_slide_data(client, script):
    """Claudeに台本を渡してスライド構成をJSON形式で生成する（Adaptive Thinking使用）。"""
    char_count = len(script.replace(" ", "").replace("\n", ""))
    target_slides = max(15, char_count // 120)

    prompt = f"""以下のプロダクトローンチ台本を、動画に同期するプレゼンテーションスライドに変換してください。

## 台本
{script}

---

## スライド設計の原則

### 枚数・密度
- 目標: **{target_slides}枚以上**（台本の話題転換・セクション区切りごとに1枚）
- 1スライド1メッセージ。詰め込みすぎない

### レイアウト使い分け（必ず適切に選ぶこと）
- **impact**: 数字・価格・CTA・感情的クライマックス・衝撃的な一言。全体の約30%
- **section**: 大きな話題転換・章の区切り・「では次に〜」の瞬間。全体の約20%
- **standard**: 複数ポイントの説明・機能・利用者の声・Q&A。全体の約50%

### タイトルの書き方（最重要）
- **20文字以内の断言文**
- NG（抽象）: 「商品の特徴について」
- OK（具体）: 「元手2万円で始められる」「97%が知らない勝ち筋」
- 数字・疑問・感嘆を積極活用: 「月利10%、3ヶ月で実証」「なぜ今すぐ動くべきか」

### contentの書き方
- impact / section: 0〜1個（補足のみ、なくてもよい）
- standard: 2〜4個の箇条書き
- 各項目は**20文字以内**、体言止めか短い断言文
- NG: 「〜することができます」 → OK: 「〜を実現」「〜の秘密」「〜で解決」

### 絵文字
- 台本の感情・内容に正確に合ったもの1つ
- 数字スライドは📊💰、感情スライドは😤💡、CTAは🔥⚡ など

---

## 出力形式（JSONのみ。説明文・コードブロック記号不要）

{{
  "title": "動画シリーズのタイトル",
  "slides": [
    {{
      "episode": 1,
      "layout": "impact",
      "title": "スライドタイトル（20文字以内）",
      "content": ["補足テキスト（短く）"],
      "emoji": "📈",
      "notes": "台本の該当箇所の抜粋"
    }}
  ]
}}

`episode`は必須。そのスライドが何話目かを整数で（1話完結ならすべて1）。"""

    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}]
    ) as stream:
        response = stream.get_final_message()
    # Adaptive Thinking使用時はthinkingブロックとtextブロックが混在する
    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise ValueError("スライドデータの生成に失敗しました")
    return try_parse_json(text)


def build_pptx(slide_data, design, pptx_size=(13.33, 7.5)):
    """高品質PPTXを生成する。レイアウト3種・装飾要素・テキスト階層を強化。"""
    W, H = pptx_size
    landscape = W >= H

    prs = Presentation()
    prs.slide_width  = Inches(W)
    prs.slide_height = Inches(H)
    blank = prs.slide_layouts[6]

    def _rgb(hex_color):
        h = hex_color.lstrip("#")
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    bg_rgb  = _rgb(design["bg"])
    tc_rgb  = _rgb(design["title"])
    cc_rgb  = _rgb(design["content"])
    acc_rgb = _rgb(design["accent"])

    def set_bg(slide):
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = bg_rgb

    def R(slide, l, t, w, h, color):
        """塗りつぶし矩形を追加する。"""
        shp = slide.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
        shp.fill.solid()
        shp.fill.fore_color.rgb = color
        shp.line.fill.background()
        return shp

    def T(slide, text, l, t, w, h, pt, color, bold=False, align=PP_ALIGN.LEFT):
        """テキストボックスを追加する。"""
        tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = align
        p.space_before = Pt(0)
        run = p.add_run()
        run.text = text
        run.font.size = Pt(pt)
        run.font.color.rgb = color
        run.font.bold = bold
        return tb

    def B(slide, items, l, t, w, h, pt, color):
        """箇条書きテキストボックスを追加する（行間・段落間を整える）。"""
        tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_before = Pt(8)
            p.space_after  = Pt(2)
            run = p.add_run()
            run.text = f"▸  {item}"
            run.font.size = Pt(pt)
            run.font.color.rgb = color

    # ── サイズ適応フォント・寸法 ──
    if landscape:
        f_hero   = 48   # impactメインタイトル
        f_title  = 32   # section/standardタイトル
        f_body   = 21   # 本文・箇条書き
        f_sub    = 18   # サブテキスト
        f_label  = 13   # 小ラベル
        bar      = 0.18 # アクセントバー高さ（インチ）
        lbar     = 0.28 # 太い左バー幅
        sep      = 0.04 # 細いセパレータ
    else:
        f_hero   = 36
        f_title  = 25
        f_body   = 17
        f_sub    = 15
        f_label  = 11
        bar      = 0.13
        lbar     = 0.20
        sep      = 0.03

    # ════════════════════════════════════════
    # タイトルスライド
    # ════════════════════════════════════════
    slide = prs.slides.add_slide(blank)
    set_bg(slide)
    # 上部アクセントバー
    R(slide, 0, 0, W, bar * 1.5, acc_rgb)
    # 下部アクセントエリア（太め）
    R(slide, 0, H - bar * 2.5, W, bar * 2.5, acc_rgb)
    # タイトル（中央寄せ）
    T(slide, slide_data.get("title", ""),
      W * 0.05, H * 0.22, W * 0.9, H * 0.48,
      f_hero, tc_rgb, bold=True, align=PP_ALIGN.CENTER)
    # タイトル下の装飾ライン
    R(slide, W * 0.3, H * 0.72, W * 0.4, sep, acc_rgb)

    # ════════════════════════════════════════
    # コンテンツスライド
    # ════════════════════════════════════════
    for slide_info in slide_data.get("slides", []):
        slide = prs.slides.add_slide(blank)
        set_bg(slide)

        layout  = slide_info.get("layout", "standard")
        emoji   = slide_info.get("emoji", "")
        title   = slide_info.get("title", "")
        content = slide_info.get("content", [])

        # ────────────────────────────────────
        # IMPACT レイアウト
        # 上下太バー + 左右細ライン + 中央大テキスト
        # ────────────────────────────────────
        if layout == "impact":
            R(slide, 0, 0,           W, bar * 1.8,  acc_rgb)   # 上バー
            R(slide, 0, H - bar * 1.8, W, bar * 1.8, acc_rgb) # 下バー
            R(slide, 0, bar * 1.8,   sep, H - bar * 3.6, acc_rgb)          # 左細ライン
            R(slide, W - sep, bar * 1.8, sep, H - bar * 3.6, acc_rgb)      # 右細ライン

            if emoji:
                T(slide, emoji,
                  sep + 0.18, bar * 1.8 + 0.12, 0.75, bar * 1.5,
                  f_title - 4, acc_rgb)

            has_sub = bool(content)
            ty = H * 0.25 if has_sub else H * 0.31
            # メインタイトル（特大・太字）
            T(slide, title,
              sep + 0.3, ty, W - sep * 2 - 0.6, H * 0.38,
              f_hero + 4, tc_rgb, bold=True, align=PP_ALIGN.CENTER)
            # タイトル下のアクセントライン
            R(slide, W * 0.37, ty + H * 0.38 + 0.06, W * 0.26, sep, acc_rgb)
            # サブテキスト
            if has_sub:
                sub = "　•　".join(content[:2])
                T(slide, sub,
                  sep + 0.3, ty + H * 0.38 + 0.14, W - sep * 2 - 0.6, 0.7,
                  f_sub + 1, cc_rgb, align=PP_ALIGN.CENTER)

        # ────────────────────────────────────
        # SECTION レイアウト
        # 左太バー + 上下水平ライン + 中央タイトル
        # ────────────────────────────────────
        elif layout == "section":
            R(slide, 0, 0,         lbar, H, acc_rgb)             # 左太バー
            R(slide, lbar, bar * 0.6, W - lbar, sep, acc_rgb)    # 上ライン
            R(slide, lbar, H - bar * 0.9, W - lbar, sep, acc_rgb) # 下ライン

            e_off = 0
            if emoji:
                T(slide, emoji,
                  W * 0.5 - 0.3, H * 0.26, 0.75, 0.6,
                  f_hero - 10, acc_rgb, align=PP_ALIGN.CENTER)
                e_off = 0.62
            # セクションタイトル（大・太字・中央）
            T(slide, title,
              lbar + 0.35, H * 0.38 + e_off, W - lbar - 0.5, H * 0.3,
              f_title + 8, tc_rgb, bold=True, align=PP_ALIGN.CENTER)
            if content:
                T(slide, content[0],
                  lbar + 0.35, H * 0.70 + e_off, W - lbar - 0.5, 0.55,
                  f_sub, cc_rgb, align=PP_ALIGN.CENTER)

        # ────────────────────────────────────
        # STANDARD レイアウト
        # 上バー + 左細ストライプ + タイトル + 区切り線 + 箇条書き
        # ────────────────────────────────────
        else:
            R(slide, 0, 0,    W, bar, acc_rgb)           # 上アクセントバー
            R(slide, 0, bar,  sep * 1.5, H - bar, acc_rgb)  # 左細ストライプ

            title_str = f"{emoji}  {title}" if emoji else title
            T(slide, title_str,
              sep * 1.5 + 0.2, bar + 0.12, W - sep * 1.5 - 0.3, 0.95,
              f_title, tc_rgb, bold=True)

            sep_y = bar + 1.1
            R(slide, sep * 1.5 + 0.2, sep_y, W - sep * 1.5 - 0.35, sep, acc_rgb)

            if content:
                B(slide, content,
                  sep * 1.5 + 0.28, sep_y + 0.14, W - sep * 1.5 - 0.45, H - sep_y - 0.2,
                  f_body, cc_rgb)

        # スピーカーノート
        notes = slide_info.get("notes", "")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

    output = BytesIO()
    prs.save(output)
    output.seek(0)
    return output.getvalue()


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _find_cjk_font():
    """Find a CJK-capable font on this system and cache the path."""
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # Fallback: glob search for any Noto CJK font
    import glob
    for pattern in [
        "/usr/share/fonts/**/*CJK*Regular*.ttc",
        "/usr/share/fonts/**/*CJK*Regular*.otf",
        "/usr/share/fonts/**/*Noto*Regular*.ttc",
    ]:
        matches = sorted(glob.glob(pattern, recursive=True))
        if matches:
            return matches[0]
    return None


_FONT_PATH = _find_cjk_font()


def get_font(size):
    if _FONT_PATH:
        try:
            return ImageFont.truetype(_FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def wrap_text(text, font, max_width, draw):
    lines, line = [], ""
    for ch in text:
        test = line + ch
        if draw.textlength(test, font=font) > max_width:
            lines.append(line)
            line = ch
        else:
            line = test
    if line:
        lines.append(line)
    return lines


def build_png_slides(slide_data, design, png_size=(1920, 1080)):
    """slide_dataとdesignからPNG画像リストを生成する。全サイズ対応（比例スケール）。"""
    W, H = png_size
    bg_c = hex_to_rgb(design["bg"])
    tc   = hex_to_rgb(design["title"])
    cc   = hex_to_rgb(design["content"])
    ac   = hex_to_rgb(design["accent"])

    telop_h = int(H * 0.22)
    area_h  = H - telop_h

    # 基準解像度 1920×1080 からのスケール係数
    sw = W / 1920
    sh = H / 1080
    s  = min(sw, sh)   # フォントは短辺に合わせる

    def fw(v): return max(1, int(v * sw))   # 横ピクセル
    def fh(v): return max(1, int(v * sh))   # 縦ピクセル
    def fs(v): return max(8, int(v * s))    # フォントサイズ

    f_huge    = get_font(fs(88))
    f_title   = get_font(fs(56))
    f_content = get_font(fs(36))
    f_small   = get_font(fs(28))

    lh_title   = fs(72)   # タイトル行間
    lh_content = fs(50)   # 本文行間

    def draw_centered(draw, text, font, lh, center_y, max_w, color):
        lines = wrap_text(text, font, max_w, draw)
        total = len(lines) * lh
        y = center_y - total // 2
        for line in lines:
            draw.text((W // 2, y), line, font=font, fill=color, anchor="mt")
            y += lh
        return y

    images = []

    # ── タイトルスライド ──
    img = Image.new("RGB", (W, H), bg_c)
    draw = ImageDraw.Draw(img)
    cy = area_h // 2
    draw.rectangle([0, cy - fh(6), W, cy + fh(6)], fill=ac)
    draw_centered(draw, slide_data.get("title", ""), f_huge,
                  fs(100), cy - fh(60), W - fw(120), tc)
    images.append(img)

    for slide_info in slide_data.get("slides", []):
        layout  = slide_info.get("layout", "standard")
        emoji   = slide_info.get("emoji", "")
        title   = slide_info.get("title", "")
        content = slide_info.get("content", [])

        img = Image.new("RGB", (W, H), bg_c)
        draw = ImageDraw.Draw(img)

        if layout == "impact":
            # ── インパクト：枠線＋中央大テキスト ──
            bw = max(4, fh(12))
            draw.rectangle([0, 0, W - 1, area_h - 1], outline=ac, width=bw)
            if emoji:
                draw.text((fw(60), fh(48)), emoji, font=f_title, fill=ac)
            has_sub = bool(content)
            cy = area_h // 2 - (fh(40) if has_sub else 0)
            bot = draw_centered(draw, title, f_huge, fs(100), cy, W - fw(160), tc)
            for item in (content[:2] if has_sub else []):
                draw.text((W // 2, bot + fh(12)), item, font=f_content, fill=cc, anchor="mt")
                bot += lh_content

        elif layout == "section":
            # ── セクション：左バー＋上下ライン＋中央タイトル ──
            draw.rectangle([0, 0, fw(18), H], fill=ac)
            draw.rectangle([0, 0, W, fh(10)], fill=ac)
            draw.rectangle([0, area_h - fh(10), W, area_h], fill=ac)
            emoji_off = 0
            if emoji:
                draw.text((W // 2, area_h // 2 - fh(100)),
                          emoji, font=f_huge, fill=ac, anchor="mm")
                emoji_off = fh(70)
            draw_centered(draw, title, f_title, lh_title,
                          area_h // 2 + emoji_off, W - fw(100), tc)
            if content:
                draw.text((W // 2, area_h // 2 + emoji_off + fh(90)),
                          content[0], font=f_small, fill=cc, anchor="mt")

        else:
            # ── standard：上バー＋タイトル折り返し＋箇条書き ──
            bar_h = fh(12)
            draw.rectangle([0, 0, W, bar_h], fill=ac)

            title_str = f"{emoji}  {title}" if emoji else title
            t_lines = wrap_text(title_str, f_title, W - fw(140), draw)
            y = fh(38)
            for line in t_lines:
                draw.text((fw(70), y), line, font=f_title, fill=tc)
                y += lh_title

            sep_y = y + fh(8)
            draw.rectangle([fw(70), sep_y, W - fw(70), sep_y + fh(4)], fill=ac)

            y = sep_y + fh(18)
            for item in content:
                for line in wrap_text(f"  •  {item}", f_content, W - fw(160), draw):
                    if y + lh_content > area_h:
                        break
                    draw.text((fw(80), y), line, font=f_content, fill=cc)
                    y += lh_content
                y += fh(8)

        images.append(img)

    return images


def build_png_zip(images, display_name):
    """PNG画像リストをZIPにまとめてバイナリを返す。"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, img in enumerate(images):
            img_buf = BytesIO()
            img.save(img_buf, format="PNG")
            zf.writestr(f"slide_{i+1:03d}.png", img_buf.getvalue())
    buf.seek(0)
    return buf.getvalue()


def group_slides_by_episode(slide_data):
    """スライドを episode フィールドでグループ分けして {ep_num: [slides]} を返す。"""
    groups = {}
    for s in slide_data.get("slides", []):
        ep = int(s.get("episode", 1))
        groups.setdefault(ep, []).append(s)
    return dict(sorted(groups.items()))


def build_slides_zip(slide_data, design, fmt, output_formats, display_name):
    """話数ごとにフォルダ分けし、PNG と PPTX を1つのZIPにまとめて返す。"""
    episodes = group_slides_by_episode(slide_data)
    video_title = slide_data.get("title", display_name)
    is_multi = len(episodes) > 1

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ep_num, slides in episodes.items():
            ep_label = f"第{ep_num}話" if is_multi else display_name
            ep_title = f"{video_title}　第{ep_num}話" if is_multi else video_title
            ep_data  = {"title": ep_title, "slides": slides}
            prefix   = f"{ep_label}/" if is_multi else ""

            if "PNG (.zip)" in output_formats:
                imgs = build_png_slides(ep_data, design, fmt["png"])
                for i, img in enumerate(imgs):
                    img_buf = BytesIO()
                    img.save(img_buf, format="PNG")
                    zf.writestr(f"{prefix}slide_{i+1:03d}.png", img_buf.getvalue())

            if "PPT (.pptx)" in output_formats:
                pptx_bytes = build_pptx(ep_data, design, fmt["pptx"])
                fname = f"{ep_label}.pptx" if is_multi else "slides.pptx"
                zf.writestr(f"{prefix}{fname}", pptx_bytes)

    buf.seek(0)
    return buf.getvalue()


def save_script(script, product_name):
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in product_name)
    output_path = OUTPUT_DIR / f"{timestamp}_{safe_name}.txt"
    output_path.write_text(script, encoding="utf-8")
    return output_path


# ── UI ──────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="台本生成システム", page_icon="🎬", layout="wide")
st.title("🎬 プロダクトローンチ 台本生成システム")

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    api_key = st.text_input("Anthropic APIキー", type="password", placeholder="sk-ant-...")
    if not api_key:
        st.warning("APIキーを入力してください")
        st.stop()

tavily_api_key = os.environ.get("TAVILY_API_KEY", "")

# セッション初回起動時にファイルからプリセットを読み込む
if "saved_presets" not in st.session_state:
    st.session_state["saved_presets"] = load_presets_from_file()

with st.sidebar:
    st.header("プリセット管理")
    st.caption("""
**使い方**
- **保存**：台本生成後に下部の「この入力内容を保存する」でプリセット名をつけて保存
- **呼び出し**：下のリストから選んで「呼び出す」をクリック
- **クリア**：「フォームをクリア」で入力欄を初期化（プリセットは削除されません）
- **エクスポート/インポート**：JSONファイルで他のPCへの持ち出しや共有が可能
""")

    if st.button("フォームをクリア", use_container_width=True, key="clear_form_btn"):
        clear_form_state()
        st.toast("入力内容をクリアしました")
        st.rerun()

    saved_presets = st.session_state.get("saved_presets", {})

    # 呼び出し
    if saved_presets:
        sel = st.selectbox("保存済みプリセット", ["── 選択 ──"] + list(saved_presets.keys()), key="preset_select")
        col_load, col_del = st.columns(2)
        with col_load:
            if st.button("呼び出す", use_container_width=True):
                if sel != "── 選択 ──":
                    load_preset_to_session(saved_presets[sel])
                    st.success(f"「{sel}」を読み込みました")
                    st.rerun()
        with col_del:
            if st.button("削除", use_container_width=True):
                if sel != "── 選択 ──":
                    # 削除前に復元バッファへ退避（最大5件）
                    if "recently_deleted" not in st.session_state:
                        st.session_state["recently_deleted"] = {}
                    rd = st.session_state["recently_deleted"]
                    rd[sel] = st.session_state["saved_presets"][sel]
                    if len(rd) > 5:
                        oldest = next(iter(rd))
                        del rd[oldest]
                    del st.session_state["saved_presets"][sel]
                    save_presets_to_file(st.session_state["saved_presets"])
                    st.toast(f"「{sel}」を削除しました（下の「削除済み」から復元できます）")
                    st.rerun()
    else:
        st.caption("保存済みプリセットはありません")

    # ── 削除済みプリセット（復元） ──
    recently_deleted = st.session_state.get("recently_deleted", {})
    if recently_deleted:
        st.caption("🗑️ 削除済み（復元可能）")
        for del_name in list(recently_deleted.keys()):
            col_r, col_rb = st.columns([3, 1])
            col_r.text(del_name)
            if col_rb.button("復元", key=f"restore_{del_name}"):
                st.session_state["saved_presets"][del_name] = recently_deleted[del_name]
                save_presets_to_file(st.session_state["saved_presets"])
                del st.session_state["recently_deleted"][del_name]
                st.toast(f"「{del_name}」を復元しました")
                st.rerun()

    # JSONインポート
    st.caption("JSONファイルから読み込む")
    uploaded = st.file_uploader("インポート", type=["json"], label_visibility="collapsed")
    if uploaded:
        try:
            data = json.loads(uploaded.read())
            if "saved_presets" not in st.session_state:
                st.session_state["saved_presets"] = {}
            st.session_state["saved_presets"].update(data)
            save_presets_to_file(st.session_state["saved_presets"])
            st.success("インポートしました")
            st.rerun()
        except Exception:
            st.error("JSONの読み込みに失敗しました")

    # JSONエクスポート
    if saved_presets:
        export_json = json.dumps(saved_presets, ensure_ascii=False, indent=2)
        st.download_button(
            "プリセットをエクスポート (.json)",
            data=export_json.encode("utf-8"),
            file_name="presets.json",
            mime="application/json",
            use_container_width=True,
        )

    st.divider()
    st.header("サンプル台本")
    samples = load_samples()
    if samples:
        st.success(f"{len(samples)} 件読み込み済み")
        for s in samples:
            st.text(f"• {s['filename']}")
    else:
        st.warning("samplesフォルダにファイルがありません")
    if st.button("再読み込み", use_container_width=True):
        st.rerun()

if "system_blocks" not in st.session_state or st.session_state.get("samples_count") != len(samples):
    st.session_state.system_blocks = build_system_prompt(samples)
    st.session_state.samples_count = len(samples)

# ── フォーム ─────────────────────────────────────────────────────────────────

with st.form("product_form"):

    # 構成タイプ
    st.subheader("構成タイプ")
    structure_type = st.radio(
        "タイプを選択",
        ["従来型", "フロントエンド型"],
        captions=[
            "実績提示→商品説明→販売。インタビュー or 一人語り。スマートイット・アルゴテック型。",
            "無料ノウハウ・セミナー形式で価値提供→「時間・リスクが心配な方はこちら」と商品販売に自然につなぐ。",
        ],
        horizontal=True,
        key="f_structure_type",
    )

    st.divider()

    # フロントエンド型ノウハウパート
    st.subheader("フロントエンド型ノウハウパート")
    include_knowhow = st.checkbox("ノウハウパートを含める", value=False, key="f_include_knowhow")
    st.caption("オンにすると、指定テーマのノウハウ・価値提供コンテンツを台本に自動で組み込みます")
    col_kh1, col_kh2 = st.columns(2)
    with col_kh1:
        knowhow_theme = st.text_input(
            "ノウハウのテーマ / キーワード",
            placeholder="例：FXスキャルピング、副業で稼ぐ方法、仮想通貨の始め方",
            key="f_knowhow_theme",
        )
    with col_kh2:
        knowhow_notes = st.text_area(
            "ノウハウの補足メモ（任意）",
            placeholder="例：初心者向けに5分足を使った手法を説明したい、具体的なエントリーポイントを入れてほしい",
            height=80,
            key="f_knowhow_notes",
        )

    st.divider()

    # 商品・基本情報
    st.subheader("商品・基本情報")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("商品名", placeholder="例：スマートイット", key="f_name")
        category = st.selectbox("ジャンル", [
            "FX・為替投資", "株式投資・トレード", "仮想通貨・Web3",
            "副業・ビジネス", "美容・スキンケア", "健康・ダイエット",
            "教育・スキルアップ", "テック・SaaS", "食品・サプリ", "その他"
        ], key="f_category")
        seller_name = st.text_input("販売者名", placeholder="例：はたけ", key="f_seller_name")
        seller_profile = st.text_area(
            "販売者のプロフィール",
            placeholder="例：元会社員で副業からFXを始め、3年で脱サラ。現在はFX系YouTuberとして活動中。フォロワー10万人。",
            height=80, key="f_seller_profile",
        )
        interviewer_name = st.text_input(
            "インタビュアー名（空欄で一人語り形式）",
            placeholder="例：ふじき　　※空欄→モノローグ形式",
            key="f_interviewer_name",
        )
        interviewer_profile = st.text_area(
            "インタビュアーのプロフィール（任意）",
            placeholder="例：元銀行員、現在は投資系メディアのライター。読者目線で質問するのが得意。",
            height=80, key="f_interviewer_profile",
        )
        seller_authority = st.text_input("販売者の権威・実績", placeholder="例：FX系YouTuber、動画1500本以上、5年以上活動", key="f_seller_authority")
    with col2:
        catchcopy = st.text_input("キャッチコピー", placeholder="例：月5分で月10万円", key="f_catchcopy")
        target_audience = st.text_input("ターゲット層", placeholder="例：投資初心者、副業したい人", key="f_target_audience")
        result1 = st.text_input("実績数値①", placeholder="例：3ヶ月で31万円の利益", key="f_result1")
        result2 = st.text_input("実績数値②", placeholder="例：1年で125万円の利益", key="f_result2")
        monthly_return = st.text_input("月利 / 月収目安", placeholder="例：月利10%、月10万円", key="f_monthly_return")
        ease_of_start = st.text_input("始めやすさの根拠", placeholder="例：2万円から、スマホだけでOK", key="f_ease_of_start")

    st.markdown("**商品の強み**（入力した分だけ使用）")
    s_cols = st.columns(4)
    strength_placeholders = [
        "例：証拠金2万円から始められる",
        "例：勝率78%で安心感がある",
        "例：ドローダウン平均10%以下",
        "例：完全自動、ON/OFFも不要",
    ]
    strengths = []
    for i, col in enumerate(s_cols):
        s = col.text_input(f"強み{i+1}", key=f"str_{i}", label_visibility="collapsed", placeholder=strength_placeholders[i])
        strengths.append(s)

    st.divider()

    # 利用者の声
    st.subheader("利用者の声（喜びの声）")
    st.caption("名前・属性と声のセットで入力してください")
    voice1 = st.text_input("声①", placeholder="例：30代会社員Aさん：導入1ヶ月で8万円の利益が出ました！初心者でも全く問題なかったです。", key="f_voice1")
    voice2 = st.text_input("声②", placeholder="例：40代主婦Bさん：スマホだけで設定できて、今は毎月安定して収入が入っています。", key="f_voice2")
    voice3 = st.text_input("声③", placeholder="例：20代フリーランスCさん：他のシステムで失敗したけどこれは違いました。", key="f_voice3")

    st.divider()

    # 社会背景・痛み訴求
    st.subheader("社会背景・痛み訴求")
    col3, col4 = st.columns(2)
    with col3:
        pain_points = st.text_area("視聴者のペイン", placeholder="例：残業しても給料が上がらない、将来が不安、副業する時間がない", height=100, key="f_pain_points")
    with col4:
        why_now = st.text_area("なぜ今必要か（why now）", placeholder="例：物価は上がるのに賃金は上がらない。自分で資産を作るしかない。", height=100, key="f_why_now")

    st.divider()

    # 第三者・信頼性
    st.subheader("第三者・信頼性")
    col5, col6, col7 = st.columns(3)
    with col5:
        third_party_type = st.selectbox("第三者の種類", ["なし", "開発者・専門家", "ユーザー・実践者", "有識者・研究者", "著名人・インフルエンサー"], key="f_third_party_type")
    with col6:
        third_party_name = st.text_input("名前・肩書き", placeholder="例：桑田（システム開発者）", key="f_third_party_name")
    with col7:
        third_party_points = st.text_input("第三者の裏付けポイント", placeholder="例：2万通りのロジックを検証、14歳からシステム開発", key="f_third_party_points")

    st.divider()

    # 販売フロー
    st.subheader("販売フロー")
    sales_flow_type = st.radio(
        "販売フロータイプを選択",
        ["直接販売型", "面談・相談誘導型"],
        captions=[
            "ローンチ動画から直接購入ページへ誘導して販売する",
            "個別Zoom面談・LINE相談などに誘導し、個別接触後に販売する",
        ],
        horizontal=True,
        key="f_sales_flow_type",
    )
    col_sf1, col_sf2 = st.columns(2)
    with col_sf1:
        sales_start_day = st.selectbox(
            "販売スタート日（直接販売型）",
            [
                "当日（即時販売）",
                "翌日（1日後）",
                "翌々日（2日後）",
                "3日後",
                "4日後",
                "5日後",
                "7日後（1週間後）",
                "その他（追加メモに記載）",
            ],
            index=1,
            key="f_sales_start_day",
            help="直接販売型を選択した場合に使用されます",
        )
    with col_sf2:
        consultation_method = st.text_input(
            "誘導先の詳細（面談・相談誘導型）",
            placeholder="例：個別Zoom面談、LINE@で個別相談",
            key="f_consultation_method",
            help="面談・相談誘導型を選択した場合に使用されます",
        )

    st.divider()

    # 価格・オファー
    st.subheader("価格・オファー")
    col8, col9, col10 = st.columns(3)
    with col8:
        regular_price = st.text_input("定価", placeholder="例：158,000円", key="f_regular_price")
        special_price = st.text_input("特別価格", placeholder="例：98,000円", key="f_special_price")
    with col9:
        limited_time = st.text_input("期間限定条件", placeholder="例：3日間限定", key="f_limited_time")
        limited_seats = st.text_input("先着・定員制限（任意）", placeholder="例：先着50名様、定員30名", key="f_limited_seats")
        installment = st.selectbox("分割対応", ["なし", "あり"], key="f_installment")
    with col10:
        bonuses = st.text_area("特典内容（カンマ区切り）", placeholder="例：導入マニュアル、トレーダー手法、キャッシュを増やす方法", height=100, key="f_bonuses")

    st.divider()

    # コメント促進パート
    st.subheader("コメント促進パート（動画末尾）")
    st.caption("話ごとに含める/含めないを選択できます。質問は空欄で自動生成します。")
    comment_includes = []
    comment_prompts = []
    for i in range(5):
        col_a, col_b = st.columns([1, 4])
        with col_a:
            include = st.checkbox(f"第{i+1}話", key=f"comment_include_{i}", value=True)
        with col_b:
            cp = st.text_input(
                f"第{i+1}話の質問",
                key=f"comment_{i}",
                label_visibility="collapsed",
                placeholder="質問を入力（空欄で自動生成）"
            )
        comment_includes.append(include)
        comment_prompts.append(cp)

    st.divider()

    # 構成オプション
    st.subheader("構成オプション")
    col11, col12 = st.columns(2)
    with col11:
        episode_structure = st.selectbox("話数構成", [
            "1話完結", "2話構成（前編・後編）", "3話構成", "4話構成", "5話構成"
        ], key="f_episode_structure")
        closing_strength = st.selectbox("クロージングの強度", [
            "真摯・控えめ（押し付けない）", "標準（バランス型）", "強め（urgency高め）", "最強（限定・希少性全開）"
        ], key="f_closing_strength")
        video_duration = st.selectbox("1話あたりの動画の長さ", [
            "3分（約900文字）",
            "5分（約1,500文字）",
            "7分（約2,100文字）",
            "10分（約3,000文字）",
            "15分（約4,500文字）",
            "20分（約6,000文字）",
            "30分（約9,000文字）",
            "45分（約13,500文字）",
            "60分（約18,000文字）",
            "90分（約27,000文字）",
            "120分（約36,000文字）",
        ], index=2, key="f_video_duration")
    with col12:
        notes = st.text_area("追加メモ（任意）", placeholder="例：競合との比較を入れたい、このワードは避けたいなど", height=100, key="f_notes")

    st.divider()

    # 話数ごとの内容指定
    st.subheader("話数ごとの内容指定")
    use_episode_themes = st.checkbox("各話の内容・テーマを指定する", value=False, key="f_use_episode_themes")
    st.caption("オンにすると、各話で話す内容を個別に指定できます。空欄の話はAIが自動で構成します。")
    episode_themes = []
    for i in range(5):
        theme = st.text_area(
            f"第{i+1}話の内容・テーマ",
            placeholder=f"例：第{i+1}話では〇〇について話す。ポイントは△△と□□。",
            height=80,
            key=f"episode_theme_{i}",
        )
        episode_themes.append(theme)

    st.divider()

    use_trend_search = st.checkbox(
        "最新トレンドをWeb検索して台本に反映する",
        value=False,
        disabled=not tavily_api_key,
        help="TavilyのAPIキーが設定されている場合に利用できます",
    )

    submitted = st.form_submit_button("台本を生成する", type="primary", use_container_width=True)

# ── 生成処理 ──────────────────────────────────────────────────────────────────

DURATION_MAX_TOKENS = {
    "3分": 2048,
    "5分": 3000,
    "7分": 4096,
    "10分": 6000,
    "15分": 8192,
    "20分": 12000,
    "30分": 16000,
    "45分": 20000,
    "60分": 24000,
    "90分": 28000,
    "120分": 32000,
}


def run_generation(client, system_blocks, messages, display_name, max_tokens=4096):
    """Claudeにリクエストを送りストリーミング表示する。台本とstatsを返す。"""
    script = ""
    placeholder = st.empty()
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            script += text
            placeholder.markdown(script)
        final = stream.get_final_message()
    usage = final.usage
    stats = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }
    return script, stats


def show_download(script, display_name, stats):
    """統計情報とダウンロードボタンを表示する。"""
    output_path = save_script(script, display_name)
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("入力トークン", f"{stats['input_tokens']:,}")
    c2.metric("出力トークン", f"{stats['output_tokens']:,}")
    if stats["cache_creation_tokens"]:
        c3.metric("キャッシュ書込み", f"{stats['cache_creation_tokens']:,}")
    if stats["cache_read_tokens"]:
        c4.metric("キャッシュ読込み", f"{stats['cache_read_tokens']:,}")
    st.success(f"保存済み: {output_path}")
    st.download_button(
        "台本をダウンロード (.txt)",
        data=script.encode("utf-8"),
        file_name=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{display_name}.txt",
        mime="text/plain",
        use_container_width=True,
        key=f"dl_{datetime.now().strftime('%H%M%S%f')}",
    )


if submitted:
    info = {
        "structure_type": structure_type,
        "include_knowhow": include_knowhow,
        "knowhow_theme": knowhow_theme,
        "knowhow_notes": knowhow_notes,
        "name": name, "category": category,
        "seller_name": seller_name, "seller_profile": seller_profile,
        "interviewer_name": interviewer_name, "interviewer_profile": interviewer_profile,
        "seller_authority": seller_authority,
        "catchcopy": catchcopy, "target_audience": target_audience,
        "result1": result1, "result2": result2,
        "monthly_return": monthly_return, "ease_of_start": ease_of_start,
        "strengths": strengths,
        "voices": [voice1, voice2, voice3],
        "pain_points": pain_points, "why_now": why_now,
        "third_party_type": third_party_type, "third_party_name": third_party_name,
        "third_party_points": third_party_points,
        "regular_price": regular_price, "special_price": special_price,
        "limited_time": limited_time, "limited_seats": limited_seats,
        "installment": installment, "bonuses": bonuses,
        "comment_includes": comment_includes,
        "comment_prompts": comment_prompts,
        "episode_structure": episode_structure, "closing_strength": closing_strength,
        "video_duration": video_duration,
        "use_episode_themes": use_episode_themes,
        "episode_themes": episode_themes,
        "notes": notes,
        "sales_flow_type": sales_flow_type,
        "sales_start_day": sales_start_day,
        "consultation_method": consultation_method,
    }
    user_prompt = build_user_prompt(info)
    display_name = name if name else "台本"

    # トレンド検索
    if use_trend_search and tavily_api_key:
        with st.spinner("最新トレンドを検索中..."):
            trends = search_trends(tavily_api_key, info.get("category", ""), info.get("name", ""))
        if trends:
            user_prompt += f"\n\n## 最新トレンド・時事情報（Web検索結果）\n{trends}\n\n上記のトレンド情報も台本に自然に盛り込んでください。"
            st.info("最新トレンドを取得しました。台本に反映します。")

    st.divider()
    st.subheader("生成結果")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        # 動画の長さからmax_tokensを決定
        duration_key = info.get("video_duration", "7分（約2,100文字）").split("（")[0]
        episode_num = int(info.get("episode_structure", "1話完結")[0]) if info.get("episode_structure", "1")[0].isdigit() else 1
        base_tokens = DURATION_MAX_TOKENS.get(duration_key, 4096)
        max_tokens = min(base_tokens * episode_num, 32000)

        messages = [{"role": "user", "content": user_prompt}]
        script, stats = run_generation(client, st.session_state.system_blocks, messages, display_name, max_tokens)

        # セッションに保存（再編集用）
        st.session_state.current_script = script
        st.session_state.current_messages = messages
        st.session_state.display_name = display_name
        st.session_state.last_info = info

        show_download(script, display_name, stats)

    except anthropic.APIError as e:
        st.error(f"APIエラー: {e}")


# ── 再編集パネル ──────────────────────────────────────────────────────────────

if "current_script" in st.session_state:

    # ── プリセット保存（フォーム外で常時動作）──
    st.divider()
    st.subheader("この入力内容を保存する")
    col_pn, col_pb = st.columns([3, 1])
    with col_pn:
        preset_name = st.text_input("プリセット名", placeholder="例：スマートイット用、FX商品A用", key="preset_save_name")
    with col_pb:
        st.write("")
        if st.button("保存する", use_container_width=True, key="save_preset_btn"):
            if preset_name and "last_info" in st.session_state:
                if "saved_presets" not in st.session_state:
                    st.session_state["saved_presets"] = {}
                st.session_state["saved_presets"][preset_name] = st.session_state.last_info
                save_presets_to_file(st.session_state["saved_presets"])
                st.success(f"「{preset_name}」を保存しました。左のサイドバーから呼び出せます。")
            elif not preset_name:
                st.warning("プリセット名を入力してください")

    st.divider()
    st.subheader("再編集")
    st.caption("生成した台本に修正指示を出して再生成できます")

    edit_instruction = st.text_area(
        "修正指示",
        placeholder="例：クロージングをもっと強くして\n例：オープニングの問いかけを変えて\n例：〇〇のセクションを削除して",
        height=100,
        key="edit_instruction",
    )

    if st.button("再編集する", type="primary", use_container_width=True):
        if not edit_instruction.strip():
            st.warning("修正指示を入力してください")
        else:
            try:
                client = anthropic.Anthropic(api_key=api_key)
                display_name = st.session_state.display_name

                messages = st.session_state.current_messages + [
                    {"role": "assistant", "content": st.session_state.current_script},
                    {"role": "user", "content": f"以下の修正指示に従って台本を修正してください：\n\n{edit_instruction}"},
                ]

                st.subheader("修正結果")
                script, stats = run_generation(client, st.session_state.system_blocks, messages, display_name)

                st.session_state.current_script = script
                st.session_state.current_messages = messages

                show_download(script, display_name, stats)

            except anthropic.APIError as e:
                st.error(f"APIエラー: {e}")

    # ── スライド生成 ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("スライド作成")

    # スライドフォーマット・デザイン設定
    col_f, col_d1 = st.columns(2)
    with col_f:
        slide_format = st.selectbox("スライドフォーマット", list(SLIDE_FORMATS.keys()))
    with col_d1:
        design_preset = st.selectbox("デザインプリセット", list(DESIGN_PRESETS.keys()) + ["カスタム"])
    if design_preset == "カスタム":
        dc1, dc2, dc3, dc4 = st.columns(4)
        bg_c    = dc1.color_picker("背景色",      "#1a1a1a")
        title_c = dc2.color_picker("タイトル色",  "#ffffff")
        cont_c  = dc3.color_picker("テキスト色",  "#e0e0e0")
        acc_c   = dc4.color_picker("アクセント色", "#4a9eff")
        design = {"bg": bg_c, "title": title_c, "content": cont_c, "accent": acc_c}
    else:
        design = DESIGN_PRESETS[design_preset]

    output_formats = st.multiselect(
        "出力形式", ["PPT (.pptx)", "PNG (.zip)"], default=["PPT (.pptx)"],
    )

    if st.button("スライドを作成する", use_container_width=True):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            chunks = split_script_into_chunks(st.session_state.current_script)
            total  = len(chunks)

            # 分割内容を事前に表示
            if total > 1:
                labels = " / ".join(lbl for _, lbl, _ in chunks)
                st.info(f"台本を **{total} 分割** して順番に生成します：{labels}")

            progress = st.progress(0)
            status   = st.empty()

            all_slides  = []
            video_title = ""

            for i, (ep_num, label, chunk_text) in enumerate(chunks):
                status.text(f"生成中：{label}（{i + 1} / {total}）")
                chunk_data = generate_slide_data(client, chunk_text)

                if not video_title:
                    video_title = chunk_data.get("title", "")

                for slide in chunk_data.get("slides", []):
                    slide["episode"] = ep_num
                    all_slides.append(slide)

                progress.progress((i + 1) / total)

            status.text("✅ 全チャンク生成完了！")
            slide_data = {"title": video_title, "slides": all_slides}

            st.session_state.slide_data           = slide_data
            st.session_state.slide_design         = design
            st.session_state.slide_format         = slide_format
            st.session_state.slide_output_formats = output_formats
            st.session_state.slide_preview_ready  = True
            st.session_state.slide_approved       = False
            for k in ("slide_pptx_bytes", "slide_zip_bytes", "slide_output_ts"):
                st.session_state.pop(k, None)
            st.rerun()
        except Exception as e:
            st.error(f"スライド生成エラー: {e}")

    # ── プレビュー & 承認フロー ──
    if st.session_state.get("slide_preview_ready"):
        _sd      = st.session_state.slide_data
        _design  = st.session_state.slide_design
        _fmt     = SLIDE_FORMATS[st.session_state.slide_format]
        _ofmts   = st.session_state.get("slide_output_formats", ["PPT (.pptx)"])
        _count   = len(_sd.get("slides", []))

        if not st.session_state.get("slide_approved"):
            # ── 全スライドプレビュー（サムネイル一覧）──
            st.info(f"全 **{_count} 枚**を確認してから出力してください。文字ズレや内容がおかしいスライドがないか確認してください。")

            orig_w, orig_h = _fmt["png"]
            prev_size = (orig_w // 4, orig_h // 4)

            with st.spinner(f"全スライドのプレビューを生成中（{_count} 枚）..."):
                prev_imgs = build_png_slides(_sd, _design, prev_size)

            n_cols = 4
            labels = ["タイトル"] + [f"スライド {i+1}" for i in range(len(prev_imgs) - 1)]
            for row_start in range(0, len(prev_imgs), n_cols):
                row = prev_imgs[row_start:row_start + n_cols]
                row_labels = labels[row_start:row_start + n_cols]
                cols = st.columns(n_cols)
                for col, img, lbl in zip(cols, row, row_labels):
                    col.image(img, caption=lbl, use_container_width=True)

            st.divider()
            col_ok, col_ng = st.columns(2)
            with col_ok:
                if st.button("OK、全部出力する", type="primary", use_container_width=True, key="slide_ok_btn"):
                    st.session_state.slide_approved = True
                    st.rerun()
            with col_ng:
                if st.button("やり直す（再生成）", use_container_width=True, key="slide_retry_btn"):
                    for k in ("slide_preview_ready", "slide_approved", "slide_data",
                              "slide_pptx_bytes", "slide_zip_bytes"):
                        st.session_state.pop(k, None)
                    st.rerun()

        else:
            # ── 全スライド出力（初回のみ生成してキャッシュ）──
            display_name = st.session_state.display_name
            ts = st.session_state.setdefault("slide_output_ts", datetime.now().strftime("%Y%m%d_%H%M%S"))

            if "slide_zip_bytes" not in st.session_state:
                episodes = group_slides_by_episode(_sd)
                ep_count = len(episodes)
                label = f"{_count} 枚 / {ep_count} 話" if ep_count > 1 else f"{_count} 枚"
                with st.spinner(f"スライドを出力中（{label}）..."):
                    st.session_state.slide_zip_bytes = build_slides_zip(
                        _sd, _design, _fmt, _ofmts, display_name
                    )

            episodes = group_slides_by_episode(_sd)
            is_multi = len(episodes) > 1
            if is_multi:
                ep_labels = "・".join(f"第{ep}話" for ep in episodes)
                st.info(f"フォルダ構成: {ep_labels}")

            st.download_button(
                "スライドをダウンロード (.zip)",
                data=st.session_state.slide_zip_bytes,
                file_name=f"{ts}_{display_name}_slides.zip",
                mime="application/zip",
                use_container_width=True,
                key="dl_slides_main",
            )
            st.success(f"全 {_count} 枚の出力が完了しました")

            if st.button("スライドを作り直す", use_container_width=True, key="slide_redo_btn"):
                for k in ("slide_preview_ready", "slide_approved",
                          "slide_zip_bytes", "slide_output_ts"):
                    st.session_state.pop(k, None)
                st.rerun()

    # ── スライド修正 ──────────────────────────────────────────────────────────
    if "slide_data" in st.session_state:
        st.divider()
        st.subheader("スライド修正")
        st.caption("生成したスライドに修正指示を出して再生成できます")

        slide_edit = st.text_area(
            "修正指示",
            placeholder="例：スライド3のタイトルを変えて\n例：箇条書きをもっと短くして\n例：スライドを5枚追加して",
            height=100,
            key="slide_edit_instruction",
        )

        if st.button("スライドを修正する", use_container_width=True):
            if not slide_edit.strip():
                st.warning("修正指示を入力してください")
            else:
                try:
                    client = anthropic.Anthropic(api_key=api_key)
                    current_json = json.dumps(st.session_state.slide_data, ensure_ascii=False, indent=2)
                    revise_prompt = f"""以下のスライドデータを修正指示に従って修正してください。

## 現在のスライドデータ（JSON）
{current_json}

## 修正指示
{slide_edit}

## 出力ルール
- JSONのみ出力。前後の説明文・コードブロック記号は不要。
- 元のJSON構造を維持してください。"""

                    with st.spinner("スライドを修正中..."):
                        response = client.messages.create(
                            model=MODEL,
                            max_tokens=32000,
                            messages=[{"role": "user", "content": revise_prompt}]
                        )
                        text = response.content[0].text
                        slide_data = try_parse_json(text)
                        st.session_state.slide_data = slide_data

                    slide_count = len(slide_data.get("slides", []))
                    st.success(f"修正完了：{slide_count} 枚")
                    design = st.session_state.get("slide_design", DESIGN_PRESETS["ダーク（黒背景・白文字）"])
                    fmt = SLIDE_FORMATS.get(st.session_state.get("slide_format", list(SLIDE_FORMATS.keys())[0]))
                    rev_ofmts = st.session_state.get("slide_output_formats", ["PPT (.pptx)"])
                    display_name = st.session_state.display_name
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    # 修正後ZIPを再生成
                    with st.spinner("出力ZIPを生成中..."):
                        rev_zip = build_slides_zip(slide_data, design, fmt, rev_ofmts, display_name)
                    st.session_state.slide_zip_bytes = rev_zip
                    st.session_state.slide_approved = True
                    st.session_state.pop("slide_output_ts", None)

                    st.download_button(
                        "修正済みスライドをダウンロード (.zip)",
                        data=rev_zip,
                        file_name=f"{ts}_{display_name}_revised_slides.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="dl_revised_zip",
                    )

                except Exception as e:
                    st.error(f"スライド修正エラー: {e}")
