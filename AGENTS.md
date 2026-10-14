# product_launch_generator

<!-- ★共通の入口 ここから（機械で配っています／youtube-tool: tools/dryrun/repo_entry_sync.js） -->

## ★コードを触る前に読むもの（全プロジェクト共通）

★**バグの型の正本はここ1か所です**（★写してはいけません。★読んでください）:

- `~/projects/defect_types_master_v1.md`（★型 113件・T-A〜T-DH）
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
- ★担当の印と状態は作業ごと。番号の部分が重なる作業IDは取り込まない。auto_start: yes の作業は Mac の見張りが自動で始める（同時1本・1日の上限・止める設定あり・QG-009・T-DH）。受信箱の取り込みも見張りが回す・止まった作業は ⚠ と1回の始め直し（QG-010）

### ★本番に出す前の別の目（2026-10-15 QG-008・型 T-I・T-AT・全案件で必須）

- ★本番に出す前は、作業を見ていない別の目（Codex か新しい Claude Code・1本）が検査の部品と本物の値を照らし、`projects/<slug>/reviews/` に記録する。記録が無ければ配置の道具が止まる（`tools/second_eye.py`・`tools/check_review.py`・`run_checked.py clasp-deploy`）

<!-- ★共通の入口 ここまで -->
