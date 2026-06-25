"""API 路由 — 健康管理（健身计划/饮食/体重/食物分析）"""

import os
import uuid
from flask import Blueprint, request, jsonify, g, current_app
from datetime import datetime, date
from models import db, FitnessPlan, DietPlan, ExercisePlan, WeightRecord, FoodAnalysis
from auth import login_required
from services.ai_service import analyze_food_image

health_bp = Blueprint("health", __name__)


# ═══════ 健身计划 ═══════
@health_bp.route("/api/plans/fitness", methods=["GET"])
@login_required
def get_fitness_plans():
    plans = (FitnessPlan.query
             .filter_by(user_id=g.user_id)
             .order_by(FitnessPlan.created_at.desc())
             .all())
    return jsonify({"code": 200, "data": [p.to_dict() for p in plans]})


@health_bp.route("/api/plans/fitness", methods=["POST"])
@login_required
def create_fitness_plan():
    data = request.json or {}
    plan = FitnessPlan(
        user_id=g.user_id,
        plan_name=data["plan_name"],
        goal=data.get("goal"),
        target_weight=data.get("target_weight"),
        start_date=datetime.strptime(data["start_date"], "%Y-%m-%d").date(),
        end_date=datetime.strptime(data["end_date"], "%Y-%m-%d").date(),
        weekly_frequency=data.get("weekly_frequency", 3),
        notes=data.get("notes"),
    )
    db.session.add(plan)
    db.session.commit()
    return jsonify({"code": 200, "data": plan.to_dict()}), 201


@health_bp.route("/api/plans/fitness/<int:plan_id>", methods=["PUT"])
@login_required
def update_fitness_plan(plan_id):
    plan = db.session.get(FitnessPlan, plan_id)
    if not plan or plan.user_id != g.user_id:
        return jsonify({"code": 404, "message": "计划不存在"}), 404
    data = request.json or {}
    for f in ["plan_name", "goal", "target_weight", "weekly_frequency", "notes", "status"]:
        if f in data:
            setattr(plan, f, data[f])
    if "start_date" in data:
        plan.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    if "end_date" in data:
        plan.end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
    db.session.commit()
    return jsonify({"code": 200, "data": plan.to_dict()})


@health_bp.route("/api/plans/fitness/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_fitness_plan(plan_id):
    plan = db.session.get(FitnessPlan, plan_id)
    if not plan or plan.user_id != g.user_id:
        return jsonify({"code": 404, "message": "计划不存在"}), 404
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"code": 200, "message": "已删除"})


# ═══════ 饮食计划 ═══════
@health_bp.route("/api/plans/diet", methods=["GET"])
@login_required
def get_diet_plans():
    plans = (DietPlan.query
             .filter_by(user_id=g.user_id)
             .order_by(DietPlan.created_at.desc())
             .all())
    return jsonify({"code": 200, "data": [p.to_dict() for p in plans]})


@health_bp.route("/api/plans/diet", methods=["POST"])
@login_required
def create_diet_plan():
    data = request.json or {}
    plan = DietPlan(
        user_id=g.user_id,
        plan_name=data["plan_name"],
        content=data.get("content"),
        daily_calorie_target=data.get("daily_calorie_target"),
        protein_target=data.get("protein_target"),
        carbs_target=data.get("carbs_target"),
        fat_target=data.get("fat_target"),
        date=datetime.strptime(data.get("date", str(date.today())), "%Y-%m-%d").date(),
        notes=data.get("notes"),
    )
    db.session.add(plan)
    db.session.commit()
    return jsonify({"code": 200, "data": plan.to_dict()}), 201


@health_bp.route("/api/plans/diet/<int:plan_id>", methods=["PUT"])
@login_required
def update_diet_plan(plan_id):
    plan = db.session.get(DietPlan, plan_id)
    if not plan or plan.user_id != g.user_id:
        return jsonify({"code": 404, "message": "计划不存在"}), 404
    data = request.json or {}
    for f in ["plan_name", "content", "daily_calorie_target", "protein_target",
              "carbs_target", "fat_target", "notes"]:
        if f in data:
            setattr(plan, f, data[f])
    if "date" in data:
        plan.date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    db.session.commit()
    return jsonify({"code": 200, "data": plan.to_dict()})


@health_bp.route("/api/plans/diet/<int:plan_id>", methods=["DELETE"])
@login_required
def delete_diet_plan(plan_id):
    plan = db.session.get(DietPlan, plan_id)
    if not plan or plan.user_id != g.user_id:
        return jsonify({"code": 404, "message": "计划不存在"}), 404
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"code": 200, "message": "已删除"})


# ═══════ 锻炼计划 ═══════
@health_bp.route("/api/plans/exercise", methods=["GET"])
@login_required
def get_exercise_plans():
    fitness_plan_id = request.args.get("fitness_plan_id", type=int)
    query = ExercisePlan.query.filter_by(user_id=g.user_id)
    if fitness_plan_id:
        query = query.filter_by(fitness_plan_id=fitness_plan_id)
    plans = query.order_by(ExercisePlan.day_of_week, ExercisePlan.id).all()
    return jsonify({"code": 200, "data": [p.to_dict() for p in plans]})


@health_bp.route("/api/plans/exercise", methods=["POST"])
@login_required
def create_exercise_plan():
    data = request.json or {}
    plan = ExercisePlan(
        user_id=g.user_id,
        fitness_plan_id=data.get("fitness_plan_id"),
        exercise_name=data["exercise_name"],
        sets=data.get("sets", 3),
        reps=data.get("reps", 12),
        duration_minutes=data.get("duration_minutes"),
        rest_seconds=data.get("rest_seconds", 60),
        day_of_week=data.get("day_of_week"),
        content=data.get("content"),
        notes=data.get("notes"),
    )
    db.session.add(plan)
    db.session.commit()
    return jsonify({"code": 200, "data": plan.to_dict()}), 201


# ═══════ 体重记录 ═══════
@health_bp.route("/api/weight", methods=["GET"])
@login_required
def get_weight_records():
    records = (WeightRecord.query
               .filter_by(user_id=g.user_id)
               .order_by(WeightRecord.record_date.desc())
               .limit(90)
               .all())
    return jsonify({"code": 200, "data": [r.to_dict() for r in records]})


@health_bp.route("/api/weight", methods=["POST"])
@login_required
def create_weight_record():
    data = request.json or {}
    record = WeightRecord(
        user_id=g.user_id,
        weight=data["weight"],
        body_fat_pct=data.get("body_fat_pct"),
        record_date=datetime.strptime(data.get("record_date", str(date.today())), "%Y-%m-%d").date(),
        notes=data.get("notes"),
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"code": 200, "data": record.to_dict()}), 201


# ═══════ 食物分析 ═══════
@health_bp.route("/api/food/analyze", methods=["POST"])
@login_required
def analyze_food():
    if "file" not in request.files:
        return jsonify({"code": 400, "message": "请上传食物图片"}), 400

    file = request.files["file"]
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{uuid.uuid4().hex}{ext}"
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], "food")
    os.makedirs(folder, exist_ok=True)
    image_path = os.path.join(folder, filename)
    file.save(image_path)

    result = analyze_food_image(image_path)

    record = FoodAnalysis(
        user_id=g.user_id,
        image_path=image_path,
        food_name=result.get("food_name"),
        calories=result.get("calories"),
        protein=result.get("protein"),
        carbs=result.get("carbs"),
        fat=result.get("fat"),
        fiber=result.get("fiber"),
        analysis_text=result.get("analysis"),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({"code": 200, "data": {**result, "record_id": record.id}})


@health_bp.route("/api/food/records", methods=["GET"])
@login_required
def get_food_records():
    records = (FoodAnalysis.query
               .filter_by(user_id=g.user_id)
               .order_by(FoodAnalysis.created_at.desc())
               .limit(50)
               .all())
    return jsonify({"code": 200, "data": [r.to_dict() for r in records]})
