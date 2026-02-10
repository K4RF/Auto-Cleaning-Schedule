# utils.py
from datetime import date, timedelta, datetime
from config_loader import KST

# ==========================================
# [함수] 담당자 자동 배정 규칙
# ==========================================
def get_manager_name(branch, clean_dt):
    day_index = clean_dt.weekday() # 0:월 ~ 6:일
    
    if branch in ["천호점", "군자점"]: 
        return "김영미"
    elif branch == "건대점": 
        return "강상윤"
    elif branch == "왕십리점": 
        return "이수연"
    elif branch == "선릉점":
        return "이인욱" if day_index >= 4 else "김진욱"
    elif branch == "강남점": 
        return "손섭준" 
    
    return "" 

# ==========================================
# [함수] 이번 주 범위 계산
# ==========================================
def get_this_week_range():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) # 월요일
    end_of_week = start_of_week + timedelta(days=6)       # 일요일
    
    # [수정] 다음 예약 확인을 위해 다음 주 화요일(+2일)까지 넉넉히 조회
    search_end = end_of_week + timedelta(days=2) 
    
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d"), search_end.strftime("%Y-%m-%d")

# ==========================================
# [함수] 청소 설정 계산 (사장님 규칙 적용)
# ==========================================
def calculate_cleaning_config(check_in_dt, check_out_dt, pkg_name):
    check_in_date = check_in_dt.date()
    duration = 1
    base_start_dt = check_out_dt

    # 1. 나이트 패키지 (19:00 ~ 익일 08:00 예약)
    # -> 청소: 다음 날 아침 08:00 시작 / 2시간 소요
    if "나이트" in pkg_name:
        next_day = check_in_date + timedelta(days=1)
        base_start_dt = datetime.combine(next_day, datetime.strptime("08:00", "%H:%M").time())
        duration = 2
        
    # 2. 데이 패키지 (10:00 ~ 17:00 예약)
    # -> 청소: 당일 17:00 시작 / 1시간 소요
    elif "데이" in pkg_name:
        base_start_dt = datetime.combine(check_in_date, datetime.strptime("17:00", "%H:%M").time())
        duration = 1
        
    # 3. 시간제 (퇴실 직후)
    else: 
        duration = 1
        # [규칙] 밤 21시(09:00 PM) 이후 종료라면 -> 다음 날 아침 08:00로 이동
        if base_start_dt.hour >= 21:
            base_start_dt = base_start_dt.replace(hour=8, minute=0) + timedelta(days=1)
            
        # (혹시나 새벽 0~7시에 끝나는 경우도 아침 8시로)
        elif base_start_dt.hour < 8:
            base_start_dt = base_start_dt.replace(hour=8, minute=0)

    return base_start_dt, duration

# ==========================================
# [함수] notion_fetcher 호환용 래퍼
# ==========================================
def calculate_cleaning_time(check_in_dt, check_out_dt, pkg_name):
    start_dt, duration = calculate_cleaning_config(check_in_dt, check_out_dt, pkg_name)
    end_dt = start_dt + timedelta(hours=duration)
    return start_dt, end_dt, duration

# ==========================================
# [함수] 가능한 시간대 목록 생성
# ==========================================
def generate_valid_slots(start_dt, duration_hours, next_booking_dt=None):
    slots = []
    
    # 마감 시간 설정
    if next_booking_dt:
        limit_dt = next_booking_dt
    else:
        limit_dt = start_dt + timedelta(hours=12)

    # 밤 9시 컷 로직
    cutoff_21pm = start_dt.replace(hour=21, minute=0, second=0, microsecond=0)
    
    earliest_end = start_dt + timedelta(hours=duration_hours)
    if earliest_end <= cutoff_21pm:
        if limit_dt > cutoff_21pm:
            limit_dt = cutoff_21pm

    # 슬롯 생성 (1시간 단위)
    current = start_dt
    safety_limit = start_dt + timedelta(hours=36)

    while current < safety_limit:
        clean_end = current + timedelta(hours=duration_hours)
        
        if clean_end > limit_dt:
            break
            
        start_str = current.strftime("%H:%M")
        end_str = clean_end.strftime("%H:%M")
        
        slots.append(f"{start_str} ~ {end_str}")
        
        current += timedelta(hours=1)
    
    if not slots:
        return "시간 협의 필요"
        
    return ", ".join(slots)