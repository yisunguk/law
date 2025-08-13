# 법제처 AI 챗봇

법제처 Open API와 OpenAI API를 활용하여 대한민국의 법령 정보에 대한 질문에 답변하는 Streamlit 챗봇 애플리케이션입니다.

## 주요 기능

- 🔍 **법령 검색**: 사용자 질문을 바탕으로 관련 법령을 검색
- 🤖 **AI 답변**: OpenAI GPT를 활용한 자연어 답변 생성
- 💬 **대화 기록**: 질문과 답변 기록을 세션에 저장
- 📊 **통계 정보**: 질문 수 및 최근 활동 통계 표시

## 기술 스택

- **Frontend**: Streamlit
- **API**: 법제처 Open API, OpenAI API
- **Language**: Python 3.11+

## 설치 및 실행

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일에서 OpenAI API 키를 설정하세요:
```
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. 애플리케이션 실행
```bash
streamlit run app.py
```

## 사용 방법

1. 웹 브라우저에서 애플리케이션에 접속
2. 질문 입력창에 법령 관련 질문을 입력
3. "질문하기" 버튼 클릭
4. AI가 관련 법령을 검색하고 답변을 제공

## 예시 질문

- "근로기준법에 대해 알려주세요"
- "개인정보보호법 관련 규정은?"
- "교통법규 위반 시 처벌은?"
- "상속법에서 정하는 상속 순위는?"

## API 정보

### 법제처 Open API
- **서비스**: 국가법령정보 공유서비스
- **제공기관**: 법제처
- **데이터 형식**: XML
- **문서**: [공공데이터포털](https://www.data.go.kr/data/15000115/openapi.do)

### OpenAI API
- **모델**: GPT-3.5-turbo
- **용도**: 자연어 답변 생성
- **문서**: [OpenAI API Documentation](https://platform.openai.com/docs)

## 주의사항

- 이 챗봇이 제공하는 정보는 참고용입니다
- 정확한 법률 상담은 전문가에게 문의하시기 바랍니다
- API 사용량에 따른 비용이 발생할 수 있습니다

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

