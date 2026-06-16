# -*- coding: utf-8 -*-
import os

import io
import re
import browser_cookie3
import urllib.request
import http.cookiejar
import pandas as pd

from bs4 import BeautifulSoup
from flask import Flask, render_template, send_file
from app import static

app = Flask(__name__)
app.register_blueprint(static.app)

def scrape_jubeat_history():
  # 対象のサイトURL
  url = "https://p.eagate.573.jp/game/jubeat/beyond/playdata/history.html"

  # 1. 保存した cookies.txt を読み込む
  cj = http.cookiejar.MozillaCookieJar("C:/Users/mi3ko/Desktop/TestProject/app/cookies.txt")
  try:
    cj.load(ignore_discard=True, ignore_expires=True)
  except SystemError:
    print("cookies.txt が見つかりません。スクリプトと同じフォルダに配置してください。")
    exit()

  # 4. CookieProcessor と Opener を構築
  cookie_processor = urllib.request.HTTPCookieProcessor(cj)
  opener = urllib.request.build_opener(cookie_processor)

  # ユーザーエージェントを設定（ロボット判定による弾きを防ぐため）
  opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')]

  # URLリソースを開く
  res = opener.open(url).read()

  # インスタンスの作成
  soup = BeautifulSoup(res, 'html.parser')

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
  history_data_table = scrape_jubeat_history()
  return render_template('index.html', history_data_table = history_data_table)

@app.route('/download')
def download():
  history_data_table = scrape_jubeat_history()
    
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
