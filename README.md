# 🌉 GrowBridge — 학술-산업 연결 주간 논문 큐레이터 AI 에이전트

관심 분야를 말하면 ① 최근 arXiv 논문을 검색 → ② 각 논문을 3줄 요약 →
③ **"이 연구가 어떤 산업/제품/직무로 이어지는가(Industry Bridge)"** 까지 번역해 주는 에이전트.
대학원(학술)에서 산업으로 넘어가는 사람의 관점을 그대로 제품화했다.
Python + Streamlit + Groq(Llama 3.3 70B) + arXiv API로 구성되며, 누구나 접속 가능한 공개 URL로 배포된다.

---

## 0. 파일 구성
```
growbridge/
├─ app.py               # 에이전트 본체 (도구 + 에이전트 루프 + UI)
├─ requirements.txt     # 의존성 (streamlit, openai, ddgs, arxiv)
└─ .streamlit/
   └─ config.toml       # 화면 테마(스크린샷용)
```

## 1. Groq API 키 발급 (무료, 카드 불필요) — 약 2분
1. https://console.groq.com 가입(이메일/Google/GitHub) → **API Keys → Create API Key** → 키(`gsk_...`) 복사.
   - 무료 티어(약 30요청/분·1,000요청/일)면 시연·소수 접속에 충분.

## 2. GitHub 저장소에 코드 올리기 — 약 3분
1. github.com → **New repository** (예: `growbridge`), **Public**.
2. `app.py`, `requirements.txt`, `.streamlit/config.toml` 업로드/커밋.

> ⚠️ **API 키는 코드/깃허브에 절대 넣지 말 것.** 아래 4단계 Secrets로만 주입한다.

## 3. Streamlit Community Cloud 배포 — 약 3분
1. https://share.streamlit.io → GitHub 로그인.
2. **Create app → Deploy a public app from GitHub**
   - Repository: `본인계정/growbridge` · Branch: `main` · Main file path: `app.py`
   - App URL: 원하는 주소(이게 제출용 공개 URL).
3. **Advanced settings → Secrets** 에:
   ```toml
   GROQ_API_KEY = "gsk_복사한_키"
   ```
4. **Deploy** → 몇 분 후 공개 URL 생성.

## 4. 로컬 실행(선택)
```bash
pip install -r requirements.txt
export GROQ_API_KEY="gsk_..."      # PowerShell: $env:GROQ_API_KEY="gsk_..."
streamlit run app.py
```

---

## 5. 제출 전 체크리스트 (과제 안내문 기준)
- [ ] 시크릿 창/다른 기기에서 URL 접속 → 정상 실행되는가
- [ ] 링크가 Public/Open 인가 (Streamlit public app이면 충족)
- [ ] 본인 PC·계정이 아닌 환경에서도 접속되는가
- [ ] URL 클릭 시 에이전트가 실제 응답하는가
- [ ] 메인 화면 + 동작 화면 캡처 ('🛠️ 도구 호출 보기' 펼친 상태)

## 6. 스크린샷 팁
- **메인 화면**: 첫 접속 시 예시 안내 화면.
- **동작 화면**: 예) *"내 분야는 자연어처리(RAG, LLM 평가)야. 이번 주 새 논문 추천하고 산업 연결까지 정리해줘"* →
  답변에 **논문 요약 + 🌉 산업 연결**이 보이고, 아래 **🛠️ 도구 호출 보기**(find_recent_papers 등)를 펼친 상태로 캡처.
  → arXiv 검색이라는 외부 도구를 실제로 호출했음이 드러나 "챗봇이 아닌 에이전트"임이 증명된다.

## 7. (확장) 진짜 '매주 자동' 만들기
배포된 무료 앱은 요청이 올 때만 동작하므로, 현재는 사용자가 열거나 **'이번 주 추천' 버튼**을 누르면
최근 7일 논문을 큐레이션한다(=on-demand 주간 다이제스트). 완전 자동 발송을 원하면:
- **GitHub Actions cron**으로 주 1회 스크립트를 돌려 결과를 Slack/이메일로 push,
- 또는 Streamlit과 분리된 작은 워커(예: cron + SMTP)로 발송.
과제 범위에서는 on-demand로 충분하며, 위 자동화는 향후 확장으로 보고서에 적어 두면 좋다.

## 8. 흔한 오류
| 증상 | 해결 |
|------|------|
| `GROQ_API_KEY 미설정` | Secrets에 키 입력 후 **Reboot app** |
| 빌드 실패(ModuleNotFound) | `requirements.txt`가 저장소 루트에 있는지 확인 |
| 논문이 비어 보임 | 최근 7일 내 신규가 없으면 자동으로 최신 논문 대체(정상) |
| 응답 느림/429 | 무료 한도 초과 → 잠시 후 재시도 |
