import requests
import json
import os
from config_loader import NOTION_KEY, PROP_NAMES

# 문제가 된 예약의 ID (사장님 로그에서 복사함)
TARGET_PAGE_ID = "3011b1ca-2919-8182-b65b-eefa8b27ea2d"

def inspect_specific_page():
    print(f"🕵️‍♂️ 문제의 예약({TARGET_PAGE_ID}) 정밀 분석 중...")
    
    url = f"https://api.notion.com/v1/pages/{TARGET_PAGE_ID}"
    headers = {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ 페이지 조회 실패: {response.status_code}")
        print(response.text)
        return

    data = response.json()
    props = data["properties"]
    
    # 1. 청소 발주 여부 확인
    target_col = PROP_NAMES["ORDER_CHECK"]
    print(f"\n1. ['{target_col}'] 컬럼 분석")
    
    if target_col not in props:
        print(f"   🚨 치명적 오류: 이 페이지에는 '{target_col}'라는 속성이 아예 없습니다!")
        print(f"   👉 가능한 속성 목록: {list(props.keys())}")
    else:
        val = props[target_col]
        print(f"   📄 Raw Data: {json.dumps(val, ensure_ascii=False)}")
        
        if "select" in val:
            if val["select"] is None:
                print("   ❌ 결과: '비어있음(None)'으로 확인됨 -> 그래서 가져온 것임!")
            else:
                print(f"   ✅ 결과: '{val['select']['name']}' 선택됨 -> (정상이라면 안 가져와야 함)")
        else:
            print(f"   ❓ 결과: Select 타입이 아님 ({val['type']})")

    # 2. 패키지 이름 확인 (중요)
    print(f"\n2. 패키지 이름 확인")
    pkg_col = PROP_NAMES["PACKAGE"]
    if pkg_col in props:
        print(f"   설정된 컬럼명: {pkg_col}")
        print(f"   📄 Raw Data: {json.dumps(props[pkg_col], ensure_ascii=False)}")
    else:
         print(f"   ⚠️ 설정된 패키지 컬럼('{pkg_col}')을 찾을 수 없음")

if __name__ == "__main__":
    inspect_specific_page()