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
    start_of_week = today - timedelta(days=today.weekday()) 
    end_of_week = start_of_week + timedelta(days=6)
    search_end = end_of_week + timedelta(days=2) 
    return start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d"), search_end.strftime("%Y-%m-%d")

# ==========================================
# [함수] 청소 설정 계산 (핵심 로직)
# ==========================================
def calculate_cleaning_config(check_in_dt, check_out_dt, pkg_name):
    """
    [규칙] 모든 청소는 이용객 '퇴실 후' 진행
    - 나이트: 익일 아침 08:00 시작 (2시간)
    - 데이: 당일 오후 17:00 시작 (1시간)
    - 시간제: 퇴실 직후 시작 (1시간)
    """
    check_in_date = check_in_dt.date()
    
    if "나이트" in pkg_name:
        next_day = check_in_date + timedelta(days=1)
        base_start_dt = datetime.combine(next_day, datetime.strptime("08:00", "%H:%M").time())
        duration = 2
        
    elif "데이" in pkg_name:
        base_start_dt = datetime.combine(check_in_date, datetime.strptime("17:00", "%H:%M").time())
        duration = 1
        
    else: 
        base_start_dt = check_out_dt
        duration = 1
        
        # 밤 9시(21시) 넘으면 -> 다음날 아침 8시로
        if base_start_dt.hour >= 21:
            base_start_dt = base_start_dt.replace(hour=8, minute=0) + timedelta(days=1)
        # 너무 이른 새벽(8시 전)이면 -> 아침 8시로
        elif base_start_dt.hour < 8:
            base_start_dt = base_start_dt.replace(hour=8, minute=0)

    return base_start_dt, duration

# ==========================================
# [함수] notion_fetcher 호환용 (3개 반환)
# ==========================================
def calculate_cleaning_time(check_in_dt, check_out_dt, pkg_name):
    """
    notion_fetcher.py 오류 방지용 래퍼 함수
    """
    start_dt, duration = calculate_cleaning_config(check_in_dt, check_out_dt, pkg_name)
    end_dt = start_dt + timedelta(hours=duration)
    return start_dt, end_dt, duration

# ==========================================
# [함수] 가능한 시간대 목록 생성 (9시 컷 + 1시간 간격)
# ==========================================
def generate_valid_slots(start_dt, duration_hours, next_booking_dt=None):
    slots = []
    
    # 1. 기본 마감 시간 설정 (다음 예약 or 12시간 뒤)
    if next_booking_dt:
        limit_dt = next_booking_dt
    else:
        limit_dt = start_dt + timedelta(hours=12) 

    # 2. [New] 밤 9시(21:00) 컷 로직 적용
    # "만약 9시 이전에 끝났어? 그러면 9시까지만 포함시켜줘"
    cutoff_21pm = start_dt.replace(hour=21, minute=0, second=0, microsecond=0)
    
    earliest_end_time = start_dt + timedelta(hours=duration_hours)

    # 조건: 가장 빠른 종료 시간이 21:00 이하라면 -> 마지노선을 21:00로 당김
    if earliest_end_time <= cutoff_21pm:
        if limit_dt > cutoff_21pm:
            limit_dt = cutoff_21pm

    current = start_dt
    safety_limit = start_dt + timedelta(hours=36)

    while current < safety_limit:
        clean_end = current + timedelta(hours=duration_hours)
        
        # 마감 시간을 넘으면 중단
        if clean_end > limit_dt:
            break
            
        start_str = current.strftime("%H:%M")
        end_str = clean_end.strftime("%H:%M")
        slots.append(f"{start_str} ~ {end_str}")
        
        # 1시간 간격
        current += timedelta(hours=1)
    
    if not slots:
        return "시간 협의 필요"
        
    return ", ".join(slots)