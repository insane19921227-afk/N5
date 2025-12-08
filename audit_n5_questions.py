import requests
import json
import time
import os
import re

# ================= 設定區 =================
FILENAME = "n5_questions.json"
BATCH_SIZE = 5  # 每次檢查 5 題
# =========================================

def get_api_key():
    print("請輸入您的 Google Gemini API Key:")
    return input("> ").strip()

def get_valid_model(api_key):
    """自動偵測可用模型 (與生成器相同的邏輯)"""
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
        
        if not candidates:
            print("❌ 找不到可用模型，嘗試使用 gemini-1.5-pro")
            return "gemini-1.5-pro"
        
        # 優先選 flash (速度快)，沒有就選 pro
        selected = candidates[0]
        for m in candidates:
            if 'flash' in m: 
                selected = m
                break
        
        print(f"✅ 自動選定模型: {selected}")
        return selected
    except:
        return "gemini-1.5-pro"

def load_data():
    if os.path.exists(FILENAME):
        try:
            with open(FILENAME, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

def save_data(data):
    with open(FILENAME, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def clean_json_string(text_str):
    text_str = re.sub(r'```json\s*', '', text_str)
    text_str = re.sub(r'```\s*', '', text_str)
    return text_str.strip()

# --- 1. 本地邏輯檢查 ---
def local_pre_check(question):
    issues = []
    opt_len = len(question.get('options', []))
    ans_idx = question.get('answer')
    section = question.get('section', '')
    
    # 檢查 Section 格式
    if not (section.startswith('N5-') or section.startswith('N4-')):
        issues.append(f"Section 格式錯誤: {section} (應為 N5-xxx 或 N4-xxx)")

    if isinstance(ans_idx, int):
        if ans_idx < 0 or ans_idx >= opt_len:
            issues.append(f"答案索引錯誤: answer={ans_idx}, 選項數={opt_len}")
    else:
        issues.append("答案格式錯誤")

    if '讀解' in section:
        q_text = question.get('question', '')
        if len(q_text) < 30:
            issues.append("讀解題疑似缺文章")
            
    return issues

# --- 2. AI 審查 (帶入自動偵測的模型) ---
def audit_batch_with_ai(api_key, model_name, questions):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    q_data_str = json.dumps(questions, ensure_ascii=False)

    prompt = f"""
    你是最嚴格的 JLPT N4/N5 題目審校員。請檢查以下 {len(questions)} 道題目。

    【輸入資料】
    {q_data_str}

    【檢查重點】
    1. **級別檢核**：確認 `section` 標示的 N4 或 N5 是否與題目難度相符。若標示 N5 但題目顯然是 N3 以上，請報錯。
    2. **唯一正解**：是否有多個選項都通？或沒有正確答案？
    3. **錯誤選項**：錯誤選項是否明顯錯誤？(不能有模稜兩可的情況)
    4. **解析檢查**：
       - 解析是否使用**繁體中文**？
       - 解析是否詳細解釋正確與錯誤原因？
       - 若解析不合格（非繁中、簡體中文、或太簡略），請提供修正後的解析。

    【輸出格式】
    回傳 JSON Array：
    [
        {{
            "id": 題目ID,
            "status": "PASS" 或 "FAIL",
            "reason": "FAIL的原因 (繁體中文)",
            "new_explanation": "若原解析不合格(如非繁中)，請在此提供修正後的繁體中文解析 (否則留空)"
        }},
        ...
    ]
    """

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
    }

    try:
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ API 錯誤 ({response.status_code}): {response.text}")
            return []
            
        data = response.json()
        if 'candidates' in data:
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(clean_json_string(raw_text))
        return []
    except Exception as e:
        print(f"❌ 連線失敗: {e}")
        return []

def main():
    api_key = get_api_key()
    if not api_key: return

    # 1. 取得正確模型
    model_name = get_valid_model(api_key)

    all_data = load_data()
    if not all_data:
        print("❌ 找不到題庫檔案。")
        return

    # 找出未驗證的題目
    unverified_list = [q for q in all_data if not q.get('verified', False)]
    total = len(unverified_list)
    print(f"📊 待審查題目: {total} 題")

    if total == 0:
        print("🎉 所有題目都已審核完畢！")
        return

    ids_to_remove = []
    modified_count = 0
    
    # 分批處理
    for i in range(0, total, BATCH_SIZE):
        batch = unverified_list[i : i + BATCH_SIZE]
        print(f"\n🔍 正在掃描第 {i+1}~{i+len(batch)} 題 (使用 {model_name})...")

        # 本地檢查
        failed_ids_in_batch = set()
        for q in batch:
            local_issues = local_pre_check(q)
            if local_issues:
                print(f"\n🚩 [程式攔截] ID: {q['id']}")
                print(f"   問題: {', '.join(local_issues)}")
                print(f"   題目: {q['question']}")
                action = input("👉 刪除(y)? ").lower()
                if action == 'y':
                    ids_to_remove.append(q['id'])
                    failed_ids_in_batch.add(q['id'])
                else:
                    q['verified'] = True

        # AI 檢查
        ai_batch = [q for q in batch if q['id'] not in failed_ids_in_batch]
        if not ai_batch: continue

        ai_results = audit_batch_with_ai(api_key, model_name, ai_batch)
        
        if not ai_results:
            print("⚠️ AI 無回應或錯誤，跳過此批次")
            continue

        for res in ai_results:
            q_id = res.get('id')
            status = res.get('status')
            reason = res.get('reason', '')
            new_explanation = res.get('new_explanation', '')

            target_q = next((q for q in ai_batch if q['id'] == q_id), None)
            if not target_q: continue

            if status == 'FAIL':
                print(f"\n🤖 [AI 警告] ID: {q_id}")
                print(f"   原因: \033[91m{reason}\033[0m")
                print(f"   題目: {target_q['question']}")
                print(f"   選項: {target_q['options']} (Ans: {target_q['options'][target_q['answer']]})")
                
                action = input("👉 刪除(y) 或 保留(n)? ").lower()
                if action == 'y':
                    ids_to_remove.append(q_id)
                    print("🗑️ 已標記刪除")
                else:
                    target_q['verified'] = True
                    print("🛡️ 已保留")
            else:
                # PASS 的情況，檢查是否需要更新解析
                if new_explanation and len(new_explanation) > 5:
                    print(f"\n📝 [解析優化] ID: {q_id}")
                    print(f"   原解析: {target_q.get('explanation', '')[:30]}...")
                    print(f"   新解析: \033[92m{new_explanation[:30]}...\033[0m")
                    target_q['explanation'] = new_explanation
                    modified_count += 1
                
                target_q['verified'] = True

        # 每個批次結束後存檔一次，避免中斷遺失
        if ids_to_remove:
            all_data = [q for q in all_data if q['id'] not in ids_to_remove]
            save_data(all_data)
            ids_to_remove = [] # 清空待刪除列表
        else:
            save_data(all_data)

    print(f"\n✅ 審查結束。共優化了 {modified_count} 題解析。")

if __name__ == "__main__":
    main()