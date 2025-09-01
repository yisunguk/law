import os, requests
from flask import Flask, request, Response, abort

TOKEN = os.environ.get("PROXY_TOKEN", "")  # 클라이언트와 공유할 비밀 토큰(선택)
app = Flask(__name__)

def _pass_through(url: str):
    r = requests.get(
        url,
        params=request.args,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    return Response(
        r.content,
        r.status_code,
        {"Content-Type": r.headers.get("Content-Type", "text/plain; charset=utf-8")}
    )

@app.before_request
def _auth():
    if TOKEN and request.headers.get("X-Proxy-Token") != TOKEN:
        abort(401)

@app.get("/health")
def health():
    return "ok"

@app.get("/ip")
def my_ip():
    # 프록시가 바깥으로 나갈 때 보이는 집 공인 IP 확인용
    ip = requests.get("https://api.ipify.org", timeout=3).text.strip()
    return ip, 200, {"Content-Type": "text/plain; charset=utf-8"}

# 법제처 DRF 대상 프록시 엔드포인트
@app.get("/drf")
def drf():
    return _pass_through("https://www.law.go.kr/DRF/lawService.do")

@app.get("/search")
def search():
    return _pass_through("https://www.law.go.kr/DRF/lawSearch.do")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
