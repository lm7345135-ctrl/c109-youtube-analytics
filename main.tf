terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# 認証とプロジェクトの基本設定
provider "google" {
  project     = "vibrant-arcanum-514402-q3"
  region      = "us-central1"
  credentials = file("gcp-key.json")
}

# 1. Artifact Registry (コンテナイメージ保管庫: 無料枠500MB/月)
resource "google_artifact_registry_repository" "youtube_app_repo" {
  location      = "us-central1"
  repository_id = "youtube-analytics-repo"
  description   = "Docker repository for YouTube Analytics App"
  format        = "DOCKER"

  # 無料枠超過を防ぐためのクリーンアップポリシー（最新2世代のみ保持）
  cleanup_policies {
    id     = "keep-minimum-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }
  cleanup_policies {
    id     = "delete-older-versions"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30日経過で削除
    }
  }
}

# 2. Cloud Run (サーバーレス実行環境: 月200万リクエスト無料)
resource "google_cloud_run_v2_service" "youtube_fast_path" {
  name     = "youtube-fast-path-service"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    containers {
      # Terraform構築時は公式の軽量ダミーイメージを入れて枠だけ作る
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      
      # 厳密なリソース制限（無料枠ガードレール）
      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
      }
    }

    # スケール制限（待機コストゼロ、最大2インスタンス）
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
  }
}

# 3. BigQueryデータセット（Slow Path用: 分析基盤）
resource "google_bigquery_dataset" "youtube_dataset" {
  dataset_id = "youtube_analytics_dataset"
  location   = "US" # 無料枠適用
}

# 4. GCSバケット（生データ一時保存用データレイク: 5GB無料枠）
resource "google_storage_bucket" "youtube_datalake" {
  name          = "youtube-datalake-vibrant-arcanum-514402-q3" # プロジェクトIDを含めて一意にする
  location      = "US-CENTRAL1"
  force_destroy = true

  # 無料枠超過を防ぐためのライフサイクルルール
  lifecycle_rule {
    condition {
      age = 3 # 3日で自動削除（要件定義書準拠）
    }
    action {
      type = "Delete"
    }
  }
}