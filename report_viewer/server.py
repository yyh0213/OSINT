import sys
import os
import json
import httpx
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import glob

from analyzer import (
    PROMPT,
    generate_daily_report,
    chat_turn,
    generate_daily_report_stream,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

app = FastAPI()


class ChatRequest(BaseModel):
    message: str


class ChatMessageRequest(BaseModel):
    message: str


class ScheduleRequest(BaseModel):
    time: str


# Global state for chat context
global_chat_history = [{"role": "system", "content": PROMPT["system_role"]}]

scheduler = AsyncIOScheduler()
REPORT_DIR = os.environ.get("REPORT_DIR", "/app/OSINT_REPORT")
os.makedirs(REPORT_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(REPORT_DIR, "config.json")
CHAT_DIR = os.path.join(REPORT_DIR, "chats")
os.makedirs(CHAT_DIR, exist_ok=True)

# Try loading from possible env locations
load_dotenv("/home/user/.osint_env")
load_dotenv("/app/.osint_env")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_USER_ID = os.environ.get("DISCORD_USER_ID", "")


app = FastAPI()


static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Serve the standard static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        return "<h1>UI is building... Please ensure index.html exists in static folder.</h1>"
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/reports")
async def list_reports():
    reports = []
    pattern = os.path.join(REPORT_DIR, "일일보고_*.txt")
    for filepath in sorted(glob.glob(pattern), reverse=True):
        filename = os.path.basename(filepath)
        reports.append({"filename": filename})
    return {"reports": reports}


@app.get("/api/reports/{filename}")
async def get_report(filename: str):
    if not filename.startswith("일일보고_") or not filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    filepath = os.path.join(REPORT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"filename": filename, "content": content}


INTELLIGENCE_URL = os.environ.get("INTELLIGENCE_URL", "http://intelligence:5050")


@app.get("/api/reliability")
async def get_reliability():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{INTELLIGENCE_URL}/api/reliability")
            res.raise_for_status()
            # reliability_viewer.py 는 rows 배열을 바로 반환 → {"data": [...]} 로 래핑
            return {"data": res.json()}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="intelligence 서비스에 연결할 수 없습니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate")
def generate_report_api():
    global global_chat_history
    # Reset chat history for a new session
    global_chat_history = [{"role": "system", "content": PROMPT["system_role"]}]
    try:
        full_report, file_path = generate_daily_report(global_chat_history)
        filename = os.path.basename(file_path)
        return {"success": True, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate_stream")
def generate_report_stream_api():
    global global_chat_history
    global_chat_history = [{"role": "system", "content": PROMPT["system_role"]}]

    def event_generator():
        try:
            for chunk in generate_daily_report_stream(global_chat_history):
                yield chunk
        except Exception as e:
            yield f"\n[X] 시스템 내부 오류 발생: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/plain")


async def send_discord_notification(report_content: str, filename: str):
    if not DISCORD_WEBHOOK_URL:
        return

    # Discord limits message to 2000 chars, so we might need to truncate
    content = report_content
    if len(content) > 1900:
        content = (
            content[:1900]
            + "\n... (보고서가 너무 길어 생략되었습니다. 웹에서 확인하세요!)"
        )

    mention = f"<@{DISCORD_USER_ID}> " if DISCORD_USER_ID else ""
    # Use configured url or fallback to localhost
    dashboard_url = os.environ.get("DASHBOARD_URL", "http://127.0.0.1:8000")
    message = f"{mention}🚨 **OSINT 일일 보고서 자동 생성 완료** ({filename})\n\n```text\n{content}\n```\n🔗 **대시보드 확인**: {dashboard_url}"

    async with httpx.AsyncClient() as client:
        await client.post(DISCORD_WEBHOOK_URL, json={"content": message})


import asyncio


async def scheduled_job():
    global global_chat_history
    global_chat_history = [{"role": "system", "content": PROMPT["system_role"]}]
    try:
        print("[Schedule] 일일 보고서 자동 생성 시작...")
        full_report, file_path = await asyncio.to_thread(
            generate_daily_report, global_chat_history
        )
        filename = os.path.basename(file_path)
        print(f"[Schedule] 보고서 생성 완료: {filename}")
        await send_discord_notification(full_report, filename)
    except Exception as e:
        print(f"[Schedule] 보고서 생성 실패: {e}")


@app.get("/api/schedule")
def get_schedule():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return {"time": data.get("schedule_time", "09:00")}
    return {"time": "09:00"}


@app.post("/api/schedule")
def set_schedule(req: ScheduleRequest):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"schedule_time": req.time}, f)

    # Update APScheduler
    scheduler.remove_all_jobs()
    hour, minute = req.time.split(":")
    scheduler.add_job(scheduled_job, CronTrigger(hour=int(hour), minute=int(minute)))
    return {"success": True, "time": req.time}


@app.post("/api/chat")
def chat_api(req: ChatRequest):
    global global_chat_history
    try:
        answer = chat_turn(req.message, global_chat_history)
        return {"reply": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Chat Session Endpoints ───────────────────────────────────────────
@app.post("/api/chats")
def create_chat():
    now = datetime.now(timezone(timedelta(hours=9)))
    session_id = now.strftime("%Y%m%d_%H%M%S")
    session = {
        "id": session_id,
        "title": "새 채팅",
        "created_at": now.isoformat(),
        "display_messages": [],
        "api_messages": [{"role": "system", "content": PROMPT["system_role"]}],
    }
    filepath = os.path.join(CHAT_DIR, f"chat_{session_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    return session


@app.get("/api/chats")
def list_chats():
    sessions = []
    for filepath in sorted(glob.glob(os.path.join(CHAT_DIR, "chat_*.json")), reverse=True):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                sessions.append({"id": data["id"], "title": data["title"], "created_at": data["created_at"]})
        except Exception:
            pass
    return {"sessions": sessions}


@app.get("/api/chats/{session_id}")
def get_chat(session_id: str):
    if "/" in session_id or ".." in session_id:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    filepath = os.path.join(CHAT_DIR, f"chat_{session_id}.json")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Chat session not found")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/chats/{session_id}/message")
def send_chat_message(session_id: str, req: ChatMessageRequest):
    if "/" in session_id or ".." in session_id:
        raise HTTPException(status_code=400, detail="Invalid session ID")
    filepath = os.path.join(CHAT_DIR, f"chat_{session_id}.json")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Not found")
    with open(filepath, "r", encoding="utf-8") as f:
        session = json.load(f)
    api_messages = session.get("api_messages", [{"role": "system", "content": PROMPT["system_role"]}])
    try:
        answer = chat_turn(req.message, api_messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    session["display_messages"].append({"role": "user", "content": req.message, "timestamp": now})
    session["display_messages"].append({"role": "assistant", "content": answer, "timestamp": now})
    session["api_messages"] = api_messages
    if len(session["display_messages"]) == 2:
        session["title"] = req.message[:40] + ("..." if len(req.message) > 40 else "")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    return {"reply": answer, "title": session["title"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


@app.on_event("startup")
async def load_schedule():
    scheduler.start()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            time_str = data.get("schedule_time", "09:00")
            try:
                hour, minute = time_str.split(":")
                scheduler.add_job(
                    scheduled_job, CronTrigger(hour=int(hour), minute=int(minute))
                )
                print(f"[Schedule] 스케줄러 등록 완료: 매일 {time_str}")
            except Exception as e:
                print(f"[Schedule] 스케줄 로드 실패: {e}")
