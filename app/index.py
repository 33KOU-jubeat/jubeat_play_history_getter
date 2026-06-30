# -*- coding: utf-8 -*-
import os

import io
import time
import re
import browser_cookie3
import urllib.request
import http.cookiejar
import pandas as pd

from bs4 import BeautifulSoup
from flask import Flask, render_template, request, send_file, session, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from app import static
from datetime import datetime  # 日時の比較判定用にインポート

app = Flask(__name__)
app.secret_key = "jubeat_secret_key_12345"
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

# アプリ起動時にテーブルが存在しない場合は自動作成する
with app.app_context():
    db.create_all()
     # テスト用初期データ（空の場合のみ追加）
    if not JubeatMusicMaster.query.first():
        sample1 = JubeatMusicMaster(music_id="96209810", seq_id=2, comment="I")
        sample2 = JubeatMusicMaster(music_id="69014196", seq_id=2, comment="[]DENTITY")
        db.session.add_all([sample1, sample2])
        db.session.commit()

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
      rival1_score_text = 0
      rival2_name_text = ""
      rival2_score_text = 0
      rival3_name_text = ""
      rival3_score_text = 0

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

# 自作サイトのボタンから直接コナミのサイトを叩いてスクレイピングする関数
def fetch_and_save_ranking(music_id, seq_id):
    # 1. 楽曲ID(mid)と難易度(seq)を組み合わせて公式のURLを生成
    url = f"https://p.eagate.573.jp/game/jubeat/beyond/ranking/best_score.html?mid={music_id}&seq={seq_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    
    try:
        # 2. ログイン不要なので、直接URLを開いてHTMLを読み込む
        with urllib.request.urlopen(req) as response:
            html = response.read().decode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            
            # 3. 曲名の取得 (h1タグや特定のタイトルクラスから抽出)
            music_name = "不明な楽曲"
            title_el = soup.find(['div'], class_=['bar_cd pg'])
            # 1. タグ全体の文字列（または中のテキスト）を取得し、カンマで分割
            # ※ HTML構造を保ったまま「>」と「<」を判定するため str(title_el) を使用します
            raw_text = str(title_el)
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
                  music_name = clean_text

            # 難易度ラベルの判定
            diff_labels = {0: "BASIC", 1: "ADVANCED", 2: "EXTREME"}
            diff_name = diff_labels.get(int(seq_id), "UNKNOWN")
            save_title = f"{music_name} [{diff_name}]"

            # 4. ランキングが掲載されているテーブルの行(tr)を解析
            # コナミのランキング表構造に合わせてtdの並びをパース
            rows = soup.find_all('tr')
            ranking_list = []
            
            for row in rows:
                cells = row.find_all('td')
                # 通常「順位、プレイヤー名、スコア、日付」など4つのセルで構成される
                if len(cells) >= 4:
                    name_text = cells[1].text.strip()
                    score_text = cells[2].text.strip().replace(',', '')
                    date_text = cells[3].text.strip()
                    
                    # ヘッダー行やノイズを除外し、数字データであるかバリデーション
                    if score_text.isdigit() and len(ranking_list) < 20:
                        ranking_list.append({
                            'player_name': name_text,
                            'score': int(score_text),
                            'play_date': date_text
                        })
            
            if not ranking_list:
                return False, "ランキングデータが見つかりませんでした。HTMLの構造が変更された可能性があります。"

            # 5. 重複防止：同一曲名・難易度の古いランキングを一旦削除
            JubeatRanking.query.filter_by(music_name=save_title).delete()
            
            # 6. 新しい上位20件をDBにコミット
            for item in ranking_list:
                new_rank = JubeatRanking(
                    music_name=save_title,
                    player_name=item['player_name'],
                    score=item['score'],
                    play_date=item['play_date']
                )
                db.session.add(new_rank)
                
            db.session.commit()
            return True, f"「{save_title}」のランキング上位20件を自動取得しました！"
            
    except Exception as e:
        db.session.rollback()
        return False, f"通信または解析エラーが発生しました: {str(e)}"


# --- ルーティング ---
@app.route('/')
def index():
  user_id = request.remote_addr
  history_data_table = DATA_STORE.get(user_id, None)
  konami_id = ID_STORE.get(user_id, None)
  if history_data_table:
    return render_template('index.html', history_data_table = history_data_table, konami_id = konami_id)
  else :
    return render_template('index.html', history_data_table = None, konami_id = None)

# 各ユーザー個別の履歴閲覧ページ
@app.route('/user/<konami_id>')
def user_page(konami_id):
    # 指定されたKONAMI IDのデータだけをDBから全件取得
    records = JubeatHistory.query.filter_by(konami_id=konami_id).all()
    
    data = []
    for r in records:
        data.append({
            "プレイ日時": r.date,
            "曲名": r.music_name,
            "難易度": r.difficulty,
            "スコア": r.score,
            "ハードモード": r.is_hardmode
        })
        
    return render_template('index.html', data=data if data else None, current_user=konami_id)

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

# 個別CSVダウンロード（URLのKONAMI IDを基準にする）
@app.route('/download/<konami_id>')
def download_user_csv(konami_id):
    records = JubeatHistory.query.filter_by(konami_id=konami_id).all()
    if not records:
        return "データがありません", 400
        
    data_for_df = []
    for r in records:
        data_for_df.append({
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
    
    df = pd.DataFrame(data_for_df)
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_buffer.seek(0)
    
    return send_file(csv_buffer, mimetype='text/csv', as_attachment=True, download_name=f'jubeat_history_{konami_id}.csv')


# データベース内の全データをCSV形式でダウンロードするルート([TODO]隠し機能にする予定)
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
            "KONAMI ID": r.konami_id,
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


# 大会対策用ページ
@app.route('/ranking_scraping')
def ranking_scraping():
    search_player = request.args.get('search_player', '').strip()
    search_music = request.args.get('search_music', '').strip()
    search_date = request.args.get('search_date', '').strip()  # 'YYYY-MM-DDTHH:MM'

    query = JubeatRanking.query

    # 1. データベース側では「プレイヤー名」と「楽曲名」の部分一致だけを高速に処理
    if search_player:
        query = query.filter(JubeatRanking.player_name.like(f"%{search_player}%"))
    if search_music:
        query = query.filter(JubeatRanking.music_name.like(f"%{search_music}%"))

    # 条件に合うデータを一度取得（曲名、順位順）
    all_rankings = query.order_by(JubeatRanking.music_name).all()

    # 2. 💡【日付エラー解決策】Python側で確実な日付オブジェクト比較を行う
    filtered_rankings = []
    
    if search_date:
        try:
            # 検索フォームの入力（'2026-06-01T00:00'）を基準となる日付オブジェクトに変換
            target_dt = datetime.strptime(search_date, '%Y-%m-%dT%H:%M')
            
            for r in all_rankings:
                # データベース内の文字列（'2026/2/2 15:30' や '2026/05/10 09:00'）をパース
                # ⚠️ 公式サイトの「月」や「日」が1桁（スペースや0埋めなし）の場合でも柔軟に対応できる正規表現的パース
                # スラッシュやスペースの表記の揺れを考慮して変換します
                try:
                    # 表記が '2026/2/2 15:30' でも '2026/02/02 15:30' でも正しく解釈されます
                    record_dt = datetime.strptime(r.play_date.strip(), '%Y/%m/%d %H:%M')
                    
                    # 💡 日付オブジェクト同士で純粋な大小比較を行う（これで2月や5月が弾かれます）
                    if record_dt >= target_dt:
                        filtered_rankings.append(r)
                except ValueError:
                    # 万が一、日時のパースに失敗した不正データは安全のため除外
                    continue
        except ValueError:
            # 検索日時のパース自体に失敗した場合は、フィルターなし（全件）にする
            filtered_rankings = all_rankings
    else:
        # 日時検索が空の場合はそのまま全件を使用
        filtered_rankings = all_rankings

    # 3. テンプレートに渡すために「曲名」をキーにした辞書に整形
    grouped_data = {}
    for r in filtered_rankings:
        if r.music_name not in grouped_data:
            grouped_data[r.music_name] = []
        grouped_data[r.music_name].append(r)
        
    return render_template(
        'ranking_scraping.html', 
        grouped_data=grouped_data,
        search_player=search_player,
        search_music=search_music,
        search_date=search_date
    )

# 💡 新設：ボタンクリックでマスターに登録された全楽曲を自動巡回する処理
@app.route('/trigger_scraping_all', methods=['POST'])
def trigger_scraping_all():
    # マスターデータを全件取得
    masters = JubeatMusicMaster.query.all()
    
    success_count = 0
    failed_count = 0
    
    for item in masters:
        success, info = fetch_and_save_ranking(item.music_id, item.seq_id)
        if success:
            success_count += 1
        else:
            failed_count += 1
            
        
        # 【重要】コナミのサーバーに大量の負荷（DoS攻撃）をかけないよう、1曲ごとに1秒の待機時間を挟む
        time.sleep(1.0)
        
    db.session.commit()
    flash(f"一括更新が完了しました。（成功: {success_count}件 / 失敗: {failed_count}件）")
    return redirect(url_for('ranking_scraping'))


# --- 追加：管理用ページ（CSVアップロードと現在の登録曲一覧） ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_page():
    if request.method == 'POST':
        # 1. アップロードされたファイルを取得
        file = request.files.get('file')
        if not file or file.filename == '':
            flash("ファイルが選択されていません。", "error")
            return redirect(url_for('admin_page'))
            
        try:
            # 2. PandasでCSVファイルを読み込む（Excel文字化け対策のエンコード指定）
            # ファイルの先頭に戻して確実に読み込めるように io.StringIO を使用
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            df = pd.read_csv(stream)
            
            # 3. 必要な列（ヘッダー）が存在するかバリデーション
            required_columns = {'music_id', 'seq_id', 'comment'}
            if not required_columns.issubset(df.columns):
                flash("CSVのヘッダーが正しくありません。'music_id', 'seq_id', 'comment' を含めてください。", "error")
                return redirect(url_for('admin_page'))
                
            success_count = 0
            
            # 4. 1行ずつデータをチェックしてDBに登録
            for _, row in df.iterrows():
                mid = str(row['music_id']).strip()
                seq = int(row['seq_id'])
                cmnt = str(row['comment']).strip()
                
                # すでに全く同じmusic_idとseq_idの組み合わせが登録されているかチェック
                exists = JubeatMusicMaster.query.filter_by(music_id=mid, seq_id=seq).first()
                if not exists:
                    new_music = JubeatMusicMaster(music_id=mid, seq_id=seq, comment=cmnt)
                    db.session.add(new_music)
                    success_count += 1
            
            db.session.commit()
            flash(f"CSVから新たに {success_count} 件の楽曲をマスターに登録しました！", "success")
            
        except Exception as e:
            db.session.rollback()
            flash(f"CSVの読み込み、または登録中にエラーが発生しました: {str(e)}", "error")
            
        return redirect(url_for('admin_page'))

    # GETリクエスト時は、現在登録されているマスター曲一覧を表示するために全件取得
    current_masters = JubeatMusicMaster.query.order_by(JubeatMusicMaster.id.desc()).all()
    diff_labels = {0: "BASIC", 1: "ADVANCED", 2: "EXTREME"}
    
    return render_template('admin.html', current_masters=current_masters, diff_labels=diff_labels)

# 任意：登録されているすべてのマスター曲を全削除するリセット用ルート（調整用）
@app.route('/admin/clear_master', methods=['POST'])
def admin_clear_master():
    try:
        JubeatMusicMaster.query.delete()
        db.session.commit()
        flash("楽曲マスターをすべてクリアしました。", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"削除エラー: {str(e)}", "error")
    return redirect(url_for('admin_page'))
