import gspread
import os
from datetime import datetime, timedelta
from config_loader import GOOGLE_JSON_KEY, SHEET_NAME, SHEET_TAB_NAME, SHEET_ID
from utils import get_this_week_range, get_manager_name
from notion_fetcher import fetch_reservations

def main():
    start_str, target_end_str, search_end_str = get_this_week_range()
    target_end_date = datetime.strptime(target_end_str, "%Y-%m-%d").date()

    print(f"🚀 시스템 가동: [충돌 시 담당자/매니저 모두 알림]")
    print(f"📅 타겟 기간: {start_str} ~ {target_end_str}")

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
                r_id = row[0]
                r_date = row[2] 
                r_deadline = row[5] if len(row) > 5 else "" 
                r_visit_time = row[7] if len(row) > 7 else ""
                r_status = row[9] if len(row) > 9 else "" 
                r_sms_staff = row[10] if len(row) > 10 else "X" 
                r_sms_manager = row[11] if len(row) > 11 else "X"
                
                existing_data_map[r_id] = {
                    "row_idx": i,
                    "date": r_date,
                    "deadline": r_deadline,
                    "visit_time": r_visit_time,
                    "status": r_status,
                    "sms_staff": r_sms_staff,
                    "sms_manager": r_sms_manager
                }
    except Exception as e:
        print(f"❌ 구글 시트 연결 실패: {e}")
        return

    reservations = fetch_reservations(start_str, search_end_str)
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
        
        # 다음 예약 계산
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

        # ====================================================
        # [핵심 로직]
        # ====================================================
        if current_id_clean in existing_data_map:
            existing_info = existing_data_map[current_id_clean]
            old_deadline = existing_info["deadline"]
            visit_time_str = existing_info["visit_time"] 
            current_status = existing_info["status"]
            current_sms_staff = existing_info["sms_staff"]
            current_sms_manager = existing_info["sms_manager"]
            
            row_idx = existing_info["row_idx"]
            new_status = current_status 
            is_conflict = False
            
            # 1. 충돌 검사
            if visit_time_str and next_time_obj:
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

            # 2. 상태 결정 & 알림 타겟 설정
            need_update = False
            
            resend_target_staff = False   # K열 리셋 여부
            resend_target_manager = False # L열 리셋 여부
            
            # Case A: 마감시간 변경
            if deadline_text != old_deadline:
                sheet.update_cell(row_idx, 6, deadline_text) 
                
                if is_conflict:
                    new_status = "🚨방문충돌"
                    resend_target_manager = True 
                    resend_target_staff = True # [수정] 충돌 시에도 담당자 알림 (시간 다시 잡으라고)
                else:
                    new_status = "🔔마감변경"
                    resend_target_staff = True
                
                need_update = True
                print(f"  🔔 [변동감지] {current['branch']} | {old_deadline} -> {deadline_text} (상태:{new_status})")

            # Case B: 마감시간 유지됨
            else:
                if is_conflict:
                    # 기존에 충돌 아니었는데 새로 충돌남
                    if current_status != "🚨방문충돌":
                        new_status = "🚨방문충돌"
                        need_update = True
                        resend_target_manager = True 
                        resend_target_staff = True # [수정] 충돌 발생 알림
                
                else: # 정상
                    if visit_time_str and current_status == "대기":
                        new_status = "발주완료"
                        need_update = True
                        print(f"  ✅ [발주확정] {current['branch']} | 시간 선택 완료 -> 발주완료")
                    
                    elif visit_time_str and current_status == "🚨방문충돌":
                        new_status = "발주완료"
                        need_update = True
                        print(f"  ♻️ [충돌해결] {current['branch']} | 시간 수정됨 -> 발주완료 복구")

            # 3. 변경사항 시트 반영
            if need_update and new_status != current_status:
                try:
                    sheet.update_cell(row_idx, 10, new_status)
                    update_count += 1
                except Exception as e:
                    print(f"  ❌ 상태 업데이트 실패: {e}")

            # 4. 알림 채널별 리셋
            # 담당자용 (K열)
            if resend_target_staff and current_sms_staff == "O":
                try:
                    sheet.update_cell(row_idx, 11, "X")
                    print(f"  📨 [담당자알림] {current['branch']} | 재발송 대기")
                except: pass
            
            # 매니저용 (L열)
            if resend_target_manager and current_sms_manager == "O":
                try:
                    sheet.update_cell(row_idx, 12, "X") 
                    print(f"  🚨 [매니저호출] {current['branch']} | 재발송 대기")
                except: pass
            
            continue

        # 신규 등록
        manager_name = get_manager_name(current["branch"], current["clean_start_dt"])
        t_start = current["clean_start_dt"].strftime("%H:%M")
        duration = str(current["duration_hours"]) 
        clean_date_str = current["clean_start_dt"].strftime("%Y-%m-%d")

        row = [
            current_id_clean, current["branch"], clean_date_str, current["pkg_name"],
            t_start, deadline_text, duration, "", manager_name, "대기", 
            "X", "X" 
        ]

        try:
            sheet.append_row(row)
            print(f"  ✅ [신규] {current['branch']} | {clean_date_str} {t_start} | {deadline_text}")
            new_count += 1
        except Exception as e:
            print(f"  ❌ 업로드 실패: {e}")

    # 삭제 로직
    rows_to_delete = []
    for sheet_id, info in existing_data_map.items():
        try:
            row_date = info["date"]
            if start_str <= row_date <= target_end_str:
                if sheet_id not in processed_ids:
                    rows_to_delete.append(info["row_idx"])
        except: continue

    rows_to_delete.sort(reverse=True)
    for row_idx in rows_to_delete:
        try:
            sheet.delete_rows(row_idx)
            print(f"  🗑️ [삭제] 예약 취소됨 (Row {row_idx})")
        except Exception as e:
            print(f"  ❌ 삭제 실패: {e}")

    print("-" * 50)
    print(f"🎉 결과: 신규 {new_count} / 변경 {update_count} / 삭제 {len(rows_to_delete)} / 충돌 {conflict_count}")

if __name__ == "__main__":
    main()