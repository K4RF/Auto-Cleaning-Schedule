import json
import requests
import os

def load_config():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ config.json 파일이 없습니다.")
        exit()

CONFIG = load_config()
NOTION_KEY = CONFIG["NOTION"]["API_KEY"]
NOTION_DB_ID = CONFIG["NOTION"]["DATABASE_ID"]

def check_columns():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("❌ 연결 실패")
        return

    properties = response.json().get("properties", {})
    print("\n📊 [노션 속성 이름 목록]")
    print("========================================")
    for name, info in properties.items():
        p_type = info['type']
        print(f"🔹 이름: '{name}' (타입: {p_type})")
        
        if "청소" in name or "발주" in name:
            print(f"   👉 [집중확인] 이 이름을 config.json에 복사해 넣으세요!")
    print("========================================")

if __name__ == "__main__":
    check_columns()