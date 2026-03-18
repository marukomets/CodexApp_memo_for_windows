# Project Context

- 自動更新: `codex-handoff prepare` / `capture` / background sync
- 生成日時: `2026-03-18T16:25:10+09:00`
- ルート: `C:/開発/Codex用OSS`

## 目的

- プロジェクト内でスレッドを切り替えるたびに前提を手で書き直す負担を減らす
- コンテキスト圧縮で性能が落ちる前に、新しいスレッドへ安全に移る
- Codex 本体の内部 DB や未公開 UI フックに依存せず、壊れにくい運用を作る
- GitHub から導入したら、各プロジェクトで追加設定しなくても使える形にする

## 制約

- Codex デスクトップアプリへ独自 UI を埋め込む公開 API は前提にしていません
- 新規スレッド開始時の完全なネイティブ hook はない前提です
- そのため、v2 は self-contained な CLI を基本にし、必要な人だけ global `AGENTS.md` 連携を opt-in で有効化する設計です

## 重要ファイル

- `README.md`
- `src`
- `tests`
- `AGENTS.md`

## 運用ルール

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

## 仮定

- 直近の主題は「これって新しいスレッド始めるとき明示しなくてもちゃんと参照してくれるのかな」の継続である。
- 文脈回復は `README.md`, `src`, `tests` から始める。
