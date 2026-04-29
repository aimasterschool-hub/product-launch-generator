#!/usr/bin/env python3
import os
import subprocess
import streamlit as st
from pathlib import Path
from datetime import datetime
import anthropic

SAMPLES_DIR = Path("samples")
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
    strengths = info.get("strengths", [])
    strengths_str = "\n".join(f"  - {s}" for s in strengths if s) or "  （未入力）"

    lines = [
        "以下のプロダクト情報をもとに、サンプル台本のスタイルを踏襲した台本を生成してください。",
        "",
        "## 商品・ビジネス基本情報",
        f"**商品名**: {info.get('name', '')}",
        f"**ジャンル/カテゴリ**: {info.get('category', '')}",
        f"**販売者名（ペルソナ）**: {info.get('seller_name', '')}",
        f"**インタビュアー名**: {info.get('interviewer_name', '')}",
        f"**販売者の権威・実績**: {info.get('seller_authority', '')}",
        f"**メインベネフィット・実績数値**: {info.get('main_benefit', '')}",
        f"**メインの謳い文句（キャッチコピー）**: {info.get('catchcopy', '')}",
        f"**ターゲット層**: {info.get('target_audience', '')}",
        f"**実績数値①（短期）**: {info.get('result1', '')}",
        f"**実績数値②（中〜長期）**: {info.get('result2', '')}",
        f"**月利/月収目安**: {info.get('monthly_return', '')}",
        f"**始めやすさの根拠**: {info.get('ease_of_start', '')}",
        "",
        "**商品の強み**:",
        strengths_str,
        "",
        "## 社会的背景・痛み訴求",
        f"**視聴者が抱えるペイン**: {info.get('pain_points', '')}",
        f"**なぜ今この商品が必要か（why now）**: {info.get('why_now', '')}",
        "",
        "## 信頼性・第三者証拠",
        f"**第三者の種類**: {info.get('third_party_type', '')}",
        f"**第三者の名前・肩書き**: {info.get('third_party_name', '')}",
        f"**第三者の裏付けポイント**: {info.get('third_party_points', '')}",
        "",
        "## 価格・オファー設定",
        f"**定価**: {info.get('regular_price', '')}",
        f"**特別価格**: {info.get('special_price', '')}",
        f"**期間限定の条件**: {info.get('limited_time', '')}",
        f"**分割対応**: {info.get('installment', '')}",
        f"**特典内容**: {info.get('bonuses', '')}",
        "",
        "## トーン・構成オプション",
        f"**動画の話数構成**: {info.get('episode_structure', '')}",
        f"**クロージングの強度**: {info.get('closing_strength', '')}",
    ]

    if info.get("notes"):
        lines += ["", f"**追加メモ・要望**: {info['notes']}"]

    lines += [
        "",
        "【出力形式の指示】",
        "- 【セクション名 - タイムコード】の見出しを使って構成を明示してください",
        "- 【ナレーション】【SE】【映像】などの役割表記を適切に含めてください",
        "- サンプル台本と同じスタイル・語り口・構成で作成してください",
        "- 話数構成が指定されている場合は、その構成に合わせて台本を分けてください",
    ]
    return "\n".join(lines)


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

# APIキー確認
api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    api_key = st.text_input("Anthropic APIキー", type="password", placeholder="sk-ant-...")
    if not api_key:
        st.warning("APIキーを入力してください")
        st.stop()

# サイドバー：サンプル台本
with st.sidebar:
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

# systemブロックをセッションにキャッシュ
if "system_blocks" not in st.session_state or st.session_state.get("samples_count") != len(samples):
    st.session_state.system_blocks = build_system_prompt(samples)
    st.session_state.samples_count = len(samples)

# ── 入力フォーム ──────────────────────────────────────────────────────────────

with st.form("product_form"):

    # ── セクション1：商品・ビジネス基本情報 ──
    st.subheader("商品・ビジネス基本情報")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("商品名 *", placeholder="例：スマートイット")
        category = st.selectbox("ジャンル / カテゴリ", [
            "FX・為替投資", "株式投資・トレード", "仮想通貨・Web3",
            "副業・ビジネス", "美容・スキンケア", "健康・ダイエット",
            "教育・スキルアップ", "テック・SaaS", "食品・サプリ", "その他"
        ])
        seller_name = st.text_input("販売者名（ペルソナ）", placeholder="例：はたけ")
        interviewer_name = st.text_input("インタビュアー名", placeholder="例：ふじき（第三者）")
        seller_authority = st.text_input("販売者の権威・実績", placeholder="例：FX系YouTuber、動画1500本、5年以上活動")
    with col2:
        main_benefit = st.text_input("メインベネフィット・実績数値", placeholder="例：月5分で月10万円")
        catchcopy = st.text_input("メインの謳い文句（キャッチコピー）", placeholder="例：月5分で月10万円")
        target_audience = st.text_input("ターゲット層", placeholder="例：投資初心者、副業したいサラリーマン")
        result1 = st.text_input("実績数値①（短期）", placeholder="例：3ヶ月で31万円の利益")
        result2 = st.text_input("実績数値②（中〜長期）", placeholder="例：1年で125万円の利益")

    col3, col4 = st.columns(2)
    with col3:
        monthly_return = st.text_input("月利 / 月収目安", placeholder="例：月利10%、月10万円")
    with col4:
        ease_of_start = st.text_input("始めやすさの根拠", placeholder="例：2万円から、スマホだけでOK")

    st.markdown("**商品の強み**（最大4件）")
    s_cols = st.columns(4)
    strengths = []
    strength_placeholders = [
        "例：証拠金2万円から始められる",
        "例：勝率78%で安心感がある",
        "例：ドローダウン平均10%以下",
        "例：完全自動、ON/OFFも不要",
    ]
    for i, col in enumerate(s_cols):
        s = col.text_input(f"強み{i+1}", key=f"str_{i}", label_visibility="collapsed", placeholder=strength_placeholders[i])
        strengths.append(s)

    st.divider()

    # ── セクション2：社会的背景・痛み訴求 ──
    st.subheader("社会的背景・痛み訴求")
    col5, col6 = st.columns(2)
    with col5:
        pain_points = st.text_area("視聴者が抱えるペイン（悩み・不安）",
            placeholder="例：残業しても給料が上がらない、将来が不安、副業する時間がない", height=100)
    with col6:
        why_now = st.text_area("なぜ今この商品が必要か（why now）",
            placeholder="例：物価は上がるのに賃金は上がらない時代。自分で資産を作るしかない。", height=100)

    st.divider()

    # ── セクション3：信頼性・第三者証拠 ──
    st.subheader("信頼性・第三者証拠")
    col7, col8, col9 = st.columns(3)
    with col7:
        third_party_type = st.selectbox("第三者の種類", [
            "開発者・専門家", "ユーザー・実践者", "有識者・研究者", "著名人・インフルエンサー", "なし"
        ])
    with col8:
        third_party_name = st.text_input("第三者の名前・肩書き", placeholder="例：桑田さん（システム開発者、20代）")
    with col9:
        third_party_points = st.text_input("第三者の裏付けポイント", placeholder="例：2万通りのロジックを検証、14歳からシステム開発")

    st.divider()

    # ── セクション4：価格・オファー設定 ──
    st.subheader("価格・オファー設定")
    col10, col11, col12 = st.columns(3)
    with col10:
        regular_price = st.text_input("定価", placeholder="例：158,000円")
        special_price = st.text_input("特別価格", placeholder="例：98,000円")
    with col11:
        limited_time = st.text_input("期間限定の条件", placeholder="例：3日間限定")
        installment = st.selectbox("分割対応", ["あり", "なし"])
    with col12:
        bonuses = st.text_area("特典内容（カンマ区切り）",
            placeholder="例：導入マニュアル、勝ち組トレーダー手法、キャッシュを増やす方法", height=100)

    st.divider()

    # ── セクション5：トーン・構成オプション ──
    st.subheader("トーン・構成オプション")
    col13, col14 = st.columns(2)
    with col13:
        episode_structure = st.selectbox("動画の話数構成", [
            "1話完結", "2話構成（前編・後編）", "3話構成", "4話構成", "5話構成"
        ])
        closing_strength = st.selectbox("クロージングの強度", [
            "真摯・控えめ（押し付けない）", "標準（バランス型）", "強め（urgency高め）", "最強（限定・希少性全開）"
        ])
    with col14:
        notes = st.text_area("追加で入れたいポイント・メモ（任意）",
            placeholder="例：競合との比較、特定のNG表現、強調したいエピソードなど", height=100)

    submitted = st.form_submit_button("台本を生成する", type="primary", use_container_width=True)

# ── 生成処理 ──────────────────────────────────────────────────────────────────

if submitted:
    if not name:
        st.error("商品名は必須です")
    else:
        info = {
            "name": name, "category": category, "seller_name": seller_name,
            "interviewer_name": interviewer_name, "seller_authority": seller_authority,
            "main_benefit": main_benefit, "catchcopy": catchcopy,
            "target_audience": target_audience, "result1": result1, "result2": result2,
            "monthly_return": monthly_return, "ease_of_start": ease_of_start,
            "strengths": strengths, "pain_points": pain_points, "why_now": why_now,
            "third_party_type": third_party_type, "third_party_name": third_party_name,
            "third_party_points": third_party_points, "regular_price": regular_price,
            "special_price": special_price, "limited_time": limited_time,
            "installment": installment, "bonuses": bonuses,
            "episode_structure": episode_structure, "closing_strength": closing_strength,
            "notes": notes,
        }
        user_prompt = build_user_prompt(info)

        st.divider()
        st.subheader("生成結果")

        try:
            client = anthropic.Anthropic(api_key=api_key)
            script = ""
            placeholder = st.empty()

            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=st.session_state.system_blocks,
                messages=[{"role": "user", "content": user_prompt}],
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

            output_path = save_script(script, name)

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
                file_name=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        except anthropic.APIError as e:
            st.error(f"APIエラー: {e}")
