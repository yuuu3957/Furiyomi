"""FastAPI 入口：掛載 API 與靜態檔，所有錯誤統一成 {"error": {"code", "message"}}。

啟動：uvicorn main:app --reload
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

load_dotenv()  # 讀取 .env 的 OPENAI_API_KEY 等設定；要在匯入路由前執行

from api.routes import ApiError, router  # noqa: E402

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Furiyomi")
app.include_router(router)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    return _error(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    return _error(422, "invalid_request", "請求格式錯誤。")


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    return _error(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(Exception)
async def _unexpected_error(request: Request, exc: Exception):
    return _error(500, "internal_error", "伺服器發生錯誤，請稍後再試。")


# 放在最後：API 路由優先，其餘路徑交給靜態檔
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
