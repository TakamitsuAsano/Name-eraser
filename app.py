import streamlit as st
import re
import io
import zipfile
import os
from docx import Document

# --- 設定: 除外したい単語リスト ---
IGNORE_LIST = [
    '参加者', '話者', '詳細', 'まとめ', '日時', 'Source', 'source', '文字起こし', 'メモ', '長さ', 'Time', 'Unknown',
    'ENG', 'JPN', 'ENG/JPN', 'ENG_JPN', 'JST', 'Gemini', 'によるメモ', 'のコピー', '標準', 'インタビュー', '対象者',
    '会議の録画', '招待済み', '添付ファイル', 'mp4', 'm4a', 'wav', 'docx', 'txt', 'pdf', 'com', 'jp', 'ac'
]

def is_valid_name(name):
    """名前として適切か判定する"""
    clean_name = name.strip()
    if not clean_name:
        return False
    if len(clean_name) <= 1:
        return False
    if clean_name.isdigit(): 
        return False
    # 除外リストに含まれるかチェック（大文字小文字無視）
    for ignore in IGNORE_LIST:
        if ignore.lower() == clean_name.lower():
            return False
        # 日付形式の除外
        if re.search(r'\d', clean_name) and re.search(r'[\/\-_]', clean_name):
            # ただしメールアドレスに含まれる数字や記号は許可したいので、
            # @が含まれている場合は日付判定をスキップして有効とする
            if '@' not in clean_name:
                return False
    return True

def extract_names(text, filename=""):
    """テキストとファイル名から名前・メールアドレス候補をすべて抽出する"""
    potential_names = set()

    # 1. メールアドレスの抽出 (最優先)
    # 本文とファイル名からメアド形式を探す
    pattern_email = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    matches_email_text = re.findall(pattern_email, text)
    matches_email_file = re.findall(pattern_email, filename)
    potential_names.update(matches_email_text)
    potential_names.update(matches_email_file)

    # 2. 本文中の '名前: ' パターン
    pattern_colon = r'(?:^|\n)(?:\[.*?\]\s*)?([^\n\r：:]{2,20}?)\s*[:：]'
    matches_colon = re.findall(pattern_colon, text)
    potential_names.update(matches_colon)

    # 3. ファイル名やヘッダーにある括弧内の文字列
    base_name = os.path.splitext(filename)[0]
    search_target = base_name + "\n" + text[:500] 
    pattern_bracket = r'[（\(]([^）\)\n\r]{2,20}?)[）\)]'
    matches_bracket = re.findall(pattern_bracket, search_target)
    potential_names.update(matches_bracket)

    # 4. 特定パターンの補足
    if "H.Sakai" in search_target:
        potential_names.add("H.Sakai")

    # フィルタリング
    unique_names = set()
    for name in potential_names:
        if is_valid_name(name):
            unique_names.add(name.strip())
    
    # 名前が長い順にソート（重要：メールアドレスのように長い文字列を先に置換するため）
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

def process_content(content, filename):
    """テキスト内容とファイル名を受け取り、置換後の内容と新しいファイル名を返す"""
    names = extract_names(content, filename)
    name_map = generate_name_map(names)

    # 本文の置換
    new_content = content
    for original, new in name_map.items():
        new_content = new_content.replace(original, new)

    # ファイル名の置換
    name_part, ext = os.path.splitext(filename)
    new_name_part = name_part
    for original, new in name_map.items():
        if original in new_name_part:
            new_name_part = new_name_part.replace(original, new)
    
    new_filename = new_name_part + ext
    return new_filename, new_content, name_map

# --- ファイル処理ラッパー ---
def process_text_file(file_obj):
    try:
        bytes_data = file_obj.getvalue()
        try:
            content = bytes_data.decode('utf-8')
        except UnicodeDecodeError:
            content = bytes_data.decode('cp932', errors='ignore')
    except:
        return None, None
    
    new_filename, new_content, _ = process_content(content, file_obj.name)
    return new_filename, new_content.encode('utf-8')

def process_docx_file(file_obj):
    try:
        doc = Document(file_obj)
    except:
        return None, None

    # 全文取得
    full_text_list = []
    for para in doc.paragraphs:
        full_text_list.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                full_text_list.append(cell.text)
    
    full_text_joined = "\n".join(full_text_list)
    
    names = extract_names(full_text_joined, file_obj.name)
    name_map = generate_name_map(names)

    # 置換実行
    for para in doc.paragraphs:
        for original, new in name_map.items():
            if original in para.text:
                para.text = para.text.replace(original, new)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for original, new in name_map.items():
                    if original in cell.text:
                        cell.text = cell.text.replace(original, new)

    name_part, ext = os.path.splitext(file_obj.name)
    new_name_part = name_part
    for original, new in name_map.items():
        if original in new_name_part:
            new_name_part = new_name_part.replace(original, new)
    new_filename = new_name_part + ext

    output_stream = io.BytesIO()
    doc.save(output_stream)
    return new_filename, output_stream.getvalue()

# --- アプリ画面 ---
st.title("🕵️ 文字起こし匿名化ツール v3")
st.markdown("""
以下の情報を一括で `Speaker_X` 等に変換します。
* **名前**（本文中の「名前:」やファイル名の括弧内）
* **メールアドレス**（本文やヘッダーに含まれるもの）

対応形式: `.txt`, `.md`, `.csv`, `.docx`
""")

uploaded_files = st.file_uploader("ファイルをドラッグ＆ドロップ", accept_multiple_files=True)

if uploaded_files:
    if st.button(f"{len(uploaded_files)} ファイルを処理開始"):
        progress_bar = st.progress(0)
        zip_buffer = io.BytesIO()
        processed_count = 0
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, file_obj in enumerate(uploaded_files):
                filename = file_obj.name
                ext = os.path.splitext(filename)[1].lower()
                
                if ext == '.docx':
                    new_name, new_data = process_docx_file(file_obj)
                else:
                    new_name, new_data = process_text_file(file_obj)
                
                if new_name and new_data:
                    zip_file.writestr(new_name, new_data)
                    processed_count += 1
                
                progress_bar.progress((i + 1) / len(uploaded_files))
        
        st.success(f"完了！ {processed_count} / {len(uploaded_files)} ファイル処理済み")
        st.download_button("📦 ZIPをダウンロード", zip_buffer.getvalue(), "anonymized_v3.zip", "application/zip")
