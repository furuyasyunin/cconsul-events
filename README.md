# C-Consul 学舎 イベント通知

GitHub Actionsで定期的にPlaywrightを使って学舎サイトにログインし、
イベント一覧をスクレイピングしてLINEに通知します。

## セットアップ
1. このリポジトリをGitHubにpush（Publicで作成）
2. Settings → Secrets and variables → Actions に以下を追加
   - LINE_CHANNEL_ACCESS_TOKEN
   - TARGET_IDS
   - LOGIN_URL
   - EVENTS_URL
   - CCONSUL_ID
   - CCONSUL_PASSWORD
3. Actionsタブでワークフローを実行 or cronに従って定期実行

## 実行環境
- Python 3.11（推奨）
- GitHub Actions (ubuntu-latest)

## カスタマイズ
- `scraper_login.py`: ログインフォームのセレクタを調整
- `parsers.py`: イベント一覧のDOMセレクタを調整
- `run.yml`: スケジュールやPythonバージョンを調整
