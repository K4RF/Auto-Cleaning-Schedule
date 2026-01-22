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
NOTION_KEY = CONFIG["NOTION"]["API_KEY"]
NOTION_DB_ID = CONFIG["NOTION"]["DATABASE_ID"]
PROP_NAMES = CONFIG["NOTION"]["PROPERTY_NAMES"]
RULES = CONFIG["CLEANING_RULES"]

# ==========================================
# [함수] 이번 주 범위 계산
# ==========================================
def get_this_week_range():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) 
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d")

# ==========================================
# [함수] 노션 업데이트 (O 체크)
# ==========================================
def mark_as_ordered(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    payload = {
        "properties": {
            PROP_NAMES["ORDER_CHECK"]: {
                "select": {"name": "O"} 
            }
        }
    }
    try:
        requests.patch(url, json=payload, headers=headers)
    except Exception:
        pass

# ==========================================
# [2] 데이터 수집 (안전 조회: 최신순 -> 필터링)
# ==========================================
def fetch_weekly_data_safe(start_str, end_str):
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # 1. 최신순(내림차순)으로 가져와서 2023년 데이터 조회 방지
    payload = {
        "filter": {
            "property": PROP_NAMES["STATUS"],
            "status": {"equals": PROP_NAMES["STATUS_VALUE"]}
        },
        "sorts": [
            {
                "property": PROP_NAMES["DATE"], 
                "direction": "descending"
            }
        ]
    }

    has_more = True
    next_cursor = None
    collected_list = []
    stop_search = False

    print("🔄 스케줄 분석 중... (최신 데이터부터 안전하게 조회)")

    while has_more and not stop_search:
        if next_cursor: payload["start_cursor"] = next_cursor
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200: break
            
        data = response.json()
        results = data.get("results", [])
        
        for page in results:
            props = page["properties"]
            
            # 날짜 파싱
            if not (props.get(PROP_NAMES["DATE"]) and props[PROP_NAMES["DATE"]]["date"]):
                continue

            date_data = props[PROP_NAMES["DATE"]]["date"]
            start_iso = date_data["start"]
            end_iso = date_data.get("end")
            
            # 날짜 문자열
            r_date_str = start_iso.split("T")[0]

            # 🛑 [안전장치] 범위 필터링
            if r_date_str > end_str: continue # 미래 패스
            if r_date_str < start_str: 
                # 과거(지난주) 나오면 즉시 종료
                stop_search = True
                break

            # ------------------------------------------------
            # 데이터 추출
            # ------------------------------------------------
            
            # 발주 여부
            is_ordered = False
            target_prop = props.get(PROP_NAMES["ORDER_CHECK"])
            if target_prop and target_prop["type"] == "select" and target_prop["select"]:
                is_ordered = True
            
            # 지점
            branch = ""
            if props.get(PROP_NAMES["BRANCH"]) and props[PROP_NAMES["BRANCH"]]["select"]:
                branch = props[PROP_NAMES["BRANCH"]]["select"]["name"]

            # 패키지
            pkg_name = ""
            full_title = ""
            if props.get(PROP_NAMES["PACKAGE"]) and props[PROP_NAMES["PACKAGE"]]["select"]:
                pkg_name = props[PROP_NAMES["PACKAGE"]]["select"]["name"]
            
            for key, val in props.items():
                if val['type'] == 'title' and val['title']:
                    full_title = val['title'][0]['plain_text']
                    break
            
            if not pkg_name:
                if "나이트" in full_title: pkg_name = "나이트 패키지"
                elif "데이" in full_title: pkg_name = "데이 패키지"
                elif "올데이" in full_title: pkg_name = "올데이"
                else: pkg_name = "시간제"

            # 🕒 청소 시간 계산 (타임존 제거 안전장치)
            try:
                dt_start = datetime.fromisoformat(start_iso)
                if dt_start.tzinfo is not None: dt_start = dt_start.replace(tzinfo=None)

                if end_iso:
                    dt_end = datetime.fromisoformat(end_iso)
                    if dt_end.tzinfo is not None: dt_end = dt_end.replace(tzinfo=None)
                else:
                    dt_end = dt_start + timedelta(hours=3)
            except ValueError:
                dt_start = datetime.strptime(start_iso, "%Y-%m-%d")
                dt_end = dt_start

            cleaning_start_dt = None
            cleaning_end_dt = None
            
            if "나이트" in pkg_name:
                # 나이트: 다음날 08:00 ~ 10:00
                cleaning_start_dt = dt_start.replace(hour=8, minute=0) + timedelta(days=1)
                cleaning_end_dt = cleaning_start_dt + timedelta(hours=2)
            
            elif "데이" in pkg_name:
                # 데이: 당일 17:00 ~ 18:00
                cleaning_start_dt = dt_start.replace(hour=17, minute=0)
                cleaning_end_dt = cleaning_start_dt + timedelta(hours=1)
                
            else: 
                # [시간제/올데이] 퇴실 시간 = 청소 시작
                cleaning_start_dt = dt_end
                
                # 이용 시간 계산
                usage_hours = (dt_end - dt_start).total_seconds() / 3600
                clean_duration = 1 if usage_hours < 4 else 2
                cleaning_end_dt = cleaning_start_dt + timedelta(hours=clean_duration)

            collected_list.append({
                "id": page["id"],
                "branch": branch,
                "pkg_name": pkg_name,
                "is_ordered": is_ordered,
                "check_in_dt": dt_start,   
                "clean_start_dt": cleaning_start_dt, 
                "clean_end_dt": cleaning_end_dt      
            })

        has_more = data.get("has_more")
        next_cursor = data.get("next_cursor")

    return collected_list

# ==========================================
# [3] 메인 실행
# ==========================================
def main():
    start_str, end_str = get_this_week_range()
    
    print(f"🚀 시스템 가동: [F열:마감정보 / H열:비움]")
    print(f"📅 타겟 기간: {start_str} ~ {end_str}")

    # 1. 구글 시트 연결
    sheet = None
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(base_dir, CONFIG["GOOGLE"]["JSON_KEY_FILE"])
        gc = gspread.service_account(filename=key_path)
        
        sheet_id = CONFIG["GOOGLE"].get("SHEET_ID")
        if not sheet_id:
            sheet = gc.open(CONFIG["GOOGLE"]["SHEET_NAME"]).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
        else:
            sheet = gc.open_by_key(sheet_id).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
    except Exception:
        print("❌ 구글 시트 연결 실패!")
        return

    # 2. 데이터 가져오기
    reservations = fetch_weekly_data_safe(start_str, end_str)
    
    # 3. 시간순 정렬 (다음 예약 계산용)
    reservations.sort(key=lambda x: x["clean_start_dt"])
    
    count = 0
    
    for i, current in enumerate(reservations):
        
        # 이미 발주된 건 스킵
        if current["is_ordered"]:
            continue
            
        # ------------------------------------------------
        # 🔍 다음 예약 확인 -> 마감시간(F열) 문구 생성
        # ------------------------------------------------
        deadline_text = "다음 예약 없음"
        
        for j in range(len(reservations)):
            other = reservations[j]
            
            if current["id"] == other["id"]: continue
            if current["branch"] != other["branch"]: continue
            
            # 같은 날짜인지 확인
            clean_date = current["clean_start_dt"].date()
            other_checkin_date = other["check_in_dt"].date()
            if clean_date != other_checkin_date: continue
            
            # 내 청소 시작 이후에 들어오는 예약 발견
            if other["check_in_dt"] >= current["clean_start_dt"]:
                in_time = other["check_in_dt"].strftime("%H:%M")
                # [요청사항] "다음 예약 xx시" 형식
                deadline_text = f"다음 예약 {in_time}"
                break
        
        # ------------------------------------------------
        # 📝 구글 시트 업로드
        # ------------------------------------------------
        t_start = current["clean_start_dt"].strftime("%H:%M")
        
        # 소요시간
        duration_sec = (current["clean_end_dt"] - current["clean_start_dt"]).total_seconds()
        duration = str(int(duration_sec / 3600))
        
        clean_date_str = current["clean_start_dt"].strftime("%Y-%m-%d")

        row = [
            current["id"].replace("-", ""), # A: ID
            current["branch"],              # B: 지점
            clean_date_str,                 # C: 날짜
            current["pkg_name"],            # D: 상세내용
            t_start,                        # E: 청소시작가능시간
            deadline_text,                  # F: [수정] 청소마감시간 -> "다음 예약 없음" or "다음 예약 19:00"
            duration,                       # G: 소요시간
            "",                             # H: [수정] 방문예상시간 -> 빈칸 (담당자 선택)
            "",                             # I: 담당자
            "대기",                          # J: 상태
            "X"                             # K: SMS
        ]

        try:
            sheet.append_row(row)
            print(f"  ✅ [등록] {current['branch']} | {clean_date_str} | 마감: {deadline_text}")
            mark_as_ordered(current["id"])
            count += 1
        except Exception as e:
            print(f"  ❌ 업로드 실패: {e}")

    if count > 0:
        print(f"🎉 총 {count}건 처리 완료!")
    else:
        print("✅ 새로 처리할 예약이 없습니다.")

if __name__ == "__main__":
    main()