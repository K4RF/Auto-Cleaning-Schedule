# debug_filter_v2.py
import requests
import json
import os
from datetime import datetime

print("🚀 디버거 시작! (1/4)")

# 1. config.json 직접 로드 (경로 문제 원천 차단)
try:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    print("✅ config.json 로드 성공 (2/4)")
except Exception as e:
    print(f"❌ config.json 로드 실패: {e}")
    exit()

NOTION_KEY = config["NOTION"]["API_KEY"]
NOTION_DB_ID = config["NOTION"]["DATABASE_ID"]
PROP_NAMES = config["NOTION"]["PROPERTY_NAMES"]

def check_why_fetched():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    target_col = PROP_NAMES["ORDER_CHECK"]
    print(f"🔎 타겟 컬럼명: '{target_col}' (3/4)")

    # 필터: 오늘 이후 + 예약완료
    today_str = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "filter": {
            "and": [
                {
                    "property": PROP_NAMES["DATE"],
                    "date": {"on_or_after": today_str}
                },
                {
                    "property": PROP_NAMES["STATUS"],
                    "status": {"equals": PROP_NAMES["STATUS_VALUE"]}
                }
            ]
        }
    }

    print(f"📡 노션 API 요청 중... ({today_str} 이후)")
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ API 오류: {response.status_code} {response.text}")
        return

    results = response.json().get("results", [])
    print(f"📥 총 {len(results)}개 데이터 수신됨 (4/4)\n")

    for i, page in enumerate(results):
        props = page["properties"]
        
        # 지점명 확인
        branch = "미지정"
        if "select" in props.get(PROP_NAMES["BRANCH"], {}) and props[PROP_NAMES["BRANCH"]]["select"]:
            branch = props[PROP_NAMES["BRANCH"]]["select"]["name"]
        
        date_val = "날짜없음"
        if props.get(PROP_NAMES["DATE"], {}).get("date"):
            date_val = props[PROP_NAMES["DATE"]]["date"]["start"]

        print(f"👉 [{i+1}] {branch} | {date_val}")

        # [핵심] 청소 발주 여부 값 확인
        if target_col not in props:
            print(f"   ❌ 속성 없음! (노션엔 없고 config에만 있음)")
            print(f"   -> 실제 속성 목록: {list(props.keys())}")
            continue

        order_prop = props[target_col]
        # 전체 구조 출력 (어떤 타입인지 확인용)
        print(f"   📄 속성 데이터: {json.dumps(order_prop, ensure_ascii=False)}")

        # Select 타입 체크
        if "select" in order_prop:
            val = order_prop["select"]
            if val is None:
                print("   ✅ 값: 비어있음 (None)")
            else:
                print(f"   ⛔ 값: '{val['name']}' (ID: {val['id']})")
        else:
            print(f"   ❓ 타입이 select가 아님! ({list(order_prop.keys())})")
        
        print("-" * 30)

if __name__ == "__main__":
    check_why_fetched()