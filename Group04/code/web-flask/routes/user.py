"""API 路由 — 用户认证"""

from flask import Blueprint, request, jsonify, g
from models import db, User
from auth import hash_password, verify_password, create_token, login_required

user_bp = Blueprint("user", __name__)


@user_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")
    nickname = data.get("nickname", username)

    if not username or not password:
        return jsonify({"code": 400, "message": "用户名和密码不能为空"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"code": 409, "message": "用户名已存在"}), 409

    user = User(
        username=username,
        password_hash=hash_password(password),
        nickname=nickname,
        role="user",
        email=data.get("email"),
        phone=data.get("phone"),
        age=data.get("age"),
        gender=data.get("gender"),
        height=data.get("height"),
        weight=data.get("weight"),
    )
    db.session.add(user)
    db.session.commit()

    token = create_token(user.id, user.role)
    return jsonify({"code": 200, "message": "注册成功", "data": {
        "token": token, "user": user.to_dict()
    }}), 201


@user_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password", "")

    user = User.query.filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({"code": 401, "message": "用户名或密码错误"}), 401

    token = create_token(user.id, user.role)
    return jsonify({"code": 200, "message": "登录成功", "data": {
        "token": token, "user": user.to_dict()
    }})


@user_bp.route("/api/auth/profile", methods=["GET"])
@login_required
def profile():
    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({"code": 404, "message": "用户不存在"}), 404
    return jsonify({"code": 200, "data": user.to_dict()})


@user_bp.route("/api/auth/profile", methods=["PUT"])
@login_required
def update_profile():
    user = db.session.get(User, g.user_id)
    data = request.json or {}
    for field in ["nickname", "email", "phone", "age", "gender", "height", "weight", "avatar"]:
        if field in data:
            setattr(user, field, data[field])
    db.session.commit()
    return jsonify({"code": 200, "data": user.to_dict()})
