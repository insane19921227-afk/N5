import requests
import json
import time
import os
import re
import random

# ================= 設定區 =================
# 建議不要超過 50，100 題很容易造成 Google API 逾時或回傳截斷
BATCH_SIZE = 30  
FILENAME = "n5_questions.json"
# =========================================

def get_api_key():
    print("請輸入您的 Google Gemini API Key:")
    return input("> ").strip()

def get_valid_model(api_key):
    print("🔍 正在偵測您的帳號可用模型...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
        candidates = []
        if 'models' in data:
            for m in data['models']:
                name = m['name'].replace('models/', '')
                methods = m.get('supportedGenerationMethods', [])
                if 'gemini' in name and 'generateContent' in methods and 'exp' not in name:
                    candidates.append(name)
        
        if not candidates: return "gemini-1.5-flash"
        
        # 優先選 flash (速度快，生成大量題目較穩)
        for m in candidates:
            if 'flash' in m: return m
        return candidates[0]
    except:
        return "gemini-1.5-flash"

def load_existing_data():
    if os.path.exists(FILENAME):
        try:
            with open(FILENAME, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

def extract_context(existing_data):
    if not existing_data: return "無"
    samples = random.sample(existing_data, min(len(existing_data), 15))
    context_list = [re.sub(r'<[^>]+>', '', q['question'])[:20] for q in samples]
    return " | ".join(context_list)

def clean_json_string(text_str):
    """
    強力清洗字串，移除所有非法的 Control Characters
    """
    text_str = re.sub(r'```json\s*', '', text_str)
    text_str = re.sub(r'```\s*', '', text_str)
    # 移除 ASCII 控制字元 (0-31)，保留換行(\n, \r) 和 Tab(\t)
    text_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text_str)
    return text_str.strip()

def generate_questions(api_key, model_name, count, existing_context, start_id, level="N5"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    # 🔥🔥🔥 這是最重要的修改：極度嚴謹 Prompt (Updated for User Requirements) 🔥🔥🔥
    prompt = f"""
    你是 JLPT 日檢 {level} 出題專家與邏輯審查員。請幫我「新增」 {count} 道 {level} 水平的單選題。
    
    【核心規則 1：極度嚴謹的唯一正解】
    這不是創意寫作，這是考試題目。
    1. **只有唯一解**：對於 {level} 程度來說，必須只有一個最佳且正確的答案。
    2. **錯誤選項 (Distractors)**：必須是「文法完全錯誤」、「時態完全錯誤」或「語意邏輯完全不通」。
    3. **禁止模稜兩可**：絕對禁止出「兩個選項文法都對，只是 A 比 B 自然」的題目。
    4. **選項互斥**：四個選項必須相異。

    【核心規則 2：避免助詞冗餘 (Critical)】
    請檢查題目挖空處的前後文。
    - 如果題目挖空處**後方**已經有助詞（如「に」、「で」、「を」、「が」、「へ」等），選項中**絕對不能**再包含該助詞。
      - ❌ 錯誤範例：題目「私は（　　）に寝ます。」，選項「夜１０時に」（因為題目已經有「に」了）
      - ✅ 正確範例：題目「私は（　　）に寝ます。」，選項「夜１０時」
    - 反之，如果題目挖空處後方**沒有**助詞，而該句法需要助詞，則選項**必須**包含助詞。

    【核心規則 3：讀解題 (Reading) 格式強制】
    若 `section` 為 "讀解"，`question` 欄位**必須**包含兩個部分：
    1. **文章本文**：一篇 80-150 字的完整短文。
    2. **提問**：針對該文章的問題。
    (格式範例：「文章：田中さんは毎日... \n\n 質問：田中さんは...」)
    🚫 嚴禁只給問題而沒有文章！

    【核心規則 4：解析與分類】
    1. **解析 (explanation)**：必須使用**繁體中文**講解。必須明確指出**正確選項為什麼對**，以及**其他三個選項為什麼錯**（例如：「選項2是動詞原形，但這裡需要過去式...」）。
    2. **分類 (section)**：只允許以下三種分類：
       - "{level}-文法"
       - "{level}-語彙"
       - "{level}-讀解"
    3. **生成比例**：請嚴格遵守生成比例：文法 40%, 語彙 40%, 讀解 20%。

    【題目要求】
    1. 避免重複：請不要生成與以下內容相似的題目：{existing_context}
    2. 難度控制：嚴格控制在 {level} 程度，不要超綱。

    【JSON 格式】
    回傳純 JSON Array，物件結構：
    {{
       "id": {start_id},
       "section": "{level}-文法" / "{level}-語彙" / "{level}-讀解", 
       "type": "題型描述 (如: 助詞, 動詞活用, 內容理解)",
       "question": "題目內容 (讀解題務必包含文章)",
       "options": ["選項1", "選項2", "選項3", "選項4"],
       "answer": 0-3 (數字),
       "explanation": "繁體中文解析 (詳細解釋每個選項)"
    }}
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        # 🔥 將溫度降至 0.2，讓 AI 非常保守、理性，減少幻覺
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
    }

    print(f"🤖 請求 AI ({model_name}) 生成 {count} 題 {level} (極度嚴謹模式)...")
    
    try:
        # 設定 300 秒超時
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=300)
        
        if response.status_code != 200: 
            print(f"❌ API 回應錯誤: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        if 'candidates' in data:
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            clean_text = clean_json_string(raw_text)
            
            try:
                result_json = json.loads(clean_text, strict=False)
                
                # 🔥 後端品質檢測 (Post-processing)
                filtered_result = []
                for q in result_json:
                    # 檢查 1: 讀解題是否真的有文章？
                    if "讀解" in q['section'] and len(q['question']) < 30:
                        print(f"⚠️ 剔除一題無效的讀解題 (無文章內容)")
                        continue
                    
                    # 檢查 2: 答案索引是否合法
                    if not (0 <= int(q['answer']) <= 3):
                        continue

                    # 檢查 3: 選項是否重複
                    if len(set(q['options'])) != 4:
                        print(f"⚠️ 剔除一題選項重複的題目")
                        continue

                    # 檢查 4: 助詞冗餘檢查 (Particle Redundancy Check)
                    q_text = q['question']
                    ans_idx = int(q['answer'])
                    ans_text = q['options'][ans_idx]
                    
                    # 尋找挖空處，通常是 （　　） 或 (    )
                    match = re.search(r'[（\(].*?[）\)]', q_text)
                    if match:
                        end_pos = match.end()
                        # 取得挖空處後方的文字
                        text_after = q_text[end_pos:].strip()
                        if len(text_after) > 0:
                            # 常見助詞列表
                            particles = ['に', 'で', 'を', 'が', 'へ', 'と', 'から', 'まで', 'より', 'は', 'も']
                            for p in particles:
                                if text_after.startswith(p) and ans_text.endswith(p):
                                    print(f"⚠️ 剔除一題助詞冗餘: 題目後方已有 '{p}'，但選項 '{ans_text}' 也包含。")
                                    q = None 
                                    break
                    
                    if q:
                        filtered_result.append(q)
                    
                return filtered_result

            except json.JSONDecodeError as e:
                print(f"⚠️ JSON 解析失敗: {e}")
                return []
        return []
    except Exception as e:
        print(f"❌ 連線或處理錯誤: {e}")
        return []

def main():
    api_key = get_api_key()
    if not api_key: return
    model_name = get_valid_model(api_key)
    all_data = load_existing_data()
    
    # --- 新增：使用者輸入設定 ---
    print("\n請選擇生成等級 (預設 N5):")
    level_input = input("> ").strip().upper()
    target_level = level_input if level_input in ["N4", "N5"] else "N5"
    
    print(f"\n請輸入生成題數 (預設 {BATCH_SIZE}):")
    count_input = input("> ").strip()
    target_count = int(count_input) if count_input.isdigit() and int(count_input) > 0 else BATCH_SIZE
    # ---------------------------

    start_id = 1
    if all_data: start_id = max(item['id'] for item in all_data) + 1

    context = extract_context(all_data)
    new_questions = generate_questions(api_key, model_name, target_count, context, start_id, target_level)

    if new_questions:
        valid_sections = ["文法", "語彙", "讀解"]
        curr = start_id
        for q in new_questions:
            q['id'] = curr
            if isinstance(q.get('answer'), str) and q['answer'].isdigit(): q['answer'] = int(q['answer'])
            
            # 確保 section 格式正確
            if not q['section'].startswith(target_level):
                raw_sec = q['section'].replace(f"{target_level}-", "")
                if raw_sec not in valid_sections:
                    if "漢" in q.get('type', '') or "外來" in q.get('type', ''): raw_sec = "語彙"
                    elif "読" in q.get('type', ''): raw_sec = "讀解"
                    else: raw_sec = "文法"
                q['section'] = f"{target_level}-{raw_sec}"
            
            curr += 1

        all_data.extend(new_questions)
        with open(FILENAME, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)
        print(f"🎉 成功新增 {len(new_questions)} 題！總數：{len(all_data)}")
    else:
        print("⚠️ 生成失敗 (請重試，建議將 BATCH_SIZE 調小至 50 以確保穩定)")

if __name__ == "__main__":
    main()