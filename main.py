# main.py
import gspread
import os
import time
import logging
from datetime import datetime
from config_loader import GOOGLE_JSON_KEY, SHEET_NAME, SHEET_TAB_NAME, SHEET_ID, COLS
from utils import get_this_week_range, get_manager_name, generate_valid_slots
from notion_fetcher import fetch_reservations

# ==========================================
# [설정] 로그 기록
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("system.log", encoding="utf-8"), 
        logging.StreamHandler()
    ]
)

def main():
    start_str, target_end_str, search_end_str = get_this_week_range()
    target_end_date = datetime.strptime(target_end_str, "%Y-%m-%d").date()

    logging.info(f"🚀 시스템 가동: [DB 보존 모드 - 삭제 기능 제거됨]")
    logging.info(f"📅 타겟 기간: {start_str} ~ {target_end_str}")

    sheet = None
    existing_data_map = {} 
    
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(base_dir, GOOGLE_JSON_KEY)
        gc = gspread.service_account(filename=key_path)
        
        if not SHEET_ID:
            sheet = gc.open(SHEET_NAME).worksheet(SHEET_TAB_NAME)
        else:
            sheet = gc.open_by_key(SHEET_ID).worksheet(SHEET_TAB_NAME)
        
        all_rows = sheet.get_all_values()
        
        for i, row in enumerate(all_rows[1:], start=2):
            if row: 
                def get_col_data(col_idx):
                    return row[col_idx - 1] if len(row) >= col_idx else ""

                r_id = get_col_data(COLS["ID"])
                
                existing_data_map[r_id] = {
                    "row_idx": i,
                    "date": get_col_data(COLS["DATE"]),
                    "deadline": get_col_data(COLS["DEADLINE"]),
                    "visit_time": get_col_data(COLS["VISIT_TIME"]),
                    "status": get_col_data(COLS["STATUS"]),
                    "sms_staff": get_col_data(COLS["SMS_STAFF"]) or "X",
                    "sms_manager": get_col_data(COLS["SMS_MANAGER"]) or "X",
                    "valid_slots": get_col_data(COLS["VALID_SLOTS"]) 
                }
    except Exception as e:
        logging.error(f"❌ 구글 시트 연결 실패: {e}")
        return

    reservations = fetch_reservations(start_str, search_end_str)
    
    if not reservations and len(existing_data_map) > 0:
        logging.warning("⚠️ [주의] 노션 예약 0건. 데이터 보호를 위해 중단합니다.")
        return

    reservations.sort(key=lambda x: x["clean_start_dt"])
    
    processed_ids = set()
    new_count = 0
    update_count = 0
    conflict_count = 0
    
    for i, current in enumerate(reservations):
        
        check_in_date = current["check_in_dt"].date()
        if check_in_date > target_end_date: continue
        if current["is_ordered"]: continue
        
        current_id_clean = current["id"].replace("-", "")
        processed_ids.add(current_id_clean)
        
        # 1. 마감 시간 및 다음 예약 계산
        deadline_text = "다음 예약 없음"
        next_time_obj = None 
        
        future_bookings = [r for r in reservations if r["id"] != current["id"] 
                           and r["branch"] == current["branch"] 
                           and r["check_in_dt"] >= current["clean_start_dt"]]
        
        future_bookings.sort(key=lambda x: x["check_in_dt"])
        
        if future_bookings:
            next_booking = future_bookings[0]
            next_time_obj = next_booking["check_in_dt"]
            
            clean_day = current["clean_start_dt"].date()
            next_day = next_time_obj.date()
            time_str = next_time_obj.strftime("%H:%M")
            date_str = next_time_obj.strftime("%m/%d")
            gap_hours = (next_time_obj - current["clean_end_dt"]).total_seconds() / 3600

            if clean_day == next_day:
                if gap_hours < 0: deadline_text = f"⚠다음 예약 {time_str} 입실 (겹침!)"
                elif gap_hours < 2: deadline_text = f"⚠다음 예약 {time_str} 입실"
                else: deadline_text = f"다음 예약 {time_str}"
            else:
                if gap_hours < 2: deadline_text = f"⚠다음 예약 {date_str} {time_str} 입실"
                else: deadline_text = f"다음 예약 {date_str} {time_str}"

        # 2. 가능한 시간대(Slots) 계산
        valid_slots_str = generate_valid_slots(
            current["clean_start_dt"], 
            current["duration_hours"], 
            next_time_obj
        )

        # ====================================================
        # [업데이트 로직]
        # ====================================================
        if current_id_clean in existing_data_map:
            existing_info = existing_data_map[current_id_clean]
            
            row_idx = existing_info["row_idx"]
            old_deadline = existing_info["deadline"]
            old_slots = existing_info["valid_slots"]
            visit_time_str = existing_info["visit_time"] 
            current_status = existing_info["status"]
            current_sms_staff = existing_info["sms_staff"]
            current_sms_manager = existing_info["sms_manager"]
            
            # [자동 보정] 방문예정시간이 비어있으면 "시간 미정"으로 채워넣기
            if not visit_time_str:
                try:
                    sheet.update_cell(row_idx, COLS["VISIT_TIME"], "시간 미정")
                    visit_time_str = "시간 미정"
                except: pass

            new_status = current_status 
            is_conflict = False
            
            # 충돌 검사
            if visit_time_str and visit_time_str != "시간 미정" and next_time_obj:
                try:
                    if "~" in visit_time_str:
                        _, end_str = visit_time_str.split("~")
                        end_str = end_str.strip() 
                        clean_date = current["clean_start_dt"].date()
                        visit_end_dt = datetime.combine(clean_date, datetime.strptime(end_str, "%H:%M").time())
                        if visit_end_dt > next_time_obj:
                            is_conflict = True
                except ValueError: pass 
            
            if is_conflict: conflict_count += 1

            need_update = False
            resend_target_staff = False  
            resend_target_manager = False
            
            is_deadline_changed = (deadline_text != old_deadline)
            is_slots_changed = (valid_slots_str != old_slots)

            if is_deadline_changed or is_slots_changed:
                if is_deadline_changed:
                    sheet.update_cell(row_idx, COLS["DEADLINE"], deadline_text)
                if is_slots_changed:
                    sheet.update_cell(row_idx, COLS["VALID_SLOTS"], valid_slots_str)
                
                time.sleep(1.0) 
                
                if is_conflict:
                    new_status = "방문시간 충돌"
                    resend_target_manager = True 
                    resend_target_staff = True 
                else:
                    new_status = "마감시간 변경"
                    resend_target_staff = True
                
                need_update = True
                if is_deadline_changed:
                    logging.info(f"  🔔[변동감지] {current['branch']} | 마감시간 변경 ({old_deadline} -> {deadline_text})")

            else:
                if is_conflict:
                    if current_status != "방문시간 충돌":
                        new_status = "방문시간 충돌"
                        need_update = True
                        resend_target_manager = True 
                        resend_target_staff = True 
                
                else:
                    if visit_time_str != "시간 미정" and current_status == "발주전":
                        new_status = "발주완료"
                        need_update = True
                        logging.info(f"  ✅ [발주확정] {current['branch']} | 시간 선택 완료 -> 발주완료")
                    elif visit_time_str != "시간 미정" and current_status == "방문시간 충돌":
                        new_status = "발주완료"
                        need_update = True
                        logging.info(f"  ♻️ [충돌해결] {current['branch']} | 시간 수정됨 -> 발주완료 복구")

            if need_update and new_status != current_status:
                try:
                    sheet.update_cell(row_idx, COLS["STATUS"], new_status)
                    time.sleep(1.0)
                    update_count += 1
                except Exception as e:
                    logging.error(f"  ❌ 상태 업데이트 실패: {e}")

            if resend_target_staff and current_sms_staff == "O":
                try:
                    sheet.update_cell(row_idx, COLS["SMS_STAFF"], "X")
                    time.sleep(1.0)
                except: pass
            
            if resend_target_manager and current_sms_manager == "O":
                try:
                    sheet.update_cell(row_idx, COLS["SMS_MANAGER"], "X") 
                    time.sleep(1.0)
                except: pass
            
            continue

        # ====================================================
        # [신규 등록]
        # ====================================================
        manager_name = get_manager_name(current["branch"], current["clean_start_dt"])
        t_start = current["clean_start_dt"].strftime("%H:%M")
        duration = str(current["duration_hours"]) 
        clean_date_str = current["clean_start_dt"].strftime("%Y-%m-%d")

        row = [
            current_id_clean, current["branch"], clean_date_str, current["pkg_name"],
            t_start, deadline_text, duration, "시간 미정", manager_name, "발주전", 
            "X", "X", valid_slots_str 
        ]

        try:
            sheet.append_row(row)
            time.sleep(1.0) 
            logging.info(f"  ✅ [신규] {current['branch']} {clean_date_str} | 옵션: {valid_slots_str}")
            new_count += 1
        except Exception as e:
            logging.error(f"  ❌ 업로드 실패: {e}")

    # [삭제 로직 제거됨] - DB 보존 모드
    
    logging.info("-" * 50)
    logging.info(f"🎉 결과: 신규 {new_count} / 변경 {update_count} / 충돌 {conflict_count} / 삭제 0 ")

if __name__ == "__main__":
    main()