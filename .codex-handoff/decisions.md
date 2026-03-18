# Decisions

- 自動更新: `codex-handoff prepare` / `capture` / background sync
- 生成日時: `2026-03-18T17:04:55+09:00`

- 2026-03-18: **結果** project.md、decisions.md、tasks.md、next-thread.md を `next-thread.md` と同じ自動更新系に揃えました。実装は [s…
- 2026-03-18: `tasks.md` に過去の自動生成タスクが積み上がる副作用が見えたので、そこも止めます。既存タスクの再注入は、手動メモや実タスクだけ残して、毎回変わる「変更ファイル確認」系は残さないようにします。
- 2026-03-18: 実装方針は見えました。`recent_sessions` の選別でレビュー専用セッションを落としつつ、既存の `tasks.md` / `decisions.md` からも同種の一時タスクを再注入しないようにします。
- 2026-03-18: その通りです。現状は handoff の自動生成が「今の会話」と「本来引き継ぐべきプロジェクト文脈」を分離できていません。
- 2026-03-18: Git 管理外のディレクトリとして path 単位で handoff を継続する。
- 2026-03-18: 新しいスレッド開始時に `codex-handoff` 前提が実際に取れるか、このリポジトリの設定どおり確認します。まず `codex-handoff prepare --stdout` を実行して、その後 `.codex-handoff` の状態を見ま…
