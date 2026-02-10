import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import os
import time
import logging
from datetime import datetime

from config_loader import FIREBASE_KEY_FILE
from utils import get_this_week_range, get_manager_name, generate_valid_slots
from notion_fetcher import fetch_reservations

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', handlers=[logging.StreamHandler()])

def main():
    start_str, target_end_str, search_end_str = get_this_week_range()
    
    logging.info(f"🚀 시스템 가동: Firebase 모드")
    logging.info(f"📅 발주 대상: {start_str} ~ {target_end_str} (일요일 예약까지)")
    logging.info(f"🔍 조회 범위: {start_str} ~ {search_end_str}")

    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(base_dir, FIREBASE_KEY_FILE)
        
        if not firebase_admin._apps:
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        logging.info("🔥 Firebase 연결 성공")
        
    except Exception as e:
        logging.error(f"❌ Firebase 연결 실패: {e}")
        return

    try:
        notion_data = fetch_reservations(start_str, search_end_str)
        logging.info(f"📥 Notion 수신: {len(notion_data)}건")
    except Exception as e:
        logging.error(f"❌ Notion 데이터 가져오기 실패: {e}")
        return

    new_count = 0
    skip_count = 0
    future_count = 0
    collection_ref = db.collection("schedules")

    for current in notion_data:
        # 미래 예약(다음주) 건너뛰기
        reservation_date = current["check_in_dt"].strftime("%Y-%m-%d")
        if reservation_date > target_end_str:
            future_count += 1
            continue

        doc_id = current["id"]
        doc_ref = collection_ref.document(doc_id)
        
        if doc_ref.get().exists:
            skip_count += 1
            continue
        
        # ----------------------------------------------------
        # [데이터 가공]
        # ----------------------------------------------------
        manager_name = get_manager_name(current["branch"], current["clean_start_dt"])
        clean_date_str = current["clean_start_dt"].strftime("%Y-%m-%d")
        start_time_str = current["clean_start_dt"].strftime("%H:%M")
        
        deadline_text = "다음 예약 없음"
        if current["next_booking_dt"]:
            deadline_text = current["next_booking_dt"].strftime("%Y-%m-%d %H:%M")
        
        valid_slots_str = generate_valid_slots(
            current["clean_start_dt"], 
            current["duration_hours"], 
            current["next_booking_dt"]
        )

        save_data = {
            "notionId": doc_id,
            "branch": current["branch"],
            "date": clean_date_str,
            "pkgName": current["pkg_name"],
            
            "cleanableStartTime": start_time_str,
            "cleanableDeadline": deadline_text,
            "durationHours": current["duration_hours"],
            "visitTime": "시간 미정",
            
            "status": "발주전",
            "cleanerName": manager_name,
            "possibleSlots": valid_slots_str,
            
            "smsSentCleaner": False,
            "smsSentManager": False,
            "images": [],
            "createdAt": firestore.SERVER_TIMESTAMP
        }

        try:
            doc_ref.set(save_data)
            logging.info(f"  ✅ [신규발주] {current['branch']} | {clean_date_str} | {current['pkg_name']}")
            new_count += 1
            time.sleep(0.1) 
        except Exception as e:
            logging.error(f"❌ 저장 실패: {e}")

    logging.info(f"🎉 완료: 신규 {new_count}건 / 중복 {skip_count}건 / 제외 {future_count}건")

if __name__ == "__main__":
    main()