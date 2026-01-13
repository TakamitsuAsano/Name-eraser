import streamlit as st
import re
import io
import zipfile
import os
from docx import Document

# --- 設定: 除外したい単語リスト（ここに含まれる単語は名前として扱わない） ---
IGNORE_LIST = [
    '参加者', '話者', '詳細', 'まとめ', '日時', 'Source', 'source', '文字起こし', 'メモ', '長さ', 'Time', 'Unknown',
    'ENG', 'JPN', 'ENG/JPN', 'ENG_JPN', 'JST', 'Gemini', 'によるメモ', 'のコピー', '標準', 'インタビュー', '対象者',
    '会議の録画', '招待済み', '添付ファイル', 'mp4', 'm4a', 'wav', 'docx', 'txt', 'pdf'
]

def is_valid_name(name):
    """名前として適切か判定する"""
    clean_name = name.strip()
    if not clean_name:
        return False
    if len(clean_name) <= 1:
        return False
    if clean_name.isdigit(): # 数字だけはNG
        return False
    # 除外リストに含まれるかチェック（大文字小文字無視）
    for ignore in IGNORE_LIST:
        if ignore.lower() == clean_name.lower():
            return False
        # "2025/10/27" のような日付っぽいものも除外
        if re.search(r'\d', clean_name) and re.search(r'[\/\-_]', clean_name):
            return False
    return True

def extract_names(text, filename=""):
    """テキストとファイル名から名前候補をすべて抽出する"""
    potential_names = set()

    # 1. 本文中の '名前: ' パターン (例: "木原良樹: " "Ayaka Takafuji: ")
    pattern_colon = r'(?:^|\n)(?:\[.*?\]\s*)?([^\n\r：:]{2,20}?)\s*[:：]'
    matches_colon = re.findall(pattern_colon, text)
    potential_names.update(matches_colon)

    # 2. ファイル名やヘッダーにある括弧内の文字列 (例: "(XIAOHUI SU)" )
    # ファイル名から拡張子を除く
    base_name = os.path.splitext(filename)[0]
    # ファイル名と本文の先頭500文字を対象に括弧の中身を探す
    search_target = base_name + "\n" + text[:500]
    
    # 丸括弧 ( ) または（ ）の中身を抽出
    pattern_bracket = r'[（\(]([^）\)\n\r]{2,20}?)[）\)]'
    matches_bracket = re.findall(pattern_bracket, search_target)
    potential_names.update(matches_bracket)

    # 3. 特定のパターン "H.Sakai" のような英字名も拾う
    # (空白区切りやドットを含む英字の塊)
    if "H.Sakai" in search_target: # 特に指定があったため明示的にチェック
        potential_names.add("H.Sakai")

    # フィルタリング
    unique_names = set()
    for name in potential_names:
        if is_valid_name(name):
            unique_names.add(name.strip())
    
    # 名前が長い順にソート（"田中太郎" を "田中" より先に置換するため）
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
    # 名前抽出
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
        # ファイル名内の名前を置換
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
    
    # 名前抽出とマップ作成（ファイル名も考慮）
    names = extract_names(full_text_joined, file_obj.name)
    name_map = generate_name_map(names)

    # 置換実行
    # 1. 段落
    for para in doc.paragraphs:
        for original, new in name_map.items():
            if original in para.text:
                para.text = para.text.replace(original, new)
    # 2. テーブル
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for original, new in name_map.items():
                    if original in cell.text:
                        cell.text = cell.text.replace(original, new)

    # ファイル名置換
    name_part, ext = os.path.splitext(file_obj.name)
    new_name_part = name_part
    for original, new in name_map.items():
        if original in new_name_part:
            new_name_part = new_name_part.replace(original, new)
    new_filename = new_name_part + ext

    # 保存
    output_stream = io.BytesIO()
    doc.save(output_stream)
    return new_filename, output_stream.getvalue()

# --- アプリ画面 ---
st.title("🕵️ 文字起こし匿名化ツール v2")
st.markdown("""
以下のファイルを一括で匿名化します。ファイル名やヘッダーに含まれる名前も検出します。
* テキストファイル (.txt, .md, .csv)
* Wordファイル (.docx)
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
        st.download_button("📦 ZIPをダウンロード", zip_buffer.getvalue(), "anonymized_v2.zip", "application/zip")
