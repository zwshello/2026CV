"""JWT 身份认证模块"""

import jwt
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
from config import SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_HOURS


def hash_password(password: str) -> str:
    """哈希密码"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: int, role: str) -> str:
    """生成 JWT token"""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码 JWT token，返回 payload 或 None"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def login_required(f):
    """装饰器：要求登录（支持 Bearer Token 和 ?token= 参数）"""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            token = request.args.get("token")

        if not token:
            return jsonify({"code": 401, "message": "请先登录"}), 401

        payload = decode_token(token)
        if payload is None:
            return jsonify({"code": 401, "message": "登录已过期，请重新登录"}), 401

        g.user_id = payload["user_id"]
        g.role = payload["role"]
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """装饰器：要求管理员权限"""

    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if g.role != "admin":
            return jsonify({"code": 403, "message": "需要管理员权限"}), 403
        return f(*args, **kwargs)

    return decorated
