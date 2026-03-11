# Railway で公開する手順

このドキュメントでは、報告書自動作成アプリを [Railway](https://railway.app) にデプロイして、インターネットから開けるようにする手順を説明します。

---

## 前提

- Railway のアカウント（GitHub 連携で無料登録可）
- このリポジトリを **GitHub にプッシュ**していること（Railway は GitHub からデプロイします）

---

## 1. リポジトリを GitHub に用意する

まだの場合、プロジェクトを GitHub にプッシュしてください。

```bash
cd 報告書自動作成
git init
git add .
git commit -m "Initial commit"
# GitHub でリポジトリを作成後
git remote add origin https://github.com/あなたのユーザー名/リポジトリ名.git
git push -u origin main
```

※ `.env` はコミットしないでください（`.gitignore` に含めています）。API キーは Railway の画面で設定します。

---

## 2. Railway でプロジェクトを作成

1. [Railway](https://railway.app) にログインする。
2. **「New Project」** をクリック。
3. **「Deploy from GitHub repo」** を選び、このリポジトリを選択する。
4. リポジトリを選ぶと、自動でビルド・デプロイが始まります。

---

## 3. 永続ストレージ（Volume）を追加する

報告書データを消さないために、SQLite 用の **Volume** を追加します。

1. Railway のプロジェクトで、作成された **Service** を開く。
2. **「Variables」** タブの近くにある **「+ New」** の **「Volume」** を選ぶ（または Settings → Volumes）。
3. Volume を追加し、**マウントパス** を **`/data`** にする。
4. **「Variables」** で次の環境変数を追加する：
   - **`REPORTS_DB`** = **`/data/reports.db`**  
     （報告書用 SQLite を Volume に保存）

---

## 4. 環境変数を設定する

同じ **Variables** タブで、以下を追加します。

| 変数名 | 値 | 説明 |
|--------|-----|------|
| `SUMMARIZE_MODE` | `api` | 要約にクラウド API を使う場合（推奨）。`rule` なら API キー不要。 |
| `OPENAI_API_KEY` | `sk-xxxx...` | OpenAI の API キー（SUMMARIZE_MODE=api の場合） |
| `REPORTS_DB` | `/data/reports.db` | 上記 Volume を使う場合（必須） |

**API を使わず試すだけの場合**

- `SUMMARIZE_MODE` = `rule` のみで OK（API キー不要）。

**公開URLを「他端末で開く」に表示したい場合**

- デプロイ後に表示される **「https://xxxx.up.railway.app」** をコピーし、
- 変数 **`PUBLIC_URL`** = `https://xxxx.up.railway.app` を追加する（`xxxx` はあなたのサービス名）。

---

## 5. デプロイの確認

1. ビルドが完了すると、**「Settings」** の **「Networking」** で **「Generate Domain」** を押すと URL が発行されます。
2. その URL（例: `https://報告書自動作成-production.up.railway.app`）をブラウザで開く。
3. トップや「他端末で開く」の案内が表示されれば成功です。PDF をアップロードして報告書が生成できるか確認してください。

---

## 6. よくあること

- **「Application failed to respond」**  
  - ビルドは成功しているか、Variables に `REPORTS_DB` が設定されているか確認する。Volume を追加した場合はマウントパスが `/data` になっているか確認する。
- **報告書が保存されない・消える**  
  - Volume を追加していないと、再デプロイで SQLite が消えます。必ず Volume を追加し、`REPORTS_DB=/data/reports.db` を設定する。
- **PDF アップロードや生成が遅い・タイムアウト**  
  - Railway の無料枠ではスリープやリソース制限がある場合があります。有料プランで改善することがあります。

---

## まとめ

| 項目 | 内容 |
|------|------|
| 起動方法 | `Procfile` の `web: uvicorn main:app --host 0.0.0.0 --port $PORT --app-dir backend` |
| データ保存 | Volume を `/data` にマウントし、`REPORTS_DB=/data/reports.db` を設定 |
| 必須の環境変数 | `REPORTS_DB`（Volume を使う場合）。API を使う場合は `OPENAI_API_KEY` と `SUMMARIZE_MODE=api` |

これで、どこからでもブラウザで報告書アプリを開いて利用できます。
