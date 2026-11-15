# 【第1段階：ビルド環境】必要なライブラリをダウンロード
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
# キャッシュを残さずユーザーディレクトリにインストール
RUN pip install --user --no-cache-dir -r requirements.txt

# 【第2段階：本番環境】実行に必要なものだけを抽出して軽量化（150MB以下要件）
FROM python:3.11-slim
WORKDIR /app

# 第1段階からインストール済みのライブラリだけをコピー
COPY --from=builder /root/.local /root/.local
COPY . .

# コピーしたライブラリにパスを通す
ENV PATH=/root/.local/bin:$PATH

# Cloud Run上で呼び出された際に実行するコマンド
CMD ["python", "youtube_firestore.py"]