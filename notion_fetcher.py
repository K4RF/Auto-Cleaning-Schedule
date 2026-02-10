import requests
from datetime import datetime, timedelta
from config_loader import NOTION_KEY, NOTION_DB_ID, PROP_NAMES, KST
from utils import calculate_cleaning_time

def fetch_reservations(start_str, search_end_str):
    url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # API 요청 시 '예약완료' 상태인 것만 요청
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    payload = {
        "filter": {
            "and": [
                {
                    "property": PROP_NAMES["DATE"],
                    "date": {"on_or_after": today_str} 
                },
                {
                    "property": PROP_NAMES["DATE"],
                    "date": {"on_or_before": search_end_str}
                },
                {
                    "property": PROP_NAMES["STATUS"],
                    "status": {"equals": PROP_NAMES["STATUS_VALUE"]} # 예약완료
                }
            ]
        },
        "sorts": [
            {"property": PROP_NAMES["BRANCH"], "direction": "ascending"},
            {"property": PROP_NAMES["DATE"], "direction": "ascending"}
        ]
    }

    has_more = True
    next_cursor = None
    collected_list = []
    
    print(f"🔄 노션 데이터 동기화 중... (검색범위: {today_str} ~ {search_end_str})")

    while has_more:
        if next_cursor: payload["start_cursor"] = next_cursor
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200: 
            print(f"❌ 노션 API 오류: {response.status_code} {response.text}")
            break
        
        data = response.json()
        results = data.get("results", [])
        
        for page in results:
            props = page["properties"]
            
            # [1차 검증] 청소 발주 여부 'O' 확인
            # 값이 있으면(None이 아니면) -> 이미 처리된 것 -> Skip
            order_prop = props.get(PROP_NAMES["ORDER_CHECK"])
            if order_prop and "select" in order_prop and order_prop["select"] is not None:
                continue

            # [2차 검증] 날짜/시간 정보 유무
            # 시간 정보가 없는 데이터(YYYY-MM-DD 길이 10)는 제외
            date_prop = props.get(PROP_NAMES["DATE"], {}).get("date", {})
            if not date_prop: continue
            
            start_iso = date_prop.get("start")
            if not start_iso or len(start_iso) <= 10:
                continue

            # --- 데이터 파싱 ---
            
            # 지점
            branch_prop = props.get(PROP_NAMES["BRANCH"])
            branch = "미지정"
            if branch_prop and "select" in branch_prop and branch_prop["select"]:
                branch = branch_prop["select"]["name"]
            
            # 패키지 (중요: config.json에서 "이름"으로 설정했으므로 Title을 읽음)
            pkg_prop = props.get(PROP_NAMES["PACKAGE"])
            full_title = "제목없음"
            if pkg_prop and "title" in pkg_prop and pkg_prop["title"]:
                full_title = pkg_prop["title"][0]["plain_text"]
            
            # 패키지명 분류
            if "데이" in full_title: pkg_name = "데이 패키지"
            elif "올데이" in full_title: pkg_name = "올데이"
            elif "나이트" in full_title: pkg_name = "나이트 패키지"
            else: pkg_name = "시간제"

            # 날짜 변환
            try:
                dt_start = datetime.fromisoformat(start_iso)
                if dt_start.tzinfo is not None: dt_start = dt_start.astimezone(KST)
                dt_start = dt_start.replace(tzinfo=None)

                end_iso = date_prop.get("end")
                if end_iso:
                    dt_end = datetime.fromisoformat(end_iso)
                    if dt_end.tzinfo is not None: dt_end = dt_end.astimezone(KST)
                    dt_end = dt_end.replace(tzinfo=None)
                else:
                    dt_end = dt_start + timedelta(hours=3)
            except ValueError:
                continue

            cleaning_start_dt, _, duration_hours = calculate_cleaning_time(dt_start, dt_end, pkg_name)

            collected_list.append({
                "id": page["id"],
                "branch": branch,
                "pkg_name": pkg_name,
                "clean_start_dt": cleaning_start_dt,
                "check_in_dt": dt_start,
                "duration_hours": duration_hours,
                "next_booking_dt": None 
            })

        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    # 다음 예약 시간 계산
    collected_list.sort(key=lambda x: (x['branch'], x['check_in_dt']))
    for i in range(len(collected_list) - 1):
        current = collected_list[i]
        next_item = collected_list[i+1]
        if current['branch'] == next_item['branch']:
            current['next_booking_dt'] = next_item['check_in_dt']

    return collected_list