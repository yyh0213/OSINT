import httpx
import os
from qdrant_client import QdrantClient
from openai import OpenAI
from datetime import datetime, timezone, timedelta
from pathlib import Path
import textwrap
from duckduckgo_search import DDGS
import json
from qdrant_client.http import models
import time

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
    당신은 수석 정보 분석관입니다. 아래 제공된 최신 OSINT 데이터와 [현재 시스템 시각]을 기준으로 '일일 종합 정보 브리핑'을 작성하십시오.

    [작성 시점 및 시간 기준 엄수]
    - 🕒 현재 시스템 시각: {current_time}
    - 24시간 이내 기준: 위 현재 시각으로부터 역산하여 '정확히 24시간 이내'에 수집된 데이터([수집일시] 참조)만 '신규 동향(New Updates)' 및 'Executive Summary'에 포함하십시오.
    - 24시간이 지난 데이터는 오직 '배경 설명(Background)'이나 맥락 용도로만 사용해야 하며, 절대 오늘의 주요 뉴스로 포장하지 마십시오.

    [작성 원칙 - 델타(Delta) 분석 지침]
    1. 시간 역전 금지: 24시간 이전의 사건을 오늘 발생한 것처럼 서술하는 것을 엄격히 금지합니다.
    2. 단순 나열 금지: 이전 상황에서 무엇이, 어떻게 변화했는지 '변화점'을 중심으로 서술하십시오. 24시간 내 변화가 없다면 '특이동향 없음'으로 명시하십시오.
    3. 상충하는 데이터가 있을 경우, 수집일시가 가장 최근인 것을 현재의 팩트로 간주하십시오.
    4. 각 항목의 내용을 서술할 때, 반드시 문장 끝에 출처 번호를 기재하십시오. (예: ...로 상황이 반전됨 [2].)

    [보고서 구조]
    🔴 1. Executive Summary (현재 시각 기준 24시간 내 발생한 가장 치명적인 국면 전환 최대 3가지. 24시간 내 주요 뉴스가 없다면 '특이 전환 없음' 명시)
    🌍 2. 지정학 및 군사 동향 (이전 전황(Background)과 최근 24시간(New Updates)을 명확히 분리하여 서술)
    💰 3. 경제 및 공급망 동향 (시장 지표의 등락 및 정책 변화. 24시간 이내 데이터 위주)
    👁️ 4. 잠재적 위협 및 이상 징후 (Blind Spots)
    📚 5. References (참고 출처 목록. 반드시 표에 "수집일시", "제목", "출처", "링크(URL)" 열을 추가할 것)
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


def search_database(query, top_k=5, hours_ago=None):
    query_vector = get_query_embedding(query)

    # 기본 검색 조건
    search_params = {
        "collection_name": COLLECTION_NAME,
        "query": query_vector,
        "limit": top_k,
    }

    # 💡 [핵심] hours_ago 값이 들어오면 해당 시간 이내의 데이터만 물리적으로 필터링
    if hours_ago is not None:
        time_threshold = int(time.time()) - (hours_ago * 3600)
        search_params["query_filter"] = models.Filter(
            must=[
                models.FieldCondition(
                    key="timestamp", range=models.Range(gte=time_threshold)
                )
            ]
        )

    response = qdrant.query_points(**search_params)

    if not response.points:
        return "관련된 최신 데이터를 찾을 수 없습니다."

    context_text = ""
    for i, hit in enumerate(response.points, 1):
        payload = hit.payload
        pub_time = "최근 24시간 이내"
        if "timestamp" in payload:
            pub_time = datetime.fromtimestamp(payload["timestamp"]).strftime(
                "%Y-%m-%d %H:%M"
            )

        context_text += f"[{i}] [수집일시: {pub_time}] 출처: {payload.get('project', 'Unknown')} (링크: {payload.get('link', 'URL 없음')})\n제목: {payload.get('title', '')}\n본문 요약: {payload.get('content', '')}\n\n"
    return context_text


def search_web_tool(query: str, max_results: int = 6) -> str:
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
            "description": "내부 DB에 정보가 부족할 때 글로벌 웹 뉴스를 검색합니다. 검색의 정확도를 위해 한국어 자연어가 아닌, 핵심 '영문 키워드' 단위로 쪼개어 검색해야 합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색 엔진에 최적화된 구체적인 영문 키워드 조합 (단어 나열형). 자연어 의문문이나 한국어는 절대 금지. (예: 'US Iran ceasefire official reaction South Korea Japan', 'Iran US truce agreement European Union response')",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


# --- 4. 대화형 AI 엔진 ---
def generate_daily_report(chat_history: list[dict[str, str | None]]):
    daily_query = "최근 24시간 동안의 글로벌 군사, 안보, 경제 관련 주요 동향"
    daily_context = search_database(daily_query, top_k=15, hours_ago=24)

    # 💡 [핵심 추가] AI에게 알려줄 현재 시각 문자열 생성
    now = datetime.now(timezone(timedelta(hours=9)))
    current_time_str = now.strftime("%Y-%m-%d %H:%M KST")
    initial_prompt = f"{PROMPT['daily_report'].format(current_time=current_time_str)}\n\n[수집된 데이터]\n{daily_context}"

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


def generate_daily_report_stream(chat_history: list[dict[str, str | None]]):
    yield ">> 데이터베이스에서 최근 24시간 글로벌 동향을 탐색 중입니다...\n"
    daily_query = "최근 24시간 동안의 글로벌 군사, 안보, 경제 관련 주요 동향"
    daily_context = search_database(daily_query, top_k=15, hours_ago=24)

    info_count = len(daily_context.split("[수집일시]")) - 1
    yield f">> DB 검색 완료. {info_count}개의 핵심 정보를 확보했습니다.\n"
    yield ">> AI 분석 엔진(Anthropic Claude 3.5 Sonnet) 가동 시작...\n\n"

    now = datetime.now(timezone(timedelta(hours=9)))
    current_time_str = now.strftime("%Y-%m-%d %H:%M KST")
    initial_prompt = f"{PROMPT['daily_report'].format(current_time=current_time_str)}\n\n[수집된 데이터]\n{daily_context}"

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

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_report + "\n\n")

    yield f"\n\n>> [시스템] 보고서 저장이 완료되었습니다: {file_path}"


def chat_turn(user_input, chat_history):
    # 1. 1차 내부 DB 검색 (Qdrant)
    new_context = search_database(user_input, top_k=15)

    # 2. 프롬프트 구성
    follow_up_prompt = f"""{PROMPT["follow_up"]}

[내부 DB 검색 결과]
{new_context}

[국장님 질문]
{user_input}

[분석관(AI) 필수 행동 지침]
1. 내부 DB에 정보가 충분하지 않거나 최신 글로벌 동향(특히 타국 정부의 공식 반응 등)이 필요하다면 반드시 'search_web' 도구를 사용하십시오.
2. 도구를 호출할 때는 질문을 분석하여 가장 핵심적인 '영문(English) 키워드 조합'으로 검색어를 변환해야 합니다. (예: "US Iran ceasefire reactions")
3. 필요하다면 도구를 여러 번 호출하여 각 국가별(US, Europe, South Korea, Japan)로 따로 검색해도 좋습니다.
4. DB의 정보랑 웹검색의 정보가 충돌하는 경우 DB의 정보를 신뢰하고, 웹검색 정보는 참조 정도로 기술하십시오.
"""

    chat_history.append({"role": "user", "content": follow_up_prompt})

    # 3. 다중 턴(Multi-Turn) 에이전트 루프 시작
    max_iterations = 5  # AI가 무한 검색에 빠지는 것을 막기 위한 안전장치

    for iteration in range(max_iterations):
        # 매 호출마다 tools를 쥐여줌
        response = llm_client.chat.completions.create(
            model=AI_MODEL,
            messages=chat_history,
            temperature=0.3,
            tools=tools,
            tool_choice="auto",
        )

        response_message = response.choices[0].message

        # AI가 더 이상 도구를 쓰지 않겠다고 판단한 경우 (최종 답변 도달)
        if not response_message.tool_calls:
            answer = response_message.content or "[응답 없음]"
            chat_history.append({"role": "assistant", "content": answer})
            return answer

        # AI가 도구를 사용하겠다고 한 경우
        assistant_msg = {
            "role": "assistant",
            "content": response_message.content,  # "추가로 검색합니다" 같은 코멘트가 있을 수 있음
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response_message.tool_calls
            ],
        }
        chat_history.append(assistant_msg)

        # 도구 실행
        for tool_call in response_message.tool_calls:
            if tool_call.function.name == "search_web":
                function_args = json.loads(tool_call.function.arguments)
                search_query = function_args.get("query")

                web_result = search_web_tool(search_query)

                chat_history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": "search_web",
                        "content": web_result,
                    }
                )

        print(
            f"    [에이전트 행동] 🧠 {iteration + 1}차 탐색 완료. 추가 정보 분석 중..."
        )

    # max_iterations를 다 채워도 답변을 못 냈을 경우 강제 답변 생성 (안전장치)
    print(
        "    [에이전트 행동] ⚠️ 최대 탐색 횟수 도달. 현재까지의 정보로 보고서 작성 중..."
    )
    final_response = llm_client.chat.completions.create(
        model=AI_MODEL, messages=chat_history, temperature=0.3
    )
    answer = final_response.choices[0].message.content
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
