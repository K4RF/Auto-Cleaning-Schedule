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