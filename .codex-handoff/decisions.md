# Decisions

- 自動更新: `codex-handoff prepare` / `capture` / background sync
- 生成日時: `2026-03-18T16:25:10+09:00`

- 2026-03-18: **結果** project.md、decisions.md、tasks.md、next-thread.md を `next-thread.md` と同じ自動更新系に揃えました。実装は [s…
- 2026-03-18: Git 管理外のディレクトリとして path 単位で handoff を継続する。
- 2026-03-18: `codex-handoff` はこの環境では正常に動いていて、新スレッド向けのブリーフも生成できています。続けて `.codex-handoff/next-thread.md` と `.codex-handoff/project.md` を見て、実際に新スレッドで拾う前提が揃…
- 2026-03-18: 新しいスレッド開始時に `codex-handoff` 前提が実際に取れるか、このリポジトリの設定どおり確認します。まず `codex-handoff prepare --stdout` を実行して、その後 `.codex-handoff` の状態を見ます。
