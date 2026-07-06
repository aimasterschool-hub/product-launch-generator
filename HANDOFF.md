# HANDOFF — product_launch_generator
最終更新：2026-07-06（監査バックログ v1 対応・Streamlit Cloud デプロイ復旧含む）

## 今回完了したこと（2026-07-06 4プロジェクト横断監査セッション）
- `~/projects/improvement_backlog_v1.md` の監査項目 P02/P04/P05/P06/P07/P08/P17 を適用（`7a7d0f1`）
  - **P02**：`requirements.txt` に上限指定（`anthropic>=0.40,<1.0` `tavily-python>=0.3,<1.0` 等）
  - **P04**：`.github/workflows/test.yml` を修正
    - 旧：`pip install python-pptx Pillow` のみ（requirements.txt 無視）
    - 新：`pip install -r requirements.txt` + `python3 -m compileall -q .` の構文検査追加
  - **P05**：未追跡の `generator.py` を削除（2ヶ月放置・app.py と機能重複・
    モデルID乖離＝Opus vs Sonnet・どこからも import されていなかった）
  - **P06**：`app.py` の `SAMPLES_DIR/OUTPUT_DIR/PRESETS_FILE/COST_LOG_FILE` を
    `BASE_DIR = Path(__file__).resolve().parent` 起点化（CWD 依存を解消）
  - **P07**：`.env.example` 追加
  - **P08**：`samples/.DS_Store` を `git rm --cached`
  - **P17**：`packages.txt` に用途コメント追加
- **⚠️ 事故発生と hotfix（2026-07-06 09:37 UTC）**：
  - 上記 P17 の `packages.txt` へのコメント追加が Streamlit Cloud デプロイを壊した
  - Streamlit Cloud は `packages.txt` を `apt-get install` にそのまま渡すため `#` がパッケージ名扱いになり
    `E: Unable to locate package #` 連発で依存インストール全体失敗
  - hotfix コミット `0d3d1b5` で `packages.txt` を単純な `fonts-noto-cjk` のみに戻し復旧
  - 教訓を規約キット §10「デプロイ設定ファイル触るときの規約」として明文化（projects-docs 側）
- 監査残タスクは `~/projects/improvement_backlog_v1.md §2.3` に「P01/P03/P09〜P16」として登録済

## プロジェクト位置づけ
マスターブループリント v1.1「ライン2：投資商品・ローンチ制作」の**ローンチ台本ジェネレーター（RAGベース：過去台本学習→新規VSL生成）**。
Streamlit UI から商品情報を投入し、`samples/` の既存台本を参照して新規ローンチ台本を Claude API で生成する。
funnel-generator（optin LP/VSL/販売LP 生成）の**前工程**（＝生成した台本を funnel-generator が食う）。

## 今回完了したこと（2026-07-03 規約適用セッション）
- **配置移動**：`~/product_launch_generator/` → `~/projects/product_launch_generator/`
  - 規約キット §1 のフォルダ構造規約（`~/projects/{project}/`）に整列
  - 事前調査でソース内絶対パス依存ゼロを確認（`Path("samples")` 等の相対パスのみ）
- **.venv 再構築**：Python 3.9.6、`requirements.txt` から再インストール
  - `anthropic / streamlit / tavily-python / python-pptx / Pillow` すべて import OK 確認
- **.gitignore 新規作成**：`.env` `.venv/` `output/` `.DS_Store` `*.pptx` `cost_log.json` `presets.json` 収録
- **secrets 監査**：ソース内ハードコードなし（`api_key` は `os.environ` / Streamlit `st.text_input` / Streamlit Secrets 経由）
- **GitHub リモート**：既に SSH（`git@github.com:aimasterschool-hub/product-launch-generator.git`）で疎通確認済み
- 本 HANDOFF.md 作成

## 現状の到達点
### 機能
- Streamlit UI（`app.py`）：商品情報入力→台本生成、Anthropic APIキーは UI で password 入力（Cloud では Secrets）
- Tavily API 連携：トレンド検索・未来リスク検索（`search_trends` / `search_future_risks`）
- 台本生成：`samples/` の 5 サンプル（AutoEdge/x2/グリフォン/クロスシステム/ゼノ）から RAG 学習
- CLI エントリ（`generator.py`）：ANTHROPIC_API_KEY 環境変数を使う CLI 版
- テスト：`test_app.py`、GitHub Actions（`.github/workflows/test.yml`）で自動実行

### 直近のコミット履歴（top 5）
- 自動入力の抽出失敗を修正：max_tokens 3000→8000、入力上限 10000→20000文字
- 骨子末尾に Claude 向け台本生成プロンプトを自動出力（販売者・話数・商品名を自動埋込）
- 未来リスク専用 Tavily 検索を追加（社会課題データを共感・緊急性パートに反映）
- 未来リスク・社会課題ネタをシステムプロンプトに追加（8パターン）
- 歴史的事例の活用ルールをシステムプロンプトに追加（定性表現・社会情景）

### インフラ
- GitHub保全：**済**（aimasterschool-hub/product-launch-generator, SSH）
- CI：**済**（GitHub Actions test.yml、Python 3.11、`python3 test_app.py`）
- secrets：**済**（.env 未使用・UI 入力ベース）
- 配置：**済**（規約準拠 `~/projects/` 配下）
- HANDOFF：**済**（本ファイル）
- 設計メモ：**未**（`product_launch_generator_design_memo.md` として整備推奨）

## 次回やること（優先順）
1. **未追跡の `generator.py` を追跡するか判断**
   - CLI 版として実運用しているなら `git add generator.py && commit`
   - 廃止済みなら `rm generator.py`
2. **funnel-generator との接続テスト**（マスターブループリント §5 Phase 2-8）
   - 本ツールで生成したローンチ台本(.docx) → funnel-generator が食う流れの一気通貫確認
3. **商品マスター**（Phase 2 で整備予定）から入力を自動化
4. 生成物の出口を **コンプラチェッカー v2.2** に接続（`compliance_checklist_v2.md §6`）
5. `product_launch_generator_design_memo.md` を規約キット §3 雛形で作成

## ハマりポイント・注意（次回の自分への警告）
- **配置移動を実施済み**（2026-07-03）。旧パス `~/product_launch_generator/` にあった `.venv` は絶対パス埋込のため削除して再作成した。**旧パスを参照しているシェル履歴・エディタのお気に入り・エイリアスがあれば更新が必要**
- **Python 3.9.6 使用**：CI は 3.11 なので、機能差分に注意。ローカルは system Python（`/Library/Developer/CommandLineTools`）から生成
- **API キー**：ソース直書きなし。Streamlit UI から入力するのが正規フロー。CLI (`generator.py`) は環境変数 `ANTHROPIC_API_KEY` を使用
- **Tavily API** も利用するので、本番運用時は `TAVILY_API_KEY` の管理も必要（UI 入力or Secrets）
- **`output/` `cost_log.json` `presets.json` は git 管理外**（生成物・ローカル状態）

## 将来メモ
- 商品マスター（Supabase 予定）と接続し、商品情報の入力を自動化
- 出力形式を funnel-generator が期待する docx 構造に揃える（マスターブループリント §3 ライン2フロー）
- Python バージョンを 3.11+ に上げる（現在 3.9.6、CI との齟齬解消）

## クラウド資産・外部リンク
- GitHubリポ：`git@github.com:aimasterschool-hub/product-launch-generator.git`
- 参照文書：`~/projects/master_system_blueprint_v1.1.md`（ライン2）／`~/projects/compliance_checklist_v2.md`（出口チェック）／`~/projects/prompts/prompt_library_v0.md`（VSL プロンプト移植待ち）
