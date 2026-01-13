import streamlit as st
import re
import io
import zipfile
import os
from docx import Document

# --- 設定 ---
IGNORE_LIST = ['参加者', '話者', '詳細', 'まとめ', '日時', 'Source', 'source', '文字起こし', 'メモ', '長さ', 'Time', 'Unknown']

def extract_names(text):
    """テキストから '名前: ' の形式を探してリストアップする"""
    # パターン: 行頭または改行後の "名前:" または "Name :"
    pattern = r'(?:^|\n)(?:\[.*?\]\s*)?([^\n\r：:]{2,20}?)\s*[:：]'
    
    matches = re.findall(pattern, text)
    
    unique_names = set()
    for name in matches:
        clean_name = name.strip()
        if (clean_name and 
            clean_name not in IGNORE_LIST and 
            not clean_name.isdigit() and
            len(clean_name) > 1):
            unique_names.add(clean_name)
    
    # 長い順にソート
    return sorted(list(unique_names), key=len, reverse=True)

def generate_name_map(names):
    """名前リストから置換マップ(Speaker_A...)を作成"""
    name_map = {}
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i, name in enumerate(names):
        replacement = f"Speaker_{chars[i % len(chars)]}"
        if i >= len(chars):
            replacement += str(i)
        name_map[name] = replacement
    return name_map

def process_text_file(file_obj, filename):
    """テキストファイルの処理"""
    try:
        bytes_data = file_obj.getvalue()
        try:
            content = bytes_data.decode('utf-8')
        except UnicodeDecodeError:
            content = bytes_data.decode('cp932', errors='ignore')
    except Exception:
        return None, None

    # 1. 名前抽出とマップ作成
    names = extract_names(content)
    name_map = generate_name_map(names)

    # 2. 本文置換
    new_content = content
    for original, new in name_map.items():
        new_content = new_content.replace(original, new)

    return new_content.encode('utf-8'), name_map

def process_docx_file(file_obj, filename):
    """Wordファイル(.docx)の処理"""
    try:
        doc = Document(file_obj)
    except Exception:
        return None, None

    # 1. 全文テキストを取得して名前を抽出
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    
    # テーブル内のテキストも念のため抽出対象にする
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                full_text.append(cell.text)
                
    content_for_search = "\n".join(full_text)
    names = extract_names(content_for_search)
    name_map = generate_name_map(names)

    # 2. 本文置換 (段落)
    for para in doc.paragraphs:
        for original, new in name_map.items():
            if original in para.text:
                # 注: スタイルを厳密に保持したい場合はRun単位の処理が必要だが、
                # 文字起こし用途なら段落単位の置換で十分かつ安全
                para.text = para.text.replace(original, new)

    # 3. 本文置換 (テーブル内)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for original, new in name_map.items():
                    if original in cell.text:
                        cell.text = cell.text.replace(original, new)

    # 4. バイナリとして保存
    output_stream = io.BytesIO()
    doc.save(output_stream)
    return output_stream.getvalue(), name_map

def anonymize_file(file_obj):
    """ファイルの拡張子に応じて処理を振り分ける"""
    filename = file_obj.name
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    processed_data = None
    name_map = {}

    if ext == '.docx':
        processed_data, name_map = process_docx_file(file_obj, filename)
    else:
        # テキストファイルとして扱う
        processed_data, name_map = process_text_file(file_obj, filename)

    if processed_data is None:
        return None, None

    # ファイル名の置換処理
    name_part, extension = os.path.splitext(filename)
    new_filename_base = name_part
    for original, new in name_map.items():
        if original in new_filename_base:
            new_filename_base = new_filename_base.replace(original, new)
    
    new_filename = new_filename_base + extension
    
    return new_filename, processed_data

# --- アプリ画面 ---
st.title("🕵️ 文字起こし匿名化ツール (Word対応)")
st.markdown("""
以下のファイルを一括で匿名化（名前→Speaker_A）します。
* テキストファイル (.txt, .md, .csv)
* Wordファイル (**`.docx`**) ※古い `.doc` は非対応

**機能:** 本文の置換 ＋ ファイル名の置換
""")

uploaded_files = st.file_uploader("ファイルをここにドラッグ＆ドロップ", 
                                  accept_multiple_files=True, 
                                  type=['txt', 'md', 'csv', 'docx'])

if uploaded_files:
    if st.button(f"{len(uploaded_files)} ファイルを処理する"):
        progress_bar = st.progress(0)
        zip_buffer = io.BytesIO()
        processed_count = 0
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, file_obj in enumerate(uploaded_files):
                new_name, new_data = anonymize_file(file_obj)
                
                if new_name and new_data:
                    zip_file.writestr(new_name, new_data)
                    processed_count += 1
                
                progress_bar.progress((i + 1) / len(uploaded_files))
        
        st.success(f"完了！ {processed_count} / {len(uploaded_files)} ファイルを処理しました。")
        
        st.download_button(
            label="📦 匿名化されたファイルをダウンロード (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="anonymized_files.zip",
            mime="application/zip"
        )
