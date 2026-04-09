import httpx
import os
from qdrant_client import QdrantClient
from openai import OpenAI
from datetime import datetime, timezone, timedelta
from pathlib import Path
import textwrap
from duckduckgo_search import DDGS
import json

# --- 1. 기본 설정 ---
DB_IP = os.environ.get("DB_IP", "192.168.45.80")
OLLAMA_URL = os.environ.get("OLLAMA_URL", f"http://{DB_IP}:11434/api/embeddings")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "osint_news")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
# --- 외부 보안 설정 (.osint_env 파일 또는 환경 변수에서 API 키 로드) ---
KEY_FILE = "/home/user/.osint_env"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY and os.path.exists(KEY_FILE):
    with open(KEY_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                OPENROUTER_API_KEY = line.split("=", 1)[1]

if not OPENROUTER_API_KEY:
    raise ValueError(
        "보안 오류: OPENROUTER_API_KEY가 없습니다! 도커 환경 변수에 입력하거나 .osint_env 파일에 저장해주세요."
    )

llm_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
AI_MODEL = os.environ.get("AI_MODEL", "anthropic/claude-sonnet-4.6")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
qdrant = QdrantClient(host=DB_IP, port=QDRANT_PORT)

# --- 2. 프롬프트 라이브러리 ---
PROMPT = {
    "system_role": "당신은 독립 정보국의 수석 정보 분석관(Chief Intelligence Analyst)입니다. 주관적 추측을 배제하고 오직 제공된 데이터의 구체적 근거에 기반하여 건조하고 명확하게 답변하십시오. 또한 모든 팩트와 주장의 끝에는 반드시 제공된 데이터의 출처 번호(예: [1], [3])를 인용 부호로 표기해야 합니다.",
    "daily_report": """
    아래 제공된 최신 OSINT 데이터를 바탕으로 '일일 종합 정보 브리핑'을 작성하십시오.
    특히 각 데이터의 [수집일시]를 면밀히 분석하여, 과거의 정보와 최근 24시간 이내의 새로운 동향을 엄격히 구분하십시오.

    [작성 원칙 - 델타(Delta) 분석 지침]
    1. 단순 나열을 금지합니다. 이전 상황(Background)에서 무엇이, 어떻게 변화(New Updates)했는지 '변화점'을 중심으로 서술하십시오.
    2. 상충하는 데이터가 있을 경우, 수집일시가 가장 최근인 것을 현재의 팩트로 간주하고 이전 데이터는 맥락 설명용으로만 사용하십시오.
    3. 각 항목의 내용을 서술할 때, 반드시 문장 끝에 출처 번호를 기재하십시오. (예: ...로 상황이 반전됨 [2].)

    [보고서 구조]
    🔴 1. Executive Summary (24시간 내 발생한 가장 치명적인 국면 전환 3가지 요약)
    🌍 2. 지정학 및 군사 동향 (이전 전황과의 차이점, 신규 병력/자산 이동 중심)
    💰 3. 경제 및 공급망 동향 (시장 지표의 어제 대비 등락 및 정책 변화)
    👁️ 4. 잠재적 위협 및 이상 징후 (Blind Spots)
    📚 5. References (참고 출처 목록. 반드시 표에 "링크(URL)" 열을 추가하여 실제 URL 주소를 포함시킬 것)
    """,
    "follow_up": "위의 대화 문맥과 새롭게 검색된 아래의 데이터를 바탕으로 사용자님의 질문에 답변하십시오. 정보가 부족하다면 '데이터 부족'을 명시하고, 답변 시 반드시 새로운 출처 번호를 본문에 인용하십시오.",
}


# --- 3. 데이터 검색 엔진 ---
def get_query_embedding(text):
    with httpx.Client() as client:
        response = client.post(
            OLLAMA_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=30.0
        )
        return response.json()["embedding"]


def search_database(query, top_k=5):
    query_vector = get_query_embedding(query)
    response = qdrant.query_points(
        collection_name=COLLECTION_NAME, query=query_vector, limit=top_k
    )

    if not response.points:
        return "관련된 최신 데이터를 찾을 수 없습니다."

    context_text = ""
    for i, hit in enumerate(response.points, 1):
        payload = hit.payload
        # payload에 저장된 timestamp를 읽기 쉬운 날짜 형태로 변환 (없으면 '최근'으로 표기)
        pub_time = "최근 24시간 이내"  # 실제 수집기(collector.py)에서 저장한 시간 포맷팅 로직 추가 가능
        if "timestamp" in payload:
            from datetime import datetime

            pub_time = datetime.fromtimestamp(payload["timestamp"]).strftime(
                "%Y-%m-%d %H:%M"
            )

        # AI가 시간을 인지할 수 있도록 [수집일시] 태그 추가
        context_text += f"[{i}] [수집일시: {pub_time}] 출처: {payload.get('project', 'Unknown')} (링크: {payload.get('link', 'URL 없음')})\n제목: {payload.get('title', '')}\n본문 요약: {payload.get('content', '')}\n\n"
    return context_text


def search_web_tool(query: str, max_results: int = 3) -> str:
    """AI가 호출할 실제 웹 검색 함수"""
    print(f"\n[에이전트 행동] 🌐 외부 웹 탐색 중... (검색어: {query})")
    try:
        results = DDGS().text(query, max_results=max_results)
        if not results:
            return "웹 검색 결과가 없습니다."

        formatted_results = ""
        for i, r in enumerate(results, 1):
            formatted_results += f"[{i}] 제목: {r.get('title')}\n요약: {r.get('body')}\n링크: {r.get('href')}\n\n"
        return formatted_results
    except Exception as e:
        return f"웹 검색 중 오류 발생: {e}"


# --- 에이전트용 '도구(Tools)' 정의 ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "내부 DB에 관련 정보가 없거나, 실시간 외부 뉴스가 필요할 때 웹을 검색합니다. 영어로 검색하면 더 정확한 결과가 나옵니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색 엔진에 입력할 구체적인 검색어 (예: 'Iran US ceasefire text discrepancy Associated Press')",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


# --- 4. 대화형 AI 엔진 ---
def generate_daily_report(chat_history):
    daily_query = "최근 24시간 동안의 글로벌 군사, 안보, 경제 관련 주요 동향"
    daily_context = search_database(daily_query, top_k=8)

    initial_prompt = f"{PROMPT['daily_report']}\n\n[수집된 데이터]\n{daily_context}"
    chat_history.append({"role": "user", "content": initial_prompt})

    response = llm_client.chat.completions.create(
        model=AI_MODEL, messages=chat_history, temperature=0.3
    )

    report_content = response.choices[0].message.content
    chat_history.append({"role": "assistant", "content": report_content})

    now = datetime.now(timezone(timedelta(hours=9)))
    date_str, time_str = now.strftime("%Y%m%d"), now.strftime("%H:%M:%S")
    save_dir = os.environ.get("REPORT_DIR", "/app/OSINT_REPORT")
    file_path = Path(save_dir) / f"일일보고_{date_str}.txt"
    os.makedirs(save_dir, exist_ok=True)

    full_report = textwrap.dedent(f"""
        {"=" * 80}
        📋 [AI OSINT 일일 종합 브리핑] - {date_str} {time_str}
        {"=" * 80}
        {report_content}
        {"=" * 80}
    """).strip()

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(full_report + "\n\n")

    return full_report, str(file_path)


def generate_daily_report_stream(chat_history):
    yield ">> 데이터베이스에서 최근 24시간 글로벌 동향을 탐색 중입니다...\n"
    daily_query = "최근 24시간 동안의 글로벌 군사, 안보, 경제 관련 주요 동향"
    daily_context = search_database(daily_query, top_k=8)

    info_count = len(daily_context.split("[수집일시]")) - 1
    yield f">> DB 검색 완료. {info_count}개의 핵심 정보를 확보했습니다.\n"
    yield ">> AI 분석 엔진(Anthropic Claude 3.5 Sonnet) 가동 시작...\n\n"

    initial_prompt = f"{PROMPT['daily_report']}\n\n[수집된 데이터]\n{daily_context}"

    # Use a copy so we don't mess up the global history mid-stream if it fails
    local_history = chat_history.copy()
    local_history.append({"role": "user", "content": initial_prompt})

    response = llm_client.chat.completions.create(
        model=AI_MODEL, messages=local_history, temperature=0.3, stream=True
    )

    report_content = ""
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            report_content += delta
            yield delta

    chat_history.append({"role": "user", "content": initial_prompt})
    chat_history.append({"role": "assistant", "content": report_content})

    now = datetime.now(timezone(timedelta(hours=9)))
    date_str, time_str = now.strftime("%Y%m%d"), now.strftime("%H:%M:%S")
    save_dir = os.environ.get("REPORT_DIR", "/app/OSINT_REPORT")
    file_path = Path(save_dir) / f"일일보고_{date_str}.txt"
    os.makedirs(save_dir, exist_ok=True)

    full_report = textwrap.dedent(f"""
        {"=" * 80}
        📋 [AI OSINT 일일 종합 브리핑] - {date_str} {time_str}
        {"=" * 80}
        {report_content}
        {"=" * 80}
    """).strip()

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(full_report + "\n\n")

    yield f"\n\n>> [시스템] 보고서 저장이 완료되었습니다: {file_path}"


def chat_turn(user_input, chat_history):
    # 1. 1차 내부 DB 검색 (Qdrant)
    new_context = search_database(user_input, top_k=5)

    # 2. 프롬프트 구성
    follow_up_prompt = f"{PROMPT['follow_up']}\n\n[내부 DB 검색 결과]\n{new_context}\n\n[국장님 질문]\n{user_input}\n\n*지시사항: 내부 DB에 정보가 충분하지 않다면 반드시 'search_web' 도구를 사용하여 외부 뉴스를 교차 검증하십시오.*"

    chat_history.append({"role": "user", "content": follow_up_prompt})

    # 3. AI 모델 호출 (도구 포함)
    response = llm_client.chat.completions.create(
        model=AI_MODEL,
        messages=chat_history,
        temperature=0.3,
        tools=tools,  # 💡 AI에게 도구를 쥐여줌
        tool_choice="auto",
    )

    response_message = response.choices[0].message

    # 4. AI가 "웹 검색 도구를 쓰겠다"고 결정한 경우
    if response_message.tool_calls:
        # AI의 도구 호출 메시지를 대화 기록에 추가
        chat_history.append(response_message)

        for tool_call in response_message.tool_calls:
            if tool_call.function.name == "search_web":
                # AI가 만든 검색어 추출
                function_args = json.loads(tool_call.function.arguments)
                search_query = function_args.get("query")

                # 실제 파이썬 함수 실행
                web_result = search_web_tool(search_query)

                # 검색 결과를 AI에게 다시 전달
                chat_history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": "search_web",
                        "content": web_result,
                    }
                )

        # 5. 외부 검색 결과를 바탕으로 최종 답변 생성
        print("    [에이전트 행동] 🧠 외부 정보 분석 및 최종 보고서 작성 중...")
        second_response = llm_client.chat.completions.create(
            model=AI_MODEL, messages=chat_history, temperature=0.3
        )
        answer = second_response.choices[0].message.content
        chat_history.append({"role": "assistant", "content": answer})
        return answer

    # AI가 도구를 쓰지 않고 (내부 DB만으로 충분하다고 판단) 바로 답변한 경우
    else:
        answer = response_message.content
        chat_history.append({"role": "assistant", "content": answer})
        return answer


# --- 대화형 CLI 메인 루프 ---
def chat_with_agent():
    chat_history = [{"role": "system", "content": PROMPT["system_role"]}]

    print("\n" + "=" * 80)
    print("📡 OSINT 분석 데스크에 오신 것을 환영합니다.")
    print("=" * 80)

    print("[*] 오늘의 글로벌 동향 데이터를 수집 및 분석 중입니다...")
    full_report, file_path = generate_daily_report(chat_history)

    print(full_report)
    print(f"[*] 보고서가 저장되었습니다: {file_path}")

    print(
        "\n💡 보고서 내용에 대해 질문하시거나, 새로운 키워드를 검색하세요. (종료를 원하면 'q' 입력)"
    )

    while True:
        user_input = input("\n>> 사용자님 지시사항: ")
        if user_input.lower() in ["q", "quit", "exit"]:
            print("시스템을 종료합니다.")
            break

        print(f"[*] '{user_input}' 관련 팩트 교차 검증 중...")
        answer = chat_turn(user_input, chat_history)

        print("\n" + "-" * 80)
        print(answer)
        print("-" * 80)


if __name__ == "__main__":
    chat_with_agent()
