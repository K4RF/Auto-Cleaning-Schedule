import json
import requests
import gspread
import os
import traceback
from datetime import datetime

# ==========================================
# [1] 설정 파일 읽기
# ==========================================
def load_config():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ 오류: 설정 파일을 찾을 수 없습니다.")
        exit()

CONFIG = load_config()

# 단축 변수
NOTION_KEY = CONFIG["NOTION"]["API_KEY"]
NOTION_DB_ID = CONFIG["NOTION"]["DATABASE_ID"]
PROP_NAMES = CONFIG["NOTION"]["PROPERTY_NAMES"]
RULES = CONFIG["CLEANING_RULES"]

# ==========================================
# [2] 노션 데이터 가져오기 (수정됨)
# ==========================================
def fetch_notion_data():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # [핵심 수정] 400 오류 해결을 위해 'select' -> 'status'로 변경 시도
    # (만약 노션 속성이 진짜 Select라면 다시 select로 바꿔야 하지만, 스크린샷상 Status가 확실함)
    payload = {
        "filter": {
            "property": PROP_NAMES["STATUS"], 
            "status": {  # <--- 여기가 'select'에서 'status'로 바뀜!
                "equals": PROP_NAMES["STATUS_VALUE"]
            }
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ 노션 연결 실패: {response.status_code}")
        print(f"이유: {response.text}")
        return []
        
    return response.json().get("results", [])

# ==========================================
# [3] 청소 정보 계산 (제목 분석 기능 추가)
# ==========================================
def parse_cleaning_info(page):
    props = page["properties"]
    
    # 1. 지점명 (Select)
    branch = ""
    if props.get(PROP_NAMES["BRANCH"]) and props[PROP_NAMES["BRANCH"]]["select"]:
        branch = props[PROP_NAMES["BRANCH"]]["select"]["name"]
    
    # 2. 날짜 (Date)
    r_date = ""
    if props.get(PROP_NAMES["DATE"]) and props[PROP_NAMES["DATE"]]["date"]:
        r_date = props[PROP_NAMES["DATE"]]["date"]["start"]

    # 3. 패키지 정보 (속성 또는 제목에서 찾기)
    pkg_name = ""
    
    # (A) 먼저 속성에서 찾아봄
    if props.get(PROP_NAMES["PACKAGE"]) and props[PROP_NAMES["PACKAGE"]]["select"]:
        pkg_name = props[PROP_NAMES["PACKAGE"]]["select"]["name"]
    
    # (B) 속성에 없으면 '제목(Title)'을 분석 (스크린샷에 제목에 패키지명이 있어서 추가함)
    if not pkg_name:
        # 제목 속성 찾기 (보통 '이름', 'Name', '제목' 중 하나)
        for key, val in props.items():
            if val['type'] == 'title' and val['title']:
                full_title = val['title'][0]['plain_text'] # 예: "황세빈 - 나이트 패키지..."
                if "나이트" in full_title:
                    pkg_name = "나이트 패키지"
                elif "데이" in full_title:
                    pkg_name = "데이 패키지"
                break
    
    # 4. 시간 계산
    start_time, end_time, duration = "", "", ""
    if "나이트" in pkg_name:
        start_time = RULES["NIGHT_START"]
        end_time = RULES["NIGHT_END"]
        duration = RULES["NIGHT_HOURS"]
    else:
        # 기본값 (데이/시간제)
        start_time = RULES["DAY_START"]
        end_time = RULES["DAY_END"]
        duration = RULES["DAY_HOURS"]
        
    return branch, r_date, pkg_name, start_time, end_time, duration

# ==========================================
# [4] 메인 실행 함수
# ==========================================
def main():
    print("🔄 시스템 가동: 노션 데이터를 확인합니다...")
    
    sheet = None
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(base_dir, CONFIG["GOOGLE"]["JSON_KEY_FILE"])
        
        gc = gspread.service_account(filename=key_path)
        
        sheet_id = CONFIG["GOOGLE"].get("SHEET_ID")
        if not sheet_id:
            print("⚠️ 경고: SHEET_ID가 설정되지 않았습니다.")
            return
            
        sheet = gc.open_by_key(sheet_id).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
        
    except Exception:
        print("\n❌ 구글 시트 연결 실패!")
        traceback.print_exc()
        return

    # 기존 데이터 확인
    existing_ids = sheet.col_values(1) 

    # 노션 조회
    pages = fetch_notion_data()
    print(f"📋 노션에서 {len(pages)}개의 확정된 예약을 찾았습니다.")
    
    new_count = 0
    for page in pages:
        page_id = page["id"].replace("-", "") 
        if page_id in existing_ids:
            continue
            
        # [변경] page 전체를 넘겨서 제목까지 분석하게 함
        branch, r_date, pkg_name, t_start, t_end, dur = parse_cleaning_info(page)
        
        row = [
            page_id, branch, r_date, pkg_name, 
            t_start, t_end, dur, 
            "", "", "대기", "X"
        ]
        
        sheet.append_row(row)
        print(f"  [신규] {branch} / {r_date} ({pkg_name}) 등록 완료")
        new_count += 1
        
    if new_count > 0:
        print(f"✅ 총 {new_count}건의 예약을 스케줄표에 등록했습니다.")
    else:
        print("✅ 새로 추가된 예약이 없습니다.")

if __name__ == "__main__":
    main()