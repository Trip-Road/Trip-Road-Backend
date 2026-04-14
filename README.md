1. 환경 변수 설정
프로젝트 최상위 폴더에 .env 파일 넣기

2. 터미널에서 아래 내용 실행
python -m venv venv
source venv\Scripts\activate
pip install -r requirements.txt

3. 서버 실행
uvicorn main:app --reload


API 주소: http://127.0.0.1:8000

Interactive API Docs (Swagger): http://127.0.0.1:8000/docs
