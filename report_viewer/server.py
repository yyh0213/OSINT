import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import glob

from analyzer import PROMPT, generate_daily_report, chat_turn

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

# Global state for chat context
global_chat_history = [{"role": "system", "content": PROMPT["system_role"]}]


app = FastAPI()

REPORT_DIR = "/home/user/OSINT/OSINT_REPORT"

os.makedirs(REPORT_DIR, exist_ok=True)
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

@app.post("/api/generate")
async def generate_report_api():
    global global_chat_history
    # Reset chat history for a new session
    global_chat_history = [{"role": "system", "content": PROMPT["system_role"]}]
    try:
        full_report, file_path = generate_daily_report(global_chat_history)
        filename = os.path.basename(file_path)
        return {"success": True, "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_api(req: ChatRequest):
    global global_chat_history
    try:
        answer = chat_turn(req.message, global_chat_history)
        return {"reply": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
