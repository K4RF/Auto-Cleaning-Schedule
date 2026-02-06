# notion_fetcher.py
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

    payload = {
        "filter": {
            "property": PROP_NAMES["STATUS"],
            "status": {"equals": PROP_NAMES["STATUS_VALUE"]}
        },
        "sorts": [{"property": PROP_NAMES["DATE"], "direction": "descending"}]
    }

    has_more = True
    next_cursor = None
    collected_list = []
    stop_search = False

    print("🔄 노션 데이터 동기화 중...")

    while has_more and not stop_search:
        if next_cursor: payload["start_cursor"] = next_cursor
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200: 
            print(f"❌ 노션 API 오류: {response.status_code}")
            break
            
        data = response.json()
        results = data.get("results", [])
        
        for page in results:
            props = page["properties"]
            if not (props.get(PROP_NAMES["DATE"]) and props[PROP_NAMES["DATE"]]["date"]): continue

            date_data = props[PROP_NAMES["DATE"]]["date"]
            start_iso = date_data["start"]
            end_iso = date_data.get("end")
            r_date_str = start_iso.split("T")[0]

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

            # 시간 계산 (KST 변환)
            try:
                dt_start = datetime.fromisoformat(start_iso)
                if dt_start.tzinfo is not None: dt_start = dt_start.astimezone(KST)
                dt_start = dt_start.replace(tzinfo=None)

                if end_iso:
                    dt_end = datetime.fromisoformat(end_iso)
                    if dt_end.tzinfo is not None: dt_end = dt_end.astimezone(KST)
                    dt_end = dt_end.replace(tzinfo=None)
                else:
                    dt_end = dt_start + timedelta(hours=3)
            except ValueError:
                dt_start = datetime.strptime(start_iso, "%Y-%m-%d")
                dt_end = dt_start

            # 청소 시간 계산 (utils 함수 사용)
            cleaning_start_dt, cleaning_end_dt, duration_hours = calculate_cleaning_time(dt_start, dt_end, pkg_name)

            collected_list.append({
                "id": page["id"],
                "branch": branch,
                "pkg_name": pkg_name,
                "is_ordered": is_ordered,
                "check_in_dt": dt_start,   
                "clean_start_dt": cleaning_start_dt, 
                "clean_end_dt": cleaning_end_dt,
                "duration_hours": duration_hours
            })

        has_more = data.get("has_more")
        next_cursor = data.get("next_cursor")

    return collected_list