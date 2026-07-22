# -*- coding: utf-8 -*-
import time
import re
import urllib.request

from bs4 import BeautifulSoup
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, current_app
from datetime import datetime, timezone, timedelta  # 日時の比較判定用にインポート
import threading  # 非同期処理（マルチスレッド）のために追加

from app.database import db, JubeatMusicMaster, JubeatRanking, JubeatRankingHard, RankingUpdate, RankingUpdateHard
from app.config import SCRAPING_STATUS

DEBUG_MESSAGE = ""

# ranking_scrapingという名前のBlueprintを作成
ranking_scraping_bp = Blueprint('ranking_scraping', __name__)


# 自作サイトのボタンから直接コナミのサイトを叩いてスクレイピングする関数
def fetch_and_save_ranking(music_id, seq_id):
    utc_now = datetime.now(timezone.utc)
    jst_zone = timezone(timedelta(hours=9))
    jst_now = utc_now.astimezone(jst_zone)
    # サーバーがUTCであっても、この段階で「2026/07/02 14:36」という純粋な文字に固定します
    jst_now_str = jst_now.strftime('%Y/%m/%d %H:%M')
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
            for item in ranking_list:
                existing = JubeatRanking.query.filter_by(
                    music_name=save_title, 
                    player_name=item["player_name"], 
                    score=item['score'], 
                    play_date=item['play_date']
                ).first()
                if existing:
                    db.session.delete(existing)
            
            # 6. 新しい上位20件をDBにコミット
            for item in ranking_list:
                new_rank = JubeatRanking(
                    music_name=save_title,
                    player_name=item['player_name'],
                    score=item['score'],
                    play_date=item['play_date'],
                    updated_at=jst_now_str
                )
                db.session.add(new_rank)
                
            db.session.commit()
            return True, f"「{save_title}」のランキング上位20件を自動取得しました！"
            
    except Exception as e:
        db.session.rollback()
        return False, f"通信または解析エラーが発生しました: {str(e)}"

# 自作サイトのボタンから直接コナミのサイトを叩いてスクレイピングする関数(ハードモード用)
def fetch_and_save_ranking_hard(music_id, seq_id):
    utc_now = datetime.now(timezone.utc)
    jst_zone = timezone(timedelta(hours=9))
    jst_now = utc_now.astimezone(jst_zone)
    # サーバーがUTCであっても、この段階で「2026/07/02 14:36」という純粋な文字に固定します
    jst_now_str = jst_now.strftime('%Y/%m/%d %H:%M')
    try:
        ranking_list = []
        for number in range(5):
            page_num = number + 1
            # 1. 楽曲ID(mid)と難易度(seq)を組み合わせて公式のURLを生成
            url = f"https://p.eagate.573.jp/game/jubeat/beyond/ranking/best_score_hard.html?mid={music_id}&seq={seq_id}&page={page_num}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            req = urllib.request.Request(url, headers=headers)
        
        
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
                
                for row in rows:
                    cells = row.find_all('td')
                    # 通常「順位、プレイヤー名、スコア、日付」など4つのセルで構成される
                    if len(cells) >= 4:
                        name_text = cells[1].text.strip()
                        score_text = cells[2].text.strip().replace(',', '')
                        date_text = cells[3].text.strip()
                        
                        # ヘッダー行やノイズを除外し、数字データであるかバリデーション
                        if score_text.isdigit() and len(ranking_list) < 100:
                            ranking_list.append({
                                'player_name': name_text,
                                'score': int(score_text),
                                'play_date': date_text
                            })
            # コナミへの負荷軽減のための1秒待機
            time.sleep(1.0)
            
        if not ranking_list:
            return False, "ランキングデータが見つかりませんでした。HTMLの構造が変更された可能性があります。"

        # すべての要素が一致する重複を排除するロジック
        unique_ranking_list = []
        seen_records = set()  # すでに処理したデータを記録する集合

        for item in ranking_list:
            # 1. 辞書の中身を、重複チェックが可能な「タプル形式」に変換する
            # (プレイヤー名、スコア、プレイ日時) のセット
            record_key = (item['player_name'], item['score'], item['play_date'])
            
            # 2. まだ一度も出現していないデータであれば、新しいリストに追加
            if record_key not in seen_records:
                seen_records.add(record_key)
                unique_ranking_list.append(item)

        # 3. 最終的なリストを、重複が消えた新しいリストに置き換える
        ranking_list = unique_ranking_list

        # 5. 重複防止：同一曲名・難易度、同一プレーヤー名、同一スコア、同一プレー日時の古いランキングを削除
        for item in ranking_list:
            existing = JubeatRankingHard.query.filter_by(
                music_name=save_title, 
                player_name=item["player_name"], 
                score=item['score'], 
                play_date=item['play_date']
            ).first()
            if existing:
                db.session.delete(existing)
            
        # 6. 新しい上位100件をDBにコミット
        for item in ranking_list:
            new_rank = JubeatRankingHard(
                music_name=save_title,
                player_name=item['player_name'],
                score=item['score'],
                play_date=item['play_date'],
                updated_at=jst_now_str
            )
            db.session.add(new_rank)
                
        db.session.commit()
        return True, f"「{save_title}」のランキング上位100件を自動取得しました！"
            
    except Exception as e:
        db.session.rollback()
        return False, f"通信または解析エラーが発生しました: {str(e)}"

# 実際のスクレイピング処理を裏で動かすための別の関数に分ける
def background_scraping_task(app_context, masters, mode):
    global SCRAPING_STATUS
    global DEBUG_MESSAGE
    
    # Flaskのデータベース操作（SQLAlchemy）を別スレッドで行うためのコンテキスト設定
    with app_context:
        SCRAPING_STATUS["is_running"] = True
        SCRAPING_STATUS["success_count"] = 0
        SCRAPING_STATUS["failed_count"] = 0
        SCRAPING_STATUS["total_count"] = len(masters)
        
        for item in masters:
            if mode == "hard":
                # データベース接続が切れないように、必要に応じてマージンを持たせる
                success, info = fetch_and_save_ranking_hard(item.music_id, item.seq_id)
            else:
                # データベース接続が切れないように、必要に応じてマージンを持たせる
                success, info = fetch_and_save_ranking(item.music_id, item.seq_id)
            if success:
                SCRAPING_STATUS["success_count"] += 1
            else:
                SCRAPING_STATUS["failed_count"] += 1
            
            # コナミへの負荷軽減のための1秒待機
            time.sleep(1.0)
            DEBUG_MESSAGE = info
            
        db.session.commit()
        SCRAPING_STATUS["is_running"] = False

# 大会対策用ページ
@ranking_scraping_bp.route('/ranking_scraping')
def root():
    return redirect(url_for('ranking_scraping.ranking_scraping', mode='normal'))

# 💡 通常モードとハードモードをパス（URL）で完全に分離
@ranking_scraping_bp.route('/ranking_scraping/<mode>')
def ranking_scraping(mode):
    if mode not in ['normal', 'hard']:
        return redirect(url_for('ranking_scraping.ranking_scraping', mode='normal'))

    search_player = request.args.get('search_player', '').strip()
    search_music = request.args.get('search_music', '').strip()
    search_date = request.args.get('search_date', '').strip()  # 'YYYY-MM-DDTHH:MM'
    sort_by = request.args.get('sort_by', 'play_date').strip()

    # まず楽曲マスターから「idの昇順（登録順）」で全楽曲を取得する
    # これにより、画面に表示される楽曲の絶対的な並び順（土台）が固定されます
    music_masters = JubeatMusicMaster.query.order_by(JubeatMusicMaster.id.asc()).all()
    if mode == 'hard':
        query = JubeatRankingHard.query
        if search_player:
            query = query.filter(JubeatRankingHard.player_name.like(f"%{search_player}%"))
        if search_music:
            query = query.filter(JubeatRankingHard.music_name.like(f"%{search_music}%"))
    else:
        query = JubeatRanking.query
        if search_player:
            query = query.filter(JubeatRanking.player_name.like(f"%{search_player}%"))
        if search_music:
            query = query.filter(JubeatRanking.music_name.like(f"%{search_music}%"))
    
    # 一旦データベースから全件取得（ここではまだ並び替えない）
    all_rankings = query.all()

    filtered_rankings = []
    latest_times = {}
    for r in all_rankings:
        if r.music_name not in latest_times:
            latest_times[r.music_name] = r.updated_at
        else:
            if r.updated_at > latest_times[r.music_name]:
                latest_times[r.music_name] = r.updated_at

    # 最新日時に一致するレコードだけを latest_rankings に残す
    latest_rankings = [r for r in all_rankings if latest_times.get(r.music_name) == r.updated_at]
    
    if search_date:
        try:
            # 検索フォームの入力（'2026-06-01T00:00'）を基準となる日付オブジェクトに変換
            target_dt = datetime.strptime(search_date, '%Y-%m-%dT%H:%M')
            
            for r in latest_rankings:
                # データベース内の文字列（'2026/2/2 15:30' や '2026/05/10 09:00'）をパース
                # 公式サイトの「月」や「日」が1桁（スペースや0埋めなし）の場合でも柔軟に対応できる正規表現的パース
                # スラッシュやスペースの表記の揺れを考慮して変換します
                try:
                    # 表記が '2026/2/2 15:30' でも '2026/02/02 15:30' でも正しく解釈されます
                    record_dt = datetime.strptime(r.play_date.strip(), '%Y/%m/%d %H:%M')
                    
                    # 日付オブジェクト同士で純粋な大小比較を行う（これで2月や5月が弾かれます）
                    if record_dt >= target_dt:
                        filtered_rankings.append(r)
                except ValueError:
                    # 万が一、日時のパースに失敗した不正データは安全のため除外
                    continue
        except ValueError:
            # 検索日時のパース自体に失敗した場合は、フィルターなし（全件）にする
            filtered_rankings = latest_rankings
    else:
        # 日時検索が空の場合はそのまま全件を使用
        filtered_rankings = latest_rankings

    # Python側で play_date を正しい日時にパースして最新順にソートする
    # 0埋めがなくても、datetimeオブジェクトに変換されるため完璧にカレンダー順で並び替わります
    def get_record_datetime(record):
        try:
            return datetime.strptime(record.play_date.strip(), '%Y/%m/%d %H:%M')
        except ValueError:
            # 万が一パースできない壊れた日付データがあった場合は、過去の固定日時を返して最下位にする
            return datetime.min

    if mode == 'hard':
        # 🔴 ハードモードの場合：スコア（score）の降順（高い順）で並び替える
        # ※スコアが全く同じ場合は、さらにプレイ日時が新しい方を上にする二段階ソートにしています
        filtered_rankings.sort(
            key=lambda r: (getattr(r, 'score', 0) if isinstance(getattr(r, 'score', 0), int) else 0, get_record_datetime(r)), 
            reverse=True
        )
    else:
        # 🟢 通常モードの場合：これまで通りプレイ日時の最新順（降順）で並び替える
        filtered_rankings.sort(key=get_record_datetime, reverse=True)

    grouped_data = {}
    if sort_by == 'master_id':
        #【並び順の解決策】マスターの曲順を維持した辞書をあらかじめ作成する
        # 難易度ラベルのマッピングを用意
        diff_labels = {0: "BASIC", 1: "ADVANCED", 2: "EXTREME"}
        
        for m in music_masters:
            # スクレイピング時に保存される曲名フォーマット（例: "曲名 [EXTREME]"）を再現
            # fetch_and_save_ranking 内の save_title の命名規則と一致させます
            # もし comment カラムに正式な曲名が入っていない場合は、後述の補足コードを参照してください
            save_title = f"{m.comment} [{diff_labels.get(m.seq_id, 'UNKNOWN')}]"
            
            # マスターに登録されている順番で空のリストを初期化（器を作る）
            grouped_data[save_title] = []

        # ソート済みのランキングデータを、用意した器に振り分ける
        for r in filtered_rankings:
            # すでに器（曲名）が存在していればデータを追加
            if r.music_name in grouped_data:
                grouped_data[r.music_name].append(r)
            else:
                # 万が一、マスター削除などで器がない古いデータが存在した場合のセーフティ
                grouped_data[r.music_name] = [r]
 
    elif sort_by == 'top_score':
        # --- B. 【新設・残したいオプション】1位のスコアが高い順に譜面を並べる ---
        # まず曲ごとにデータを集める
        for r in filtered_rankings:
            if r.music_name not in grouped_data:
                grouped_data[r.music_name] = []
            grouped_data[r.music_name].append(r)
            
        # 各楽曲内のランキングをスコア順にソート
        for music_name in grouped_data:
            grouped_data[music_name].sort(key=lambda x: (x.score if isinstance(x.score, int) else 0, get_record_datetime(x)), reverse=True)
            
        # 楽曲ブロック全体の並び順を「各曲の1位（インデックス0）のスコア」を基準にソート
        # 辞書の要素を1位のスコアが高い順に並び替えた新しい辞書を生成
        grouped_data = dict(sorted(
            grouped_data.items(),
            key=lambda item: item[1][0].score if (item[1] and isinstance(item[1][0].score, int)) else 0,
            reverse=True
        ))

    else:
        # --- C. 【本来の挙動へ修正】純粋なランキング更新日時順 ---
        # データを一度純粋な時系列最新順にソート
        filtered_rankings.sort(key=get_record_datetime, reverse=True)
        
        # 出現した（＝直近でプレイされた）順に曲の器を作って詰め込む
        for r in filtered_rankings:
            if r.music_name not in grouped_data:
                grouped_data[r.music_name] = []
            grouped_data[r.music_name].append(r)

        # 💡 3. モードが「hard」なら、各楽曲内のランキングリストだけを個別にスコア順に最終ソート
        # これにより、全体の譜面の並び順（AやC）を壊すことなく、中身だけをスコア順にできます
        if mode == 'hard':
            for music_name in grouped_data:
                grouped_data[music_name].sort(key=lambda x: (x.score if isinstance(x.score, int) else 0, get_record_datetime(x)), reverse=True)
        else:
            for music_name in grouped_data:
                grouped_data[music_name].sort(key=get_record_datetime, reverse=True)

    # 難易度ラベルのマッピング
    diff_labels = {0: "BASIC", 1: "ADVANCED", 2: "EXTREME"}

    # 💡 1. マスターに登録されている「すべての譜面名」のリストを作成
    all_master_titles = []
    for m in music_masters:
        title = f"{m.comment} [{diff_labels.get(m.seq_id, 'UNKNOWN')}]"
        all_master_titles.append(title)

    # 💡 2. 絞り込みの結果、データが存在している（表示対象の）譜面名を取得
    visible_titles = set([k for k, v in grouped_data.items() if len(v) > 0])

    # 💡 3. すべての譜面から表示対象を差し引いて「非表示になった譜面」をリストアップ
    # マスターの登録順（id順）を維持したまま抽出します
    hidden_music_list = []
    for title in all_master_titles:
        if title not in visible_titles:
            # 検索条件（楽曲名）が指定されている場合は、そのワードに掠ってもいない曲は除外する（ノイズ軽減）
            if search_music and search_music.lower() not in title.lower():
                continue
            hidden_music_list.append(title)

    # 検索等で「中身が空になった楽曲ブロック」を画面非表示にしたい場合のクレンジング
    # （空のブロックもそのまま表示させたい場合は、このループ処理は消去してOKです）
    grouped_data = {k: v for k, v in grouped_data.items() if len(v) > 0}

    if mode == 'hard':
        update_record = RankingUpdateHard.query.order_by(RankingUpdateHard.id.desc()).first()
        html_name = 'ranking_scraping_hard.html'
    else:
        update_record = RankingUpdate.query.order_by(RankingUpdate.id.desc()).first()
        html_name = 'ranking_scraping.html'
    if not update_record:
        update_date = ""
    else:
        update_date = update_record.update_date

    return render_template(
        html_name, 
        grouped_data=grouped_data,
        search_player=search_player,
        search_music=search_music,
        search_date=search_date,
        update_date=update_date,
        sort_by=sort_by,
        current_mode=mode, # 💡 現在のモード（'normal' または 'hard'）をHTMLに渡す
        hidden_music_list=hidden_music_list,
        status=SCRAPING_STATUS
    )

# ボタンクリックでマスターに登録された全楽曲を自動巡回する処理
@ranking_scraping_bp.route('/trigger_scraping_normal', methods=['GET', 'POST'])
def trigger_scraping_normal():
    
    utc_now = datetime.now(timezone.utc)
    jst_zone = timezone(timedelta(hours=9))
    jst_now = utc_now.astimezone(jst_zone)
    # サーバーがUTCであっても、この段階で「2026/07/02 14:36」という純粋な文字に固定します
    jst_now_str = jst_now.strftime('%Y/%m/%d %H:%M')
    
    # 新しいレコードを追加
    new_record = RankingUpdate(
        update_date=jst_now_str
    )
    db.session.add(new_record)
            
    # まとめてDBに保存確定（コミット）
    db.session.commit()

    global SCRAPING_STATUS
    
    # すでに裏で実行中の場合は二重起動を防ぐ
    if SCRAPING_STATUS["is_running"]:
        # 外部サービスからのアクセス時はリダイレクトさせず、文字を返す（エラー防止）
        if request.method == 'GET':
            return "BUSY", 200
        flash("現在、すでに一括更新がバックグラウンドで実行中です。しばらくお待ちください。")
        return redirect(url_for('ranking_scraping.ranking_scraping', mode='normal'))
        
    masters = JubeatMusicMaster.query.all()
    if not masters:
        if request.method == 'GET':
            return "EMPTY", 200
        flash("楽曲マスターに曲が登録されていません。")
        return redirect(url_for('ranking_scraping.ranking_scraping', mode='normal'))
        
    # 現スレッドのFlaskアプリコンテキストを複製して裏スレッドに引き渡す
    app_context = current_app._get_current_object().app_context()
    
    # threadingを使って、処理を別動隊（バックグラウンド）に丸投げする
    thread = threading.Thread(
        target=background_scraping_task, 
        args=(app_context, masters, "normal")
    )
    thread.start() # 裏で実行開始！

    if request.method == 'GET':
        return "OK", 200
    
    # 30秒を待たずに、一瞬でユーザー画面をリフレッシュする
    flash("楽曲ランキングの一括更新をバックグラウンドで開始しました。完了まで約2分かかります。ページを再読み込みして進捗を確認してください。")
    return redirect(url_for('ranking_scraping.ranking_scraping', mode='normal'))


# ボタンクリックでマスターに登録された全楽曲を自動巡回する処理
@ranking_scraping_bp.route('/trigger_scraping_hard', methods=['GET', 'POST'])
def trigger_scraping_hard():
    
    utc_now = datetime.now(timezone.utc)
    jst_zone = timezone(timedelta(hours=9))
    jst_now = utc_now.astimezone(jst_zone)
    # サーバーがUTCであっても、この段階で「2026/07/02 14:36」という純粋な文字に固定します
    jst_now_str = jst_now.strftime('%Y/%m/%d %H:%M')
    
    # 新しいレコードを追加
    new_record = RankingUpdateHard(
        update_date=jst_now_str
    )
    db.session.add(new_record)
            
    # まとめてDBに保存確定（コミット）
    db.session.commit()

    global SCRAPING_STATUS
    
    # すでに裏で実行中の場合は二重起動を防ぐ
    if SCRAPING_STATUS["is_running"]:
        # 外部サービスからのアクセス時はリダイレクトさせず、文字を返す（エラー防止）
        if request.method == 'GET':
            return "BUSY", 200
        flash("現在、すでに一括更新がバックグラウンドで実行中です。しばらくお待ちください。")
        return redirect(url_for('ranking_scraping.ranking_scraping', mode='hard'))
        
    masters = JubeatMusicMaster.query.all()
    if not masters:
        if request.method == 'GET':
            return "EMPTY", 200
        flash("楽曲マスターに曲が登録されていません。")
        return redirect(url_for('ranking_scraping.ranking_scraping', mode='hard'))
        
    # 現スレッドのFlaskアプリコンテキストを複製して裏スレッドに引き渡す
    app_context = current_app._get_current_object().app_context()
    
    # threadingを使って、処理を別動隊（バックグラウンド）に丸投げする
    thread = threading.Thread(
        target=background_scraping_task, 
        args=(app_context, masters, "hard")
    )
    thread.start() # 裏で実行開始！

    if request.method == 'GET':
        return "OK", 200
    
    # 30秒を待たずに、一瞬でユーザー画面をリフレッシュする
    flash("楽曲ランキングの一括更新をバックグラウンドで開始しました。完了まで約20分かかります。ページを再読み込みして進捗を確認してください。")
    return redirect(url_for('ranking_scraping.ranking_scraping', mode='hard'))
