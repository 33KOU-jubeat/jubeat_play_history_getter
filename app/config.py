import os

class Config:
    SECRET_KEY = "jubeat_secret_key_12345"
    # --- データベース設定 ---
    # Renderの環境変数（DATABASE_URL）があればそれを使い、なければローカル用にSQLiteを使う
    # ※RenderのURLが「postgres://」で始まる場合、SQLAlchemy用に「postgresql://」に置換する対策を入れています
    db_url = os.environ.get('DATABASE_URL', 'sqlite:///jubeat_local.db')
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# グローバル変数で現在の実行ステータスを管理（画面に進行状況を出すため）
SCRAPING_STATUS = {
    "is_running": False,
    "success_count": 0,
    "failed_count": 0,
    "total_count": 0
}