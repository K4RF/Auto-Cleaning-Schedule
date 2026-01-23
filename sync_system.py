import json
import requests
import gspread
import os
import traceback
from datetime import datetime, timedelta, date, timezone

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

# 한국 시간대(KST) 정의
KST = timezone(timedelta(hours=9))

# ==========================================
# [함수] 담당자 자동 배정 (선릉점 규칙 업데이트)
# ==========================================
def get_manager_name(branch, clean_dt):
    """
    지점과 청소 날짜(요일)를 기준으로 담당자를 자동으로 결정합니다.
    clean_dt: datetime 객체 (청소 시작 시간)
    """
    # 0:월, 1:화, 2:수, 3:목, 4:금, 5:토, 6:일
    day_index = clean_dt.weekday() 
    
    if branch in ["천호점", "군자점"]:
        return "김영미"
    
    elif branch == "건대점":
        return "강상윤"
        
    elif branch == "왕십리점":
        return "이수연"
        
    elif branch == "선릉점":
        # [수정됨] 금(4), 토(5), 일(6) -> 이인욱님
        if day_index >= 4:
            return "이인욱"
        # 월(0) ~ 목(3) -> 김진욱님
        else:
            return "김진욱"
            
    elif branch == "강남점":
        return "손섭준" 
        
    return "" # 그 외 지점은 빈칸

# ==========================================
# [함수] 날짜 범위 계산
# ==========================================
def get_this_week_range():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) 
    end_of_week = start_of_week + timedelta(days=6)
    search_end = end_of_week + timedelta(days=2) 
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d"), search_end.strftime("%Y-%m-%d")

# ==========================================
# [2] 데이터 수집
# ==========================================
def fetch_reservations(start_str, search_end_str):
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

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

    print("🔄 스케줄 정밀 분석 중... ")

    while has_more and not stop_search:
        if next_cursor: payload["start_cursor"] = next_cursor
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200: break
            
        data = response.json()
        results = data.get("results", [])
        
        for page in results:
            props = page["properties"]
            
            if not (props.get(PROP_NAMES["DATE"]) and props[PROP_NAMES["DATE"]]["date"]):
                continue

            date_data = props[PROP_NAMES["DATE"]]["date"]
            start_iso = date_data["start"]
            end_iso = date_data.get("end")
            r_date_str = start_iso.split("T")[0]

            # 1차 필터
            if r_date_str > search_end_str: continue 
            if r_date_str < start_str: 
                stop_search = True
                break

            # 데이터 추출
            is_ordered = False
            target_prop = props.get(PROP_NAMES["ORDER_CHECK"])
            if target_prop and target_prop["type"] == "select" and target_prop["select"]:
                is_ordered = True
            
            branch = ""
            if props.get(PROP_NAMES["BRANCH"]) and props[PROP_NAMES["BRANCH"]]["select"]:
                branch = props[PROP_NAMES["BRANCH"]]["select"]["name"]

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

            # 🕒 시간 계산 (KST 변환 필수)
            try:
                dt_start = datetime.fromisoformat(start_iso)
                if dt_start.tzinfo is not None:
                    dt_start = dt_start.astimezone(KST)
                dt_start = dt_start.replace(tzinfo=None)

                if end_iso:
                    dt_end = datetime.fromisoformat(end_iso)
                    if dt_end.tzinfo is not None:
                        dt_end = dt_end.astimezone(KST)
                    dt_end = dt_end.replace(tzinfo=None)
                else:
                    dt_end = dt_start + timedelta(hours=3)
            except ValueError:
                dt_start = datetime.strptime(start_iso, "%Y-%m-%d")
                dt_end = dt_start

            cleaning_start_dt = None
            cleaning_end_dt = None
            
            if "나이트" in pkg_name:
                cleaning_start_dt = dt_start.replace(hour=8, minute=0) + timedelta(days=1)
                cleaning_end_dt = cleaning_start_dt + timedelta(hours=2)
            elif "데이" in pkg_name:
                cleaning_start_dt = dt_start.replace(hour=17, minute=0)
                cleaning_end_dt = cleaning_start_dt + timedelta(hours=1)
            else: 
                # [시간제/올데이]
                cleaning_start_dt = dt_end
                
                # 심야/새벽 방어 로직 (KST 기준)
                if cleaning_start_dt.hour >= 21:
                     cleaning_start_dt = cleaning_start_dt.replace(hour=8, minute=0) + timedelta(days=1)
                elif cleaning_start_dt.hour < 8:
                     cleaning_start_dt = cleaning_start_dt.replace(hour=8, minute=0)
                
                clean_duration = 1 
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
    start_str, target_end_str, search_end_str = get_this_week_range()
    target_end_date = datetime.strptime(target_end_str, "%Y-%m-%d").date()

    print(f"🚀 시스템 가동: [청소 담당자 반영]")
    print(f"📅 타겟 기간: {start_str} ~ {target_end_str}")

    sheet = None
    existing_ids = set()
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(base_dir, CONFIG["GOOGLE"]["JSON_KEY_FILE"])
        gc = gspread.service_account(filename=key_path)
        
        sheet_id = CONFIG["GOOGLE"].get("SHEET_ID")
        if not sheet_id:
            sheet = gc.open(CONFIG["GOOGLE"]["SHEET_NAME"]).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
        else:
            sheet = gc.open_by_key(sheet_id).worksheet(CONFIG["GOOGLE"]["SHEET_TAB_NAME"])
            
        existing_ids = set(sheet.col_values(1))
    except Exception:
        print("❌ 구글 시트 연결 실패!")
        return

    reservations = fetch_reservations(start_str, search_end_str)
    reservations.sort(key=lambda x: x["clean_start_dt"])
    
    count = 0
    
    for i, current in enumerate(reservations):
        
        # 날짜 필터
        check_in_date = current["check_in_dt"].date()
        if check_in_date > target_end_date: continue

        if current["is_ordered"]: continue
        
        current_id_clean = current["id"].replace("-", "")
        if current_id_clean in existing_ids: continue
            
        # 다음 예약 확인
        deadline_text = "다음 예약 없음"
        future_bookings = []
        for other in reservations:
            if current["id"] == other["id"]: continue
            if current["branch"] != other["branch"]: continue
            if other["check_in_dt"] >= current["clean_start_dt"]:
                future_bookings.append(other)
        
        future_bookings.sort(key=lambda x: x["check_in_dt"])
        
        if future_bookings:
            next_booking = future_bookings[0]
            next_time = next_booking["check_in_dt"]
            
            clean_day = current["clean_start_dt"].date()
            next_day = next_time.date()
            time_str = next_time.strftime("%H:%M")
            date_str = next_time.strftime("%m/%d")
            
            gap_hours = (next_time - current["clean_end_dt"]).total_seconds() / 3600

            if clean_day == next_day:
                if gap_hours < 0: deadline_text = f"⚠다음 예약 {time_str} 입실 (겹침!)"
                elif gap_hours < 2: deadline_text = f"⚠다음 예약 {time_str} 입실"
                else: deadline_text = f"다음 예약 {time_str}"
            else:
                if gap_hours < 2: deadline_text = f"⚠다음 예약 {date_str} {time_str} 입실"
                else: deadline_text = f"다음 예약 {date_str} {time_str}"

        # 담당자 배정
        manager_name = get_manager_name(current["branch"], current["clean_start_dt"])

        t_start = current["clean_start_dt"].strftime("%H:%M")
        duration_sec = (current["clean_end_dt"] - current["clean_start_dt"]).total_seconds()
        duration = str(int(duration_sec / 3600))
        clean_date_str = current["clean_start_dt"].strftime("%Y-%m-%d")

        row = [
            current_id_clean, current["branch"], clean_date_str, current["pkg_name"],
            t_start, deadline_text, duration, "", manager_name, "대기", "X"
        ]

        try:
            sheet.append_row(row)
            print(f"  ✅ [등록] {current['branch']} | {clean_date_str} {t_start} | 담당: {manager_name}")
            count += 1
        except Exception as e:
            print(f"  ❌ 업로드 실패: {e}")

    if count > 0:
        print(f"🎉 총 {count}건 처리 완료!")
    else:
        print("✅ 새로 추가할 예약이 없습니다.")

if __name__ == "__main__":
    main()