# -*- coding: utf-8 -*-
import io
import pandas as pd

from flask import Blueprint, render_template, request, session, redirect, url_for, flash

from app.database import db, JubeatMusicMaster

# adminという名前のBlueprintを作成
admin_bp = Blueprint('admin', __name__)

# --- 追加：管理用ページ（CSVアップロードと現在の登録曲一覧） ---
@admin_bp.route('/admin', methods=['GET', 'POST'])
def admin_page():
    if request.method == 'POST':
        # 1. アップロードされたファイルを取得
        file = request.files.get('file')
        if not file or file.filename == '':
            flash("ファイルが選択されていません。", "error")
            return redirect(url_for('admin.admin_page'))
            
        try:
            # 2. PandasでCSVファイルを読み込む（Excel文字化け対策のエンコード指定）
            # ファイルの先頭に戻して確実に読み込めるように io.StringIO を使用
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            df = pd.read_csv(stream)
            
            # 3. 必要な列（ヘッダー）が存在するかバリデーション
            required_columns = {'music_id', 'seq_id', 'name', 'level', 'is_beyond_limits', 'comment'}
            if not required_columns.issubset(df.columns):
                flash("CSVのヘッダーが正しくありません。'music_id', 'seq_id', 'name', 'level', 'is_beyond_limits', 'comment' を含めてください。", "error")
                return redirect(url_for('admin.admin_page'))
                
            success_count = 0
            
            insert_data_list = []
            # 4. 1行ずつデータをチェックしてDBに登録
            for _, row in df.iterrows():
                mid = str(row['music_id']).strip()
                seq = int(row['seq_id'])
                name = str(row['name']).strip()
                lvl = float(row['level'])
                bl = int(row['is_beyond_limits'])
                comm = str(row['comment']).strip()
                
                # すでに全く同じmusic_idとseq_idの組み合わせが登録されているかチェック
                exists = JubeatMusicMaster.query.filter_by(music_id=mid, seq_id=seq).first()
                if not exists:
                    # 407件分のデータをメモリ上のリストにすべて格納
                    insert_data_list.append({
                        "music_id": mid,
                        "seq_id": seq,
                        "name": name,
                        "level": lvl,
                        "is_beyond_limits": bl,
                        "comm": comm
                    })
                    success_count += 1
            
            chunk_size = 100
            for i in range(0, len(insert_data_list), chunk_size):
                chunk = insert_data_list[i:i + chunk_size]
                db.session.bulk_insert_mappings(JubeatMusicMaster, chunk)
                db.session.commit()  # チャンクごとに即座に確定させて通信を終わらせる
            flash(f"CSVから新たに {success_count} 件の楽曲をマスターに登録しました！", "success")
            
        except Exception as e:
            db.session.rollback()
            flash(f"CSVの読み込み、または登録中にエラーが発生しました: {str(e)}", "error")
            
        return redirect(url_for('admin.admin_page'))

    # GETリクエスト時は、現在登録されているマスター曲一覧を表示するために全件取得
    current_masters = JubeatMusicMaster.query.order_by(JubeatMusicMaster.id.desc()).all()
    diff_labels = {0: "BASIC", 1: "ADVANCED", 2: "EXTREME"}
    
    return render_template('admin.html', current_masters=current_masters, diff_labels=diff_labels)

# 任意：登録されているすべてのマスター曲を全削除するリセット用ルート（調整用）
@admin_bp.route('/admin/clear_master', methods=['POST'])
def admin_clear_master():
    try:
        JubeatMusicMaster.query.delete()
        db.session.commit()
        flash("楽曲マスターをすべてクリアしました。", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"削除エラー: {str(e)}", "error")
    return redirect(url_for('admin.admin_page'))