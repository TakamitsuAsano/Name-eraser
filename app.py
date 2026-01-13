import streamlit as st
import re
import io
import zipfile
import os

# --- 設定 ---
IGNORE_LIST = ['参加者', '話者', '詳細', 'まとめ', '日時', 'Source', 'source', '文字起こし', 'メモ', '長さ', 'Time', 'Unknown']

def extract_names(text):
    """テキストから '名前: ' の形式を探してリストアップする"""
    # パターン1: 行頭にある "名前:" または "Name :" (日本語/英語コロン対応)
    # のようなタグがある場合も考慮
    pattern = r'(?:^|\n)(?:\[.*?\]\s*)?([^\n\r：:]{2,20}?)\s*[:：]'
    
    matches = re.findall(pattern, text)
    
    unique_names = set()
    for name in matches:
        clean_name = name.strip()
        # 除外リストになく、数字だけでないものを抽出
        if (clean_name and 
            clean_name not in IGNORE_LIST and 
            not clean_name.isdigit() and
            len(clean_name) > 1):
            unique_names.add(clean_name)
    
    # 長い順にソート（部分一致置換を防ぐため）
    return sorted(list(unique_names), key=len, reverse=True)

def anonymize_text_and_filename(file_obj):
    """1つのファイルを読み込み、本文とファイル名を匿名化する"""
    try:
        # バイナリとして読み込んでデコード（文字コード判定）
        bytes_data = file_obj.getvalue()
        try:
            content = bytes_data.decode('utf-8')
        except UnicodeDecodeError:
            content = bytes_data.decode('cp932', errors='ignore')
    except Exception:
        return None, None, "読込エラー"

    original_filename = file_obj.name
    
    # 1. 名前の抽出
    names = extract_names(content)
    
    # 2. 置換マップの作成 (Speaker A, Speaker B...)
    name_map = {}
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i, name in enumerate(names):
        replacement = f"Speaker_{chars[i % len(chars)]}"
        if i >= len(chars):
            replacement += str(i)
        name_map[name] = replacement

    # 3. 本文の置換
    new_content = content
    for original, new in name_map.items():
        new_content = new_content.replace(original, new)

    # 4. ファイル名の置換
    name_part, ext = os.path.splitext(original_filename)
    new_filename_base = name_part
    
    # ファイル名に含まれる名前も置換
    for original, new in name_map.items():
        if original in new_filename_base:
            new_filename_base = new_filename_base.replace(original, new)
            
    new_filename = new_filename_base + ext

    return new_filename, new_content, name_map

# --- アプリ画面の構築 ---
st.title("🕵️ 文字起こし匿名化ツール")
st.markdown("""
文字起こしファイル（.txt）をアップロードすると、以下の処理を一括で行います。
1. **本文中の名前** を `Speaker_A`, `Speaker_B`... に置換
2. **ファイル名に含まれる名前** も同様に置換
3. 処理結果を **zipファイル** でダウンロード
""")

uploaded_files = st.file_uploader("ファイルをここにドラッグ＆ドロップ (複数選択可)", 
                                  accept_multiple_files=True, 
                                  type=['txt', 'md', 'csv'])

if uploaded_files:
    if st.button(f"{len(uploaded_files)} ファイルを処理する"):
        progress_bar = st.progress(0)
        zip_buffer = io.BytesIO()
        
        processed_count = 0
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, file_obj in enumerate(uploaded_files):
                new_name, new_content, _ = anonymize_text_and_filename(file_obj)
                
                if new_name and new_content:
                    zip_file.writestr(new_name, new_content)
                    processed_count += 1
                
                # 進捗バー更新
                progress_bar.progress((i + 1) / len(uploaded_files))
        
        st.success(f"完了！ {processed_count} / {len(uploaded_files)} ファイルを処理しました。")
        
        # ダウンロードボタン
        st.download_button(
            label="📦 匿名化されたファイルをダウンロード (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="anonymized_files.zip",
            mime="application/zip"
        )