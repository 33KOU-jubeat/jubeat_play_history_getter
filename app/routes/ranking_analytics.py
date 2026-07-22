# -*- coding: utf-8 -*-
import time

from flask import Blueprint, render_template, request
from datetime import datetime # 日時の比較判定用にインポート

from app.database import JubeatRanking

# ranking_analyticsという名前のBlueprintを作成
ranking_analytics_bp = Blueprint('ranking_analytics', __name__)

@ranking_analytics_bp.route('/ranking_scraping/normal/ranking_analytics')
def ranking_analytics():
    # 画面のフォームから条件を取得
    target_player = request.args.get('player_name', '').strip()
    start_date_form = request.args.get('start_date', '').strip() # 'YYYY-MM-DD'
    end_date_form = request.args.get('end_date', '').strip()     # 'YYYY-MM-DD'
    # 表記が '2026/2/2 15:30' でも '2026/02/02 15:30' でも正しく解釈されます
    start_date = datetime.strptime(start_date_form, '%Y/%m/%d')
    end_date = datetime.strptime(end_date_form, '%Y/%m/%d')

    analysis_data = []

    if target_player:
        # 指定プレイヤーの全過去ランクイン履歴をDBから全件取得
        records = JubeatRanking.query.filter(JubeatRanking.player_name == target_player).all()
        
        # 期間の絞り込みとデータ蓄積
        music_logs = {}
        for r in records:
            # play_date ("2026/07/01 15:30") の日付部分を比較用に成形
            rec_date = datetime.strptime(r.play_date.strip(), '%Y/%m/%d')
            
            if start_date and rec_date < start_date:
                continue
            if end_date and rec_date > end_date:
                continue
                
            if r.music_name not in music_logs:
                music_logs[r.music_name] = []
            
            # 💡 スコアやランクの代わりに、プレイ日時(play_date)をリストに追加
            music_logs[r.music_name].append(r.play_date)

        # 2. 画面表示用にデータをリスト形式に整形
        for music_name, dates in music_logs.items():
            # 💡 各楽曲内のプレイ日時を、最新の時間が上に来るようにソート
            # ※ "2026/06/20 15:30" などの形式であれば、文字列ソートの逆順で最新順になります
            sorted_dates = sorted(dates, reverse=True)
            
            analysis_data.append({
                "music_name": music_name,
                "count": len(sorted_dates), # ランクイン回数
                "play_dates": sorted_dates   # 💡 すべてのプレイ日時のリスト
            })
            
        # ランクイン回数（更新回数）が多い楽曲順にソート
        analysis_data = sorted(analysis_data, key=lambda x: x["count"], reverse=True)

    return render_template(
        'ranking_analytics.html',
        analysis_data=analysis_data,
        target_player=target_player,
        start_date=start_date,
        end_date=end_date
    )