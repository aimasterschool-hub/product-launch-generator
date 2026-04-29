#!/usr/bin/env python3
import os
import subprocess
import streamlit as st
from pathlib import Path
from datetime import datetime
import anthropic
from tavily import TavilyClient

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

    comment_prompt = info.get("comment_prompt", "").strip()
    comment_instruction = f"「{comment_prompt}」" if comment_prompt else "商品内容に合った質問を自動生成してください"

    lines = [
        "以下のプロダクト情報をもとに、サンプル台本のスタイルを踏襲した台本を生成してください。",
        "",
        "## 構成タイプ",
        f"**タイプ**: {structure_type}",
        f"**説明**: {structure_desc}",
        f"**話し方スタイル**: {dialogue_style}",
        "",
        "## 商品・基本情報",
        f"**商品名**: {info.get('name', '')}",
        f"**ジャンル**: {info.get('category', '')}",
        f"**販売者名**: {info.get('seller_name', '')}",
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
        "## 価格・オファー",
        f"**定価**: {info.get('regular_price', '')}",
        f"**特別価格**: {info.get('special_price', '')}",
        f"**期間限定条件**: {info.get('limited_time', '')}",
        f"**分割対応**: {info.get('installment', 'なし')}",
        f"**特典内容**: {info.get('bonuses', '')}",
        "",
        "## コメント促進パート（動画末尾）",
        f"**視聴者への質問**: {comment_instruction}",
        "",
        "## 構成オプション",
        f"**話数構成**: {info.get('episode_structure', '1話完結')}",
        f"**クロージングの強度**: {info.get('closing_strength', '標準')}",
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
        "- 動画末尾にコメント促進パートを必ず含めてください",
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
    )

    st.divider()

    # 商品・基本情報
    st.subheader("商品・基本情報")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("商品名", placeholder="例：スマートイット")
        category = st.selectbox("ジャンル", [
            "FX・為替投資", "株式投資・トレード", "仮想通貨・Web3",
            "副業・ビジネス", "美容・スキンケア", "健康・ダイエット",
            "教育・スキルアップ", "テック・SaaS", "食品・サプリ", "その他"
        ])
        seller_name = st.text_input("販売者名", placeholder="例：はたけ")
        interviewer_name = st.text_input(
            "インタビュアー名（空欄で一人語り形式）",
            placeholder="例：ふじき　　※空欄→モノローグ形式"
        )
        seller_authority = st.text_input("販売者の権威・実績", placeholder="例：FX系YouTuber、動画1500本以上、5年以上活動")
    with col2:
        catchcopy = st.text_input("キャッチコピー", placeholder="例：月5分で月10万円")
        target_audience = st.text_input("ターゲット層", placeholder="例：投資初心者、副業したい人")
        result1 = st.text_input("実績数値①", placeholder="例：3ヶ月で31万円の利益")
        result2 = st.text_input("実績数値②", placeholder="例：1年で125万円の利益")
        monthly_return = st.text_input("月利 / 月収目安", placeholder="例：月利10%、月10万円")
        ease_of_start = st.text_input("始めやすさの根拠", placeholder="例：2万円から、スマホだけでOK")

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
    voice1 = st.text_input("声①", placeholder="例：30代会社員Aさん：導入1ヶ月で8万円の利益が出ました！初心者でも全く問題なかったです。")
    voice2 = st.text_input("声②", placeholder="例：40代主婦Bさん：スマホだけで設定できて、今は毎月安定して収入が入っています。")
    voice3 = st.text_input("声③", placeholder="例：20代フリーランスCさん：他のシステムで失敗したけどこれは違いました。")

    st.divider()

    # 社会背景・痛み訴求
    st.subheader("社会背景・痛み訴求")
    col3, col4 = st.columns(2)
    with col3:
        pain_points = st.text_area("視聴者のペイン", placeholder="例：残業しても給料が上がらない、将来が不安、副業する時間がない", height=100)
    with col4:
        why_now = st.text_area("なぜ今必要か（why now）", placeholder="例：物価は上がるのに賃金は上がらない。自分で資産を作るしかない。", height=100)

    st.divider()

    # 第三者・信頼性
    st.subheader("第三者・信頼性")
    col5, col6, col7 = st.columns(3)
    with col5:
        third_party_type = st.selectbox("第三者の種類", ["なし", "開発者・専門家", "ユーザー・実践者", "有識者・研究者", "著名人・インフルエンサー"])
    with col6:
        third_party_name = st.text_input("名前・肩書き", placeholder="例：桑田（システム開発者）")
    with col7:
        third_party_points = st.text_input("第三者の裏付けポイント", placeholder="例：2万通りのロジックを検証、14歳からシステム開発")

    st.divider()

    # 価格・オファー
    st.subheader("価格・オファー")
    col8, col9, col10 = st.columns(3)
    with col8:
        regular_price = st.text_input("定価", placeholder="例：158,000円")
        special_price = st.text_input("特別価格", placeholder="例：98,000円")
    with col9:
        limited_time = st.text_input("期間限定条件", placeholder="例：3日間限定")
        installment = st.selectbox("分割対応", ["なし", "あり"])
    with col10:
        bonuses = st.text_area("特典内容（カンマ区切り）", placeholder="例：導入マニュアル、トレーダー手法、キャッシュを増やす方法", height=100)

    st.divider()

    # コメント促進パート
    st.subheader("コメント促進パート（動画末尾）")
    comment_prompt = st.text_input(
        "視聴者に聞きたい質問 / お題（空欄で自動生成）",
        placeholder="例：今の月収に満足していますか？コメントで教えてください！"
    )
    st.caption("空欄の場合、商品内容に合った質問を自動で生成します")

    st.divider()

    # 構成オプション
    st.subheader("構成オプション")
    col11, col12 = st.columns(2)
    with col11:
        episode_structure = st.selectbox("話数構成", [
            "1話完結", "2話構成（前編・後編）", "3話構成", "4話構成", "5話構成"
        ])
        closing_strength = st.selectbox("クロージングの強度", [
            "真摯・控えめ（押し付けない）", "標準（バランス型）", "強め（urgency高め）", "最強（限定・希少性全開）"
        ])
    with col12:
        notes = st.text_area("追加メモ（任意）", placeholder="例：競合との比較を入れたい、このワードは避けたいなど", height=100)

    use_trend_search = st.checkbox(
        "最新トレンドをWeb検索して台本に反映する",
        value=False,
        disabled=not tavily_api_key,
        help="TavilyのAPIキーが設定されている場合に利用できます",
    )

    submitted = st.form_submit_button("台本を生成する", type="primary", use_container_width=True)

# ── 生成処理 ──────────────────────────────────────────────────────────────────

def run_generation(client, system_blocks, messages, display_name):
    """Claudeにリクエストを送りストリーミング表示する。台本とstatsを返す。"""
    script = ""
    placeholder = st.empty()
    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
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
        "name": name, "category": category, "seller_name": seller_name,
        "interviewer_name": interviewer_name, "seller_authority": seller_authority,
        "catchcopy": catchcopy, "target_audience": target_audience,
        "result1": result1, "result2": result2,
        "monthly_return": monthly_return, "ease_of_start": ease_of_start,
        "strengths": strengths,
        "voices": [voice1, voice2, voice3],
        "pain_points": pain_points, "why_now": why_now,
        "third_party_type": third_party_type, "third_party_name": third_party_name,
        "third_party_points": third_party_points,
        "regular_price": regular_price, "special_price": special_price,
        "limited_time": limited_time, "installment": installment, "bonuses": bonuses,
        "comment_prompt": comment_prompt,
        "episode_structure": episode_structure, "closing_strength": closing_strength,
        "notes": notes,
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
        messages = [{"role": "user", "content": user_prompt}]
        script, stats = run_generation(client, st.session_state.system_blocks, messages, display_name)

        # セッションに保存（再編集用）
        st.session_state.current_script = script
        st.session_state.current_messages = messages
        st.session_state.display_name = display_name

        show_download(script, display_name, stats)

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

                # 会話履歴に現在の台本とアシスタントの返答を追加
                messages = st.session_state.current_messages + [
                    {"role": "assistant", "content": st.session_state.current_script},
                    {"role": "user", "content": f"以下の修正指示に従って台本を修正してください：\n\n{edit_instruction}"},
                ]

                st.subheader("修正結果")
                script, stats = run_generation(client, st.session_state.system_blocks, messages, display_name)

                # 最新の台本に更新
                st.session_state.current_script = script
                st.session_state.current_messages = messages

                show_download(script, display_name, stats)

            except anthropic.APIError as e:
                st.error(f"APIエラー: {e}")
