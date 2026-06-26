# -*- coding: utf-8 -*-
import os

import io
import re
import browser_cookie3
import urllib.request
import http.cookiejar
import pandas as pd

from bs4 import BeautifulSoup
from flask import Flask, render_template, request, send_file, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from app import static

app = Flask(__name__)
app.register_blueprint(static.app)

DATA_STORE = {}
ID_STORE = {}

# ★重要★ すべてのドメイン（e-amusement側）からのデータ受信を許可する設定
CORS(app)

# --- データベース設定 ---
# Renderの環境変数（DATABASE_URL）があればそれを使い、なければローカル用にSQLiteを使う
# ※RenderのURLが「postgres://」で始まる場合、SQLAlchemy用に「postgresql://」に置換する対策を入れています
db_url = os.environ.get('DATABASE_URL', 'sqlite:///jubeat_local.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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

# アプリ起動時にテーブルが存在しない場合は自動作成する
with app.app_context():
    db.create_all()

def parse_html_list(html_list):
  # インスタンスの作成
  soup = BeautifulSoup(html_list[0], "html.parser")

  # プレイ履歴の曲名を取得
  info_date = soup.find_all("div", class_="info_date")

  date_list = []
  for tag in info_date:
    
    # 1. タグ全体の文字列（または中のテキスト）を取得し、カンマで分割
    # ※ HTML構造を保ったまま「>」と「<」を判定するため str(tag) を使用します
    raw_text = str(tag)
    comma_split_items = raw_text.split(",")
    
    for item in comma_split_items:
      # 2. 正則表現を使って「>」と「<」に挟まれた部分をすべて抽出
      # [^><]+ は「>」でも「<」でもない文字が1文字以上続く部分にマッチします
      matches = re.findall(r'>([^><]+)<', item)
        
      for match in matches:
        # 前後の余計な空白や改行を削除（トリミング）
        clean_text = match.strip()
            
        # 3. 空部分は無視する
        if clean_text:
          if clean_text != "プレー日時:":
            date_list.append(clean_text)


  # プレイ履歴の曲名を取得
  info_title = soup.find_all("div", class_="info_title")

  title_list = []
  for tag in info_title:
    
    # 1. タグ全体の文字列（または中のテキスト）を取得し、カンマで分割
    # ※ HTML構造を保ったまま「>」と「<」を判定するため str(tag) を使用します
    raw_text = str(tag)
    comma_split_items = raw_text.split(",")
    
    for item in comma_split_items:
      # 2. 正則表現を使って「>」と「<」に挟まれた部分をすべて抽出
      # [^><]+ は「>」でも「<」でもない文字が1文字以上続く部分にマッチします
      matches = re.findall(r'>([^><]+)<', item)
        
      for match in matches:
        # 前後の余計な空白や改行を削除（トリミング）
        clean_text = match.strip()
            
        # 3. 空部分は無視する
        if clean_text:
          title_list.append(clean_text)

  # プレイ履歴の難易度・スコアを取得
  info_score = soup.find_all("div", class_="info_score")

  difficulty_list = []
  score_list = []
  hardmode_list = []
  for tag in info_score:
    
    # 1. タグ全体の文字列（または中のテキスト）を取得し、カンマで分割
    # ※ HTML構造を保ったまま「>」と「<」を判定するため str(tag) を使用します
    raw_text = str(tag)
    comma_split_items = raw_text.split(",")
    
    for item in comma_split_items:
      hardmode_flag = 0
      target = 'li class=\"'
      idx = item.find(target)
      difficulty_temp = item[idx+len(target):]
      target = '\"'
      idx_difficulty = difficulty_temp.find(target)


      # 2. 正則表現を使って「>」と「<」に挟まれた部分をすべて抽出
      # [^><]+ は「>」でも「<」でもない文字が1文字以上続く部分にマッチします
      matches = re.findall(r'>([^><]+)<', item)
        
      for match in matches:
        # 前後の余計な空白や改行を削除（トリミング）
        clean_text_all = match.strip()
        target = ' '
        idx = clean_text_all.find(target)
        clean_text = clean_text_all[:idx]
            
        # 3. 空部分は無視する
        if clean_text:
          if clean_text == "HARD":
            hardmode_flag = 1
          else :
            difficulty_list.append(difficulty_temp[:idx_difficulty])
            score_list.append(clean_text)  

      hardmode_list.append(hardmode_flag)

  # プレイ履歴のマッチング相手・難易度・スコアを取得
  player_match = soup.find_all("div", class_="player_match")
  rival1_name_list = []
  rival1_score_list = []
  rival2_name_list = []
  rival2_score_list = []
  rival3_name_list = []
  rival3_score_list = []
  for tag in player_match:

    # 1. タグ全体の文字列（または中のテキスト）を取得し、カンマで分割
    # ※ HTML構造を保ったまま「>」と「<」を判定するため str(tag) を使用します
    raw_text = str(tag)
    comma_split_items = raw_text.split(",")
      
    for item in comma_split_items:
      # デフォルト値設定
      rival1_name_text = ""
      rival1_score_text = ""
      rival2_name_text = ""
      rival2_score_text = ""
      rival3_name_text = ""
      rival3_score_text = ""

      # マッチング人数をカウント
      matching_num = item.count("<ul>")

      if matching_num != 0:
        # 2. 正則表現を使って「>」と「<」に挟まれた部分をすべて抽出
        # [^><]+ は「>」でも「<」でもない文字が1文字以上続く部分にマッチします
        matches = re.findall(r'>([^><]+)<', item)

        rival_list = []
        for match in matches:
          clean_text = match.strip()
          if clean_text:
            rival_list.append(match)

        if len(rival_list) >= 6:
          rival1_name_text = rival_list[0].strip()
          clean_text_all = rival_list[1].strip()
          target = ' '
          idx = clean_text_all.find(target)
          rival1_score_text = clean_text_all[:idx]
          rival2_name_text = rival_list[2].strip()
          clean_text_all = rival_list[3].strip()
          target = ' '
          idx = clean_text_all.find(target)
          rival2_score_text = clean_text_all[:idx]
          rival3_name_text = rival_list[4].strip()
          clean_text_all = rival_list[5].strip()
          target = ' '
          idx = clean_text_all.find(target)
          rival3_score_text = clean_text_all[:idx]
        elif len(rival_list) >= 4:
          rival1_name_text = rival_list[0].strip()
          clean_text_all = rival_list[1].strip()
          target = ' '
          idx = clean_text_all.find(target)
          rival1_score_text = clean_text_all[:idx]
          rival2_name_text = rival_list[2].strip()
          clean_text_all = rival_list[3].strip()
          target = ' '
          idx = clean_text_all.find(target)
          rival2_score_text = clean_text_all[:idx]
        elif len(rival_list) >= 2:
          rival1_name_text = rival_list[0].strip()
          clean_text_all = rival_list[1].strip()
          target = ' '
          idx = clean_text_all.find(target)
          rival1_score_text = clean_text_all[:idx]

      rival1_name_list.append(rival1_name_text)
      rival1_score_list.append(rival1_score_text)
      rival2_name_list.append(rival2_name_text)
      rival2_score_list.append(rival2_score_text)
      rival3_name_list.append(rival3_name_text)
      rival3_score_list.append(rival3_score_text)


  history_data_list = []
  for i in range(len(title_list)):
    play_data = {
      "date": date_list[i],
      "music_title": title_list[i],
      "difficulty": difficulty_list[i],
      "score": score_list[i],
      "hardmode": hardmode_list[i],
      "rival1_name": rival1_name_list[i],
      "rival1_score": rival1_score_list[i],
      "rival2_name": rival2_name_list[i],
      "rival2_score": rival2_score_list[i],
      "rival3_name": rival3_name_list[i],
      "rival3_score": rival3_score_list[i]
    }
    history_data_list.append(play_data)

  return history_data_list

@app.route('/')
def index():
  user_id = request.remote_addr
  history_data_table = DATA_STORE.get(user_id, None)
  konami_id = ID_STORE.get(user_id, None)
  if history_data_table:
    return render_template('index.html', history_data_table = history_data_table, konami_id = konami_id)
  else :
    return render_template('index.html', history_data_table = None, konami_id = None)

# 2. JavaScriptからHTMLデータを受け取るAPI（POSTエンドポイント）
@app.route('/receive_html', methods=['POST'])
def receive_html():
    try:
        # JSON形式のデータを受け取る
        req_data = request.get_json()
        if not req_data or 'html_list' not in req_data:
            return jsonify({"status": "error", "message": "データが空です"}), 400
            
        konami_id = req_data['konami_id']
        html_list = req_data['html_list']
        history_data = parse_html_list(html_list)
        
        if not history_data:
            return jsonify({"status": "error", "message": "データの解析に失敗しました"}), 400

        user_id = request.remote_addr

        # 【重複対策】同じ日時・曲名・難易度のデータが既にDBにあれば、二重登録を防ぐために削除（または上書き）する処理
        for item in history_data:
            existing = JubeatHistory.query.filter_by(
                konami_id=konami_id, 
                date=item["date"], 
                music_name=item["music_title"], 
                difficulty=item["difficulty"]
            ).first()
            if existing:
                db.session.delete(existing)
            
            # 新しいレコードを追加
            new_record = JubeatHistory(
                user_id=user_id,
                konami_id=konami_id,
                date=item["date"], 
                music_name=item["music_title"],
                difficulty=item["difficulty"],
                score=item["score"],
                is_hardmode=item["hardmode"],
                rival1_name=item["rival1_name"],
                rival1_score=item["rival1_score"],
                rival2_name=item["rival2_name"],
                rival2_score=item["rival2_score"],
                rival3_name=item["rival3_name"],
                rival3_score=item["rival3_score"]
            )
            db.session.add(new_record)
            
        # まとめてDBに保存確定（コミット）
        db.session.commit()

        DATA_STORE[user_id] = history_data
        ID_STORE[user_id] = konami_id
        
        return jsonify({"status": "success", "message": "データを正常に処理しました"})
        
    except Exception as e:
        db.session.rollback() # エラー時は処理を取り消す
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download')
def download():
  user_id = request.remote_addr
  history_data_table = DATA_STORE.get(user_id, None)
    
  # PandasでDataFrameに変換し、メモリ上でCSVを作成（utf-8-sigでExcel対策）
  df = pd.DataFrame(history_data_table)
  csv_buffer = io.BytesIO()
  df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
  csv_buffer.seek(0)
    
  # ファイルとしてブラウザにレスポンスを返す
  return send_file(
    csv_buffer,
    mimetype='text/csv',
    as_attachment=True,
    download_name='jubeat_history.csv'
  )

# データベース内の全データをCSV形式でダウンロードするルート
@app.route('/download_all')
def download_all():
    # 1. データベースからすべてのレコードを取得する
    all_records = JubeatHistory.query.all()
    
    if not all_records:
        return "データベースにデータが1件も登録されていません。", 400
    
    # 2. PandasのDataFrameに変換するために、全データを辞書型リストに整形
    # ※全件データであることが分かるよう、識別用の「ユーザーID(IP)」も列に含めています
    all_data = []
    for r in all_records:
        all_data.append({
            "ユーザーID": r.user_id,
            "プレー日時": r.date,
            "曲名": r.music_name,
            "難易度": r.difficulty,
            "スコア": r.score,
            "ハードモード": r.is_hardmode,
            "ライバル1_名前": r.rival1_name,
            "ライバル1_スコア": r.rival1_score,
            "ライバル2_名前": r.rival2_name,
            "ライバル2_スコア": r.rival2_score,
            "ライバル3_名前": r.rival3_name,
            "ライバル3_スコア": r.rival3_score            
        })
        
    # 3. DataFrameに変換し、メモリ上でCSVを作成（Excel文字化け対策のBOM付きUTF-8）
    df = pd.DataFrame(all_data)
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_buffer.seek(0)
    
    # 4. ファイル名を分けてブラウザに送信
    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name='jubeat_all_history_database.csv'
    )