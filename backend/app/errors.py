from fastapi.responses import JSONResponse


def err(status_code: int, code: str, message: str) -> JSONResponse:
    """统一错误结构：{"error": {"code", "message"}}。不泄露堆栈。"""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
