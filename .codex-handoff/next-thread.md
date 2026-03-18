# Next Thread Brief: Codex用OSS

- 生成日時: `2026-03-18T17:04:55+09:00`
- ルート: `C:/開発/Codex用OSS`
- メモ保存先: `C:/Users/stsuc/.codex-handoff/projects/codex-oss-963061a73d87`

## このプロジェクトの目的

- プロジェクト内でスレッドを切り替えるたびに前提を手で書き直す負担を減らす
- コンテキスト圧縮で性能が落ちる前に、新しいスレッドへ安全に移る
- Codex 本体の内部 DB や未公開 UI フックに依存せず、壊れにくい運用を作る
- GitHub から導入したら、各プロジェクトで追加設定しなくても使える形にする

### 重要ファイル

- `README.md`
- `src`
- `tests`
- `.codex-handoff`
- `AGENTS.md`

## 現在の主題

- 変更ファイルを確認する: `src/codex_handoff/codex_sessions.py`, `src/codex_handoff/service.py`, `src/codex_handoff/sources.py` など

## 直近の会話要点

### セッション `019cffd6`
- 開始 `2026-03-18T07:25:54.177Z` / 更新 `2026-03-18T08:04:15.429Z`
- 最初の依頼: ## Code review guidelines: # Review guidelines: You are acting as a reviewer for a proposed code change made by another engineer. Below are some default guidelines for determining whether the original author would appreciate the issue being flagged. These are not the final word…
- 直近の依頼: 進めてください
- 直近の回答: `codex-handoff` の最適化を入れました。レビュー専用の一時会話を handoff 文脈から外し、tracked な `.codex-handoff` を dirty 判定に含めるようにしています。実装は [codex_sessions.py](C:/開発/Codex用OSS/src/codex_handoff/codex_sessions.py)、[service.py](C:/開発/Codex用OSS/src/codex_handoff/service.py)、[sources.py](C:/開発/Codex用OSS/src/codex…

### セッション `019cffd1`
- 開始 `2026-03-18T07:21:07.461Z` / 更新 `2026-03-18T07:22:20.683Z`
- 最初の依頼: これって新しいスレッド始めるとき明示しなくてもちゃんと参照してくれるのかな
- 直近の回答: このリポジトリでは、かなり高い確率で参照されます。ただし「Codex アプリがネイティブに自動記憶している」のではなく、`AGENTS.md` の指示で新スレッド開始時に `codex-handoff prepare` を実行して、[.codex-handoff/next-thread.md](C:/開発/Codex用OSS/.codex-handoff/next-thread.md) と [.codex-handoff/project.md](C:/開発/Codex用OSS/.codex-handoff/project.md) を読む運用になっている…

### セッション `019cff79`
- 開始 `2026-03-18T05:45:06.101Z` / 更新 `2026-03-18T06:55:40.381Z`
- 最初の依頼: 引き継げてる？
- 直近の依頼: 最適化して、全てnext-thread.mdと同じく自動で更新されていくようにしてください。
- 直近の回答: **結果** [project.md](C:/開発/Codex用OSS/.codex-handoff/project.md)、[decisions.md](C:/開発/Codex用OSS/.codex-handoff/decisions.md)、[tasks.md](C:/開発/Codex用OSS/.codex-handoff/tasks.md)、[next-thread.md](C:/開発/Codex用OSS/.codex-handoff/next-thread.md) を `next-thread.md` と同じ自動更新系に揃えました。実装は [s…

## 直近の決定事項

- 2026-03-18: **結果** project.md、decisions.md、tasks.md、next-thread.md を `next-thread.md` と同じ自動更新系に揃えました。実装は [s…
- 2026-03-18: `tasks.md` に過去の自動生成タスクが積み上がる副作用が見えたので、そこも止めます。既存タスクの再注入は、手動メモや実タスクだけ残して、毎回変わる「変更ファイル確認」系は残さないようにします。
- 2026-03-18: 実装方針は見えました。`recent_sessions` の選別でレビュー専用セッションを落としつつ、既存の `tasks.md` / `decisions.md` からも同種の一時タスクを再注入しないようにします。
- 2026-03-18: その通りです。現状は handoff の自動生成が「今の会話」と「本来引き継ぐべきプロジェクト文脈」を分離できていません。
- 2026-03-18: Git 管理外のディレクトリとして path 単位で handoff を継続する。
- 2026-03-18: 新しいスレッド開始時に `codex-handoff` 前提が実際に取れるか、このリポジトリの設定どおり確認します。まず `codex-handoff prepare --stdout` を実行して、その後 `.codex-handoff` の状態を見ま…

## 未完了タスク

- [ ] 変更ファイルを確認する: `src/codex_handoff/codex_sessions.py`, `src/codex_handoff/service.py`, `src/codex_handoff/sources.py` など
- [ ] 変更ファイルを確認する: `.codex-handoff/decisions.md`, `.codex-handoff/next-thread.md`, `.codex-handoff/project.md` など

## 現在の作業状態

- プロジェクト名: `Codex用OSS`
- 直近に検出した Codex セッション: 3 件
- Git ルート: `C:/開発/Codex用OSS`
- ブランチ: `master`
- 作業ツリー: `dirty`

### 変更ファイル

- `src/codex_handoff/codex_sessions.py` (M)
- `src/codex_handoff/service.py` (M)
- `src/codex_handoff/sources.py` (M)
- `tests/test_cli.py` (M)
- `src/codex_handoff/relevance.py` (??)

### 直近コミット

- `ec18474` Automate handoff sync and package Windows background app

### 検出した重要パス

- `README.md`
- `src`
- `tests`

## 新スレッドで最初にやるべき 3 手

1. `tasks.md` の先頭タスクを確認する: 変更ファイルを確認する: `src/codex_handoff/codex_sessions.py`, `src/codex_handoff/service.py`, `src/codex_handoff/sources.py` など
2. 変更ファイルを確認して現在地を把握する: `src/codex_handoff/codex_sessions.py`, `src/codex_handoff/service.py`, `src/codex_handoff/sources.py` など
3. 直近の回答内容を踏まえて次の判断を置く: `codex-handoff` の最適化を入れました。レビュー専用の一時会話を handoff 文脈から外し、tracked な `.codex-handoff` を dirty 判定に含めるようにしています。実装は [codex_ses…

## 明示すべき仮定

### 制約

- Codex デスクトップアプリへ独自 UI を埋め込む公開 API は前提にしていません
- 新規スレッド開始時の完全なネイティブ hook はない前提です
- そのため、v2 は self-contained な CLI を基本にし、必要な人だけ global `AGENTS.md` 連携を opt-in で有効化する設計です

### 運用ルール

- global store の生成物は UTF-8 BOM なし
- global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱う
- 差分本文や環境変数値などの機密は収集しない
- Git がないディレクトリでも、パス単位の project store として動作する
- 既存のローカル `.codex-handoff/` が見つかった場合は global store へ取り込みつつ、その後は同期ミラーとして再利用する

### Windows PowerShell 互換

global store は UTF-8 BOM なしで保持します。リポジトリ内 `.codex-handoff/` の同期ミラーは Windows PowerShell 5.1 の `Get-Content` でもそのまま読めるように UTF-8 BOM 付きで書き出します。

- このリポジトリで作業を始める前に、`codex-handoff prepare` を実行して `.codex-handoff/next-thread.md` を最新化する。
- 続いて `.codex-handoff/next-thread.md` と `.codex-handoff/project.md` を読んで、前提・決定事項・未完了タスクを把握してから作業する。
- これらのファイルが存在する限り、前スレッドの文脈をユーザーに再説明させない。
- `codex-handoff` が利用できない場合だけ、その旨を短く伝えて通常どおり進める。

### 仮定

- 直近の主題は「これって新しいスレッド始めるとき明示しなくてもちゃんと参照してくれるのかな」の継続である。
- 文脈回復は `README.md`, `src`, `tests` から始める。

### AGENTS.md

<!-- codex-handoff:start -->
## codex-handoff
- このリポジトリで作業を始める前に、`codex-handoff prepare` を実行して `.codex-handoff/next-thread.md` を最新化する。
- 続いて `.codex-handoff/next-thread.md` と `.codex-handoff/project.md` を読んで、前提・決定事項・未完了タスクを把握してから作業する。
- これらのファイルが存在する限り、前スレッドの文脈をユーザーに再説明させない。
- `codex-handoff` が利用できない場合だけ、その旨を短く伝えて通常どおり進める。
<!-- codex-handoff:end -->
