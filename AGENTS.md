# product_launch_generator

<!-- ★共通の入口 ここから（機械で配っています／youtube-tool: tools/dryrun/repo_entry_sync.js） -->

## ★コードを触る前に読むもの（全プロジェクト共通）

★**バグの型の正本はここ1か所です**（★写してはいけません。★読んでください）:

- `~/projects/defect_types_master_v1.md`（★型 93件・T-A〜T-CN）
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

<!-- ★共通の入口 ここまで -->
