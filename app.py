"""
GrowBridge — 내 연구·관심사를 산업과 잇는 주간 논문 큐레이터 AI 에이전트
--------------------------------------------------------------------------
컨셉: 대학원(학술) ↔ 산업의 연결을 매주 짚어 주는 에이전트.
  - 최근 arXiv 논문을 검색(find_recent_papers)
  - 각 논문을 "3줄 요약 + 산업 연결(Industry Bridge)"로 정리
  - 관심 분야 저장(set_research_focus) / 읽을 논문 저장(save_to_reading_list)
  - 필요 시 산업 동향을 웹에서 보강(web_search)

구조: LLM(Groq, OpenAI 호환)이 두뇌, 위 함수들이 도구(tool),
      run_agent()가 에이전트 루프, Streamlit이 UI/배포 계층.
누구나 URL로 접속해 사용할 수 있으며 외부 로그인이 없다.
"""

import os
import json
import datetime
import random
import string
import streamlit as st
from openai import OpenAI

# ----------------------------------------------------------------------------
# 0. 기본 설정
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="GrowBridge · 학술-산업 연결 논문 큐레이터",
    page_icon="🌉",
    layout="centered",
)

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_AGENT_STEPS = 6  # 딥다이브(멀티스텝)를 위해 여유를 둠

# ---- 영속 저장(프로필 코드 방식) --------------------------------------------
# 관심사·읽을목록을 짧은 코드에 묶어 JSON 파일에 보관한다.
# Community Cloud에서 컨테이너가 재시작되면 파일이 사라질 수 있으나,
# 같은 앱 세션 동안의 새로고침/재방문에는 코드로 복원된다.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_gb_data")
PROFILE_FILE = os.path.join(DATA_DIR, "profiles.json")


def _load_all_profiles() -> dict:
    try:
        with open(PROFILE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_all_profiles(data: dict) -> bool:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def _new_code(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def get_api_key() -> str:
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY", "")


def get_client():
    key = get_api_key()
    if not key:
        return None
    return OpenAI(api_key=key, base_url=GROQ_BASE_URL)


# ----------------------------------------------------------------------------
# 1. 도구(tool) — 평범한 Python 함수들
# ----------------------------------------------------------------------------
def find_recent_papers(keywords: str, days: int = 7, max_results: int = 6,
                       category: str = "") -> str:
    """arXiv에서 최근 `days`일 내 신규 논문을 최신순으로 검색한다(키 불필요).
    category 예: cs.AI, cs.LG, cs.CL, stat.ML, q-bio.NC 등.
    날짜 창에 결과가 없으면 가장 최신 논문으로 대체한다."""
    try:
        import arxiv
    except ImportError:
        return "[arxiv 패키지를 불러올 수 없습니다. requirements.txt에 'arxiv'가 있는지 확인하세요.]"

    try:
        query = f"cat:{category} AND ({keywords})" if category else keywords
        search = arxiv.Search(
            query=query,
            max_results=max(max_results * 4, 24),
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        client = arxiv.Client(page_size=50, delay_seconds=3, num_retries=2)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

        within, newest = [], []
        for r in client.results(search):
            authors = ", ".join(a.name for a in r.authors[:4])
            cats = ", ".join(r.categories[:3])
            abstract = " ".join((r.summary or "").split())[:380]
            item = (
                f"제목: {r.title.strip()}\n"
                f"  날짜: {r.published.date().isoformat()} | 분야: {cats}\n"
                f"  저자: {authors}\n"
                f"  링크: {r.entry_id}\n"
                f"  초록: {abstract}…"
            )
            newest.append(item)
            if r.published >= cutoff:
                within.append(item)
            if len(newest) >= max_results * 4:
                break

        picked = within[:max_results]
        note = ""
        if not picked:  # 최근 days일 내 결과가 없으면 최신 논문으로 대체
            picked = newest[:max_results]
            note = f"(최근 {days}일 내 신규 논문이 없어, 검색어에 맞는 가장 최근 논문으로 확장했습니다. 결과가 분야와 동떨어져 보이면 더 구체적인 연구 키워드로 다시 시도하세요.)\n"
        if not picked:
            return "검색 결과가 없습니다. 키워드를 바꿔 보세요."
        cat_txt = (", cat=" + category) if category else ""
        header = f"[arXiv 최근 {days}일 검색 · 키워드='{keywords}'{cat_txt}]\n{note}"
        return header + "\n\n".join(f"{i}. {p}" for i, p in enumerate(picked, 1))
    except Exception as e:
        return f"[arXiv 검색 실패: {e}]"


def set_research_focus(field: str, keywords: str) -> str:
    """사용자의 관심 산업·연구 분야와 핵심 키워드를 저장한다(주간 추천의 기준)."""
    st.session_state.research_focus = {"field": field, "keywords": keywords}
    return f"관심 산업·연구 저장 완료 — 분야: {field} / 키워드: {keywords}"


def save_to_reading_list(title: str, url: str = "", why: str = "") -> str:
    """관심 논문을 읽을 목록에 저장한다."""
    st.session_state.reading_list.append({"title": title, "url": url, "why": why})
    return f"읽을 목록에 추가됨: {title}"


def web_search(query: str, max_results: int = 4) -> str:
    """논문 주제의 산업 적용/기업 동향 등 현재 시점 정보를 웹에서 보강한다(키 불필요)."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        out = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                out.append(f"- {r.get('title','')}: {(r.get('body','') or '')[:160]} ({r.get('href','')})")
        return "\n".join(out) if out else "검색 결과가 없습니다."
    except Exception as e:
        return f"[웹 검색을 사용할 수 없어 모델 지식으로 답변합니다. 사유: {e}]"


def save_profile() -> str:
    """현재 관심사·읽을목록을 짧은 코드로 저장한다(재방문 시 복원용)."""
    code = st.session_state.get("profile_code") or _new_code()
    data = _load_all_profiles()
    data[code] = {
        "research_focus": st.session_state.get("research_focus"),
        "reading_list": st.session_state.get("reading_list", []),
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    ok = _save_all_profiles(data)
    st.session_state.profile_code = code
    if ok:
        return f"프로필 저장 완료. 다음에 이 코드로 복원하세요 → 프로필 코드: {code}"
    return f"프로필을 임시 저장했습니다(코드: {code}). 단, 서버 재시작 시 사라질 수 있습니다."


def load_profile(code: str) -> str:
    """프로필 코드로 관심사·읽을목록을 복원한다."""
    code = (code or "").strip().upper()
    data = _load_all_profiles()
    prof = data.get(code)
    if not prof:
        return f"코드 '{code}'에 해당하는 프로필을 찾을 수 없습니다. 코드를 확인해 주세요."
    st.session_state.research_focus = prof.get("research_focus")
    st.session_state.reading_list = prof.get("reading_list", [])
    st.session_state.profile_code = code
    rf = st.session_state.research_focus
    field = rf["field"] if rf else "미설정"
    return (f"프로필 복원 완료(코드 {code}) — 관심 분야: {field}, "
            f"읽을 논문 {len(st.session_state.reading_list)}건.")


TOOL_IMPL = {
    "find_recent_papers": find_recent_papers,
    "set_research_focus": set_research_focus,
    "save_to_reading_list": save_to_reading_list,
    "web_search": web_search,
    "save_profile": save_profile,
    "load_profile": load_profile,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_recent_papers",
            "description": "arXiv에서 최근 신규 논문을 최신순으로 검색한다. 사용자가 '이번 주/최근 논문', '추천 논문', 특정 주제의 최신 연구를 원할 때 사용한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "검색 키워드(영문 권장). 예: 'retrieval augmented generation'"},
                    "days": {"type": "integer", "description": "최근 며칠(기본 7)"},
                    "max_results": {"type": "integer", "description": "논문 수(기본 6)"},
                    "category": {"type": "string", "description": "arXiv 분류코드(선택). 예: cs.AI, cs.LG, cs.CL, stat.ML"},
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_research_focus",
            "description": "사용자의 관심 산업 또는 연구 분야와 핵심 키워드를 저장한다. 사용자가 자기 관심사를 처음 밝힐 때 사용한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "description": "관심 산업 또는 연구 분야"},
                    "keywords": {"type": "string", "description": "핵심 키워드(쉼표 구분, 학술 검색어로 확장해 저장 권장)"},
                },
                "required": ["field", "keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_reading_list",
            "description": "사용자가 관심을 보인 논문을 '읽을 목록'에 저장한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "논문 제목"},
                    "url": {"type": "string", "description": "논문 링크(선택)"},
                    "why": {"type": "string", "description": "저장 이유(선택)"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "논문 주제의 산업 적용 사례·관련 기업·제품 동향 등 현재 시점 정보를 웹에서 보강한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색어"},
                    "max_results": {"type": "integer", "description": "결과 개수(기본 4)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_profile",
            "description": "현재 관심 산업·연구와 읽을목록을 짧은 코드로 저장한다. 사용자가 '저장/기억해줘'라고 하거나 관심사·읽을목록이 갱신된 뒤 사용한다.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_profile",
            "description": "프로필 코드로 이전에 저장한 관심 산업·연구와 읽을목록을 복원한다. 사용자가 코드를 제시하며 '불러와줘/복원'을 요청할 때 사용한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "이전에 발급받은 프로필 코드"},
                },
                "required": ["code"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "너는 'GrowBridge'다. 대학원 연구(학술)와 산업 현장을 잇는 주간 논문 큐레이터 에이전트다.\n"
    "임무: 사용자의 관심 산업·연구 분야에 맞는 최신 논문을 찾아 주고, 각 논문이 '학술'에서 그치지 않고 "
    "'어떤 산업·제품·직무와 연결되는지'까지 짚어 주는 것이다.\n"
    "원칙:\n"
    "1) 사용자가 관심 산업/연구 분야를 밝히면 set_research_focus로 저장한다.\n"
    "2) 최신·추천 논문 요청 시 find_recent_papers를 호출한다.\n"
    "   - 검색어는 반드시 영문 '학술 검색어'로 변환한다.\n"
    "   - 산업·정책·경영 키워드(예: '지역 산업', '물류', '제조 혁신')는 arXiv에서 직접 매칭되지 않으므로, "
    "그 산업과 관련된 '연구 주제'로 확장한다. 예: '지역 산업'→'regional economic development, industrial clusters, "
    "urban economics'; '물류'→'supply chain optimization, vehicle routing'; '제조'→'predictive maintenance, "
    "industrial automation'.\n"
    "   - 사회과학·경제 주제는 category에 econ.GN, q-fin.EC 등을 함께 시도한다. CS/AI 주제는 cs.AI, cs.LG, cs.CL 등을 쓴다.\n"
    "3) 각 논문은 다음 형식으로 정리한다:\n"
    "   - 제목(+링크, 날짜)\n"
    "   - 핵심 기여 요약(3줄 이내, 쉬운 한국어)\n"
    "   - 산업 연결: 이 연구가 어떤 산업/제품/직무에 의미가 있고 왜 중요한지 구체적으로.\n"
    "4) 산업 적용 근거가 더 필요하면 web_search로 보강한다.\n"
    "5) 사용자가 흥미를 보인 논문은 save_to_reading_list로 저장한다.\n"
    "6) 과장 없이, 실무자가 바로 쓸 수 있게 구체적으로 답한다. 논문 내용을 지어내지 말고 검색된 초록에 근거한다.\n"
    "7) 검색 결과가 입력 분야와 동떨어져 보이면(예: 결과가 '대체'되었다고 표시되면), 무관한 논문을 억지로 추천하지 말고 "
    "그 사실을 솔직히 알린 뒤 더 구체적인 연구 키워드를 사용자에게 제안한다.\n"
    "\n"
    "[딥다이브 모드] 사용자가 특정 논문/주제를 '딥다이브' 또는 '심층 분석' 요청하면, 한 번에 끝내지 말고 "
    "다음 단계를 스스로 도구를 호출해 순서대로 수행한다:\n"
    "  (1) 대상 논문의 핵심 기여·방법을 정리한다.\n"
    "  (2) web_search로 그 기술의 '실제 적용 기업·제품·사례'를 조사한다.\n"
    "  (3) find_recent_papers로 '후속/경쟁 연구'를 추가로 찾는다.\n"
    "  (4) 위를 종합해 '연구 → 산업 전환 리포트'(요약 / 산업 적용 / 관련 기업 / 후속연구 / 한 줄 결론)로 정리한다.\n"
    "  여러 도구를 반드시 복수 회 호출해 근거를 쌓은 뒤 결론을 낸다.\n"
    "\n"
    "[프로필 기억] 관심사나 읽을목록이 갱신되면 save_profile로 저장하고 발급된 코드를 사용자에게 알려 준다. "
    "사용자가 코드를 제시하면 load_profile로 복원한다."
)


# ----------------------------------------------------------------------------
# 2. 에이전트 루프
# ----------------------------------------------------------------------------
def run_agent(api_messages, client, max_steps: int = MAX_AGENT_STEPS):
    tool_log = []
    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=GROQ_MODEL, messages=api_messages, tools=TOOLS, temperature=0.4,
        )
        msg = resp.choices[0].message
        if not getattr(msg, "tool_calls", None):
            api_messages.append({"role": "assistant", "content": msg.content or ""})
            return msg.content or "", tool_log, api_messages

        api_messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            if not isinstance(args, dict):
                args = {}
            func = TOOL_IMPL.get(name)
            result = func(**args) if func else f"알 수 없는 도구: {name}"
            tool_log.append({"name": name, "args": args, "result": result})
            api_messages.append({
                "role": "tool", "tool_call_id": tc.id, "name": name, "content": str(result),
            })

    final = client.chat.completions.create(
        model=GROQ_MODEL, messages=api_messages, temperature=0.4
    )
    text = final.choices[0].message.content or ""
    api_messages.append({"role": "assistant", "content": text})
    return text, tool_log, api_messages


# ----------------------------------------------------------------------------
# 3. 세션 상태
# ----------------------------------------------------------------------------
if "reading_list" not in st.session_state:
    st.session_state.reading_list = []
if "research_focus" not in st.session_state:
    st.session_state.research_focus = None
if "display" not in st.session_state:
    st.session_state.display = []
if "api_messages" not in st.session_state:
    st.session_state.api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
if "profile_code" not in st.session_state:
    st.session_state.profile_code = None
if "last_assistant" not in st.session_state:
    st.session_state.last_assistant = ""


# ----------------------------------------------------------------------------
# 4. 사이드바
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🌉 GrowBridge")
    st.caption("내 연구·관심사를 산업과 잇는 주간 논문 큐레이터")

    if get_api_key():
        st.success("에이전트 두뇌 연결됨 (Groq)")
    else:
        st.error("GROQ_API_KEY 미설정")
        st.caption("배포 시 Settings → Secrets 에 키를 넣으세요.")

    st.divider()
    st.markdown("#### 🧭 관심 산업 / 연구")
    rf = st.session_state.research_focus
    if rf:
        st.markdown(f"**{rf['field']}**  \n키워드: {rf['keywords']}")
    else:
        st.caption("관심 산업이나 연구를 말하면 여기에 저장됩니다.")

    st.markdown("#### 📌 읽을 논문")
    if st.session_state.reading_list:
        for p in st.session_state.reading_list:
            line = f"- {p['title']}"
            if p.get("url"):
                line += f"  \n  [링크]({p['url']})"
            st.markdown(line)
    else:
        st.caption("관심 논문이 여기에 쌓입니다.")

    st.divider()
    weekly = st.button("📚 이번 주 추천 논문 받기", use_container_width=True)
    deepdive = st.button("🔬 마지막 추천 딥다이브", use_container_width=True,
                         help="방금 추천한 논문 중 1편을 골라 멀티스텝 심층 분석합니다.")

    st.divider()
    st.markdown("#### 💾 내 기억(프로필)")
    if st.session_state.profile_code:
        st.caption(f"내 프로필 코드: **{st.session_state.profile_code}**")
    save_profile_btn = st.button("관심사·읽을목록 저장", use_container_width=True)
    if save_profile_btn:
        msg = save_profile()
        st.success(msg)
    code_in = st.text_input("프로필 코드로 복원", placeholder="예: 7F3KQ2", key="code_input")
    if st.button("복원하기", use_container_width=True):
        if code_in.strip():
            st.success(load_profile(code_in))
            st.rerun()
        else:
            st.warning("복원할 코드를 입력하세요.")

    st.divider()
    if st.button("대화 초기화", use_container_width=True):
        st.session_state.display = []
        st.session_state.api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.reading_list = []
        st.session_state.research_focus = None
        st.session_state.last_assistant = ""
        st.rerun()
    st.caption("도구: arXiv 검색 · 관심사 저장 · 읽을목록 · 웹검색 · 프로필 기억")


# ----------------------------------------------------------------------------
# 5. 메인 화면
# ----------------------------------------------------------------------------
st.title("🌉 GrowBridge")
st.markdown("##### 관심 산업·연구를 입력하면 관련 최신 논문을 찾아 **학술과 산업을 잇는** 주간 큐레이터 에이전트")

if not st.session_state.display:
    st.info(
        "관심 산업이나 연구를 말하고 추천을 받아보세요 👇\n\n"
        "- \"내 관심은 물류 산업이야. 관련 최신 연구를 찾아 산업 연결까지 정리해줘\"\n"
        "- \"자연어처리(RAG, LLM 평가) 이번 주 새 논문 추천하고 산업 연결까지 정리해줘\"\n"
        "- \"확산모델(diffusion) 논문 중 제조/헬스케어에 연결되는 걸 찾아줘\"\n\n"
        "왼쪽 **📚 이번 주 추천 논문 받기** 버튼으로 바로 시작할 수도 있어요."
    )

for turn in st.session_state.display:
    with st.chat_message(turn["role"]):
        st.markdown(turn["text"])
        if turn.get("tool_log"):
            with st.expander(f"🛠️ 에이전트가 호출한 도구 {len(turn['tool_log'])}개 보기"):
                for t in turn["tool_log"]:
                    st.markdown(f"**{t['name']}** `({t['args']})`")
                    st.code(t["result"])

# 입력: 채팅창 / '이번 주 추천' / '딥다이브' 버튼
prompt = st.chat_input("관심 분야나 요청을 입력하세요…")
if not prompt and weekly:
    rf = st.session_state.research_focus
    if rf:
        prompt = (f"내 관심사({rf['field']} / {rf['keywords']}) 기준으로 이번 주(최근 7일) "
                  "arXiv 신규 논문을 추천하고, 각 논문을 3줄 요약 + 산업 연결 관점으로 정리해줘.")
    else:
        prompt = ("이번 주(최근 7일) 주목할 만한 AI/머신러닝 arXiv 신규 논문을 추천하고, "
                  "각 논문을 3줄 요약 + 산업 연결 관점으로 정리해줘. "
                  "내 관심 분야가 무엇인지도 함께 물어봐줘.")
if not prompt and deepdive:
    if st.session_state.last_assistant.strip():
        prompt = ("딥다이브 모드로 진행해줘. 방금 네가 추천한 논문 중 가장 유망한 1편을 골라, "
                  "① 핵심 정리 → ② web_search로 실제 적용 기업·제품 조사 → "
                  "③ find_recent_papers로 후속·경쟁 연구 검색 → ④ '연구→산업 전환 리포트'로 종합해줘. "
                  "여러 도구를 단계적으로 호출해서 근거를 쌓아줘.")
    else:
        prompt = ("딥다이브 모드. 먼저 내 관심 분야의 대표 논문 1편을 find_recent_papers로 찾은 뒤, "
                  "①핵심 ②web_search로 산업 적용 ③후속 연구 ④연구→산업 전환 리포트로 종합해줘.")

if prompt:
    st.session_state.display.append({"role": "user", "text": prompt, "tool_log": []})
    with st.chat_message("user"):
        st.markdown(prompt)

    client = get_client()
    if client is None:
        with st.chat_message("assistant"):
            st.error("GROQ_API_KEY가 설정되지 않아 응답할 수 없습니다. 배포 환경의 Secrets를 확인하세요.")
    else:
        st.session_state.api_messages.append({"role": "user", "content": prompt})
        with st.chat_message("assistant"):
            with st.spinner("최신 논문을 찾고 산업 연결을 분석하는 중…"):
                try:
                    text, tool_log, st.session_state.api_messages = run_agent(
                        st.session_state.api_messages, client
                    )
                except Exception as e:
                    text, tool_log = f"오류가 발생했습니다: {e}", []
            st.markdown(text)
            if tool_log:
                with st.expander(f"🛠️ 에이전트가 호출한 도구 {len(tool_log)}개 보기"):
                    for t in tool_log:
                        st.markdown(f"**{t['name']}** `({t['args']})`")
                        st.code(t["result"])
        st.session_state.display.append(
            {"role": "assistant", "text": text, "tool_log": tool_log}
        )
        st.session_state.last_assistant = text
    st.rerun()
