# codex-handoff

`codex-handoff` は、Codex で新しいスレッドを始める前に、同一プロジェクトの前提・決定事項・未完了タスク・現在の作業状態を自動で整理するローカル CLI です。

正本のメモは `~/.codex-handoff/projects/<project-id>/` に保存しつつ、各リポジトリの `.codex-handoff/` に読みやすい同期ミラーを置きます。Codex 側の読み込み導線は `~/.codex/AGENTS.md` へ 1 回だけ入れます。

v2.1 では shell を使いたくない人向けに `codex-handoff-ui` を追加しました。配布時はこの GUI を単体 `exe` にして配り、初回起動時に `%LOCALAPPDATA%\CodexHandoff` へ自己インストールできます。

v2.2 では background sync を追加し、初回セットアップ後は GUI を開かなくても active workspace の handoff を裏で更新できるようにしました。
新しく作ったプロジェクトでも、Codex でそのフォルダを active workspace にした時点で project store を自動作成して追従します。

## 目的

- プロジェクト内でスレッドを切り替えるたびに前提を手で書き直す負担を減らす
- コンテキスト圧縮で性能が落ちる前に、新しいスレッドへ安全に移る
- Codex 本体の内部 DB や未公開 UI フックに依存せず、壊れにくい運用を作る
- GitHub から導入したら、各プロジェクトで追加設定しなくても使える形にする

## インストール

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv tool install codex-handoff
codex-handoff setup
```

開発中のローカル clone から試す場合:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv tool install .
codex-handoff setup
```

## 使い方

通常運用では、最初に `setup` を 1 回実行すれば十分です。これは global store と `AGENTS` 用スニペットを作るだけで、`~/.codex/AGENTS.md` は勝手に書き換えません。

```powershell
codex-handoff setup
codex-handoff setup --install-global-agents
codex-handoff uninstall-global-agents
codex-handoff prepare --stdout
codex-handoff capture --note "API エラー調査の続き"
codex-handoff where
codex-handoff doctor
```

### GUI で使う

開発環境から GUI を起動する場合:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv run codex-handoff-ui
```

GUI は初回セットアップ専用の 2 ステップウィザードです。

- Step 1: 配布 exe 自身を `%LOCALAPPDATA%\CodexHandoff` へインストール
- Step 2: チェックボックスの状態を `Apply setup` で反映
- Done: 以後は GUI を開かなくても active workspace の handoff を自動更新
- 必要ならその場で current workspace の handoff をコピー

### `setup`

マシンごとの初回セットアップです。

- `~/.codex-handoff/` を作成
- `~/.codex-handoff/global-agents-snippet.md` を作成

デフォルトでは `~/.codex/AGENTS.md` を変更しません。

完全自動に寄せたい場合だけ、明示的に次を実行します。

```powershell
codex-handoff setup --install-global-agents
```

この場合も、既存の `~/.codex/AGENTS.md` があればバックアップを作ってから、`codex-handoff` の管理ブロックだけを追加または更新します。ファイル全体を置き換えることはしません。

これにより、新しい Codex スレッドでも `codex-handoff prepare --stdout` を試しやすくなります。

### `uninstall-global-agents`

`~/.codex/AGENTS.md` に入れた `codex-handoff` の管理ブロックだけを削除します。ここでもバックアップを作成します。ほかの既存ルールは残します。

### `prepare`

カレントディレクトリからプロジェクトを自動判定し、対応する global store を自動で作成または再利用して、`project.md`、`decisions.md`、`tasks.md`、`next-thread.md` をまとめて更新します。同時にリポジトリ内 `.codex-handoff/` の同期ミラーも更新します。`--stdout` を付けると、そのまま新スレッドへ貼れる本文を出力します。

### `capture`

現在の Git 状態を `state.json` に保存し、`project.md`、`decisions.md`、`tasks.md`、`next-thread.md` を再生成します。`--note` を付けると、その内容を優先度の高いタスクとして自動生成結果へ反映します。更新後はリポジトリ内 `.codex-handoff/` にも同期します。

### `where`

現在のプロジェクトに対応する global store と、リポジトリ内の local mirror の場所を表示します。

### `doctor`

global setup、現在の project store、global store 側の UTF-8 BOM なし、Git 利用可否を確認します。

### `init`

互換コマンドです。現在のプロジェクト store を先に作りたい場合だけ使います。通常は `prepare` や `capture` が自動作成するため不要です。

## 保存先

- global 設定と全プロジェクトのメモ: `~/.codex-handoff/`
- Codex への自動読込ルール: `~/.codex/AGENTS.md`
- プロジェクトごとの正本: `~/.codex-handoff/projects/<project-id>/`
- リポジトリ内の同期ミラー: `.codex-handoff/`
- 保存される主なファイル:
  - `project.md`
  - `decisions.md`
  - `tasks.md`
  - `state.json`
  - `next-thread.md`

`project.md`、`decisions.md`、`tasks.md`、`next-thread.md` はすべて自動生成対象です。README、AGENTS、Git 状態、Codex の最近のメインセッションをもとに再構成します。

## 設計方針

- global store の生成物は UTF-8 BOM なし
- global store を正本にし、リポジトリ内 `.codex-handoff/` は同期ミラーとして扱う
- 差分本文や環境変数値などの機密は収集しない
- Git がないディレクトリでも、パス単位の project store として動作する
- 既存のローカル `.codex-handoff/` が見つかった場合は global store へ取り込みつつ、その後は同期ミラーとして再利用する

### Windows PowerShell 互換

global store は UTF-8 BOM なしで保持します。リポジトリ内 `.codex-handoff/` の同期ミラーは Windows PowerShell 5.1 の `Get-Content` でもそのまま読めるように UTF-8 BOM 付きで書き出します。

## 現実的な制約

- Codex デスクトップアプリへ独自 UI を埋め込む公開 API は前提にしていません
- 新規スレッド開始時の完全なネイティブ hook はない前提です
- そのため、v2 は self-contained な CLI を基本にし、必要な人だけ global `AGENTS.md` 連携を opt-in で有効化する設計です

## Windows 配布

エンドユーザー向けには GUI を単体 `exe` にして配る前提です。この `exe` は初回起動時に `%LOCALAPPDATA%\CodexHandoff` へ自己インストールでき、開き直しなしでそのまま Step 2 に進めます。

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_gui.ps1
```

生成物は `dist\CodexHandoffSetup.exe` です。将来はこの `exe` を Inno Setup などでインストーラー化できますが、現段階でも「ダウンロードして実行」の配布は可能です。

ビルド時には次も自動生成します。

- `build-assets/codex-handoff.ico`
- `build-assets/version_info.txt`

そのため、配布用 `exe` にはアプリ用アイコンと Windows のバージョン情報が入ります。

## GitHub Releases

GitHub Releases 向けの Windows ビルド workflow は [release-windows.yml](C:\開発\Codex用OSS\.github\workflows\release-windows.yml) です。

- `workflow_dispatch` で手動実行可能
- `v*` タグ push で自動実行
- 成果物として `CodexHandoffSetup.exe` を artifact に保存
- タグ実行時はそのまま Release asset に添付

想定フロー:

```powershell
git tag v0.5.2
git push origin v0.5.2
```
