import json
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# [1] 설정 파일(config.json) 읽어오기
# ==========================================
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ 오류: 'config.json' 파일을 찾을 수 없습니다.")
        exit()

CONFIG = load_config()

# 단축 변수 설정 (사용하기 편하게)
NOTION_KEY = CONFIG["NOTION"]["API_KEY"]
NOTION_DB_ID = CONFIG["NOTION"]["DATABASE_ID"]
PROP_NAMES = CONFIG["NOTION"]["PROPERTY_NAMES"]
RULES = CONFIG["CLEANING_RULES"]

# ==========================================
# [2] 노션 데이터 가져오기
# ==========================================
def fetch_notion_data():
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # 설정 파일에 지정된 '예약상태'와 '값(예약확정)'으로 필터링
    payload = {
        "filter": {
            "property": PROP_NAMES["STATUS"], 
            "select": {
                "equals": PROP_NAMES["STATUS_VALUE"]
            }
        }
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"❌ 노션 연결 실패: {response.status_code}")
        print(response.text)
        return []
        
    return response.json().get("results", [])

# ==========================================
# [3] 청소 정보 계산 (데이/나이트 판별)
# ==========================================
def parse_cleaning_info(props):
    # 1. 지점명 가져오기
    branch = ""
    p_branch = props.get(PROP_NAMES["BRANCH"]) # config에 적힌 이름으로 찾음
    if p_branch and p_branch["select"]:
        branch = p_branch["select"]["name"]
    
    # 2. 날짜 가져오기
    r_date = ""
    p_date = props.get(PROP_NAMES["DATE"])
    if p_date and p_date["date"]:
        r_date = p_date["date"]["start"]

    # 3. 패키지 정보 및 시간 계산
    pkg_name = ""
    p_pkg = props.get(PROP_NAMES["PACKAGE"])
    if p_pkg and p_pkg["select"]:
        pkg_name = p_pkg["select"]["name"]

    # 기본값 초기화
    start_time, end_time, duration = "", "", ""

    # 패키지 이름에 따른 로직 (데이/시간제 vs 나이트)
    if "나이트" in pkg_name:
        start_time = RULES["NIGHT_START"]
        end_time = RULES["NIGHT_END"]
        duration = RULES["NIGHT_HOURS"]
    else:
        # 데이패키지 또는 시간제 (기본값)
        start_time = RULES["DAY_START"]
        end_time = RULES["DAY_END"]
        duration = RULES["DAY_HOURS"]
        
    return branch, r_date, pkg_name, start_time, end_time, duration

# ==========================================
# [4] 메인 실행 함수 (구글 시트 전송)
# ==========================================
def main():
    print("🔄 시스템 가동: 노션 데이터를 확인합니다...")
    
    # 구글 시트 연결
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            CONFIG["GOOGLE"]["JSON_KEY_FILE"], scope
        )
        client = gspread.authorize(creds)
        sheet = client.open(CONFIG["GOOGLE"]["SHEET_NAME"]).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
    except Exception as e:
        print(f"❌ 구글 시트 연결 오류: {e}")
        return

    # 기존 데이터 확인 (중복 방지)
    existing_ids = sheet.col_values(1) # A열(No) 조회

    # 노션 조회
    pages = fetch_notion_data()
    print(f"📋 노션에서 {len(pages)}개의 확정된 예약을 찾았습니다.")
    
    new_count = 0
    
    for page in pages:
        page_id = page["id"].replace("-", "") # ID 깔끔하게 정리
        
        # 이미 등록된 건이면 패스
        if page_id in existing_ids:
            continue
            
        # 노션 속성(Properties) 가져오기
        props = page["properties"]
        
        # 데이터 해석 (위에서 만든 함수 사용)
        branch, r_date, pkg_name, t_start, t_end, dur = parse_cleaning_info(props)
        
        # 구글 시트에 넣을 데이터 순서 (헤더와 일치해야 함)
        # [No, 지점명, 날짜, 패키지종류, 시작가능, 마감, 소요시간, (방문시간), (담당자), 상태, SMS발송]
        row = [
            page_id,    # A
            branch,     # B
            r_date,     # C
            pkg_name,   # D
            t_start,    # E
            t_end,      # F
            dur,        # G
            "",         # H (방문예상시간 - 비워둠)
            "",         # I (담당자 - 비워둠)
            "대기",     # J
            "X"         # K
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