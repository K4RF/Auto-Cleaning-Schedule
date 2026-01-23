# utils.py
from datetime import date, timedelta
from config_loader import KST

# ==========================================
# [함수] 담당자 자동 배정 규칙
# ==========================================
def get_manager_name(branch, clean_dt):
    day_index = clean_dt.weekday() # 0:월 ~ 6:일
    
    if branch in ["천호점", "군자점"]: return "김영미"
    elif branch == "건대점": return "강상윤"
    elif branch == "왕십리점": return "이수연"
    elif branch == "선릉점":
        # 금(4), 토(5), 일(6) -> 이인욱
        return "이인욱" if day_index >= 4 else "김진욱"
    elif branch == "강남점": return "손섭준" 
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
# [함수] 청소 시간 계산 로직
# ==========================================
def calculate_cleaning_time(dt_start, dt_end, pkg_name):
    cleaning_start_dt = None
    cleaning_end_dt = None
    clean_duration_hours = 0 
    
    if "나이트" in pkg_name:
        cleaning_start_dt = dt_start.replace(hour=8, minute=0) + timedelta(days=1)
        clean_duration_hours = 2
        cleaning_end_dt = cleaning_start_dt + timedelta(hours=clean_duration_hours)
        
    elif "데이" in pkg_name:
        cleaning_start_dt = dt_start.replace(hour=17, minute=0)
        clean_duration_hours = 1
        cleaning_end_dt = cleaning_start_dt + timedelta(hours=clean_duration_hours)
        
    else: 
        # 시간제 / 올데이
        cleaning_start_dt = dt_end
        
        # 심야/새벽 방어 로직
        if cleaning_start_dt.hour >= 21:
                cleaning_start_dt = cleaning_start_dt.replace(hour=8, minute=0) + timedelta(days=1)
        elif cleaning_start_dt.hour < 8:
                cleaning_start_dt = cleaning_start_dt.replace(hour=8, minute=0)
        
        clean_duration_hours = 1 
        cleaning_end_dt = cleaning_start_dt + timedelta(hours=clean_duration_hours)

    return cleaning_start_dt, cleaning_end_dt, clean_duration_hours