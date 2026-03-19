# codex-handoff

`codex-handoff` は、Codex で新しいスレッドを始める前に、同一プロジェクトの前提・決定事項・未完了タスク・現在の作業状態を自動で整理するローカル CLI です。

正本のメモは `~/.codex-handoff/projects/<project-id>/` に保存しつつ、各リポジトリの `.codex-handoff/` に読みやすい同期ミラーを置きます。Codex 側の読み込み導線は `~/.codex/AGENTS.md` へ 1 回だけ入れます。

v2.1 では shell を使いたくない人向けに `codex-handoff-ui` を追加しました。配布時はこの GUI を単体 `exe` にして配り、初回起動時に `%LOCALAPPDATA%\CodexHandoff` へ自己インストールできます。

v2.2 では background sync を追加し、初回セットアップ後は GUI を開かなくても active workspace の handoff を裏で更新できるようにしました。
新しく作ったプロジェクトでも、Codex でそのフォルダを active workspace にした時点で project store を自動作成して追従します。

v0.6 では `memory.json` を構造化メモリの正本として追加し、ユーザーの思想・仕様・制約・採用判断に加えて、進捗・検証・コミット・変更ファイル、現在の主題、注目パス、次アクションを分けて保持するようにしました。あわせて、薄いユーザー共通設定は `~/.codex-handoff/user-memory.json` に分離して保持します。

## 対象環境

- Windows 11
- CodexWindowsApp
- PowerShell
- `uv` が使える Python 環境、または GitHub Releases から取得した Windows 用 `setup.exe`

## 目的

- プロジェクト内でスレッドを切り替えるたびに前提を手で書き直す負担を減らす
- コンテキスト圧縮で性能が落ちる前に、新しいスレッドへ安全に移る
- Codex 本体の内部 DB や未公開 UI フックに依存せず、壊れにくい運用を作る
- GitHub から導入したら、各プロジェクトで追加設定しなくても使える形にする

## 最初に選ぶ導線

### CLI で使う人

- `uv tool install codex-handoff` で CLI を入れる
- `codex-handoff setup --install-global-agents` を 1 回だけ実行する
- 以後は各プロジェクトで `codex-handoff prepare --stdout` を呼ぶ

### GUI / installer で使う人

- GitHub Releases から `CodexHandoffSetup.exe` または版付き `CodexHandoffSetup-<version>.exe` を取得する
- `setup.exe` を起動して `%LOCALAPPDATA%\CodexHandoff` へ自己インストールする
- Step 2 の `Apply setup` で global setup と background sync を有効化する

## インストール

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv tool install codex-handoff
codex-handoff setup
```

自動で次スレッドに引き継がせたいなら、インストール直後の最短導線は次です。

```powershell
codex-handoff setup --install-global-agents
codex-handoff prepare --stdout
```

開発中のローカル clone から試す場合:

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv tool install .
codex-handoff setup
```

このリポジトリ自身を開発している間は、installed CLI より checkout 中の source を優先してください。

```powershell
$env:UV_CACHE_DIR = Join-Path $env:USERPROFILE '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $env:USERPROFILE '.uv-python'
uv run codex-handoff prepare --stdout
```

## 導入確認

インストール直後は、次の 3 点ができれば成功です。

```powershell
codex-handoff where
codex-handoff doctor
codex-handoff prepare --stdout
```

- `where` で `~/.codex-handoff/projects/<project-id>/` と `.codex-handoff/` の両方が表示される
- `doctor` で global setup と project store の問題が出ない
- `prepare --stdout` で `.codex-handoff/next-thread.md` 相当の本文が出る

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
- `~/.codex-handoff/user-memory.json` を作成

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

カレントディレクトリからプロジェクトを自動判定し、対応する global store を自動で作成または再利用して、`project.md`、`decisions.md`、`tasks.md`、`memory.json`、`next-thread.md` をまとめて更新します。同時にリポジトリ内 `.codex-handoff/` の同期ミラーも更新します。`--stdout` を付けると、そのまま新スレッドへ貼れる本文を出力します。

### `capture`

現在の Git 状態を `state.json` に保存し、`project.md`、`decisions.md`、`tasks.md`、`memory.json`、`next-thread.md` を再生成します。`--note` を付けると、その内容を優先度の高いタスクとして自動生成結果へ反映します。更新後はリポジトリ内 `.codex-handoff/` にも同期します。

### `where`

現在のプロジェクトに対応する global store と、リポジトリ内の local mirror の場所を表示します。

### `doctor`

global setup、現在の project store、global store 側の UTF-8 BOM なし、Git 利用可否を確認します。

### `init`

互換コマンドです。現在のプロジェクト store を先に作りたい場合だけ使います。通常は `prepare` や `capture` が自動作成するため不要です。

## 動作の流れ

新しいスレッドを始める時は、だいたい次の順で動きます。

1. `setup` が global store と AGENTS 用の設定を用意する
2. `prepare` が現在の workspace から `project-id` を決める
3. 既存の project store があれば再利用し、なければ新規作成する
4. `memory.json` を含む handoff 一式を更新する
5. リポジトリ内 `.codex-handoff/` に読みやすい同期ミラーを書き出す
6. 新スレッドでは `AGENTS.md` 経由で `prepare --stdout` を試し、その出力を前提に再開する

## 保存先

- global 設定と全プロジェクトのメモ: `~/.codex-handoff/`
- Codex への自動読込ルール: `~/.codex/AGENTS.md`
- プロジェクトごとの正本: `~/.codex-handoff/projects/<project-id>/`
- リポジトリ内の同期ミラー: `.codex-handoff/`
- 保存される主なファイル:
  - `project.md`
  - `decisions.md`
  - `tasks.md`
  - `memory.json`
  - `state.json`
  - `next-thread.md`

`project.md`、`decisions.md`、`tasks.md`、`memory.json`、`next-thread.md` はすべて自動生成対象です。README、AGENTS、Git 状態、Codex の最近のメインセッションをもとに再構成します。`memory.json` は構造化メモリの正本で、`semantic_entries`、`worklog_entries`、`current_focus`、`focus_paths`、`next_actions` を持ちます。`state.json` は live status の置き場で、`captured_at`、Git の現在地、追跡ブランチとの差分、必要に応じて GitHub Release / workflow の最新状態を毎回再取得して持ちます。`~/.codex-handoff/user-memory.json` には、返答言語や危険操作前の確認方針のような薄いユーザー共通設定だけを保持します。

## 保存するもの / しないもの

| 種類 | 例 | 保存先 |
| --- | --- | --- |
| project memory | 仕様、決定事項、`focus_paths`、`next_actions`、最近の進捗 | `~/.codex-handoff/projects/<project-id>/memory.json` |
| user-global memory | 回答言語、危険操作前の確認、恒常的な環境前提 | `~/.codex-handoff/user-memory.json` |
| 同期ミラー | `project.md`、`decisions.md`、`tasks.md`、`next-thread.md` | リポジトリ内 `.codex-handoff/` |
| 保存しないもの | 差分本文、環境変数値、機密、長い推論本文 | 保存しない |

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

生成物は常に次の 2 つです。

- `dist\CodexHandoffSetup.exe`
- `dist\CodexHandoffSetup-<version>.exe`

前者は常に最新を指す固定名、後者は GitHub Releases や手動配布で差し替わりを追跡しやすい版付きファイル名です。現段階では「ダウンロードして実行」の配布を前提にしており、Inno Setup のような別インストーラーは必須ではありません。

利用者視点では次の挙動です。

- `setup.exe` は `%LOCALAPPDATA%\CodexHandoff` に本体を入れる
- 更新時は新しい `setup.exe` をそのまま再実行すれば上書きできる
- background sync は active workspace を見て handoff を裏で更新する
- 不要になったら `%LOCALAPPDATA%\CodexHandoff` を削除し、必要なら `codex-handoff uninstall-global-agents` で AGENTS の管理ブロックも外せる

ビルド時には次も自動生成します。

- `build-assets/codex-handoff.ico`
- `build-assets/version_info.txt`

そのため、配布用 `exe` にはアプリ用アイコンと Windows のバージョン情報が入ります。

この開発元リポジトリでは、`.codex-handoff/`、`dist/`、`build/`、`build-assets/` 配下の生成物は commit しない前提です。公開用の配布物は Git 管理ではなく GitHub Releases に載せます。

## GitHub Releases

GitHub Releases 向けの Windows ビルド workflow は [release-windows.yml](.github/workflows/release-windows.yml) です。

- `workflow_dispatch` で手動実行可能
- `v*` タグ push で自動実行
- 成果物として `CodexHandoffSetup.exe` と `CodexHandoffSetup-<version>.exe` を artifact に保存
- タグ実行時はそのまま両方を Release asset に添付

想定フロー:

```powershell
git tag v0.6.8
git push origin v0.6.8
```

## ライセンス

MIT License です。詳細は `LICENSE` を参照してください。
