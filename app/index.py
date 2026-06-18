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
from flask_cors import CORS
from app import static

app = Flask(__name__)
app.register_blueprint(static.app)

DATA_STORE = {}

# ★重要★ すべてのドメイン（e-amusement側）からのデータ受信を許可する設定
CORS(app)

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

  history_data_list = []
  for i in range(len(title_list)):
    play_data = {
      "date": date_list[i],
      "music_title": title_list[i],
      "difficulty": difficulty_list[i],
      "score": score_list[i],
      "hardmode": hardmode_list[i]
    }
    history_data_list.append(play_data)

  return history_data_list

@app.route('/')
def index():
  user_id = request.remote_addr
  history_data_table = DATA_STORE.get(user_id, None)
  if history_data_table:
    return render_template('index.html', history_data_table = history_data_table)
  else :
    return render_template('index.html', history_data_table = None)

# 2. JavaScriptからHTMLデータを受け取るAPI（POSTエンドポイント）
@app.route('/receive_html', methods=['POST'])
def receive_html():
    try:
        # JSON形式のデータを受け取る
        req_data = request.get_json()
        if not req_data or 'html_list' not in req_data:
            return jsonify({"status": "error", "message": "データが空です"}), 400
            
        html_list = req_data['html_list']
        history_data = parse_html_list(html_list)
        
        if not history_data:
            return jsonify({"status": "error", "message": "データの解析に失敗しました"}), 400

        user_id = request.remote_addr
        DATA_STORE[user_id] = history_data
        
        return jsonify({"status": "success", "message": "データを正常に処理しました"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download')
def download():
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
