"""Flask 应用入口"""

import os
from flask import Flask
from flask_cors import CORS
from config import DATABASE_PATH, UPLOAD_FOLDER
from models import db
from routes.user import user_bp
from routes.fitness import fitness_bp
from routes.health import health_bp


def create_app() -> Flask:
    app = Flask(__name__)

    # 配置
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "group04-fitness-rehab-2026")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

    # 初始化
    CORS(app, supports_credentials=True)
    db.init_app(app)

    # 注册蓝图
    app.register_blueprint(user_bp)
    app.register_blueprint(fitness_bp)
    app.register_blueprint(health_bp)

    # 确保上传目录和数据库存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    with app.app_context():
        db.create_all()
        # 创建默认管理员
        from models import User
        from auth import hash_password
        if not User.query.filter_by(username="admin").first():
            admin = User(
                username="admin",
                password_hash=hash_password("admin123"),
                nickname="管理员",
                role="admin",
            )
            db.session.add(admin)
            db.session.commit()
            print("[INFO] 默认管理员创建: admin / admin123")

    @app.route("/api/health")
    def health_check():
        return {"code": 200, "message": "Fitness System API is running"}

    return app


if __name__ == "__main__":
    app = create_app()
    print("=" * 50)
    print("  智能康复+健身辅助系统 API")
    print("  http://localhost:5000")
    print("  默认管理员: admin / admin123")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
