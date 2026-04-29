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
OUTPUT_DIR = Path("output")
MODEL = "claude-opus-4-7"


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
            "以下のサンプル台本のスタイル・構成・トーン・語彙・リズムを分析し、"
            "同じスタイルで新しい台本を作成してください。\n\n"
            "分析のポイント:\n"
            "- 構成の型（オープニング→問題提起→解決策→特徴→CTA など）\n"
            "- トーンと語彙（丁寧語・親しみやすさ・専門性）\n"
            "- 文章のリズムと長さ\n"
            "- 聴衆への語りかけ方\n"
            "- 特徴や利点の伝え方\n"
            "- コール・トゥ・アクションの形式\n"
        ),
    }
    if not samples:
        instruction_block["text"] += "\nサンプルがないため、一般的なプロダクトローンチのベストプラクティスに従って生成してください。"
        return [instruction_block]

    samples_text = "\n\n".join(
        f"=== サンプル {i + 1}: {s['filename']} ===\n{s['content']}"
        for i, s in enumerate(samples)
    )
    samples_block = {
        "type": "text",
        "text": f"## 学習用サンプル台本\n\n{samples_text}",
        "cache_control": {"type": "ephemeral"},
    }
    return [instruction_block, samples_block]


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
    """Claudeに台本を渡してスライド構成をJSON形式で生成する。"""
    # 台本の文字数から目標スライド枚数を算出（約120文字に1枚、最低15枚）
    char_count = len(script.replace(" ", "").replace("\n", ""))
    target_slides = max(15, char_count // 120)

    prompt = f"""これはプロダクトローンチ動画の台本です。
この台本に完全同期する動画用スライドを作成してください。
スライドは「まとめ」ではなく、台本を読み上げながら視聴者が見るリアルタイム字幕スライドです。

## 台本
{script}

## スライド作成の基本方針
- 台本の【セクション】や話題の切れ目ごとに必ずスライドを1枚作成する
- 目標スライド枚数：**{target_slides}枚以上**（台本が長い場合はさらに増やす）
- 1枚のスライドが担当するナレーション量は台本の2〜4文程度が目安
- 話題が変わったら必ず新しいスライドにする（オープニング・問題提起・解決策・実績・価格・CTAなど各パートで最低1枚）

## デザインルール
- プロのデザイナーが作ったような洗練されたスライド構成
- 下部20%はテロップスペースなので、テキストは上寄せ配置
- 各スライドに台本内容に合った絵文字を `emoji` フィールドで指定
- タイトルは短く印象的に（20文字以内）
- 箇条書きは1スライド最大4つ、各項目は簡潔に（30文字以内）
- 箇条書きが不要なスライド（インパクト重視の1行メッセージなど）は `content` を空配列にしてよい

## 自己チェック（出力前に必ず確認）
- スライド枚数が{target_slides}枚以上あるか
- 台本の各セクション・場面転換に対応したスライドが存在するか
- タイトルと本文の内容が重複していないか
- emoji は台本の内容とマッチしているか

## 出力ルール
- JSONのみ出力。説明文・コードブロック記号（```）は不要
- 必ず以下のJSON形式を守ること

## JSON形式
{{
  "title": "動画タイトル",
  "slides": [
    {{
      "title": "スライドタイトル",
      "content": ["箇条書き1", "箇条書き2"],
      "emoji": "📈",
      "notes": "このスライドに対応するナレーション（台本の該当部分をそのまま抜粋）"
    }}
  ]
}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError("スライドデータの生成に失敗しました")
    return json.loads(match.group())


def build_pptx(slide_data, design, pptx_size=(13.33, 7.5)):
    """slide_dataとdesignからデザイン適用済みPPTXバイナリを生成して返す。"""
    W, H = pptx_size

    prs = Presentation()
    prs.slide_width  = Inches(W)
    prs.slide_height = Inches(H)

    blank = prs.slide_layouts[6]  # 完全ブランクレイアウト

    def _rgb(hex_color):
        h = hex_color.lstrip("#")
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    bg_rgb    = _rgb(design["bg"])
    title_rgb = _rgb(design["title"])
    cont_rgb  = _rgb(design["content"])
    acc_rgb   = _rgb(design["accent"])

    def set_bg(slide):
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = bg_rgb

    def add_rect(slide, left, top, width, height, color):
        shape = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()
        return shape

    def add_textbox(slide, text, left, top, width, height, font_size, color, bold=False, align=PP_ALIGN.LEFT):
        txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = align
        run = p.add_run()
        run.text = text
        run.font.size = Pt(font_size)
        run.font.color.rgb = color
        run.font.bold = bold

    def add_bullets(slide, items, left, top, width, height, font_size, color):
        txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = txBox.text_frame
        tf.word_wrap = True
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            run = p.add_run()
            run.text = f"  •  {item}"
            run.font.size = Pt(font_size)
            run.font.color.rgb = color

    # 縦型か横型かでフォントサイズを調整
    landscape = W > H
    title_main_pt = 40 if landscape else 32
    title_pt      = 28 if landscape else 22
    content_pt    = 20 if landscape else 17

    # ── タイトルスライド ──
    slide = prs.slides.add_slide(blank)
    set_bg(slide)
    add_rect(slide, 0, H / 2 - 0.06, W, 0.12, acc_rgb)
    add_textbox(slide, slide_data.get("title", ""),
                0.5, H / 2 - 1.3, W - 1, 1.1,
                title_main_pt, title_rgb, bold=True, align=PP_ALIGN.CENTER)

    # ── コンテンツスライド ──
    for slide_info in slide_data.get("slides", []):
        slide = prs.slides.add_slide(blank)
        set_bg(slide)

        # 上部アクセントバー
        add_rect(slide, 0, 0, W, 0.12, acc_rgb)

        # タイトル
        emoji = slide_info.get("emoji", "")
        title_text = f"{emoji}  {slide_info.get('title', '')}" if emoji else slide_info.get("title", "")
        add_textbox(slide, title_text, 0.4, 0.22, W - 0.8, 0.85, title_pt, title_rgb, bold=True)

        # 区切り線
        add_rect(slide, 0.4, 1.15, W - 0.8, 0.05, acc_rgb)

        # 箇条書き
        content_items = slide_info.get("content", [])
        if content_items:
            add_bullets(slide, content_items, 0.5, 1.3, W - 1, H - 1.7, content_pt, cont_rgb)

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


def get_font(size):
    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]
    for p in font_paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
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
    """slide_dataとdesignからPNG画像リストを生成する。"""
    W, H = png_size
    bg  = hex_to_rgb(design["bg"])
    tc  = hex_to_rgb(design["title"])
    cc  = hex_to_rgb(design["content"])
    ac  = hex_to_rgb(design["accent"])

    font_title_main = get_font(80)
    font_title      = get_font(56)
    font_content    = get_font(38)

    images = []

    # タイトルスライド
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, H//2 - 6, W, H//2 + 6], fill=ac)
    title_text = slide_data.get("title", "")
    draw.text((W // 2, H // 2 - 60), title_text, font=font_title_main, fill=tc, anchor="mm")
    images.append(img)

    # コンテンツスライド
    for slide_info in slide_data.get("slides", []):
        img = Image.new("RGB", (W, H), bg)
        draw = ImageDraw.Draw(img)

        # アクセントバー（上部）
        draw.rectangle([0, 0, W, 14], fill=ac)

        # タイトル（絵文字付き）
        emoji = slide_info.get("emoji", "")
        title_text = f"{emoji}  {slide_info.get('title', '')}" if emoji else slide_info.get("title", "")
        draw.text((80, 60), title_text, font=font_title, fill=tc)

        # 区切り線
        draw.rectangle([80, 160, W - 80, 168], fill=ac)

        # 箇条書き（下部20%はテロップスペースとして空ける）
        max_y = int(H * 0.78)
        y = 210
        for item in slide_info.get("content", []):
            wrapped = wrap_text(f"  •  {item}", font_content, W - 200, draw)
            for line in wrapped:
                if y + 58 > max_y:
                    break
                draw.text((100, y), line, font=font_content, fill=cc)
                y += 58
            y += 10

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

with st.sidebar:
    st.header("プリセット管理")
    st.caption("""
**使い方**
- **保存**：台本生成後に下部の「この入力内容を保存する」でプリセット名をつけて保存
- **呼び出し**：下のリストから選んで「呼び出す」をクリック
- **エクスポート/インポート**：JSONファイルで他のPCへの持ち出しや共有が可能
""")

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
                    del st.session_state["saved_presets"][sel]
                    st.rerun()
    else:
        st.caption("保存済みプリセットはありません")

    # JSONインポート
    st.caption("JSONファイルから読み込む")
    uploaded = st.file_uploader("インポート", type=["json"], label_visibility="collapsed")
    if uploaded:
        try:
            data = json.loads(uploaded.read())
            if "saved_presets" not in st.session_state:
                st.session_state["saved_presets"] = {}
            st.session_state["saved_presets"].update(data)
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

        # プリセット保存
        st.divider()
        st.subheader("この入力内容を保存する")
        col_pn, col_pb = st.columns([3, 1])
        with col_pn:
            preset_name = st.text_input("プリセット名", placeholder="例：スマートイット用、FX商品A用", key="preset_save_name")
        with col_pb:
            st.write("")
            if st.button("保存する", use_container_width=True, key="save_preset_btn"):
                if preset_name:
                    if "saved_presets" not in st.session_state:
                        st.session_state["saved_presets"] = {}
                    st.session_state["saved_presets"][preset_name] = info
                    st.success(f"「{preset_name}」を保存しました。左のサイドバーから呼び出せます。")

    except anthropic.APIError as e:
        st.error(f"APIエラー: {e}")


# ── 再編集パネル ──────────────────────────────────────────────────────────────

if "current_script" in st.session_state:
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
    st.caption("台本が完成したらYouTube横動画用スライドを自動生成します（16:9 / 1920×1080）")

    # スライドフォーマット・デザイン設定
    col_f, col_d1 = st.columns(2)
    with col_f:
        slide_format = st.selectbox("スライドフォーマット", list(SLIDE_FORMATS.keys()))
    with col_d1:
        design_preset = st.selectbox("デザインプリセット", list(DESIGN_PRESETS.keys()) + ["カスタム"])
    if design_preset == "カスタム":
        with col_d2:
            dc1, dc2, dc3, dc4 = st.columns(4)
            bg_c    = dc1.color_picker("背景色",     "#1a1a1a")
            title_c = dc2.color_picker("タイトル色", "#ffffff")
            cont_c  = dc3.color_picker("テキスト色", "#e0e0e0")
            acc_c   = dc4.color_picker("アクセント色","#4a9eff")
            design = {"bg": bg_c, "title": title_c, "content": cont_c, "accent": acc_c}
    else:
        design = DESIGN_PRESETS[design_preset]

    # 出力形式
    output_formats = st.multiselect(
        "出力形式",
        ["PPT (.pptx)", "PNG (.zip)"],
        default=["PPT (.pptx)"],
    )

    if st.button("スライドを作成する", use_container_width=True):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            with st.spinner("スライド構成を生成中..."):
                slide_data = generate_slide_data(client, st.session_state.current_script)

            fmt = SLIDE_FORMATS[slide_format]
            st.session_state.slide_data = slide_data
            st.session_state.slide_design = design
            st.session_state.slide_format = slide_format
            slide_count = len(slide_data.get("slides", []))
            st.success(f"{slide_count} 枚のスライドを生成しました")

            display_name = st.session_state.display_name
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

            if "PPT (.pptx)" in output_formats:
                with st.spinner("PPTXを作成中..."):
                    pptx_bytes = build_pptx(slide_data, design, fmt["pptx"])
                st.download_button(
                    "PPTをダウンロード (.pptx)",
                    data=pptx_bytes,
                    file_name=f"{ts}_{display_name}_slides.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )

            if "PNG (.zip)" in output_formats:
                with st.spinner("PNG画像を生成中..."):
                    images = build_png_slides(slide_data, design, fmt["png"])
                    zip_bytes = build_png_zip(images, display_name)
                st.download_button(
                    "PNGをダウンロード (.zip)",
                    data=zip_bytes,
                    file_name=f"{ts}_{display_name}_slides_png.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        except Exception as e:
            st.error(f"スライド生成エラー: {e}")

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
                            max_tokens=8192,
                            messages=[{"role": "user", "content": revise_prompt}]
                        )
                        text = response.content[0].text
                        match = re.search(r'\{.*\}', text, re.DOTALL)
                        if not match:
                            raise ValueError("修正データの生成に失敗しました")
                        slide_data = json.loads(match.group())
                        st.session_state.slide_data = slide_data

                    slide_count = len(slide_data.get("slides", []))
                    st.success(f"修正完了：{slide_count} 枚")
                    design = st.session_state.get("slide_design", DESIGN_PRESETS["ダーク（黒背景・白文字）"])
                    fmt = SLIDE_FORMATS.get(st.session_state.get("slide_format", list(SLIDE_FORMATS.keys())[0]))
                    display_name = st.session_state.display_name
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                    if "PPT (.pptx)" in output_formats:
                        pptx_bytes = build_pptx(slide_data, design, fmt["pptx"])
                        st.download_button(
                            "修正済みPPTをダウンロード (.pptx)",
                            data=pptx_bytes,
                            file_name=f"{ts}_{display_name}_revised.pptx",
                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            use_container_width=True,
                            key="dl_revised_pptx",
                        )

                    if "PNG (.zip)" in output_formats:
                        images = build_png_slides(slide_data, design, fmt["png"])
                        zip_bytes = build_png_zip(images, display_name)
                        st.download_button(
                            "修正済みPNGをダウンロード (.zip)",
                            data=zip_bytes,
                            file_name=f"{ts}_{display_name}_revised_png.zip",
                            mime="application/zip",
                            use_container_width=True,
                            key="dl_revised_png",
                        )

                except Exception as e:
                    st.error(f"スライド修正エラー: {e}")
