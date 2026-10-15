# product_launch_generator — Claude Code 作業ガイド

<!-- ★共通の入口 ここから（機械で配っています／youtube-tool: tools/dryrun/repo_entry_sync.js） -->

## ★コードを触る前に読むもの（全プロジェクト共通）

★**バグの型の正本はここ1か所です**（★写してはいけません。★読んでください）:

- `~/projects/defect_types_master_v1.md`（★型 116件・T-A〜T-DL）
- GitHub: https://github.com/aimasterschool-hub/projects-docs/blob/main/defect_types_master_v1.md
- ★実例と「直した形」の詳細: `~/projects/youtube-tool/docs/defect_map.md` の §3

★**型番号で呼び合います**（Director の記憶・Codex・Claude Code で同じ番号）。

### ★共通の規約（詳しくは正本の末尾）

- ★**規約A** 同じ処理が複数箇所にあるなら、★**先に全箇所を数えてから**直す
- ★**規約B** 数える機能には★**陽性対照**を対にする（★0件は安全を意味しない）
- ★**規約C** ★「測れなかった」と「異常だった」を★同じ値で返さない
- ★**規約D** 数字には札を付ける（【一次】【実測】【計算】【推定】【未測】＋【範囲】）
- ★**規約E** 切り替えるもの（鍵・URL・設定）は★使う直前に読む
- ★**規約F** 検査IDは★一意にする

### ★新しい型を見つけたら

1. `youtube-tool/docs/defect_map.md` の §3 に節を足す（どこ・症状・実測・直した形・見張り）
2. 同じファイルの §5 に型を1行足す（★なぜダメか／どう直すか）
3. `node tools/dryrun/types_master_sync.js --write`（★正本の1枚に配る）
4. `node tools/dryrun/repo_entry_sync.js --write`（★全リポの入口を更新）

### ★作業の前の点検 PREFLIGHT（2026-10-11 ユーザー決定・全案件で必須）

- ★作業の前に `~/projects/ai-handoff-hub/projects/global-ai-handoff/PREFLIGHT.md` を読み、★7項目（過去の失敗を引く・失敗の予測3つ・前提の鮮度・本人に頼む前の理由・数字の出典・全部数える・記録）を通す
- ★報告に★4つの欄（過去の失敗／失敗の予測／本人に頼んだこと／数字の出典）を入れる。★欄が無いと DONE にならない（Hub の `tools/check_preflight.py`）

### ★Hub に書くとき（2026-10-13 GAH-HUB-OWN-CLONE・型 T-DE・全案件で必須）

- ★Hub（ai-handoff-hub）に書くときは `python3 ~/projects/ai-handoff-hub/tools/hubgit.py clone <作業のID>` の clone で書き、`hubgit.py push` で上げる。共有の作業場では commit・push しない

### ★1つの作業は1つの画面・報告と STATE の先頭（2026-10-14 QG-004・QG-005・型 T-DH・全案件で必須）

- ★作業を始める前に `python3 ~/projects/ai-handoff-hub/tools/task_owner.py claim <案件> <作業のID>` で担当の印を付ける（Codex は `--window <画面の id>`）。★担当中の画面があれば、後から来た画面は聞かずに「この作業は画面 ◯◯ が担当中です。この画面は閉じてOK」とだけ出して終わる（終了コード 4。読めない 2 は引き継がずに止まる・QG-005・T-DE）
- ★報告の先頭は「やったこと・結果・次（本人／AI）」の3見出し、STATE の先頭は「最終更新・現在地・次の一手・詰まっている点」（型は `~/projects/ai-handoff-hub/projects/global-ai-handoff/HUB_RULES.md`）
- ★取り込みは QUEUED（未着手）。作業中（IN_PROGRESS）は task_owner の claim のあとだけ。未着手は `python3 ~/projects/ai-handoff-hub/tools/task_queue.py list` で見る（30分で ⚠・QG-007・T-DH）
- ★担当の印と状態は作業ごと。番号の部分が重なる作業IDは取り込まない。auto_start: yes の作業は Mac の見張りが自動で始める（同時1本・1日の上限・止める設定あり・QG-009・T-DH）。受信箱の取り込みも見張りが回す・止まった作業は ⚠ と1回の始め直し（QG-010）・作業には優先度（高・中・低）。見張りは始める前に PC の重さと使用量を読み、低いものから止める（読めなければ中・低は始めない・QG-015）

### ★本番に出す前の別の目（2026-10-15 QG-008・型 T-I・T-AT・全案件で必須）

- ★本番に出す前は、作業を見ていない別の目（Codex か新しい Claude Code・1本）が検査の部品と本物の値を照らし、`projects/<slug>/reviews/` に記録する。記録が無ければ配置の道具が止まる（`tools/second_eye.py`・`tools/check_review.py`・`run_checked.py clasp-deploy`）

<!-- ★共通の入口 ここまで -->

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
