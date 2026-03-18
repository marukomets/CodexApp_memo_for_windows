# Next Thread Brief: Codex用OSS

- 生成日時: `2026-03-18T16:25:10+09:00`
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
- `AGENTS.md`

## 現在の主題

- これって新しいスレッド始めるとき明示しなくてもちゃんと参照してくれるのかな

## 直近の会話要点

### セッション `019cffd1`
- 開始 `2026-03-18T07:21:07.461Z` / 更新 `2026-03-18T07:22:20.683Z`
- 最初の依頼: これって新しいスレッド始めるとき明示しなくてもちゃんと参照してくれるのかな
- 直近の回答: このリポジトリでは、かなり高い確率で参照されます。ただし「Codex アプリがネイティブに自動記憶している」のではなく、`AGENTS.md` の指示で新スレッド開始時に `codex-handoff prepare` を実行して、[.codex-handoff/next-thread.md](C:/開発/Codex用OSS/.codex-handoff/next-thread.md) と [.codex-handoff/project.md](C:/開発/Codex用OSS/.codex-handoff/project.md) を読む運用になっている…

### セッション `019cff79`
- 開始 `2026-03-18T05:45:06.101Z` / 更新 `2026-03-18T06:55:40.381Z`
- 最初の依頼: 引き継げてる？
- 直近の依頼: 最適化して、全てnext-thread.mdと同じく自動で更新されていくようにしてください。
- 直近の回答: **結果** [project.md](C:/開発/Codex用OSS/.codex-handoff/project.md)、[decisions.md](C:/開発/Codex用OSS/.codex-handoff/decisions.md)、[tasks.md](C:/開発/Codex用OSS/.codex-handoff/tasks.md)、[next-thread.md](C:/開発/Codex用OSS/.codex-handoff/next-thread.md) を `next-thread.md` と同じ自動更新系に揃えました。実装は [s…

### セッション `019cfe88`
- 開始 `2026-03-18T01:21:28.232Z` / 更新 `2026-03-18T05:44:53.602Z`
- 最初の依頼: Codexappとても使いやすくはまっています。 ですが、プロジェクト内でもスレッドを変えると一切のメモリを引き継がない、端末を変えても同様に引継ぎができないなど主に引継ぎや事前のすり合わせをする際に多少の不便さを感じる部分があります。 そもそも同じスレッド内でずっと進められればそれに越したことはないですが、長引いた結果コンテキスト圧縮を繰り返すと目に見えて性能が落ちるためスレッドを定期的に新しくすることは必須かと思っています。 これを解決できるCodexapp用のOSS開発できます？
- 直近の依頼: まぁ後で考えよう。一回他のスレッドに引き継げるか試してみよう
- 直近の回答: そうしてください。今の状態なら、新しいスレッド側でこのプロジェクトを開いたときに、background sync が更新した [next-thread.md](C:\Users\stsuc\.codex-handoff\projects\codex-oss-963061a73d87\next-thread.md) を参照できる状態です。 見るべきポイントは単純です。新スレッドで、 - 今の会話の要点が最初から把握されるか - Git なしでも文脈が落ちないか - 追加説明の手間がどこまで減ったか ここを見てください。もし引き継ぎがまだ薄いなら、次は「要…

## 直近の決定事項

- 2026-03-18: **結果** project.md、decisions.md、tasks.md、next-thread.md を `next-thread.md` と同じ自動更新系に揃えました。実装は [s…
- 2026-03-18: Git 管理外のディレクトリとして path 単位で handoff を継続する。
- 2026-03-18: `codex-handoff` はこの環境では正常に動いていて、新スレッド向けのブリーフも生成できています。続けて `.codex-handoff/next-thread.md` と `.codex-handoff/project.md` を見て、実際に新スレッドで拾う前提が揃…
- 2026-03-18: 新しいスレッド開始時に `codex-handoff` 前提が実際に取れるか、このリポジトリの設定どおり確認します。まず `codex-handoff prepare --stdout` を実行して、その後 `.codex-handoff` の状態を見ます。

## 未完了タスク

- [ ] これって新しいスレッド始めるとき明示しなくてもちゃんと参照してくれるのかな
- [ ] 変更ファイルを確認する: `.github/workflows/release-windows.yml`, `.gitignore`, `README.md` など
- [ ] 重要ファイルを確認して文脈を戻す: `README.md`, `src`, `tests`
- [ ] 最適化して、全てnext-thread.mdと同じく自動で更新されていくようにしてください。

## 現在の作業状態

- プロジェクト名: `Codex用OSS`
- 直近に検出した Codex セッション: 3 件
- Git ルート: `C:/開発/Codex用OSS`
- ブランチ: `master`
- 作業ツリー: `dirty`

### 変更ファイル

- `.github/workflows/release-windows.yml` (??)
- `.gitignore` (??)
- `README.md` (??)
- `build-assets/CodexHandoffBackground.zip` (??)
- `build-assets/background-build/CodexHandoffBackground/Analysis-00.toc` (??)
- `build-assets/background-build/CodexHandoffBackground/COLLECT-00.toc` (??)
- `build-assets/background-build/CodexHandoffBackground/CodexHandoffBackground.exe` (??)
- `build-assets/background-build/CodexHandoffBackground/CodexHandoffBackground.pkg` (??)
- `build-assets/background-build/CodexHandoffBackground/EXE-00.toc` (??)
- `build-assets/background-build/CodexHandoffBackground/PKG-00.toc` (??)
- `build-assets/background-build/CodexHandoffBackground/PYZ-00.pyz` (??)
- `build-assets/background-build/CodexHandoffBackground/PYZ-00.toc` (??)

### 検出した重要パス

- `README.md`
- `src`
- `tests`

## 新スレッドで最初にやるべき 3 手

1. `tasks.md` の先頭タスクを確認する: これって新しいスレッド始めるとき明示しなくてもちゃんと参照してくれるのかな
2. 変更ファイルを確認して現在地を把握する: `.github/workflows/release-windows.yml`, `.gitignore`, `README.md` など
3. 直近の回答内容を踏まえて次の判断を置く: このリポジトリでは、かなり高い確率で参照されます。ただし「Codex アプリがネイティブに自動記憶している」のではなく、`AGENTS.md` の指示で新スレッド開始時に `codex-handoff prepare` を実行して、[.c…

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
