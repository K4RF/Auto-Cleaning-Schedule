import json
import requests
import gspread
import os
import traceback
from datetime import datetime, timedelta, date

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
        print(f"❌ 오류: config.json 파일을 찾을 수 없습니다.")
        exit()

CONFIG = load_config()

# 단축 변수
NOTION_KEY = CONFIG["NOTION"]["API_KEY"]
NOTION_DB_ID = CONFIG["NOTION"]["DATABASE_ID"]
PROP_NAMES = CONFIG["NOTION"]["PROPERTY_NAMES"]
RULES = CONFIG["CLEANING_RULES"]

# ==========================================
# [함수] 이번 주 범위 계산 (월~일)
# ==========================================
def get_this_week_range():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) 
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.isoformat(), end_of_week.isoformat()

# ==========================================
# [2] 노션 데이터 가져오기 (똑똑한 필터링)
# ==========================================
def fetch_notion_data():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    start_date, end_date = get_this_week_range()
    print(f"📅 검색 범위: 이번 주 ({start_date} ~ {end_date})")

    # 필터 조건: (예약완료) AND (이번주) AND (발주안된것)
    payload = {
        "filter": {
            "and": [
                {
                    "property": PROP_NAMES["STATUS"],
                    "status": {"equals": PROP_NAMES["STATUS_VALUE"]} # 예약완료
                },
                {
                    "property": PROP_NAMES["DATE"],
                    "date": {
                        "on_or_after": start_date,
                        "on_or_before": end_date
                    }
                },
                {
                    # [핵심] 청소 발주 여부가 'O'가 아닌 것만 가져오기
                    "property": PROP_NAMES["ORDER_CHECK"],
                    "select": {
                        "does_not_equal": "O"
                    }
                }
            ]
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"❌ 노션 연결 실패: {response.status_code} - {response.text}")
        return []
        
    return response.json().get("results", [])

# ==========================================
# [함수] 노션에 'O' 체크하기 (발주 완료 처리)
# ==========================================
def mark_as_ordered(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # '청소 발주 여부'를 'O'로 업데이트
    payload = {
        "properties": {
            PROP_NAMES["ORDER_CHECK"]: {
                "select": {"name": "O"} 
            }
        }
    }
    
    requests.patch(url, json=payload, headers=headers)
    print(f"   👉 노션 업데이트 완료: [O] 체크됨")

# ==========================================
# [3] 데이터 해석 및 계산
# ==========================================
def parse_cleaning_info(page):
    props = page["properties"]
    
    # 1. 지점
    branch = ""
    if props.get(PROP_NAMES["BRANCH"]) and props[PROP_NAMES["BRANCH"]]["select"]:
        branch = props[PROP_NAMES["BRANCH"]]["select"]["name"]
    
    # 2. 날짜
    r_date = ""
    if props.get(PROP_NAMES["DATE"]) and props[PROP_NAMES["DATE"]]["date"]:
        r_date = props[PROP_NAMES["DATE"]]["date"]["start"]
        # 날짜 뒤에 시간(T00:00:00)이 붙어있으면 떼어냄
        if "T" in r_date:
            r_date = r_date.split("T")[0]

    # 3. 패키지 (제목 분석 포함)
    pkg_name = ""
    if props.get(PROP_NAMES["PACKAGE"]) and props[PROP_NAMES["PACKAGE"]]["select"]:
        pkg_name = props[PROP_NAMES["PACKAGE"]]["select"]["name"]
    
    if not pkg_name:
        for key, val in props.items():
            if val['type'] == 'title' and val['title']:
                full_title = val['title'][0]['plain_text']
                if "나이트" in full_title: pkg_name = "나이트 패키지"
                elif "데이" in full_title: pkg_name = "데이 패키지"
                elif "시간제" in full_title: pkg_name = "시간제"
                break
    
    # 4. 시간 계산
    start_time, end_time, duration = "", "", ""
    if "나이트" in pkg_name:
        start_time = RULES["NIGHT_START"]
        end_time = RULES["NIGHT_END"]
        duration = RULES["NIGHT_HOURS"]
    else:
        start_time = RULES["DAY_START"]
        end_time = RULES["DAY_END"]
        duration = RULES["DAY_HOURS"]
        
    return branch, r_date, pkg_name, start_time, end_time, duration

# ==========================================
# [4] 메인 실행 함수
# ==========================================
def main():
    print("🔄 시스템 가동: [이번 주 + 미발주] 건을 조회합니다...")
    
    # 구글 시트 연결
    sheet = None
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(base_dir, CONFIG["GOOGLE"]["JSON_KEY_FILE"])
        gc = gspread.service_account(filename=key_path)
        
        sheet_id = CONFIG["GOOGLE"].get("SHEET_ID")
        if not sheet_id:
            print("⚠️ 경고: SHEET_ID가 없습니다. 이름으로 찾습니다.")
            sheet = gc.open(CONFIG["GOOGLE"]["SHEET_NAME"]).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
        else:
            sheet = gc.open_by_key(sheet_id).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
    except Exception:
        print("❌ 구글 시트 연결 실패!")
        traceback.print_exc()
        return

    # 노션 조회
    pages = fetch_notion_data()
    print(f"📋 처리할 신규 예약: {len(pages)}건")
    
    new_count = 0
    for page in pages:
        page_id = page["id"].replace("-", "") 
        
        # 데이터 해석
        branch, r_date, pkg_name, t_start, t_end, dur = parse_cleaning_info(page)
        
        # 구글 시트 추가
        row = [
            page_id, branch, r_date, pkg_name, 
            t_start, t_end, dur, 
            "", "", "대기", "X"
        ]
        
        try:
            sheet.append_row(row)
            print(f"  [등록] {r_date} | {branch} ({pkg_name}) -> 시트 저장 완료")
            
            # [중요] 성공했으면 노션에도 'O' 체크
            mark_as_ordered(page["id"])
            new_count += 1
            
        except Exception as e:
            print(f"  ❌ 에러 발생 ({branch}): {e}")
        
    if new_count > 0:
        print(f"✅ 총 {new_count}건 처리 완료! (노션 'O' 체크 포함)")
    else:
        print("✅ 처리할 새로운 예약이 없습니다.")

if __name__ == "__main__":
    main()