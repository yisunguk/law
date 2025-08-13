# ⚖️ 법제처 AI 챗봇

법제처 Open API와 OpenAI를 활용한 지능형 법령 상담 서비스입니다.

## 🚀 주요 기능

- **법령 검색**: 법제처 Open API를 통한 실시간 법령 정보 검색
- **AI 답변**: OpenAI GPT 모델을 활용한 지능형 법령 상담
- **스트리밍 응답**: ChatGPT와 유사한 실시간 답변 생성
- **사용자 친화적 UI**: 모던하고 직관적인 채팅 인터페이스
- **대화 기록**: 질문과 답변 히스토리 저장 및 관리

## 🛠️ 기술 스택

- **Frontend**: Streamlit
- **AI**: OpenAI GPT-3.5-turbo
- **API**: 법제처 Open API
- **Language**: Python 3.8+

## 📋 설치 및 실행

### 1. 저장소 클론
```bash
git clone <repository-url>
cd law
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

#### Streamlit Cloud 사용 시
Streamlit Cloud의 Secrets에서 다음을 설정:
```toml
OPENAI_API_KEY = "your-openai-api-key"
```

#### 로컬 실행 시
`.env` 파일 생성:
```env
OPENAI_API_KEY=your-openai-api-key
```

### 5. 앱 실행
```bash
streamlit run app.py
```

## 🔑 API 키 설정

### OpenAI API 키
- [OpenAI Platform](https://platform.openai.com/)에서 API 키 발급
- Streamlit Cloud의 Secrets에 설정하거나 환경 변수로 설정

### 법제처 Open API
- 법제처 Open API 키는 코드에 이미 포함되어 있음
- 필요시 [법제처 Open API](https://www.law.go.kr/)에서 새로운 키 발급

## 💡 사용 방법

1. **질문 입력**: 법령에 대한 질문을 입력창에 입력
2. **전송**: Enter 키를 누르거나 전송 버튼 클릭
3. **AI 답변**: AI가 관련 법령을 검색하고 답변 생성
4. **법령 정보**: 관련 법령의 상세 정보 확인

## 📱 UI 특징

- **ChatGPT 스타일**: 현대적이고 직관적인 채팅 인터페이스
- **반응형 디자인**: 모바일과 데스크톱 모두 지원
- **스트리밍 효과**: 실시간으로 답변이 생성되는 시각적 효과
- **사이드바**: 사용 안내와 통계 정보 제공

## 🔧 코드 구조

```
app.py                 # 메인 애플리케이션 파일
requirements.txt       # Python 패키지 의존성
README.md             # 프로젝트 문서
```

### 주요 함수

- `search_law_data()`: 법제처 API 호출 및 법령 검색
- `generate_ai_response_stream()`: OpenAI API를 통한 스트리밍 답변 생성
- `display_law_info()`: 법령 정보 표시
- `save_conversation()`: 대화 내용 저장

## ⚠️ 주의사항

- 제공되는 정보는 참고용이며, 정확한 법률 상담은 전문가에게 문의
- OpenAI API 사용량에 따른 비용 발생 가능
- 법제처 API 호출 제한이 있을 수 있음

## 📄 라이선스

이 프로젝트는 교육 및 연구 목적으로 개발되었습니다.

## 🤝 기여

버그 리포트나 기능 제안은 이슈로 등록해 주세요.

## 📞 문의

프로젝트 관련 문의사항이 있으시면 이슈로 등록해 주세요. 