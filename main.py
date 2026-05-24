from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

import os
import json
import random
import time
import asyncio
from pathlib import Path
import re
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Set, Tuple
import base64
import tempfile
from datetime import datetime
import hashlib
import aiohttp

# =========================================
# APP
# =========================================

app = FastAPI(title="Pen Platform - V10 AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# CONFIG
# =========================================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AI_ENABLED = bool(OPENROUTER_API_KEY)

# =========================================
# AI EXPLANATION GENERATOR
# =========================================

async def generate_ai_explanation(question_text: str, user_answer: str, correct_answer: str, explanation: str, skill: str) -> str:
    """Generate AI explanation using OpenRouter"""
    if not AI_ENABLED:
        return None
    
    skill_arabic = get_skill_arabic(skill)
    
    prompt = f"""أنت مدرس لغة عربية خبير للثانوية العامة في مصر. اشرح للطالب إجابته بأسلوب واضح ومختصر (3-5 أسطر).

السؤال: {question_text[:300]}

إجابة الطالب: {user_answer}
الإجابة الصحيحة: {correct_answer}

المهارة: {skill_arabic}

الشرح الموجود: {explanation[:200] if explanation else 'لا يوجد'}

المطلوب:
1. اشرح لماذا الإجابة خطأ (أو صح) بأسلوب بسيط
2. أعط قاعدة سريعة أو نصيحة للطالب
3. استخدم أسلوب مشجع (زي مدرس حقيقي)
4. خلي الشرح باللهجة المصرية أو عربي فصحى بسيط
5. أقصى طول 4 أسطر

الشرح:"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [
                        {"role": "system", "content": "أنت مدرس لغة عربية خبير. اشرح بطريقة مختصرة وواضحة ومشجعة. استخدم لغة بسيطة."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 200
                },
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                }
            ) as response:
                data = await response.json()
                ai_text = data["choices"][0]["message"]["content"]
                return ai_text.strip()
    except Exception as e:
        print(f"❌ AI Error: {e}")
        return None

async def generate_ai_feedback(question_text: str, user_answer: str, correct_answer: str, is_correct: bool, skill: str, explanation: str) -> str:
    """Generate AI feedback for the answer"""
    if not AI_ENABLED:
        return None
    
    skill_arabic = get_skill_arabic(skill)
    result_text = "صحيحة" if is_correct else "خاطئة"
    
    prompt = f"""أنت مدرس لغة عربية مشجع للثانوية العامة. الطالب جاوب إجابة {result_text}.

السؤال: {question_text[:250]}
إجابة الطالب: {user_answer}
الإجابة الصحيحة: {correct_answer}
المهارة: {skill_arabic}

المطلوب (3-4 أسطر فقط):
{"- امدح الطالب وشجعه" if is_correct else "- اشرح بلطف لماذا الإجابة خطأ"}
- أعط نصيحة سريعة أو قاعدة
- استخدم أسلوب دافئ ومشجع
- باللهجة المصرية أو عربي بسيط

الرد:"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json={
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [
                        {"role": "system", "content": "أنت مدرس لغة عربية مشجع. ردودك مختصرة ودافئة ومفيدة."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 180
                },
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                }
            ) as response:
                data = await response.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"❌ AI Feedback Error: {e}")
        return None

# =========================================
# COMPLETE SKILL MAPPING
# =========================================

SKILL_ALIASES = {
    "بلاغة": ["بلاغة", "صورة بيانية", "محسنات بديعية", "تصوير", "لغة مجازية", "تشبيه", "استعارة", "كناية", "مجاز", "جناس", "طباق", "مقابلة", "سجع", "تورية", "أساليب"],
    "نحو": ["نحو", "إعراب", "صرف", "تطبيقات نحوية", "تركيب", "تحليل نحوي", "بنية جملة", "اشتقاق", "مشتقات", "مصادر", "اسم فاعل", "اسم مفعول", "صيغ مبالغة", "مبتدأ", "خبر", "فاعل", "مفعول", "حال", "تمييز", "مضاف"],
    "أدب": ["أدب", "مدارس أدبية", "تاريخ أدب", "حركات أدبية", "كلاسيكية", "رومانسية", "واقعية", "ديوان", "أبولو"],
    "قراءة": ["قراءة", "قراءة نقدية", "فهم قرائي", "تحليل نص", "تحديد فكرة", "بناء النص", "ترابط الأفكار"],
    "مفردات": ["مفردات", "معاني", "ترادف", "تضاد", "معنى", "كلمات"],
    "استنتاج": ["استنتاج", "استدلال", "استنباط", "تحليل", "تركيب", "تفسير"],
    "فكرة": ["فكرة", "فكرة رئيسية", "مغزى", "أفكار"],
    "دليل": ["دليل", "أدلة", "شاهد", "قرينة", "برهان"],
    "غرض": ["غرض", "هدف", "رسالة"],
    "مقارنة": ["مقارنة", "موازنة", "شبه", "اختلاف"],
    "تعبير": ["تعبير", "كتابة", "إنشاء"],
}

SKILL_ARABIC_MAP = {
    "parsing": "الإعراب", "interpretation": "استنتاج", "evidence_extraction": "دليل",
    "literary_school_identification": "أدب", "text_structure_analysis": "بناء النص",
    "topical_coherence": "ترابط الأفكار", "grammar_usage": "نحو", "application": "تطبيق",
    "implicit_reasoning": "استنتاج", "inference": "استدلال", "deduction": "استنباط",
    "synthesis": "تحليل", "prediction": "توقع", "emotional_tone_inference": "نبرة",
    "grammar_identification": "نحو", "grammar_transformation": "تحويل",
    "grammar_rules_application": "تطبيق نحوي", "morphology": "صرف",
    "poetic_imagery_analysis": "صورة بيانية", "rhetoric_analysis": "بلاغة",
    "rhetorical_device_analysis": "محسنات", "idea_identification": "فكرة",
    "main_idea_detection": "فكرة رئيسية", "vocabulary_context": "مفردات",
    "contextual_vocabulary": "مفردات", "definition_extraction": "معنى",
    "compare_and_contrast": "مقارنة", "evaluation": "تقييم", "text_analysis": "تحليل نص",
    "critical_reading": "قراءة", "purpose_identification": "غرض",
    "syntax_analysis": "إعراب", "semantic_analysis": "دلالة", "stylistic_analysis": "أسلوب",
    "logical_structure": "منطق", "argumentation": "حجاج", "coherence": "ترابط",
    "cohesion": "تماسك", "text_typology": "أنماط", "discourse_analysis": "خطاب",
    "morphology_identification": "صرف",
    "بلاغة": "بلاغة", "نحو": "نحو", "إعراب": "الإعراب", "صرف": "صرف",
    "أدب": "أدب", "قراءة": "قراءة", "مفردات": "مفردات", "استنتاج": "استنتاج",
    "فكرة": "فكرة", "دليل": "دليل", "غرض": "غرض", "مقارنة": "مقارنة",
    "تفسير": "استنتاج", "تعبير": "تعبير",
}

SKILL_EMOJI = {
    "استنتاج": "🧠", "نحو": "📝", "الإعراب": "📝", "صرف": "📝",
    "بلاغة": "✨", "أدب": "📚", "قراءة": "📖", "مفردات": "📖",
    "تعبير": "✍️", "فكرة": "💡", "دليل": "🔍", "غرض": "🎯",
    "مقارنة": "⚖️", "فكرة رئيسية": "⭐", "بناء النص": "📖",
    "ترابط الأفكار": "🔗", "تطبيق": "🔧", "تقييم": "📊",
    "توقع": "🔮", "تحليل": "🧩", "استدلال": "🔎", "استنباط": "💡",
    "تحويل": "🔄", "تطبيق نحوي": "✅", "صورة بيانية": "🎨",
    "محسنات": "✨", "نبرة": "🎭", "معنى": "📝", "دلالة": "💭",
    "أسلوب": "✨", "منطق": "🧩", "حجاج": "💬", "ترابط": "🔗",
    "تماسك": "🔗", "أنماط": "📖", "خطاب": "📖",
}

SKILL_TEACHING_TIPS = {
    "صورة بيانية": {
        "استعارة مكنية": "حذف المشبه به وترك صفة من صفاته",
        "استعارة تصريحية": "ذكر المشبه به صراحة وحذف المشبه",
        "تشبيه": "وجود أداة تشبيه + مشبه + مشبه به",
        "كناية": "ذكر شيء وإرادة لازم معناه",
    },
    "بلاغة": {
        "استعارة مكنية": "اسأل: هل المشبه موجود؟ هل فيه صفات المشبه به؟",
        "استعارة تصريحية": "اسأل: هل المشبه به مذكور بوضوح؟",
    },
    "صرف": {
        "مصدر": "كل مصدر على وزن (مفاعلة) من فعل رباعي (فاعل)",
    },
}

SKILL_RECOMMENDATIONS = {
    "بلاغة": ["التشبيه", "الاستعارة المكنية", "الاستعارة التصريحية", "المجاز المرسل", "الكناية"],
    "نحو": ["المبتدأ والخبر", "الفاعل", "المفعول به", "الحال", "التمييز"],
    "الإعراب": ["إعراب الفعل المضارع", "الأسماء الخمسة", "المثنى والجمع"],
    "صرف": ["المجرد والمزيد", "المصادر", "المشتقات", "اسم الفاعل", "اسم المفعول"],
    "أدب": ["المدرسة الكلاسيكية", "المدرسة الرومانسية", "المدرسة الواقعية"],
    "قراءة": ["تحليل النص", "استخراج الأفكار", "نقد المحتوى"],
    "مفردات": ["المعاني في السياق", "الترادف", "التضاد"],
    "استنتاج": ["الاستنتاج", "الاستدلال", "قراءة ما بين السطور"],
}

def resolve_skills(query: str) -> List[str]:
    query_lower = query.lower().strip()
    for arabic_name, skills in SKILL_ALIASES.items():
        if arabic_name in query_lower: return skills
    for eng, ar in SKILL_ARABIC_MAP.items():
        if ar in query_lower: return [eng]
    return []

def get_skill_arabic(skill: str) -> str:
    if not skill or skill == "عام": return "عام"
    if skill in SKILL_ARABIC_MAP: return SKILL_ARABIC_MAP[skill]
    skill_lower = skill.lower()
    for key, value in SKILL_ARABIC_MAP.items():
        if key.lower() == skill_lower: return value
    return skill

def get_skill_display(skill: str) -> str:
    arabic = get_skill_arabic(skill)
    emoji = SKILL_EMOJI.get(arabic, "📖")
    return f"{emoji} {arabic}"

def get_skill_category(skill: str) -> str:
    arabic = get_skill_arabic(skill)
    for category in SKILL_ALIASES.keys():
        if arabic == category: return category
    return arabic

# =========================================
# STUDENT SERVICE
# =========================================

class StudentService:
    _rtdb = None
    _local_db: Dict = {"users": {}, "reported_questions": []}
    _initialized = False
    
    @classmethod
    def initialize(cls):
        if cls._initialized: return
        cls._initialized = True
        try:
            import firebase_admin
            from firebase_admin import credentials
            b64 = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")
            if b64:
                decoded = base64.b64decode(b64).decode("utf-8")
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                    f.write(decoded)
                cred = credentials.Certificate(f.name)
                os.unlink(f.name)
                try: firebase_admin.get_app()
                except ValueError: firebase_admin.initialize_app(cred, {"databaseURL": "https://forme-6167f-default-rtdb.firebaseio.com"})
                from firebase_admin import db
                cls._rtdb = db
                print("✅ Firebase ready!")
        except ImportError: print("⚠️ firebase_admin not installed")
        except Exception as e: print(f"⚠️ Firebase: {e}")
    
    @classmethod
    def _now_iso(cls) -> str: return datetime.now().isoformat()
    @classmethod
    def _now_ts(cls) -> int: return int(datetime.now().timestamp() * 1000)
    
    @classmethod
    def create_user(cls, username: str, password: str, name: str = "") -> Dict:
        username = username.strip().lower()
        if cls._rtdb:
            try:
                if cls._rtdb.reference(f"users/{username}").get(): return {"error": "اسم المستخدم موجود بالفعل"}
            except: pass
        if username in cls._local_db["users"]: return {"error": "اسم المستخدم موجود بالفعل"}
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        user_data = {"username": username, "password": hashed_password, "name": name or username, "created_at": cls._now_iso(), "chat_id": f"user_{username}", "asked_questions": [], "total_score": 0, "total_exams": 0, "total_questions_answered": 0, "skill_stats": {}, "recent_exams": [], "greeted": False, "questions_since_analysis": 0, "last_wrong_skills": []}
        cls._local_db["users"][username] = user_data
        if cls._rtdb:
            try: cls._rtdb.reference(f"users/{username}").set(user_data)
            except: pass
        return {"success": True, "username": username, "chat_id": f"user_{username}"}
    
    @classmethod
    def login_user(cls, username: str, password: str) -> Dict:
        username = username.strip().lower()
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        user_data = None
        if cls._rtdb:
            try: user_data = cls._rtdb.reference(f"users/{username}").get()
            except: pass
        if not user_data: user_data = cls._local_db["users"].get(username)
        if not user_data: return {"error": "اسم المستخدم غير موجود"}
        if user_data.get("password") != hashed_password: return {"error": "كلمة المرور غير صحيحة"}
        return {"success": True, "username": username, "name": user_data.get("name", username), "chat_id": f"user_{username}"}
    
    @classmethod
    def get_user_data(cls, username: str) -> Dict:
        if cls._rtdb:
            try:
                data = cls._rtdb.reference(f"users/{username}").get()
                if data: return data
            except: pass
        return cls._local_db["users"].get(username, {})
    
    @classmethod
    def update_user_data(cls, username: str, updates: Dict):
        user_data = cls.get_user_data(username)
        user_data.update(updates)
        cls._local_db["users"][username] = user_data
        if cls._rtdb:
            try: cls._rtdb.reference(f"users/{username}").update(updates)
            except: pass
    
    @classmethod
    def mark_greeted(cls, username: str): cls.update_user_data(username, {"greeted": True})
    
    @classmethod
    def add_asked_question(cls, username: str, question_id: str):
        user_data = cls.get_user_data(username)
        asked = user_data.get("asked_questions", [])
        if question_id not in asked:
            asked.append(question_id)
            if len(asked) > 500: asked = asked[-500:]
        questions_since = user_data.get("questions_since_analysis", 0) + 1
        cls.update_user_data(username, {"asked_questions": asked, "questions_since_analysis": questions_since})
    
    @classmethod
    def save_exam_result(cls, username: str, result: Dict):
        correct = result.get("correct", 0); total = result.get("total", 1)
        percentage = int((correct / max(total, 1)) * 100)
        wrong_questions = result.get("wrong_questions", [])
        wrong_skills = result.get("wrong_skills", [])
        all_skills = result.get("all_skills", [])
        user_data = cls.get_user_data(username)
        skill_stats = user_data.get("skill_stats", {})
        skill_counter = Counter(all_skills); wrong_skill_counter = Counter(wrong_skills)
        for skill in set(all_skills + wrong_skills):
            if skill not in skill_stats: skill_stats[skill] = {"correct": 0, "wrong": 0, "total": 0}
            skill_stats[skill]["total"] = skill_stats[skill].get("total", 0) + skill_counter.get(skill, 0)
            skill_stats[skill]["wrong"] = skill_stats[skill].get("wrong", 0) + wrong_skill_counter.get(skill, 0)
            skill_stats[skill]["correct"] = skill_stats[skill]["total"] - skill_stats[skill]["wrong"]
        recent_exams = user_data.get("recent_exams", [])
        recent_exams.append({"correct": correct, "total": total, "percentage": percentage, "wrong_skills": wrong_skills, "wrong_questions": wrong_questions, "timestamp": cls._now_ts()})
        if len(recent_exams) > 10: recent_exams = recent_exams[-10:]
        cls.update_user_data(username, {"skill_stats": skill_stats, "total_exams": user_data.get("total_exams", 0) + 1, "total_score": user_data.get("total_score", 0) + correct, "total_questions_answered": user_data.get("total_questions_answered", 0) + total, "recent_exams": recent_exams, "last_wrong_skills": list(set(wrong_skills))})
        if cls._rtdb:
            try: cls._rtdb.reference(f"students/{username}/exams").push({"score": correct, "total": total, "percentage": percentage, "wrong_questions": wrong_questions, "wrong_skills": wrong_skills, "timestamp": cls._now_ts()})
            except: pass
    
    @classmethod
    def _calculate_grade(cls, percentage: int) -> str:
        if percentage >= 90: return "ممتاز 🏆"
        elif percentage >= 80: return "جيد جداً 🌟"
        elif percentage >= 65: return "جيد 👍"
        elif percentage >= 50: return "مقبول 📚"
        return "ضعيف 💪"
    
    @classmethod
    def get_wrong_questions(cls, username: str) -> List[str]:
        wrong_qs = []
        for exam in cls.get_user_data(username).get("recent_exams", []): wrong_qs.extend(exam.get("wrong_questions", []))
        if cls._rtdb:
            try:
                exams = cls._rtdb.reference(f"students/{username}/exams").get() or {}
                for exam in exams.values(): wrong_qs.extend(exam.get("wrong_questions", []))
            except: pass
        return list(set(wrong_qs))
    
    @classmethod
    def get_last_wrong_skills(cls, username: str) -> List[str]: return cls.get_user_data(username).get("last_wrong_skills", [])
    
    @classmethod
    def get_leaderboard(cls) -> List[Dict]:
        users = []
        source = cls._local_db["users"]
        if cls._rtdb:
            try: source = cls._rtdb.reference("users").get() or {}
            except: pass
        for uid, data in source.items():
            if "password" in data:
                total_exams = data.get("total_exams", 0); total_score = data.get("total_score", 0)
                total_questions = data.get("total_questions_answered", 0)
                if total_exams > 0 and total_questions > 0: users.append({"name": data.get("name", uid), "avg": int((total_score / total_questions) * 100), "exams": total_exams})
        users.sort(key=lambda x: (x["avg"], x["exams"]), reverse=True)
        return users[:10]
    
    @classmethod
    def report_question(cls, question_id: str, username: str):
        cls._local_db["reported_questions"].append({"question_id": question_id, "reported_by": username, "timestamp": cls._now_ts()})
        if cls._rtdb:
            try: cls._rtdb.reference(f"reported_questions/{question_id}").push({"question_id": question_id, "reported_by": username})
            except: pass

StudentService.initialize()

# =========================================
# DATA LOADING
# =========================================

MAX_QUESTION_LENGTH = 350
MAX_PASSAGE_PREVIEW = 150
SESSION_TIMEOUT = 900
RATE_LIMIT_SECONDS = 0.3

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

ALL_QUESTIONS: List[Dict] = []
MCQ_QUESTIONS: List[Dict] = []
QUESTIONS_BY_DIFFICULTY: Dict[str, List[Dict]] = defaultdict(list)
QUESTIONS_BY_SKILL: Dict[str, List[Dict]] = defaultdict(list)
BAD_QUESTIONS: List[Dict] = []

def detect_question_type(question: Dict) -> str:
    choices = question.get("choices", [])
    if not choices or len(choices) < 2: return "open_text"
    answer_key = str(question.get("answer_key", "")).strip()
    if not answer_key: return "open_text"
    if answer_key.isdigit(): return "mcq"
    if answer_key in ["أ", "ب", "ج", "د"]: return "mcq"
    if answer_key.lower() in ["a", "b", "c", "d"]: return "mcq"
    return "open_text"

def get_answer_index(question: Dict) -> Optional[int]:
    answer_key = str(question.get("answer_key", "")).strip()
    choices = question.get("choices", [])
    if not choices: return None
    if answer_key.isdigit():
        idx = int(answer_key) - 1
        return idx if 0 <= idx < len(choices) else None
    if answer_key in ["أ", "ب", "ج", "د"]: return ["أ", "ب", "ج", "د"].index(answer_key)
    if answer_key.lower() in ["a", "b", "c", "d"]: return ["a", "b", "c", "d"].index(answer_key.lower())
    return None

def validate_question(q: Dict) -> Tuple[bool, str]:
    if not q.get("question") or len(q.get("question", "").strip()) < 5: return False, "سؤال قصير"
    if not q.get("answer_key"): return False, "لا يوجد answer_key"
    if get_answer_index(q) is None: return False, "answer_key غير صالح"
    if len(q.get("choices", [])) < 2: return False, "اختيارات أقل من 2"
    return True, "صالح"

def extract_all_questions(data, depth=0, context=None):
    if context is None: context = {"passage": "", "section": "", "poem": "", "previous_lines": []}
    questions = []
    if depth > 15: return questions
    if isinstance(data, dict):
        passage_text = ""
        if "passage" in data:
            passage = data["passage"]
            if isinstance(passage, dict): passage_text = passage.get("text", "")
            elif isinstance(passage, str): passage_text = passage
        section_title = data.get("section_title", data.get("title", ""))
        poem_text = data.get("poem", data.get("poem_text", ""))
        previous_lines = data.get("previous_lines", data.get("context_lines", []))
        new_context = {"passage": passage_text or context["passage"], "section": section_title or context["section"], "poem": poem_text or context["poem"], "previous_lines": previous_lines if previous_lines else context["previous_lines"]}
        if "prompt" in data and "question_id" in data:
            questions.append({"question_id": data.get("question_id", ""), "prompt": data.get("prompt", ""), "question": data.get("prompt", ""), "explanation": data.get("explanation", ""), "answer_key": data.get("answer_key", ""), "choices": data.get("choices", data.get("options", [])), "difficulty": data.get("difficulty", "medium"), "skill": data.get("skill", "عام"), "passage": new_context["passage"], "section_title": new_context["section"], "poem": new_context["poem"], "previous_lines": new_context["previous_lines"], "question_type": ""})
        elif "question" in data:
            questions.append({"question_id": data.get("id", data.get("question_id", "")), "prompt": data.get("question", ""), "question": data.get("question", ""), "explanation": data.get("explanation", data.get("answer", "")), "answer_key": data.get("answer_key", data.get("correct", "")), "choices": data.get("choices", data.get("options", [])), "difficulty": data.get("difficulty", "medium"), "skill": data.get("skill", "عام"), "passage": new_context["passage"], "section_title": new_context["section"], "poem": new_context["poem"], "previous_lines": new_context["previous_lines"], "question_type": ""})
        for key in ["questions", "sections", "lessons", "items", "exercises", "sub_questions"]:
            if key in data and isinstance(data[key], list):
                for item in data[key]: questions.extend(extract_all_questions(item, depth+1, new_context))
        for key, value in data.items():
            if key not in ["questions", "sections", "lessons", "items", "exercises", "sub_questions", "passage", "poem"]:
                if isinstance(value, (dict, list)): questions.extend(extract_all_questions(value, depth+1, new_context))
    elif isinstance(data, list):
        for item in data: questions.extend(extract_all_questions(item, depth+1, context))
    return questions

def load_all_data():
    global ALL_QUESTIONS, MCQ_QUESTIONS, QUESTIONS_BY_DIFFICULTY, QUESTIONS_BY_SKILL, BAD_QUESTIONS
    ALL_QUESTIONS = []; MCQ_QUESTIONS = []; QUESTIONS_BY_DIFFICULTY = defaultdict(list); QUESTIONS_BY_SKILL = defaultdict(list); BAD_QUESTIONS = []
    seen = set()
    if not DATA_DIR.exists(): DATA_DIR.mkdir(exist_ok=True); return
    files = list(DATA_DIR.glob("*.json"))
    print(f"📚 {len(files)} files")
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                questions = extract_all_questions(data)
                for q in questions:
                    q_text = str(q.get("question", ""))[:100]
                    if q_text and q_text not in seen:
                        seen.add(q_text)
                        is_valid, reason = validate_question(q)
                        if is_valid:
                            q["question_type"] = detect_question_type(q)
                            q["skill"] = get_skill_category(q.get("skill", "عام"))
                            ALL_QUESTIONS.append(q)
                            if q["question_type"] == "mcq": MCQ_QUESTIONS.append(q)
                            QUESTIONS_BY_DIFFICULTY[q.get("difficulty", "medium")].append(q)
                            QUESTIONS_BY_SKILL[q.get("skill", "عام")].append(q)
                        else: BAD_QUESTIONS.append({"question": q.get("question", "")[:100], "reason": reason})
        except Exception as e: print(f"❌ {file.name}: {e}")
    print(f"🔥 {len(ALL_QUESTIONS)} valid | {len(MCQ_QUESTIONS)} MCQ | {len(BAD_QUESTIONS)} bad")

load_all_data()

# =========================================
# SESSION MANAGEMENT
# =========================================

class ExamSession:
    def __init__(self, questions: List[Dict], level: str = "medium", mode: str = "normal"):
        self.questions = questions
        self.current_index = 0
        self.score = 0
        self.total = len(questions)
        self.level = level
        self.active = True
        self.mode = mode
        self.last_activity = time.time()
        self.wrong_questions = []
        self.wrong_skills = []
        self.all_skills = []
        self.consecutive_correct = 0
        self.streak = 0
    
    def is_expired(self) -> bool: return time.time() - self.last_activity > SESSION_TIMEOUT
    def has_next(self) -> bool: return self.current_index < len(self.questions)
    
    def check_answer(self, user_answer: int, username: str = None) -> Dict:
        self.last_activity = time.time()
        if not self.has_next(): return {"error": "no_more_questions"}
        question = self.questions[self.current_index]
        correct_idx = get_answer_index(question)
        user_idx = user_answer - 1
        is_correct = (correct_idx is not None and correct_idx == user_idx)
        if is_correct:
            self.score += 1
            self.consecutive_correct += 1
            self.streak = max(self.streak, self.consecutive_correct)
        else:
            qid = question.get("question_id", "")
            if qid: self.wrong_questions.append(qid)
            self.wrong_skills.append(question.get("skill", "عام"))
            self.consecutive_correct = 0
        self.all_skills.append(question.get("skill", "عام"))
        choices = question.get("choices", [])
        correct_answer_text = ""
        if correct_idx is not None and 0 <= correct_idx < len(choices):
            choice = choices[correct_idx]
            correct_answer_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
        if username: StudentService.add_asked_question(username, question.get("question_id", ""))
        result = {"correct": is_correct, "correct_answer": correct_answer_text, "explanation": question.get("explanation", ""), "current_score": self.score, "question_number": self.current_index + 1, "total": self.total, "section_title": question.get("section_title", ""), "skill": question.get("skill", "عام"), "question_id": question.get("question_id", ""), "user_answer_idx": user_idx, "choices": choices, "consecutive_correct": self.consecutive_correct, "streak": self.streak, "question_text": question.get("prompt", question.get("question", ""))}
        self.current_index += 1
        if not self.has_next(): self.active = False
        return result

user_sessions: Dict[str, ExamSession] = {}
LAST_MESSAGE_TIME: Dict[str, float] = {}
ACTIVE_USERS: Dict[str, str] = {}

async def cleanup_expired_sessions():
    while True:
        try:
            expired = [cid for cid, s in user_sessions.items() if s.is_expired()]
            for cid in expired: del user_sessions[cid]
        except: pass
        await asyncio.sleep(60)

# =========================================
# HELPERS
# =========================================

def get_unasked_questions(questions: List[Dict], username: str, count: int) -> List[Dict]:
    user_data = StudentService.get_user_data(username)
    asked = set(user_data.get("asked_questions", []))
    unasked = [q for q in questions if q.get("question_id", "") not in asked]
    if len(unasked) >= count: return random.sample(unasked, count)
    elif unasked: return unasked[:count]
    return random.sample(questions, min(count, len(questions)))

def filter_by_skills_exact(questions: List[Dict], skill_query: str) -> List[Dict]:
    resolved = resolve_skills(skill_query)
    if not resolved: return []
    resolved_normalized = set()
    for s in resolved:
        resolved_normalized.add(s.lower())
        resolved_normalized.add(get_skill_arabic(s).lower())
    filtered = []
    for q in questions:
        q_skill = q.get("skill", "عام").lower()
        q_skill_arabic = get_skill_arabic(q_skill).lower()
        for rs in resolved_normalized:
            if rs in q_skill or q_skill in rs or rs in q_skill_arabic or q_skill_arabic in rs:
                filtered.append(q)
                break
    return filtered

def get_questions_by_skills(questions: List[Dict], skills: List[str], count: int) -> List[Dict]:
    if not skills: return random.sample(questions, min(count, len(questions)))
    matching = [q for q in questions if q.get("skill", "عام") in skills]
    if len(matching) >= count: return random.sample(matching, count)
    remaining = count - len(matching)
    other = [q for q in questions if q not in matching]
    matching.extend(random.sample(other, min(remaining, len(other))))
    return matching

def get_passage_preview(q: Dict) -> str:
    section = q.get("section_title", "")
    passage = q.get("passage", "")
    if section: return f"📖 *من {section[:60]}*"
    if passage:
        preview = passage[:MAX_PASSAGE_PREVIEW].replace("\n", " ")
        return f"📖 *{preview}...*"
    return ""

def format_professional_question(q: Dict, session: ExamSession) -> str:
    msg = ""
    preview = get_passage_preview(q)
    if preview: msg += f"{preview}\n\n"
    
    question_num = session.current_index + 1
    skill_display = get_skill_display(q.get("skill", "عام"))
    streak_emoji = "🔥" if session.consecutive_correct >= 3 else "⭐" if session.consecutive_correct >= 2 else ""
    
    msg += f"🎯 *سؤال {question_num}/{session.total}* | {skill_display}\n"
    msg += f"📊 *التقدم:* {question_num}/{session.total} | ⭐ *النقاط:* {session.score}"
    if streak_emoji: msg += f" | {streak_emoji} *سلسلة:* {session.consecutive_correct}"
    msg += "\n\n"
    
    question_text = str(q.get("prompt", q.get("question", "سؤال")))[:MAX_QUESTION_LENGTH]
    msg += f"*{question_text}*\n\n"
    
    choices = q.get("choices", [])
    if choices:
        for idx, choice in enumerate(choices, 1):
            choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
            msg += f"{idx}️⃣ {choice_text}\n"
    
    msg += "\n✍️ *اكتب رقم الإجابة* | 📄 `النص` للعرض"
    return msg

async def format_teacher_feedback(result: Dict, session: ExamSession) -> str:
    """Teacher feedback with AI explanation"""
    msg = ""
    
    if result["correct"]:
        praises = ["🎉 *ممتاز!*", "🔥 *إجابة قوية!*", "👏 *واضح إنك فاهم!*", "💯 *أحسنت!*"]
        msg += f"{random.choice(praises)}\n\n"
        
        if result.get("consecutive_correct", 0) >= 3:
            msg += f"🔥 *سلسلة رائعة!* {result['consecutive_correct']} إجابات صحيحة متتالية!\n\n"
    else:
        msg += "❌ *ليست الإجابة الصحيحة*\n\n"
        
        user_idx = result.get("user_answer_idx", -1)
        choices = result.get("choices", [])
        if 0 <= user_idx < len(choices):
            choice = choices[user_idx]
            user_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
            msg += f"✍️ *اخترت:* {user_idx+1}️⃣ {user_text}\n\n"
        
        msg += f"✅ *الإجابة الصحيحة:* {result['correct_answer']}\n\n"
    
    # Try AI explanation first
    ai_explanation = None
    if AI_ENABLED:
        user_idx = result.get("user_answer_idx", -1)
        choices = result.get("choices", [])
        user_answer_text = ""
        if 0 <= user_idx < len(choices):
            choice = choices[user_idx]
            user_answer_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
        
        ai_explanation = await generate_ai_feedback(
            result.get("question_text", ""),
            user_answer_text,
            result["correct_answer"],
            result["correct"],
            result.get("skill", "عام"),
            result.get("explanation", "")
        )
    
    if ai_explanation:
        msg += f"🤖 *شرح المدرس:*\n{ai_explanation}\n\n"
    else:
        # Fallback to built-in tips
        skill = result.get("skill", "عام")
        tip = SKILL_TEACHING_TIPS.get(get_skill_arabic(skill))
        if tip:
            msg += f"📌 *قاعدة:*\n{random.choice(list(tip.values())) if isinstance(tip, dict) else tip}\n\n"
        
        if result["explanation"] and len(str(result["explanation"])) > 10:
            msg += f"📝 *الشرح:*\n{str(result['explanation'])[:300]}\n\n"
    
    msg += f"📊 *نتيجتك:* {result['current_score']}/{result['question_number']}"
    if result.get("consecutive_correct", 0) >= 2: msg += f" | 🔥 *سلسلة:* {result['consecutive_correct']}"
    msg += "\n"
    
    return msg

def format_professional_report(session: ExamSession, username: str = None) -> str:
    final_score = session.score; total = session.total
    percentage = int((final_score / total) * 100) if total > 0 else 0
    
    if username:
        try: StudentService.save_exam_result(username, {"correct": final_score, "total": total, "wrong_questions": session.wrong_questions, "wrong_skills": list(set(session.wrong_skills)), "all_skills": session.all_skills})
        except: pass
    
    if percentage >= 90: emoji, grade = "🏆", "ممتاز"
    elif percentage >= 80: emoji, grade = "🌟", "جيد جداً"
    elif percentage >= 65: emoji, grade = "👍", "جيد"
    elif percentage >= 50: emoji, grade = "📚", "مقبول"
    else: emoji, grade = "💪", "ضعيف"
    
    msg = f"🏁 *انتهى التدريب*\n\n📊 *النتيجة:* {final_score}/{total} | 📈 *{percentage}%*\n🏅 *التقدير:* {emoji} {grade}\n"
    if session.streak >= 2: msg += f"🔥 *أفضل سلسلة:* {session.streak}\n"
    msg += "\n"
    
    skill_perf = {}
    for i, skill in enumerate(session.all_skills):
        is_wrong = skill in session.wrong_skills
        if skill not in skill_perf: skill_perf[skill] = {"correct": 0, "wrong": 0}
        if is_wrong: skill_perf[skill]["wrong"] += 1
        else: skill_perf[skill]["correct"] += 1
    
    strengths = []; weaknesses = []
    for skill, perf in skill_perf.items():
        total_s = perf["correct"] + perf["wrong"]
        pct = int((perf["correct"] / total_s) * 100) if total_s > 0 else 0
        if pct >= 80: strengths.append((skill, pct))
        elif pct < 50: weaknesses.append((skill, pct))
    
    if strengths or weaknesses:
        msg += "📈 *تقرير مستواك*\n\n"
        if strengths: msg += "✅ *نقاط قوتك:*\n" + "\n".join([f"   {get_skill_display(s)}" for s, p in strengths]) + "\n\n"
        if weaknesses:
            msg += "⚠️ *تحتاج تحسين:*\n" + "\n".join([f"   {get_skill_display(s)}" for s, p in weaknesses]) + "\n"
            if weaknesses:
                weak_arabic = get_skill_arabic(weaknesses[0][0])
                msg += f"\n📚 *لو ذاكرت {weak_arabic} اليوم*\nدرجتك المتوقعة: {percentage}% ➜ {min(percentage + 15, 95)}%\n\n"
    
    msg += "🎯 *أنصحك:*\n"
    if weaknesses: msg += f"• `اختبرني في {get_skill_arabic(weaknesses[0][0])}`\n"
    msg += "• `تدريب سريع` | `علاج أخطائي` | `خطة التركيز`"
    return msg

def get_smart_greeting(username: str, user_data: Dict) -> str:
    name = user_data.get("name", username)
    if not user_data.get("greeted", False):
        StudentService.mark_greeted(username)
        return f"""🤖 *Pen*: أهلاً يا {name} 👋

مدرسك الشخصي في العربي 📚
{'🧠 *مدعوم بالذكاء الاصطناعي*' if AI_ENABLED else ''}

⚡ *ابدأ:* `تدريب سريع` | `اختبرني` | `تحدي`
📚 *مراجعة:* `بلاغة` `نحو` `أدب` `قراءة`"""
    
    total_exams = user_data.get("total_exams", 0)
    if total_exams == 0: return f"👋 *{name}*\n⚡ جاهز؟ `تدريب سريع`"
    
    total_q = user_data.get("total_questions_answered", 0)
    recent_exams = user_data.get("recent_exams", [])
    last_avg = 0
    if recent_exams: last_avg = int((recent_exams[-1].get("correct", 0) / max(recent_exams[-1].get("total", 1), 1)) * 100)
    
    msg = f"👋 *{name}* | 📊 *{last_avg}%* | 📝 *{total_q} سؤال*\n\n"
    last_wrong = StudentService.get_last_wrong_skills(username)
    if last_wrong and last_avg < 70: msg += "💡 *ركز على:* `علاج أخطائي`\n"
    else: msg += "⚡ `تدريب سريع` | `تحدي`\n"
    return msg

# =========================================
# MAIN PROCESSOR
# =========================================

def is_rate_limited(chat_id: str) -> bool:
    current_time = time.time()
    if current_time - LAST_MESSAGE_TIME.get(chat_id, 0) < RATE_LIMIT_SECONDS: return True
    LAST_MESSAGE_TIME[chat_id] = current_time
    return False

async def process_message(chat_id: str, body: str, username: str = None) -> str:
    try:
        if is_rate_limited(chat_id): return ""
        
        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            if session.active and not session.is_expired():
                if body.strip() in ["النص", "نص", "عرض"]:
                    q = session.questions[session.current_index]
                    passage = q.get("passage", "")
                    if passage: return f"📖 *النص الكامل:*\n\n{passage[:800]}"
                    return "📖 *مفيش نص*"
                
                if "تقرير" in body or "بلغ" in body:
                    idx = min(session.current_index, len(session.questions)-1)
                    qid = session.questions[idx].get("question_id", "")
                    if username and qid: StudentService.report_question(qid, username)
                    if session.has_next(): return "✅ *تم*\n\n" + format_professional_question(session.questions[session.current_index], session)
                    return "✅ *تم*"
                
                try:
                    numbers = re.findall(r'\d+', body)
                    if not numbers: return "❌ *اكتب رقم الإجابة* | 📄 `النص` للعرض"
                    answer_num = int(numbers[0])
                except: return "❌ *رقم فقط*"
                
                current_q = session.questions[session.current_index]
                max_choices = len(current_q.get("choices", []))
                if answer_num < 1 or answer_num > max(4, max_choices): return f"❌ *1-{max(4, max_choices)}*"
                
                try: result = session.check_answer(answer_num, username)
                except: del user_sessions[chat_id]; return "❌ *خطأ*\n🔄 `تدريب سريع`"
                
                if "error" in result: del user_sessions[chat_id]; return "🔄 *انتهى*\n`تدريب سريع`"
                
                response = await format_teacher_feedback(result, session)
                
                if session.active and session.has_next():
                    response += "\n➡️ " + format_professional_question(session.questions[session.current_index], session)
                else:
                    response += "\n" + format_professional_report(session, username)
                    del user_sessions[chat_id]
                
                return response
            else: del user_sessions[chat_id]
        
        body_lower = body.lower().strip()
        
        if body_lower in ["تدريب سريع", "سريع"]: return start_exam(chat_id, count=3, username=username)
        if body_lower in ["تحدي", "تحد", "صعب"]: return start_exam(chat_id, level="hard", count=5, username=username)
        if body_lower in ["علاج أخطائي", "علاج"]:
            if username: return start_exam(chat_id, focus_on_wrong=True, username=username)
            return "❌ سجل دخول"
        if body_lower in ["مراجعة", "مراجعه"]: return get_skill_menu()
        if body_lower in ["الترتيب"]: return get_leaderboard_text()
        
        if any(x in body_lower for x in ["اختبرني"]):
            level = "medium"
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower: level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            skill_query = None
            for word in body_lower.split():
                if word in ["في", "على", "عن"]: continue
                if resolve_skills(word): skill_query = word; break
            return start_exam(chat_id, level=level, skill_query=skill_query, username=username)
        
        if any(x in body_lower for x in ["امتحان"]) and "اختبرني" not in body_lower:
            level = None
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower: level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            return generate_exam(level=level, username=username)
        
        if body_lower in ["مستوايا", "مستوى", "تحليل"]:
            if username: return get_level_analytics(username)
            return "📊 *سجل دخول*"
        
        if any(x in body_lower for x in ["خطة", "تركيز"]): return generate_focus_plan(username)
        
        if any(x in body_lower for x in ["اهلا", "مرحبا", "سلام", "هاي"]):
            if username: return get_smart_greeting(username, StudentService.get_user_data(username))
            return get_default_greeting()
        
        resolved = resolve_skills(body_lower)
        if resolved: return start_exam(chat_id, skill_query=body_lower, username=username)
        
        if username: return get_smart_greeting(username, StudentService.get_user_data(username))
        return get_default_greeting()
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback; traceback.print_exc()
        return "❌ *حصل خطأ*"

# =========================================
# EXAM STARTERS
# =========================================

def start_exam(chat_id: str, level: str = "medium", skill_query: str = None, username: str = None, count: int = 5, focus_on_wrong: bool = False) -> str:
    if focus_on_wrong and username:
        wrong_ids = StudentService.get_wrong_questions(username)
        if not wrong_ids: return "✅ *مافيش أخطاء!* 🎉\n⚡ `تدريب سريع`"
        filtered = [q for q in MCQ_QUESTIONS if q.get("question_id", "") in wrong_ids]
        if not filtered: return "✅ *مافيش أخطاء!*"
    elif skill_query:
        filtered = filter_by_skills_exact(MCQ_QUESTIONS if MCQ_QUESTIONS else ALL_QUESTIONS, skill_query)
        if not filtered:
            available = set()
            for q in ALL_QUESTIONS[:30]: available.add(get_skill_display(q.get("skill", "عام")))
            return f"❌ *مفيش أسئلة*\n\n🎯 *جرب:*\n" + "\n".join([f"• {s}" for s in sorted(available)[:8]])
    else:
        if username and count >= 5:
            last_wrong = StudentService.get_last_wrong_skills(username)
            if last_wrong:
                focused = get_questions_by_skills(MCQ_QUESTIONS if MCQ_QUESTIONS else ALL_QUESTIONS, last_wrong, count)
                if focused:
                    session = ExamSession(focused, level, "smart")
                    user_sessions[chat_id] = session
                    return "🎯 *سأركز على أخطائك*\n\n" + format_professional_question(focused[0], session)
        filtered = MCQ_QUESTIONS.copy() if MCQ_QUESTIONS else ALL_QUESTIONS.copy()
    
    if level in ["easy", "medium", "hard"]:
        level_filtered = [q for q in filtered if q.get("difficulty") == level]
        if level_filtered: filtered = level_filtered
    if not filtered: return "❌ *مفيش أسئلة*"
    
    selected = get_unasked_questions(filtered, username, count) if username and not focus_on_wrong else random.sample(filtered, min(count, len(filtered)))
    if len(selected) < 2: return "❌ *عدد غير كافي*"
    
    session = ExamSession(selected, level)
    user_sessions[chat_id] = session
    return format_professional_question(selected[0], session)

def get_skill_menu() -> str:
    return """📚 *اختر مهارة:*

✨ `بلاغة` `نحو` `إعراب`
📚 `أدب` `قراءة` `مفردات`
🧠 `استنتاج` `مقارنة`

⚡ `تدريب سريع` | `تحدي`"""

def generate_exam(level: str = None, count: int = 5, username: str = None) -> str:
    if not ALL_QUESTIONS: return "❌ مفيش أسئلة"
    filtered = ALL_QUESTIONS.copy()
    if level and level in ["easy", "medium", "hard"]: filtered = [q for q in filtered if q.get("difficulty") == level]
    if not filtered: return "❌ مفيش أسئلة"
    selected = get_unasked_questions(filtered, username, count) if username else random.sample(filtered, min(count, len(filtered)))
    level_name = {"easy": "سهل 🟢", "medium": "متوسط 🟡", "hard": "صعب 🔴"}.get(level, "شامل")
    exam = f"📝 *امتحان {level_name}*\n{'─' * 20}\n\n"
    for i, q in enumerate(selected, 1):
        preview = get_passage_preview(q)
        if preview: exam += f"{preview}\n"
        exam += f"*{i}.* {get_skill_display(q.get('skill', 'عام'))}\n{str(q.get('prompt', 'سؤال'))[:MAX_QUESTION_LENGTH]}\n"
        if q.get("choices"):
            for idx, choice in enumerate(q.get("choices", []), 1):
                exam += f"   {idx}️⃣ {choice.get('text', str(choice)) if isinstance(choice, dict) else str(choice)}\n"
            exam += "\n"
    exam += f"{'─' * 20}\n💪 *ربنا معاك*"
    return exam

def generate_focus_plan(username: str = None) -> str:
    msg = "🎯 *خطة التركيز*\n" + "─" * 20 + "\n\n"
    if username:
        user_data = StudentService.get_user_data(username)
        recent_exams = user_data.get("recent_exams", [])
        if recent_exams:
            all_wrong = []; total_recent = 0
            for exam in recent_exams: total_recent += exam.get("total", 0); all_wrong.extend(exam.get("wrong_skills", []))
            msg += f"📊 *آخر {total_recent} سؤال*\n\n"
            if all_wrong:
                wrong_counter = Counter(all_wrong)
                msg += "🔴 *أضعف نقاطك:*\n"
                for skill, count in wrong_counter.most_common(5):
                    pct = int((count / max(total_recent, 1)) * 100)
                    msg += f"   {get_skill_display(skill)}: {pct}%\n"
                msg += f"\n⚡ `علاج أخطائي`\n"
            else: msg += "✅ *كل إجاباتك صحيحة!*\n⚡ `تحدي`\n\n"
        else: msg += "📝 *لسه مفيش بيانات*\n⚡ `تدريب سريع`\n\n"
    return msg

def get_level_analytics(username: str) -> str:
    user_data = StudentService.get_user_data(username)
    recent_exams = user_data.get("recent_exams", [])
    if not recent_exams: return "📊 *لسه مفيش بيانات*\n⚡ `تدريب سريع`"
    recent_correct = sum(e.get("correct", 0) for e in recent_exams)
    recent_total = sum(e.get("total", 0) for e in recent_exams)
    recent_avg = int((recent_correct / max(recent_total, 1)) * 100)
    msg = f"📊 *تحليل*\n{'─' * 20}\n\n📈 *{recent_avg}%* | 🏅 *{StudentService._calculate_grade(recent_avg)}*\n\n"
    all_wrong = []
    for e in recent_exams: all_wrong.extend(e.get("wrong_skills", []))
    if all_wrong:
        wrong_counter = Counter(all_wrong)
        msg += "🔴 *يحتاج مراجعة:*\n"
        for skill, count in wrong_counter.most_common(4): msg += f"   {get_skill_display(skill)} ({count})\n"
    msg += f"\n⚡ `علاج أخطائي`"
    return msg

def get_leaderboard_text() -> str:
    leaders = StudentService.get_leaderboard()
    if not leaders: return "🏆 *الترتيب*\n\nلسه مفيش بيانات"
    msg = "🏆 *أفضل الطلاب*\n" + "─" * 20 + "\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        msg += f"{medal} {user['name']} - {user['avg']}%\n"
    return msg

def get_default_greeting() -> str:
    return f"""🤖 *Pen*: أهلاً بك 👋
{'🧠 *مدعوم بالذكاء الاصطناعي*' if AI_ENABLED else ''}

⚡ `تدريب سريع` | `اختبرني` | `تحدي`
📚 `بلاغة` `نحو` `أدب` `قراءة`"""

# =========================================
# API ENDPOINTS
# =========================================

@app.post("/api/register")
async def register(request: Request):
    try:
        data = await request.json()
        username = data.get("username", "").strip(); password = data.get("password", "").strip(); name = data.get("name", "").strip()
        if not username or not password: return JSONResponse({"error": "مطلوب"}, 400)
        if len(username) < 3: return JSONResponse({"error": "3 أحرف"}, 400)
        if len(password) < 6: return JSONResponse({"error": "6 أحرف"}, 400)
        result = StudentService.create_user(username, password, name)
        if "error" in result: return JSONResponse(result, 400)
        return JSONResponse(result)
    except Exception as e: return JSONResponse({"error": str(e)}, 500)

@app.post("/api/login")
async def login(request: Request):
    try:
        data = await request.json()
        username = data.get("username", "").strip(); password = data.get("password", "").strip()
        if not username or not password: return JSONResponse({"error": "مطلوب"}, 400)
        result = StudentService.login_user(username, password)
        if "error" in result: return JSONResponse(result, 401)
        ACTIVE_USERS[result["chat_id"]] = username
        return JSONResponse(result)
    except Exception as e: return JSONResponse({"error": str(e)}, 500)

@app.post("/api/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id", ""); message = data.get("message", "").strip(); username = data.get("username", "")
        if not message: return JSONResponse({"reply": ""})
        ACTIVE_USERS[chat_id] = username
        reply = await process_message(chat_id, message, username)
        return JSONResponse({"reply": reply, "ok": True})
    except Exception as e: return JSONResponse({"reply": "❌ خطأ", "ok": False})

@app.get("/api/leaderboard")
async def leaderboard(): return JSONResponse(StudentService.get_leaderboard())

@app.get("/health")
async def health(): return {"status": "healthy", "version": "v10-ai", "questions": len(ALL_QUESTIONS), "mcq": len(MCQ_QUESTIONS), "ai_enabled": AI_ENABLED}

@app.get("/", response_class=HTMLResponse)
async def auth_page():
    auth_path = BASE_DIR / "auth.html"
    return auth_path.read_text(encoding="utf-8") if auth_path.exists() else "<h1>not found</h1>"

@app.get("/app", response_class=HTMLResponse)
async def app_page():
    app_path = BASE_DIR / "app.html"
    return app_path.read_text(encoding="utf-8") if app_path.exists() else "<h1>not found</h1>"

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print(f"🚀 Pen V10 AI | {len(ALL_QUESTIONS)} questions | AI: {AI_ENABLED}")
