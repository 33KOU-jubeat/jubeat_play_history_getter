# -*- coding: utf-8 -*-
import io
import pandas as pd
import numpy as np  # 中央値や各種計算の補助用（または標準のstatisticsモジュールでも可）
import statistics
from flask import Blueprint, render_template, request, send_file
from datetime import datetime, timezone, timedelta  # 日時の比較判定用にインポート

from app.database import db, JubeatHistory

# userpageという名前のBlueprintを作成
userpage_bp = Blueprint('userpage', __name__)

# Python側で play_date を正しい日時にパースして最新順にソートする
# 0埋めがなくても、datetimeオブジェクトに変換されるため完璧にカレンダー順で並び替わります
def get_record_datetime(record):
    try:
        return datetime.strptime(record.date.strip(), '%Y/%m/%d %H:%M')
    except ValueError:
        # 万が一パースできない壊れた日付データがあった場合は、過去の固定日時を返して最下位にする
        return datetime.min


# 各ユーザー個別の履歴閲覧ページ
@userpage_bp.route('/user/<konami_id>')
def user_page(konami_id):
    # 指定されたKONAMI IDのデータだけをDBから全件取得
    records = JubeatHistory.query.filter_by(konami_id=konami_id).all()

    # reverse=True を指定することで「最新日時が一番上（降順）」になります
    records.sort(key=get_record_datetime, reverse=True)
    
    data = []
    for r in records:
        data.append({
            "プレイ日時": r.date,
            "曲名": r.music_name,
            "難易度": r.difficulty,
            "スコア": r.score,
            "ハードモード": r.is_hardmode
        })
        
    return render_template('get_history_userpage.html', data=data if data else None, current_user=konami_id)

@userpage_bp.route('/user/<konami_id>/analytics')
def user_analytics_page(konami_id):
    # 1. 画面から「曲名」「難易度」「ハードモードの有無」の3つを独立して受け取る
    target_music = request.args.get('music_name', '').strip()
    target_diff = request.args.get('difficulty', '').strip()
    target_hard = request.args.get('is_hard', '').strip() # "true" または "false"

    # 2. ユーザーの全履歴から「曲名」「難易度」「ハードモード」の組み合わせリストを生成
    user_records = JubeatHistory.query.filter_by(konami_id=konami_id).all()
    
    # 選択肢用のユニークなリストを作成
    # 画面で見やすいように整形したデータを集めます
    dropdown_items = []
    seen = set()
    for r in user_records:
        mode_str = "(HARD)" if r.is_hardmode else ""
        # 識別用に一意のキーを作成
        item_key = (r.music_name, r.difficulty, r.is_hardmode)
        if item_key not in seen:
            seen.add(item_key)
            dropdown_items.append({
                "music_name": r.music_name,
                "difficulty": r.difficulty,
                "is_hard": r.is_hardmode,
                "mode_text": mode_str,
                # プルダウンの表示用テキスト
                "display_text": f"{r.music_name} [{r.difficulty}] {mode_str}"
            })
            
    # 曲名順にソート
    dropdown_items = sorted(dropdown_items, key=lambda x: x["music_name"])

    # 3. 指定された「楽曲×難易度×モード」でデータをピンポイント抽出
    target_records = []
    stats = None

    if target_music and target_diff:
        # 3つの条件すべてに合致するデータだけをDBから引っ張る
        target_records = JubeatHistory.query.filter_by(
            konami_id=konami_id,
            music_name=target_music,
            difficulty=target_diff,
            is_hardmode=target_hard
        ).order_by(JubeatHistory.id.desc()).all()
        
        scores = [r.score for r in target_records if isinstance(r.score, int)]
        
        if scores:
            stats = {
                "play_count": len(scores),
                "max_score": max(scores),
                "min_score": min(scores),
                "average_score": round(statistics.mean(scores), 1),
                "median_score": statistics.median(scores),
            }

    # reverse=True を指定することで「最新日時が一番上（降順）」になります
    target_records.sort(key=get_record_datetime, reverse=True)

    return render_template(
        'user_analytics.html',
        current_user=konami_id,
        dropdown_items=dropdown_items,
        target_music=target_music,
        target_diff=target_diff,
        target_hard=target_hard,
        target_records=target_records,
        stats=stats
    )

@userpage_bp.route('/user/<konami_id>/rival_data')
def rival_data_page(konami_id):
    # 1. 検索フォームから「対戦相手の名前（またはID）」を取得
    vs_user_id = request.args.get('vs_user_id', '').strip()

    # 自分の全プレイ履歴をデータベースから取得（既存通り）
    records = JubeatHistory.query.filter_by(konami_id=konami_id).order_by(JubeatHistory.id.desc()).all()
    
    # reverse=True を指定することで「最新日時が一番上（降順）」になります
    records.sort(key=get_record_datetime, reverse=True)

    # 💡 2. 新設：JubeatHistory内のrivalデータを用いた勝敗集計ロジック
    match_data = []
    win_count = 0
    lose_count = 0
    draw_count = 0

    if vs_user_id:
        for r in records:
            # 各レコードの rival1 または rival2 または rival3 に指定した相手がいるかチェック
            is_matched = False
            vs_score = 0
            
            # モデルの属性名（rival1_name等）が実際のDBカラム名と一致しているか確認してください
            if hasattr(r, 'rival1_name') and r.rival1_name == vs_user_id:
                is_matched = True
                vs_score = getattr(r, 'rival1_score', 0)
            elif hasattr(r, 'rival2_name') and r.rival2_name == vs_user_id:
                is_matched = True
                vs_score = getattr(r, 'rival2_score', 0)
            elif hasattr(r, 'rival3_name') and r.rival3_name == vs_user_id:
                is_matched = True
                vs_score = getattr(r, 'rival3_score', 0)
                
            # マッチングが見つかった場合、自分(r.score)と相手(vs_score)を比較
            if is_matched and isinstance(r.score, int) and isinstance(vs_score, int):
                if r.score > vs_score:
                    result = "WIN"
                    win_count += 1
                elif r.score < vs_score:
                    result = "LOSE"
                    lose_count += 1
                else:
                    result = "DRAW"
                    draw_count += 1

                match_data.append({
                    "music_name": r.music_name,
                    "difficulty": r.difficulty,
                    "is_hard": r.is_hardmode,
                    "my_score": r.score,
                    "vs_score": vs_score,
                    "result": result,
                    "match_date": getattr(r, 'date', '') # プレイ日時があれば取得
                })

    return render_template(
        'rival_data.html',
        current_user=konami_id,
        vs_user_id=vs_user_id,
        match_data=match_data,
        win_count=win_count,
        lose_count=lose_count,
        draw_count=draw_count
    )

# 個別CSVダウンロード（URLのKONAMI IDを基準にする）
@userpage_bp.route('/download/<konami_id>')
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


