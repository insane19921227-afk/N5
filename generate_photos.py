import os
import json

# 設定圖片根目錄
ROOT_DIR = "Accomplishment"
OUTPUT_FILE = "photos.json"

# 定義稀有度權重 (排序用: SQR > SR > R > N)
RARITY_ORDER = {"SQR": 4, "SR": 3, "R": 2, "N": 1}

def generate_photo_db():
    if not os.path.exists(ROOT_DIR):
        print(f"❌ 找不到資料夾 '{ROOT_DIR}'，請確認已建立並放入照片。")
        return

    photo_db = []
    id_counter = 1

    print("📸 開始掃描相片庫...")

    # 遍歷 N, R, SR, SQR 資料夾
    for rarity in ["N", "R", "SR", "SQR"]:
        folder_path = os.path.join(ROOT_DIR, rarity)
        if not os.path.exists(folder_path):
            print(f"⚠️ 警告: 找不到 '{rarity}' 資料夾，跳過。")
            continue

        for filename in os.listdir(folder_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                # 解析檔名: "程小時&陸光_萬聖節.jpg"
                name_parts = os.path.splitext(filename)[0].split('_')
                
                character = "未知"
                title = name_parts[0]
                
                if len(name_parts) >= 2:
                    character = name_parts[0]
                    title = name_parts[1]
                
                # 建立資料物件
                photo_obj = {
                    "id": id_counter,
                    "rarity": rarity,
                    "character": character,
                    "title": title,
                    "path": f"{ROOT_DIR}/{rarity}/{filename}", # 相對路徑
                    "filename": filename
                }
                
                photo_db.append(photo_obj)
                id_counter += 1
                print(f"   ✅ 加入: [{rarity}] {character} - {title}")

    # 存檔
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(photo_db, f, ensure_ascii=False, indent=4)

    print("---------------------------------------")
    print(f"🎉 相片資料庫建立完成！共 {len(photo_db)} 張。")
    print(f"📂 已儲存為: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_photo_db()