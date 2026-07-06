# product_launch_generator — Claude Code 作業ガイド
最終更新：2026-07-06

## 0. セッション開始時の前提（自動読込・ユーザー明示不要）

- **グローバル設定**：`~/.claude/CLAUDE.md`（開発規約・ブループリント・secrets・自発リマインド §7.1）
- **セッション状態**：本ディレクトリの `HANDOFF.md`（毎セッション終了時に更新→push）
- **改善バックログ**：`~/projects/improvement_backlog_v1.md` の **§1（横断）** と **§2.3（PLG 個別 P01〜P17）**、**§5.3 Phase 4 移行前必須** を必要に応じ参照

## 0.1 このプロジェクトの位置づけ

マスターブループリント（`~/projects/master_system_blueprint_v*.md` 最新版）**ライン2：投資商品・ローンチ制作**のローンチ台本ジェネレーター（RAG ベース：過去台本から新規VSL生成）。**funnel-generator の前工程**（本ツールで生成した台本を funnel-generator が食う）。

## 0.2 起動・実行

```bash
# Webアプリ
streamlit run app.py

# CI と同じ検証
python3 -m compileall -q .
python3 test_app.py
```

必要な環境変数：`ANTHROPIC_API_KEY`／`TAVILY_API_KEY`（`.env.example` 参照。Streamlit UI 入力も可）

## 0.3 デプロイ

Streamlit Cloud にデプロイ済み（`aimasterschool-hub/product-launch-generator/main/app.py`）。**`packages.txt` を触るときは規約 §10 を必ず参照**（コメント記法非対応・apt-get install にパススルーされるため、`#` を書くと `Unable to locate package #` でデプロイ失敗する。2026-07-06 事故発生済み）。

## 0.4 このプロジェクト固有の注意（監査バックログ抜粋）

- 🔴 **`test_app.py` が app.py の関数をコピーしてテスト**しており、CI が実質空回り（P01 未対応）→ **app.py を変えてもテスト通る**、いつ壊れるか予測不能。テスト追加時は本物の関数を import する形に直すこと（当面の smoke test は `compileall` で構文チェックのみ）
- 🔴 **`app.py` 3131行の巨大モジュール**（P09 未対応）→ 分割方針は改善バックログ §2.3 P09 参照（`pricing.py`／`samples.py`／`prompts.py`／`search.py`／`slides.py`／`persistence.py`）
- 🔴 モデルID 5箇所リテラル散在（P03 未対応。app.py と `MODEL="claude-sonnet-4-6"` を1箇所使うが、`claude-haiku-4-5-20251001` は 3箇所リテラル直書き）
- 🟡 Anthropic クライアント10箇所で個別初期化（P10 未対応。変数名 `client`/`client_ex`/`client_o`/`client2`/`client_blk` バラバラ）
- 🟡 `except Exception: pass` が13箇所（P14 未対応。Tavily 検索失敗を握りつぶすので、トレンド反映が失敗しても気づけない）
- 🟡 `st.session_state` エンタングル（P15 未対応。`PRESET_SIMPLE_KEYS` と `clear_form_state` のキーリストがずれている→プリセット項目追加時に片方忘れる典型バグ）
- ✅ Python 3.9.6 ローカル vs Python 3.11 CI の差（意図的・許容）
- ✅ CWD 依存パスは `BASE_DIR = Path(__file__).resolve().parent` で解消済（P06 対応・2026-07-06）
