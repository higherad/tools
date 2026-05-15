"""
ADLOG 메모 변경/삭제 Cloud Run 서버
- /fetch-mids : 구글 시트에서 MID 목록 조회
- /process    : MID별 메모 변경/삭제 실행 (한 배치)
"""

import os
import json
import queue as _queue
import threading
import traceback

import google.auth
from google.auth.transport.requests import Request
import gspread

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

CONFIG = {
    "login_url": "https://adlog.kr/bbs/login.php?url=%2Fadlog%2F",
    "id":        os.environ.get("ADLOG_ID", "higherad"),
    "password":  os.environ.get("ADLOG_PW", "higherad1105!"),
}

_lock = threading.Lock()

BROWSER_ARGS = ["--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu"]


def login(page):
    page.goto(CONFIG["login_url"], wait_until="domcontentloaded")
    page.wait_for_selector("#login_id", state="visible", timeout=10000)
    page.locator("#login_id").fill(CONFIG["id"])
    page.locator("input[type='password']").fill(CONFIG["password"])
    page.locator("button[type='submit']").click()
    page.wait_for_load_state("domcontentloaded")


# ── 메모 처리 ───────────────────────────────────────────────

def process_mid(page, mid, change_from, change_to, delete_cond):
    """
    MID 검색 → 모든 행에 메모 변경/삭제 적용
    반환: {updated, skipped, no_row, error}
    """
    search_input = page.locator("input#stx").first
    search_btn   = page.locator("button.tool_sch_search").first

    search_input.click(click_count=3)
    search_input.fill(mid)
    search_btn.click()
    page.wait_for_load_state("domcontentloaded")

    rows = page.locator("tbody tr[class*='api_rows_']:not([class*='tr2'])").all()
    if not rows:
        return {"updated": 0, "skipped": 0, "no_row": True, "error": 0}

    updated = skipped = errors = 0

    for row_num, row in enumerate(rows, 1):
        try:
            row_class  = row.get_attribute("class") or ""
            base_class = row_class.split()[0]

            try:
                memo_text = page.locator(
                    f"tr[class*='{base_class}'] td.pr.vat.blur_disp"
                ).first.inner_text(timeout=2000)
            except Exception:
                memo_text = ""

            needs_change = bool(change_from) and change_from in memo_text
            needs_delete = bool(delete_cond) and delete_cond in memo_text

            if not needs_change and not needs_delete:
                skipped += 1
                continue

            # 메모 모달 열기
            row.locator("button.btn01.btn_memo_modify_form").first.click()
            page.wait_for_selector("textarea", state="visible", timeout=6000)

            ta      = page.locator("textarea").first
            current = ta.input_value()
            new_val = current

            if change_from and change_from in new_val:
                new_val = new_val.replace(change_from, change_to or "")

            if delete_cond and delete_cond in new_val:
                lines   = new_val.splitlines()
                new_val = "\n".join(l for l in lines if delete_cond not in l)

            if new_val == current:
                page.mouse.click(10, 10)
                skipped += 1
                continue

            ta.fill(new_val)
            page.locator("button.btn02.btn_memo_modify").first.click()
            page.wait_for_load_state("domcontentloaded")
            updated += 1

        except PlaywrightTimeout:
            errors += 1
        except Exception:
            errors += 1

    return {"updated": updated, "skipped": skipped, "no_row": False, "error": errors}


# ── Flask ────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app, origins=[
    "https://higheradtool.kro.kr",
    "http://localhost",
    "http://127.0.0.1",
])


@app.route("/fetch-mids", methods=["POST"])
def fetch_mids():
    """구글 시트에서 MID 목록 조회"""
    data   = request.get_json(force=True)
    sid    = data.get("spreadsheet_id", "").strip()
    sname  = data.get("sheet_name", "").strip()
    col    = data.get("mid_col", "B").strip().upper()

    if not sid or not sname:
        return jsonify({"success": False, "message": "spreadsheet_id / sheet_name 필수"}), 400

    # 컬럼 문자 → 0-based 인덱스
    col_idx = ord(col[0]) - ord("A") if col.isalpha() else max(0, int(col) - 1)

    try:
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        if hasattr(creds, "expired") and creds.expired:
            creds.refresh(Request())
        gc        = gspread.authorize(creds)
        worksheet = gc.open_by_key(sid).worksheet(sname)
        all_rows  = worksheet.get_all_values()[1:]  # 헤더 스킵

        mids = []
        for row in all_rows:
            if len(row) > col_idx:
                val = str(row[col_idx]).strip()
                if val and val.lower() not in ("mid", ""):
                    mids.append(val)

        return jsonify({"success": True, "mids": mids, "count": len(mids)})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/process", methods=["POST"])
def process():
    """MID 배치 메모 변경/삭제"""
    data    = request.get_json(force=True)
    entries = data.get("entries", [])
    if not entries:
        return jsonify({"success": False, "message": "entries 필수"}), 400

    with _lock:
        pw = None
        browser = None
        context = None
        try:
            pw      = sync_playwright().start()
            browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
            context = browser.new_context()
            page    = context.new_page()
            page.set_default_timeout(15000)

            login(page)

            # 플레이스 순위 체크 페이지 이동
            page.locator("a[href*='naver_place_rank_check.php']").first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_selector("select#sfl", state="visible", timeout=10000)
            page.locator("select#sfl").first.select_option(value="api_keyword2")

            results = []
            for entry in entries:
                mid          = str(entry.get("mid", "")).strip()
                change_from  = str(entry.get("change_from", "")).strip()
                change_to    = str(entry.get("change_to",   "")).strip()
                delete_cond  = str(entry.get("delete_cond", "")).strip()

                if not mid:
                    continue

                try:
                    r = process_mid(page, mid, change_from, change_to, delete_cond)
                    msg = (
                        "검색결과 없음" if r["no_row"]
                        else f"변경 {r['updated']} / 건너뜀 {r['skipped']} / 오류 {r['error']}"
                    )
                    results.append({
                        "mid":     mid,
                        "success": not r["no_row"] and r["error"] == 0,
                        "updated": r["updated"],
                        "skipped": r["skipped"],
                        "no_row":  r["no_row"],
                        "error":   r["error"],
                        "message": msg,
                    })
                except Exception as e:
                    results.append({
                        "mid": mid, "success": False, "updated": 0, "skipped": 0,
                        "no_row": False, "error": 1,
                        "message": traceback.format_exc(limit=2)[-100:],
                    })

        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
        finally:
            try: context.close()
            except Exception: pass
            try: browser.close()
            except Exception: pass
            try: pw.stop()
            except Exception: pass

    return jsonify({"success": True, "results": results})


@app.route("/process-stream", methods=["POST"])
def process_stream():
    """MID 배치 메모 변경/삭제 — MID별 결과 실시간 스트리밍"""
    data    = request.get_json(force=True)
    entries = data.get("entries", [])
    if not entries:
        return jsonify({"success": False, "message": "entries 필수"}), 400

    q = _queue.Queue()

    def worker():
        with _lock:
            pw = None
            browser = None
            context = None
            try:
                pw      = sync_playwright().start()
                browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
                context = browser.new_context()
                page    = context.new_page()
                page.set_default_timeout(15000)

                login(page)
                page.locator("a[href*='naver_place_rank_check.php']").first.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_selector("select#sfl", state="visible", timeout=10000)
                page.locator("select#sfl").first.select_option(value="api_keyword2")

                for entry in entries:
                    mid         = str(entry.get("mid", "")).strip()
                    change_from = str(entry.get("change_from", "")).strip()
                    change_to   = str(entry.get("change_to",   "")).strip()
                    delete_cond = str(entry.get("delete_cond", "")).strip()

                    if not mid:
                        continue

                    try:
                        r = process_mid(page, mid, change_from, change_to, delete_cond)
                        msg = (
                            "검색결과 없음" if r["no_row"]
                            else f"변경 {r['updated']} / 건너뜀 {r['skipped']} / 오류 {r['error']}"
                        )
                        q.put(("mid_result", {
                            "mid":     mid,
                            "success": not r["no_row"] and r["error"] == 0,
                            "updated": r["updated"],
                            "skipped": r["skipped"],
                            "no_row":  r["no_row"],
                            "error":   r["error"],
                            "message": msg,
                        }))
                    except Exception:
                        q.put(("mid_result", {
                            "mid": mid, "success": False, "updated": 0, "skipped": 0,
                            "no_row": False, "error": 1,
                            "message": traceback.format_exc(limit=2)[-100:],
                        }))

            except Exception as e:
                q.put(("error", str(e)))
            finally:
                try: context.close()
                except Exception: pass
                try: browser.close()
                except Exception: pass
                try: pw.stop()
                except Exception: pass

        q.put(("done", True))

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            try:
                kind, data = q.get(timeout=120)
                if kind == "mid_result":
                    yield f"data: {json.dumps({'mid_result': data}, ensure_ascii=False)}\n\n"
                elif kind == "error":
                    yield f"data: {json.dumps({'error': data})}\n\n"
                    break
                elif kind == "done":
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    break
            except _queue.Empty:
                yield f"data: {json.dumps({'ping': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/ping",   methods=["GET"])
def ping():   return jsonify({"status": "ok"})

@app.route("/health", methods=["GET"])
def health(): return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"▶ macro-5-adlog-memo 서버 시작 (포트: {port})")
    app.run(host="0.0.0.0", port=port, threaded=True)
