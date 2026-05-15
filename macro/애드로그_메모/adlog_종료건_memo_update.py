"""
ADLOG - 메모 '1test' → 'test' 자동 변경 (최적화 + 전체 행 처리)
========================================
실행 방법: python adlog_memo_update.py
필요 패키지:
    pip install playwright gspread google-auth
    playwright install chromium

최적화 포인트:
  - time.sleep() 제거 → wait_for_selector / expect 로 대체
  - 검색 select 옵션은 첫 번째만 설정, 이후 생략
  - 메모 열 텍스트 미리 확인 → 1test 없으면 모달 자체를 안 열기
  - networkidle → domcontentloaded 로 교체 (훨씬 빠름)
  - ★ 수정: 검색 결과의 첫 번째 행뿐 아니라 모든 행을 처리
"""

import os
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ============================================================
#  설정 영역 - 여기만 수정하세요
# ============================================================
CONFIG = {
    "url":      "https://adlog.kr/bbs/login.php?url=%2Fadlog%2F",
    "id":       "higherad",
    "password": "higherad1105!",
    "headless": False,
}

SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "higherad-b9d62",
    "private_key_id": "c97cf06c4ea8c5b5cf0e5800bd55e1817da03663",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDziNhBf9nN8alK\n9W39n7g4JCKG6pi9/9Bc52mCcqcrgG2GBUuUtgSX5nSe23jJnU/V67P+bZcNr3Cu\nnMoyxPEj9iucfHhxcWDbINBFUa8wjWuOKiZagP3fBTg9WKeoW+L+Z3gbP84KPDOx\nYJUONeER8Co8O3IiI3IxxGo9uP6t2zyYO8mCUIo68uI7pyV49suyyTYWz1LBDoEy\nLCeKVFtVPmiBZoGso3Vx1U96gQqIFdqNrmRTbrk8/sC0GpUOzYBFVWc37uDWeCVc\nwE95S0UfxwhoaqyGt93HFEzlyq1HdmjBdx3R3/EhKbr7AnOi8fzat8BqmSU0J8eT\nrQkUlSv5AgMBAAECggEASpZW5Xiq1JB3MSYKEeuhGFC44mlnbomy30Fg5zsGSCSF\nZs6oX1t//KXwgdbmH5m2oeYWso4N/XsGH/SVWQdIc6MpqDvXB6eZ6oMaRqDF7zDh\nCCGQrZdkKbIHj4JflwjNdO1rs6zPBgN6MZFLFZca38uWo+vxANOqXeOyRkUqe0RZ\nTNQ77NIbjRex+Au02n33SwzA9C7nEuaaQXcK09M0/PjHpqxYkDfDYSxXTqAM8ezJ\niJaiGdRmlLdDAdf4384HZllRYCs1PXgpJh8fbnkiQs0tzq8pzqCMlN89G9FzRF/3\nDIGpEG/K+/WrCtYv3U+aQBlS0ntARwoY2B7b8cXQoQKBgQD8/veJzNpwnVlxHHjs\nSGI6JWPKpBFmNOs2HFl7pD261qfglku7h4rwmceleEmgNZNd+YRZCrtQfKSKfIww\nVeiGhZQAjDvhgUjVIOgao0Uy4VkNIffFbiBQIpCm8MfdHedf0CV6u/W3XnLlIkrP\nhzpPvewXdiNpSTGkcsdy/lyKGwKBgQD2bR4uWY4SsAag+np7OlbrBaQeZs5PSsO5\nlfWdK2TGCkyZrdWA6JYTRQcgvKNsIjnltLXlhqddNRr0fm5SDZh2EjBQaJrzYuPt\ny0yOCxLQ5IvEbzLR5sUe+FYdznYFCwJ+BOZugxQ4LqgNpujjbQtZPtQxhzUct7X1\nzDamgYmDewKBgQCZXjNPnRja5fhfooQHsQWi/CGXqYhGrlPcdKkmU/V7+z6/3jzA\nzTVED+VAgUAY2AGjGWzK0b+l1jmlHkWZ06pnSjjjcB+o38f4M7+gzlNXudZTKMFc\nNRtvmNSZ7yMp/0PRCIx/78vQQnhiQTyau/50cszZmCt1WwK2D0Krilks+wKBgCOt\nCIGNVZQ/B7amjLTqbUr5NhlwqM2x9UQZAcYPUjeZph1ZnV9cTN3dUHrc1IwDKH6o\n+uyP4gsMdSqQY0hdz4TIfVYmzsgNuRHkLOEjmUXE0LdPofvhfQhOy6jlCxEP1vyH\nmRTGxVac6pePYogKcWoqPm4tNPNDZYSAXCke99mhAoGBAOpZCW/ug+D0la8enX5+\nJs8O7UBH0xAa6XmR1MhfaHZtZJuYxHXFoVTs8LDWVO8+DYbcGrYcM2GKbqaFsvMo\nn3TJV15cxLgyc671btqx+5MCNIvG2rkSymkEX9cEmSY9Osk2+McQqNZvv80xnVxJ\n/FAMml7/9NT9oZOII1eY1B8k\n-----END PRIVATE KEY-----\n",
    "client_email": "higherad-sheets@higherad-b9d62.iam.gserviceaccount.com",
    "client_id": "114348474204615774567",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/higherad-sheets%40higherad-b9d62.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com",
}

SHEET = {
    "spreadsheet_id": "14j9wwFedE-kwAebFSnBWjgCYcoCUW2L0hDdBmtGqAf8",
    "sheet_name":     "종료리스트",
    "mid_col":        1,   # B열 = 인덱스 1 (0-based)
    "data_start_row": 1,   # 헤더 제외
}

REPLACE_FROM = "1test"
REPLACE_TO   = "end"
# ============================================================


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")



def get_mid_list():
    log("구글 시트에서 MID 목록 읽는 중...")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=scopes)
    gc = gspread.authorize(creds)
    worksheet = gc.open_by_key(SHEET["spreadsheet_id"]).worksheet(SHEET["sheet_name"])

    mid_list = []
    for row in worksheet.get_all_values()[SHEET["data_start_row"]:]:
        if len(row) > SHEET["mid_col"]:
            val = str(row[SHEET["mid_col"]]).strip()
            if val and val != "MID":
                mid_list.append(val)

    log(f"MID {len(mid_list)}개 로드 완료")
    return mid_list


def process_row(page, row, row_num, mid):
    """
    단일 행(tr)에 대해 메모 확인 → 필요시 수정 후 저장.
    반환값: "updated" | "skipped" | "error"
    """
    try:
        # ── 메모 셀 텍스트 미리 확인 (모달 열기 전 빠른 체크) ──
        row_class = row.get_attribute("class") or ""
        base_class = row_class.split()[0]  # e.g. "api_rows_2436650"

        memo_cell_text = ""
        try:
            memo_cell_text = page.locator(
                f"tr[class*='{base_class}'] td.pr.vat.blur_disp"
            ).first.inner_text(timeout=2_000)
        except Exception:
            memo_cell_text = ""

        if REPLACE_FROM not in memo_cell_text:
            log(f"    행 {row_num}: 메모에 '{REPLACE_FROM}' 없음, 건너뜀")
            return "skipped"

        # ── 메모 버튼 클릭 → 모달 열기 ──
        memo_btn = row.locator("button.btn01.btn_memo_modify_form").first
        memo_btn.click()
        page.wait_for_selector("textarea", state="visible", timeout=6_000)

        memo_ta = page.locator("textarea").first
        current_text = memo_ta.input_value()

        if REPLACE_FROM not in current_text:
            log(f"    행 {row_num}: 모달 메모에 '{REPLACE_FROM}' 없음, 닫기")
            page.mouse.click(10, 10)
            return "skipped"

        # ── 치환 & 저장 ──
        new_text = current_text.replace(REPLACE_FROM, REPLACE_TO)
        memo_ta.fill(new_text)
        page.locator("button.btn02.btn_memo_modify").first.click()
        page.wait_for_load_state("domcontentloaded")
        log(f"    행 {row_num}: 저장 완료 ({repr(current_text)} → {repr(new_text)})")
        return "updated"

    except PlaywrightTimeout as e:
        log(f"    행 {row_num}: ⚠ 타임아웃: {e}")
        return "error"
    except Exception as e:
        log(f"    행 {row_num}: ⚠ 오류: {e}")
        return "error"


def run():
    mid_list = get_mid_list()
    if not mid_list:
        log("MID 목록이 비어있습니다. 종료합니다.")
        return

    results = {"updated": [], "skipped": [], "no_row": [], "error": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=CONFIG["headless"])
        page = browser.new_context().new_page()

        # ── 1. 로그인 ──────────────────────────────────────
        log("로그인 중...")
        page.goto(CONFIG["url"], wait_until="domcontentloaded")
        page.wait_for_selector("#login_id", state="visible", timeout=10_000)
        page.locator("#login_id").fill(CONFIG["id"])
        page.locator("input[type='password']").fill(CONFIG["password"])
        page.locator("button[type='submit']").click()
        page.wait_for_load_state("domcontentloaded")
        log("로그인 완료")

        # ── 2. 플레이스 순위 체크 이동 ─────────────────────
        page.locator("a[href*='naver_place_rank_check.php']").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_selector("select#sfl", state="visible", timeout=10_000)
        log("플레이스 순위 체크 페이지 완료")

        # 검색 옵션은 최초 1회만 설정
        page.locator("select#sfl").first.select_option(value="api_keyword2")
        search_input = page.locator("input#stx").first
        search_btn   = page.locator("button.tool_sch_search").first

        # ── 3. 각 MID 처리 ────────────────────────────────
        for idx, mid in enumerate(mid_list, 1):
            log(f"[{idx}/{len(mid_list)}] MID: {mid}")
            try:
                # 검색어 입력 & 검색
                search_input.click(click_count=3)
                search_input.fill(mid)
                search_btn.click()
                page.wait_for_load_state("domcontentloaded")

                # ★ 전체 행 가져오기 (첫 번째 행만이 아닌 모든 행)
                # tr2 클래스(순위 상세 펼침 행)는 메모 버튼이 없으므로 제외
                rows = page.locator(
                    "tbody tr[class*='api_rows_']:not([class*='tr2'])"
                ).all()

                if not rows:
                    log(f"  → 검색 결과 없음")
                    results["no_row"].append(mid)
                    continue

                log(f"  → 총 {len(rows)}개 행 발견")

                mid_updated  = 0
                mid_skipped  = 0
                mid_error    = 0

                for row_num, row in enumerate(rows, 1):
                    status = process_row(page, row, row_num, mid)
                    if status == "updated":
                        mid_updated += 1
                    elif status == "skipped":
                        mid_skipped += 1
                    else:
                        mid_error += 1

                # MID 단위 결과 집계
                if mid_updated > 0:
                    results["updated"].append(mid)
                elif mid_error > 0:
                    results["error"].append(mid)
                else:
                    results["skipped"].append(mid)

                log(f"  → MID {mid} 완료: 변경 {mid_updated} / 건너뜀 {mid_skipped} / 오류 {mid_error}")

            except PlaywrightTimeout as e:
                log(f"  ⚠ 타임아웃: {e}")
                results["error"].append(mid)
            except Exception as e:
                log(f"  ⚠ 오류: {e}")
                results["error"].append(mid)

        browser.close()

    # ── 4. 결과 요약 ───────────────────────────────────────
    log("\n" + "=" * 50)
    log(f"  ✅ 변경 완료: {len(results['updated'])}개  → {results['updated']}")
    log(f"  ⏭  건너뜀   : {len(results['skipped'])}개  → {results['skipped']}")
    log(f"  ❌ 결과없음 : {len(results['no_row'])}개  → {results['no_row']}")
    log(f"  ⚠  오류     : {len(results['error'])}개  → {results['error']}")
    log("=" * 50)


if __name__ == "__main__":
    try:
        run()
        log("3초 후 자동으로 종료됩니다...")
        time.sleep(3)
    except PlaywrightTimeout as e:
        log(f"시간 초과: {e}")
    except Exception as e:
        log(f"오류 발생: {e}")
        raise
