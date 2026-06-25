"""阿里云百炼 Qwen-VL-Plus 多模态 AI 分析服务"""

import base64
import json
import requests
from config import QWEN_API_KEY, QWEN_API_URL, QWEN_MODEL


def _encode_image(image_path: str) -> str:
    """将图片编码为 base64 data URL"""
    import mimetypes
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    return f"data:{mime};base64,{data}"


def analyze_fitness_image(image_path: str, exercise_type: str = None,
                          pose_info: dict = None) -> dict:
    """
    使用 Qwen-VL-Plus 分析健身动作图片
    返回 { analysis_text, score, suggestions, errors }
    """
    if not QWEN_API_KEY or QWEN_API_KEY == "your-api-key-here":
        return _mock_analysis(exercise_type)

    prompt = _build_prompt(exercise_type, pose_info)

    image_url = _encode_image(image_path)

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一位专业的健身教练和运动康复专家。请根据用户上传的健身动作图片，分析动作的规范性、指出存在的问题并给出改进建议。请以结构化 JSON 格式回复。"
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ],
        "max_tokens": 1000,
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(QWEN_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _parse_ai_response(content, exercise_type)
        else:
            return _mock_analysis(exercise_type, f"AI 服务返回错误: {resp.status_code}")
    except Exception as e:
        return _mock_analysis(exercise_type, f"AI 服务连接失败: {str(e)}")


def analyze_food_image(image_path: str) -> dict:
    """使用 Qwen-VL-Plus 分析食物图片的营养成分"""
    if not QWEN_API_KEY or QWEN_API_KEY == "your-api-key-here":
        return _mock_food_analysis()

    prompt = """请识别这张图片中的食物，分析其营养成分。以 JSON 格式返回：
{
  "food_name": "食物名称",
  "calories": 热量(kcal),
  "protein": 蛋白质(g),
  "carbs": 碳水化合物(g),
  "fat": 脂肪(g),
  "fiber": 膳食纤维(g),
  "analysis": "简要营养分析和饮食建议"
}"""

    image_url = _encode_image(image_path)

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一位专业的营养师。请根据用户上传的食物图片，识别食物并分析其营养成分。以 JSON 格式回复。"
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ],
        "max_tokens": 800,
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(QWEN_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            return _parse_food_response(content)
        else:
            return _mock_food_analysis()
    except Exception:
        return _mock_food_analysis()


def _build_prompt(exercise_type: str, pose_info: dict) -> str:
    cfg = {
        "squat": "深蹲",
        "pushup": "俯卧撑",
        "pullup": "引体向上",
        "situp": "仰卧起坐",
        "bicep_curl": "哑铃弯举",
        "shoulder_press": "肩部推举",
        "dumbbell_fly": "哑铃飞鸟",
    }
    ex_name = cfg.get(exercise_type, "健身动作")

    prompt = f"""请分析这张{ex_name}动作图片。以 JSON 格式返回：
{{
  "exercise_detected": "检测到的动作类型",
  "is_correct": true/false (动作是否规范),
  "score": 0-100之间的评分,
  "analysis": "详细分析",
  "errors": ["存在问题1", "问题2"],
  "suggestions": ["改进建议1", "改进建议2"]
}}"""

    if pose_info:
        prompt += f"\n\n姿态检测数据：关节角度={pose_info.get('angle')}°, 状态={pose_info.get('phase', 'unknown')}"

    return prompt


def _parse_ai_response(content: str, exercise_type: str) -> dict:
    """解析 AI 返回的 JSON"""
    try:
        # 尝试提取 JSON 块
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        result = json.loads(content.strip())
        return {
            "analysis_text": result.get("analysis", content),
            "score": float(result.get("score", 75)),
            "suggestions": result.get("suggestions", []),
            "errors": result.get("errors", []),
            "is_correct": result.get("is_correct", True),
            "raw_response": content,
        }
    except (json.JSONDecodeError, IndexError):
        return {
            "analysis_text": content,
            "score": 75.0,
            "suggestions": ["请保持标准动作姿势"],
            "errors": [],
            "is_correct": True,
            "raw_response": content,
        }


def _parse_food_response(content: str) -> dict:
    """解析食物分析返回"""
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        result = json.loads(content.strip())
        return {
            "food_name": result.get("food_name", "未知食物"),
            "calories": float(result.get("calories", 0)),
            "protein": float(result.get("protein", 0)),
            "carbs": float(result.get("carbs", 0)),
            "fat": float(result.get("fat", 0)),
            "fiber": float(result.get("fiber", 0)),
            "analysis": result.get("analysis", content),
        }
    except (json.JSONDecodeError, IndexError):
        return {
            "food_name": "未能识别",
            "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0,
            "analysis": content,
        }


def _mock_analysis(exercise_type: str = None, note: str = "") -> dict:
    """无 API Key 时的模拟返回"""
    return {
        "analysis_text": f"[模拟分析] AI 模型未连接 — 请配置阿里云百炼 API Key。{note}",
        "score": 78.0,
        "suggestions": ["保持动作节奏稳定", "注意呼吸配合", "核心收紧保持身体稳定"],
        "errors": [],
        "is_correct": True,
    }


def _mock_food_analysis() -> dict:
    return {
        "food_name": "示例食物 (模拟)",
        "calories": 350.0,
        "protein": 25.0,
        "carbs": 40.0,
        "fat": 12.0,
        "fiber": 5.0,
        "analysis": "[模拟] AI 服务未连接 — 请配置 API Key 后获取准确分析结果。",
    }
