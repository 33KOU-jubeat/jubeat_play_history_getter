from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# --- データベースのテーブル（モデル）定義 ---
class JubeatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False) # 簡易的な識別用（IPなど）
    konami_id = db.Column(db.String(50), nullable=False) # コナミID
    date = db.Column(db.String(255), nullable=False) # プレー日時
    music_name = db.Column(db.String(255), nullable=False) # 曲名
    difficulty = db.Column(db.String(50)) # 難易度
    score = db.Column(db.Integer) # スコア
    is_hardmode = db.Column(db.Integer) # ハードモード有無
    rival1_name = db.Column(db.String(50)) # 他プレイヤー1の名前
    rival1_score = db.Column(db.Integer) # 他プレイヤー1のスコア
    rival2_name = db.Column(db.String(50)) # 他プレイヤー2の名前
    rival2_score = db.Column(db.Integer) # 他プレイヤー2のスコア
    rival3_name = db.Column(db.String(50)) # 他プレイヤー3の名前
    rival3_score = db.Column(db.Integer) # 他プレイヤー3のスコア

# 取得対象の楽曲IDと難易度をあらかじめ登録しておくマスターテーブル
class JubeatMusicMaster(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    music_id = db.Column(db.String(50), nullable=False) # 楽曲ID (mid)
    seq_id = db.Column(db.Integer, nullable=False)      # 難易度 (0, 1, 2)
    comment = db.Column(db.String(100))                 # 管理用の曲名メモなど

# ランキング結果保存用テーブル
class JubeatRanking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    music_name = db.Column(db.String(255), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    play_date = db.Column(db.String(50), nullable=False)

# ランキング結果最終更新日時格納用テーブル
class RankingUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    update_date = db.Column(db.String(255), nullable=False)