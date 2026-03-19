<!-- codex-handoff:start -->
## codex-handoff
- このリポジトリは `codex-handoff` 自身の開発元なので、ここでの文脈回復は installed CLI より `uv run codex-handoff prepare --stdout` を優先して最新の source 実装を使う。
- `uv run` 実行前は `UV_CACHE_DIR` と `UV_PYTHON_INSTALL_DIR` を全プロジェクト共通設定どおりにセットする。
- fallback として `codex-handoff prepare` も使えるが、source と installed CLI がずれていない時だけにする。
- 続いて `.codex-handoff/project.md`、`.codex-handoff/decisions.md`、`.codex-handoff/tasks.md`、`.codex-handoff/memory.json`、`.codex-handoff/next-thread.md` を読んで、前提・決定事項・未完了タスク・構造化メモリを把握してから作業する。
- これらのファイルが存在する限り、前スレッドの文脈をユーザーに再説明させない。
- `codex-handoff` が利用できない場合だけ、その旨を短く伝えて通常どおり進める。
<!-- codex-handoff:end -->
