# -*- coding: utf-8 -*-
from flask import Flask, session
from flask_cors import CORS

from app import static
from app.database import db, JubeatMusicMaster
from app.config import Config
# 分割したBlueprintをインポート
from app.routes.ranking_scraping import ranking_scraping_bp
from app.routes.admin import admin_bp
from app.routes.get_history import get_history_bp
from app.routes.userpage import userpage_bp

app = Flask(__name__)
app.register_blueprint(static.app)

# ★重要★ コナミ公式ドメインからの通信だけを許可する
CORS(app, origins=["https://p.eagate.573.jp"])

# 設定の読み込み
app.config.from_object(Config)

# データベースの初期化
db.init_app(app)

# 各Blueprintをアプリに登録
app.register_blueprint(ranking_scraping_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(get_history_bp)
app.register_blueprint(userpage_bp)

# アプリ起動時にテーブルが存在しない場合は自動作成する
with app.app_context():
    db.create_all()
     # テスト用初期データ（空の場合のみ追加）
    if not JubeatMusicMaster.query.first():
        sample1 = JubeatMusicMaster(music_id="96209810", seq_id=2, comment="I")
        sample2 = JubeatMusicMaster(music_id="69014196", seq_id=2, comment="[]DENTITY")
        db.session.add_all([sample1, sample2])
        db.session.commit()
