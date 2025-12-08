import os
import json
import time
import re
import google.generativeai as genai
from datetime import datetime

# ================= 配置區域 =================
# 請在這裡填入你的 Google API Key
API_KEY = "AIzaSyCGKYYZwXc8izAchp9AEGP9VSPhaoxJUe0"
# ===========================================

# 設定 API Key
if API_KEY == "YOUR_GOOGLE_API_KEY":
    API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    raise ValueError("請提供 Google API Key。")

genai.configure(api_key=API_KEY)

# 檔案路徑
N5_FILE = "JLPT_n5_questions.json"
N4_FILE = "JLPT_n4_questions.json"

# 類別映射 (Category Mapping)
CATEGORY_MAP = {
    "vocabulary": "語彙",
    "grammar": "文法",
    "reading": "讀解"
}

def get_model_recommendation(model_name):
    """
    根據模型名稱返回推薦程度與理由
    """
    model_name = model_name.lower()
    
    if "gemini-1.5-pro" in model_name:
        return {
            "score": "⭐⭐⭐⭐⭐ (強烈推薦)",
            "reason": "邏輯推理能力最強，適合處理 JLPT 複雜的語法解析與題目生成，支援 JSON 模式。",
            "color": "\033[92m" # Green
        }
    elif "gemini-1.5-flash" in model_name:
        return {
            "score": "⭐⭐⭐⭐⭐ (推薦 - 速度快)",
            "reason": "速度最快且成本低，邏輯能力足夠應付 N4/N5，支援 JSON 模式。",
            "color": "\033[92m" # Green
        }
    elif "gemini-pro-latest" in model_name:
         return {
            "score": "⭐⭐⭐⭐ (推薦 - 最新版)",
            "reason": "Gemini Pro 最新版本，能力強大，本程式會針對此模型優化 Prompt 以減少錯誤。",
            "color": "\033[94m" # Blue
        }
    elif "gemini-1.0-pro" in model_name or "gemini-pro" in model_name:
        return {
            "score": "⭐⭐⭐ (尚可)",
            "reason": "舊版標準模型，能力尚可，但對 JSON 格式的遵循度不如 1.5 系列穩定。",
            "color": "\033[93m" # Yellow
        }
    else:
        return {
            "score": "❓ (未知)",
            "reason": "其他模型。",
            "color": "\033[90m" # Grey
        }

def list_and_select_model():
    """
    列出所有可用模型並讓使用者選擇
    """
    print("正在查詢可用模型列表...\n")
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if not available_models:
            print("錯誤：找不到任何支援 generateContent 的模型。")
            return None

        print(f"{'ID':<4} | {'模型名稱 (Model Name)':<40} | {'推薦程度':<15} | {'理由'}")
        print("-" * 100)

        valid_choices = []
        for idx, model_name in enumerate(available_models):
            rec = get_model_recommendation(model_name)
            reset_color = "\033[0m"
            print(f"{idx:<4} | {rec['color']}{model_name:<40}{reset_color} | {rec['score']:<15} | {rec['reason']}")
            valid_choices.append(model_name)

        print("-" * 100)
        
        while True:
            choice = input("\n請輸入想使用的模型 ID (數字): ")
            if choice.isdigit():
                choice_idx = int(choice)
                if 0 <= choice_idx < len(valid_choices):
                    selected_model = valid_choices[choice_idx]
                    print(f"\n已選擇模型: {selected_model}")
                    return selected_model
            print("無效的輸入，請重試。")

    except Exception as e:
        print(f"查詢模型失敗: {e}")
        return None

def load_existing_questions(filepath):
    """
    讀取現有的題目檔案
    """
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"讀取 {filepath} 失敗: {e}")
        return []

def is_duplicate(new_q, existing_questions):
    """
    檢查題目是否重複 (比對題目文字)
    """
    new_q_text = new_q.get("question", "").strip()
    for eq in existing_questions:
        if eq.get("question", "").strip() == new_q_text:
            return True
    return False

def get_next_batch_version(questions):
    """
    掃描現有題目，找出最大的版本號 (vXX)，並返回下一個版本號 (字串，如 'v03')
    """
    max_ver = 0
    # 檢查 tags 或 id 中的 vXX
    # ID 格式: N5-文法-v01-09
    pattern = re.compile(r"-v(\d+)-")
    
    for q in questions:
        q_id = str(q.get("id", ""))
        match = pattern.search(q_id)
        if match:
            ver = int(match.group(1))
            if ver > max_ver:
                max_ver = ver
        
        # 也可以檢查 tags
        for tag in q.get("tags", []):
            if tag.startswith("v") and tag[1:].isdigit():
                ver = int(tag[1:])
                if ver > max_ver:
                    max_ver = ver

    next_ver = max_ver + 1
    return f"v{next_ver:02d}"

def audit_questions(model_name, questions):
    """
    使用 LLM 審查題目品質
    """
    if not questions:
        return []

    print(f"正在進行內部審查 (共 {len(questions)} 題)...")
    
    questions_str = json.dumps(questions, ensure_ascii=False, indent=2)
    
    prompt = f"""
    你是一個嚴格的日語 JLPT 題目審查員。請檢查以下 JSON 格式的題目列表。
    
    ### 審查標準:
    1. **正確性**: 答案 (answer 索引) 是否正確對應到 options 中的選項？
    2. **日語自然度**: 題目和選項的日語是否自然、正確？
    3. **格式**: 是否包含 question, options, answer, explanation？
    4. **重複性**: 選項是否有重複？
    
    ### 題目列表:
    {questions_str}
    
    ### 輸出要求:
    請回傳一個 JSON 物件，包含一個 "passed_indices" 陣列，列出**通過審查**的題目在原列表中的索引 (0-based index)。
    如果題目有問題，請**不要**包含在 passed_indices 中。
    
    範例輸出:
    {{
        "passed_indices": [0, 2, 3] 
    }}
    
    請只輸出 JSON。
    """
    
    try:
        model = genai.GenerativeModel(model_name, generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        result = json.loads(response.text)
        passed_indices = result.get("passed_indices", [])
        
        valid_questions = []
        for idx in passed_indices:
            if 0 <= idx < len(questions):
                valid_questions.append(questions[idx])
        
        print(f"審查完成。通過: {len(valid_questions)} / {len(questions)}")
        return valid_questions
        
    except Exception as e:
        print(f"審查過程發生錯誤，將假設所有題目通過 (但請人工複查): {e}")
        return questions

def generate_batch(model_name, level, counts):
    """
    生成一批特定等級的題目
    """
    model = genai.GenerativeModel(model_name, generation_config={"response_mime_type": "application/json"})
    
    prompt = f"""
    請生成 JLPT {level} 等級的練習題。
    
    ### 數量要求:
    - 文字語彙 (Vocabulary): {counts['vocabulary']} 題
    - 文法 (Grammar): {counts['grammar']} 題 (請包含至少一半的星號重組題 star_ordering)
    - 讀解 (Reading): {counts['reading']} 題
    
    ### 輸出格式 (JSON Array):
    [
      {{
        "category": "vocabulary",  <-- 請標註類別: vocabulary, grammar, 或 reading
        "tags": ["{level}", "Vocabulary", "Kanji"],
        "type": "kanji_reading",
        "question": "...",
        "options": ["A", "B", "C", "D"],
        "answer": 0,
        "explanation": "繁體中文解析..."
      }},
      ...
    ]
    
    ### 規範:
    1. **絕對排除聽解**。
    2. 解析必須用**繁體中文**。
    3. 每一題只有一個正確答案。answer 為 0-3 的索引。
    4. 讀解題請提供短文。
    """
    
    print(f"正在生成 {level} 題目 (目標: V:{counts['vocabulary']}, G:{counts['grammar']}, R:{counts['reading']})...")
    try:
        response = model.generate_content(prompt)
        text = response.text
        if text.strip().startswith("```"):
             text = text.strip().split("\n", 1)[1].rsplit("\n", 1)[0]
        
        data = json.loads(text)
        
        # 處理可能的結構差異
        final_list = []
        if isinstance(data, dict):
            for key in data:
                if isinstance(data[key], list):
                    final_list.extend(data[key])
            if level in data and isinstance(data[level], list): # 針對 {"N5": [...]}
                 final_list = data[level]
        elif isinstance(data, list):
            final_list = data
            
        return final_list
    except Exception as e:
        print(f"生成失敗: {e}")
        return []

def main():
    selected_model = list_and_select_model()
    if not selected_model:
        return

    # 目標題數
    TARGET_COUNTS = {
        "vocabulary": 10,
        "grammar": 10,
        "reading": 5
    }
    
    for level, filename in [("N5", N5_FILE), ("N4", N4_FILE)]:
        print(f"\n=== 處理 {level} ===")
        
        # 1. 讀取現有題目
        existing_questions = load_existing_questions(filename)
        
        # 2. 決定本次 Batch Version
        batch_version = get_next_batch_version(existing_questions)
        print(f"本次生成版本號: {batch_version}")
        
        collected_valid_questions = []
        needed_total = sum(TARGET_COUNTS.values())
        
        # 為了確保各類別數量，我們簡單統計一下目前收集到的
        current_counts = {"vocabulary": 0, "grammar": 0, "reading": 0}
        
        retry_count = 0
        while len(collected_valid_questions) < needed_total and retry_count < 3:
            remaining = needed_total - len(collected_valid_questions)
            print(f"尚缺約 {remaining} 題，開始生成...")
            
            batch = generate_batch(selected_model, level, TARGET_COUNTS)
            
            # 過濾重複
            unique_batch = []
            for q in batch:
                if not is_duplicate(q, existing_questions) and not is_duplicate(q, collected_valid_questions):
                    unique_batch.append(q)
            
            print(f"生成 {len(batch)} 題，去重後剩 {len(unique_batch)} 題。")
            
            # 內部審查
            if unique_batch:
                audited_batch = audit_questions(selected_model, unique_batch)
                
                # 分類並收集
                for q in audited_batch:
                    cat = q.get("category", "vocabulary").lower() # 預設 vocabulary
                    if cat not in current_counts: cat = "vocabulary" # fallback
                    
                    # 簡單檢查是否超過該類別需求 (可選，這裡先不嚴格限制，多一點無妨)
                    collected_valid_questions.append(q)
                    current_counts[cat] += 1
            
            retry_count += 1
            
        print(f"最終收集到 {len(collected_valid_questions)} 題新題目。")
        
        # 3. 分配 ID 與 Tags
        # ID 格式: N5-文法-v01-09
        # 需要針對每個類別分別計數
        cat_indices = {
            "vocabulary": 1,
            "grammar": 1,
            "reading": 1
        }
        
        if collected_valid_questions:
            for q in collected_valid_questions:
                raw_cat = q.get("category", "vocabulary").lower()
                if raw_cat not in CATEGORY_MAP: raw_cat = "vocabulary"
                
                cat_display = CATEGORY_MAP[raw_cat] # 語彙, 文法, 讀解
                idx = cat_indices.get(raw_cat, 1)
                
                # 生成 ID
                new_id = f"{level}-{cat_display}-{batch_version}-{idx:02d}"
                q["id"] = new_id
                
                # 更新 Tags
                # 確保 tags 包含: Level, Category, Version, ID
                if "tags" not in q:
                    q["tags"] = []
                
                # 移除舊的重複 tags
                q["tags"] = [t for t in q["tags"] if t not in [level, batch_version, new_id]]
                
                # 加入必要 tags
                q["tags"].extend([level, batch_version, new_id])
                
                # 加上 metadata
                q["metadata"] = {
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "model": selected_model,
                    "batch": batch_version
                }
                
                cat_indices[raw_cat] += 1
                
            # 合併
            existing_questions.extend(collected_valid_questions)
            
            # 寫入檔案
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(existing_questions, f, ensure_ascii=False, indent=2)
                print(f"已更新 {filename}。")
            except Exception as e:
                print(f"寫入失敗: {e}")
        else:
            print("本次沒有新增任何題目。")

if __name__ == "__main__":
    main()