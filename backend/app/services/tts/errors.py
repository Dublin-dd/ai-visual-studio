"""配音统一错误类型：各供应商都抛这个，便于上层统一捕获。"""


class TTSError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
