import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BASE_DIR / "tools"
OUT_FILE = BASE_DIR / "tools-manifest.json"

ICON_BY_NAME = {
    "메모장": "⏰",
    "등급 확인": "🎖️",
    "URL 인코딩_디코딩": "🔗",
    "네이버 키워드 조합기": "🔑",
    "키워드 쉼표 병합기": "⚡",
    "플레이스 단가 계산기": "💰",
    "플레이스 주소 정리": "🔧",
    "엑셀 시트 분리": "🗂️",
    "자동완성 체크": "✅",
    "10위 이내 키워드": "🔍",
    "미션 진행 상황판": "📒",
    "업체별 수량 관리": "📚",
    "업무 관련 URL": "📍",
    "블로그 태그 검색": "🏷️",
    "진행중 중복 체크": "💻",
    "영업점 순위 비교": "📊",
}

LABEL_BY_NAME = {
    "엑셀 시트 분리": "엑셀 시트 분리 도구",
}


def build_manifest():
    items = []
    for p in sorted(TOOLS_DIR.glob("*.html"), key=lambda x: x.name):
        name = p.stem
        icon = ICON_BY_NAME.get(name, "🧰")
        label_name = LABEL_BY_NAME.get(name, name)
        items.append(
            {
                "file": f"tools/{p.name}",
                "label": f"{icon} {label_name}",
            }
        )
    return items


if __name__ == "__main__":
    manifest = build_manifest()
    OUT_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {OUT_FILE}")
