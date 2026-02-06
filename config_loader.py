# config_loader.py
import json
import os
from datetime import timezone, timedelta

# 한국 시간대(KST) 정의
KST = timezone(timedelta(hours=9))

def load_config():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ 오류: config.json 파일을 찾을 수 없습니다.")
        exit()

# 설정 로드
CONFIG = load_config()
NOTION_KEY = CONFIG["NOTION"]["API_KEY"]
NOTION_DB_ID = CONFIG["NOTION"]["DATABASE_ID"]
PROP_NAMES = CONFIG["NOTION"]["PROPERTY_NAMES"]
RULES = CONFIG["CLEANING_RULES"]
GOOGLE_JSON_KEY = CONFIG["GOOGLE"]["JSON_KEY_FILE"]
SHEET_NAME = CONFIG["GOOGLE"]["SHEET_NAME"]
SHEET_TAB_NAME = CONFIG["GOOGLE"]["SHEET_TAB_NAME"]
SHEET_ID = CONFIG["GOOGLE"].get("SHEET_ID")

# [New] 시트 열 번호 정의 (1부터 시작)
# 나중에 시트 순서가 바뀌면 이 숫자만 수정하면 됩니다.
COLS = {
    "ID": 1,          # A열
    "DATE": 3,        # C열
    "DEADLINE": 6,    # F열 (마감시간)
    "VISIT_TIME": 8,  # H열 (방문예정시간)
    "STATUS": 10,     # J열 (상태)
    "SMS_STAFF": 11,  # K열 (담당자문자)
    "SMS_MANAGER": 12, # L열 (매니저알림)
    "VALID_SLOTS": 13 # M열: 가능한시간대
}