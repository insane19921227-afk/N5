import json
import os

# 預設檔案，可根據需求修改
FILENAME = "JLPT_n5_questions.json"

def load_data():
    if not os.path.exists(FILENAME):
        print(f"❌ 找不到題庫檔案: {FILENAME}")
        return []
    try:
        with open(FILENAME, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 讀取失敗: {e}")
        return []

def save_data(data):
    with open(FILENAME, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("✅ 檔案已更新！")

def delete_batch(data):
    print("\n--- 批量刪除題目 ---")
    print("說明：請輸入 ID，用「逗號」隔開 (例如: N5-文法-v01-01, N5-讀解-v02-05)")
    raw_input = input("請輸入 ID > ").strip()

    if not raw_input:
        print("❌ 未輸入內容。")
        return data

    # 1. 解析輸入的字串
    target_ids = set()
    
    for item in raw_input.split(','):
        item = item.strip()
        if item:
            target_ids.add(item)

    if not target_ids:
        print("❌ 沒有有效的 ID。")
        return data

    # 2. 執行刪除邏輯
    initial_count = len(data)
    
    # 保留「ID 不在刪除清單中」的題目
    # 注意：現在 ID 是字串，直接比對
    new_data = [q for q in data if str(q.get('id', '')) not in target_ids]
    
    final_count = len(new_data)
    deleted_count = initial_count - final_count

    if deleted_count > 0:
        print(f"🗑️ 成功刪除 {deleted_count} 題！")
        
        # 計算實際被刪除的 ID
        remaining_ids = set(str(q.get('id', '')) for q in new_data)
        original_ids = set(str(q.get('id', '')) for q in data)
        actual_deleted_ids = original_ids - remaining_ids
        
        print(f"   (已移除 ID: {sorted(list(actual_deleted_ids))})")
        return new_data
    else:
        print("⚠️ 找不到任何符合的 ID，沒有題目被刪除。")
        return data

def renumber_ids(data):
    print("\n⚠️ 警告：目前的 ID 格式包含版本與類別資訊 (如 N5-文法-v01-01)。")
    print("重新編號可能會破壞這些資訊，建議不要執行。")
    confirm = input("確定要強制重新編號為純數字嗎？(y/n): ").lower()
    
    if confirm == 'y':
        for index, q in enumerate(data):
            q['id'] = index + 1
        print(f"✅ 已將 {len(data)} 題重新編號為純數字 (1, 2, 3...)。")
        return data
    else:
        print("已取消。")
        return data

def main():
    global FILENAME
    print("請選擇要管理的檔案:")
    print("1. N5 (JLPT_n5_questions.json)")
    print("2. N4 (JLPT_n4_questions.json)")
    f_choice = input("請選擇 (1/2): ").strip()
    
    if f_choice == '2':
        FILENAME = "JLPT_n4_questions.json"
    else:
        FILENAME = "JLPT_n5_questions.json"
        
    while True:
        data = load_data()
        print(f"\n=== 目前管理檔案: {FILENAME} ===")
        print(f"目前題庫總數: {len(data)} 題")
        print("1. 批量刪除題目 (輸入 ID)")
        print("2. 重新編號 (不推薦)")
        print("3. 離開")
        print("==============================")
        
        choice = input("請選擇功能 (1-3): ").strip()

        if choice == '1':
            data = delete_batch(data)
            save_data(data)
        elif choice == '2':
            data = renumber_ids(data)
            save_data(data)
        elif choice == '3':
            break
        else:
            print("無效的選擇")

if __name__ == "__main__":
    main()