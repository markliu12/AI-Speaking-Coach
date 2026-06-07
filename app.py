from __future__ import annotations

import json
import os
import re
import statistics
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent.resolve()
STATIC_DIR = ROOT / "static"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))


@dataclass(frozen=True)
class IntentRule:
    name: str
    examples: list[str]
    patterns: list[str]


@dataclass(frozen=True)
class Scenario:
    key: str
    name: str
    category: str
    role: str
    user_goal: str
    opening: str
    required_slots: list[str]
    slot_prompts: dict[str, str]
    intents: list[IntentRule]
    milestones: list[str]
    keywords: list[str]
    phrase_bank: dict[str, str]


@dataclass
class Turn:
    user_text: str
    assistant_text: str
    intent: str
    slots: dict[str, str]
    missing_slots: list[str]
    pronunciation: dict[str, Any]
    corrections: list[dict[str, str]]
    expression_tips: list[str]
    pipeline: dict[str, int | str]
    created_at: float = field(default_factory=time.time)


@dataclass
class Session:
    id: str
    scenario: Scenario
    level: str
    user_id: str
    started_at: float = field(default_factory=time.time)
    slots: dict[str, str] = field(default_factory=dict)
    turns: list[Turn] = field(default_factory=list)


def intent(name: str, examples: list[str], patterns: list[str]) -> IntentRule:
    return IntentRule(name=name, examples=examples, patterns=patterns)


SCENARIOS: dict[str, Scenario] = {
    "restaurant": Scenario(
        key="restaurant",
        name="餐厅点餐",
        category="daily",
        role="You are a warm restaurant server. Help the learner complete a realistic restaurant order.",
        user_goal="Ask for recommendations, order food, mention preferences or allergies, and pay politely.",
        opening="Good evening. Welcome in. Would you like to start with something to drink?",
        required_slots=["drink", "main_course", "preference", "payment"],
        slot_prompts={
            "drink": "What would you like to drink?",
            "main_course": "What would you like for your main course?",
            "preference": "Any allergies, spice level, or cooking preference?",
            "payment": "Would you like the bill together or separately?",
        },
        intents=[
            intent("order_drink", ["I'd like water.", "Can I have tea?"], [r"\b(water|tea|coffee|juice|cola|drink)\b"]),
            intent("order_food", ["I'd like the steak.", "Can I get pasta?"], [r"\b(steak|pasta|salad|burger|rice|noodle|chicken|fish|soup|main)\b"]),
            intent("ask_recommendation", ["What do you recommend?"], [r"\brecommend\b", r"\bsuggestion\b"]),
            intent("state_preference", ["Not too spicy.", "I am allergic to peanuts."], [r"\b(allerg|spicy|mild|rare|medium|well done|vegetarian|no\s+\w+)\b"]),
            intent("ask_bill", ["Could I have the bill?"], [r"\b(bill|check|pay|card|cash|together|separately)\b"]),
        ],
        milestones=["drink", "main_course", "preference", "payment"],
        keywords=["menu", "order", "recommend", "allergy", "spicy", "bill", "please", "could"],
        phrase_bank={
            "give me": "Could I have ...?",
            "i want": "I'd like ...",
            "how much": "How much is ...?",
        },
    ),
    "travel": Scenario(
        key="travel",
        name="旅行问路",
        category="travel",
        role="You are a helpful local person at a train station.",
        user_goal="Ask for directions, confirm transport details, and solve a travel problem.",
        opening="Hi there. You look a bit lost. Where are you trying to go?",
        required_slots=["destination", "transport", "time"],
        slot_prompts={
            "destination": "Which place are you trying to reach?",
            "transport": "Would you prefer the subway, bus, taxi, or walking?",
            "time": "What time do you need to arrive?",
        },
        intents=[
            intent("ask_direction", ["How can I get to the museum?"], [r"\b(get to|go to|where|direction|near|station|museum|hotel|airport)\b"]),
            intent("choose_transport", ["I prefer the subway."], [r"\b(subway|metro|bus|taxi|train|walk|uber)\b"]),
            intent("ask_time", ["How long does it take?"], [r"\b(how long|time|minutes|arrive|leave)\b"]),
            intent("ask_price", ["How much is the ticket?"], [r"\b(price|cost|ticket|fare|expensive)\b"]),
        ],
        milestones=["destination", "transport", "time"],
        keywords=["station", "ticket", "left", "right", "straight", "transfer", "platform", "arrive"],
        phrase_bank={
            "where is": "Could you tell me where ... is?",
            "i want go": "I'd like to go to ...",
            "how much time": "How long does it take?",
        },
    ),
    "interview": Scenario(
        key="interview",
        name="求职面试",
        category="career",
        role="You are a hiring manager conducting a realistic English interview.",
        user_goal="Answer interview questions clearly with evidence, impact, and professional phrasing.",
        opening="Thanks for joining today. Could you tell me about yourself and the role you are looking for?",
        required_slots=["background", "strength", "example", "question"],
        slot_prompts={
            "background": "What is your professional or academic background?",
            "strength": "What is one strength that fits this role?",
            "example": "Can you give me a concrete example or result?",
            "question": "What question would you like to ask the interviewer?",
        },
        intents=[
            intent("self_intro", ["I have three years of experience."], [r"\b(experience|major|worked|study|background|role)\b"]),
            intent("strength", ["My strength is communication."], [r"\b(strength|good at|skill|strong|advantage)\b"]),
            intent("example", ["For example, I led a project."], [r"\b(example|project|result|delivered|improved|learned)\b"]),
            intent("ask_interviewer", ["What is the team culture like?"], [r"\b(question|team|culture|position|next step)\b"]),
        ],
        milestones=["background", "strength", "example", "question"],
        keywords=["experience", "project", "team", "role", "skill", "challenge", "result", "learned"],
        phrase_bank={
            "i want this job": "I am excited about this opportunity because it matches my experience in ...",
            "i am good at": "One of my strengths is ...",
            "i did many things": "I was responsible for ... and delivered ...",
        },
    ),
    "meeting": Scenario(
        key="meeting",
        name="商务会议",
        category="career",
        role="You are a colleague in a business meeting.",
        user_goal="Share opinions, clarify points, disagree politely, and propose next actions.",
        opening="Before we decide, could you give us your view on the current proposal?",
        required_slots=["opinion", "risk", "timeline", "action_item"],
        slot_prompts={
            "opinion": "What is your main opinion on the proposal?",
            "risk": "What risk or concern should we consider?",
            "timeline": "What timeline do you suggest?",
            "action_item": "What should the next action item be?",
        },
        intents=[
            intent("share_opinion", ["I think this proposal is practical."], [r"\b(i think|in my view|proposal|agree|disagree|point)\b"]),
            intent("raise_risk", ["The main risk is the timeline."], [r"\b(risk|concern|problem|issue|challenge)\b"]),
            intent("clarify_timeline", ["We need two weeks."], [r"\b(timeline|deadline|week|month|schedule|resource)\b"]),
            intent("propose_action", ["I suggest we test it first."], [r"\b(action|suggest|next|owner|follow up|do)\b"]),
        ],
        milestones=["opinion", "risk", "timeline", "action_item"],
        keywords=["proposal", "risk", "timeline", "resource", "agree", "concern", "action", "deadline"],
        phrase_bank={
            "i don't agree": "I see it differently because ...",
            "you are wrong": "I have a different perspective on that point.",
            "we should do it": "I suggest we ... because ...",
        },
    ),
    "ielts": Scenario(
        key="ielts",
        name="雅思口语",
        category="exam",
        role="You are an IELTS Speaking examiner. Ask concise questions and keep a formal exam tone.",
        user_goal="Answer IELTS-style questions with fluency, coherence, vocabulary range, and grammatical accuracy.",
        opening="Let's talk about daily routines. What part of your day do you enjoy the most?",
        required_slots=["answer", "reason", "example", "reflection"],
        slot_prompts={
            "answer": "Give a direct answer first.",
            "reason": "Why do you feel that way?",
            "example": "Can you give a specific example?",
            "reflection": "How has this changed compared with the past?",
        },
        intents=[
            intent("direct_answer", ["I enjoy the evening most."], [r"\b(i enjoy|i prefer|my favorite|i usually|i often)\b"]),
            intent("give_reason", ["because it helps me relax."], [r"\b(because|since|as|the reason)\b"]),
            intent("give_example", ["For example, last week I..."], [r"\b(for example|for instance|last week|once|when i)\b"]),
            intent("compare_reflect", ["In the past, I used to..."], [r"\b(used to|in the past|nowadays|compared|change)\b"]),
        ],
        milestones=["answer", "reason", "example", "reflection"],
        keywords=["because", "example", "usually", "prefer", "used", "nowadays", "experience", "important"],
        phrase_bank={
            "very good": "particularly valuable",
            "many things": "a wide range of activities",
            "i like it": "I find it enjoyable because ...",
        },
    ),
}


COMMON_CORRECTIONS = [
    (re.compile(r"\bi am agree\b", re.I), "I agree", "Use 'agree' as a verb without 'am'.", "grammar"),
    (re.compile(r"\bhe go\b", re.I), "he goes", "Use third-person singular -s in the present simple.", "grammar"),
    (re.compile(r"\bshe go\b", re.I), "she goes", "Use third-person singular -s in the present simple.", "grammar"),
    (re.compile(r"\bi have (\w+) yesterday\b", re.I), r"I had \1 yesterday", "Use past tense with a past-time marker.", "tense"),
    (re.compile(r"\bdiscuss about\b", re.I), "discuss", "Use 'discuss' without 'about'.", "collocation"),
    (re.compile(r"\bmore better\b", re.I), "better", "Avoid double comparatives.", "grammar"),
    (re.compile(r"\badvices\b", re.I), "advice", "'Advice' is usually uncountable.", "word_form"),
    (re.compile(r"\binformations\b", re.I), "information", "'Information' is uncountable.", "word_form"),
    (re.compile(r"\bI very like\b", re.I), "I really like", "Use an adverb before 'like'.", "expression"),
    (re.compile(r"\bi want go\b", re.I), "I'd like to go", "Use 'would like to' or 'want to' before a verb.", "grammar"),
]


FILLERS = {"um", "uh", "er", "ah", "like"}
SESSIONS: dict[str, Session] = {}
USER_PROGRESS: dict[str, list[dict[str, Any]]] = {}


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if not length:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def clamp_score(value: float, low: int = 35, high: int = 99) -> int:
    return int(max(low, min(high, round(value))))


def scenario_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": item.key,
            "name": item.name,
            "category": item.category,
            "goal": item.user_goal,
            "milestones": item.milestones,
        }
        for item in SCENARIOS.values()
    ]


def detect_intent(text: str, scenario: Scenario) -> str:
    lowered = text.lower()
    best_name = "general_answer"
    best_score = 0
    for rule in scenario.intents:
        score = 0
        for pattern in rule.patterns:
            if re.search(pattern, lowered):
                score += 2
        for example in rule.examples:
            score += len(set(words(example)).intersection(words(lowered)))
        if score > best_score:
            best_score = score
            best_name = rule.name
    return best_name


def extract_slots(text: str, scenario: Scenario, intent_name: str) -> dict[str, str]:
    lowered = text.lower()
    extracted: dict[str, str] = {}

    if scenario.key == "restaurant":
        if match := re.search(r"\b(water|tea|coffee|juice|cola|wine|beer)\b", lowered):
            extracted["drink"] = match.group(1)
        if match := re.search(r"\b(steak|pasta|salad|burger|rice|noodle|chicken|fish|soup)\b", lowered):
            extracted["main_course"] = match.group(1)
        if re.search(r"\b(allerg|spicy|mild|rare|medium|well done|vegetarian|no\s+\w+)\b", lowered):
            extracted["preference"] = text
        if re.search(r"\b(bill|check|pay|card|cash|together|separately)\b", lowered):
            extracted["payment"] = text
    elif scenario.key == "travel":
        if match := re.search(r"\b(to|for)\s+([a-z][a-z\s]{2,30})", lowered):
            extracted["destination"] = match.group(2).strip()
        if match := re.search(r"\b(subway|metro|bus|taxi|train|walk|uber)\b", lowered):
            extracted["transport"] = match.group(1)
        if re.search(r"\b(\d{1,2}(:\d{2})?\s?(am|pm)?|minutes|hour|morning|afternoon|evening)\b", lowered):
            extracted["time"] = text
    elif scenario.key == "interview":
        if re.search(r"\b(experience|major|worked|study|background|role)\b", lowered):
            extracted["background"] = text
        if re.search(r"\b(strength|good at|skill|strong|advantage)\b", lowered):
            extracted["strength"] = text
        if re.search(r"\b(example|project|result|delivered|improved|learned)\b", lowered):
            extracted["example"] = text
        if "?" in text or re.search(r"\b(question|team|culture|position|next step)\b", lowered):
            extracted["question"] = text
    elif scenario.key == "meeting":
        if intent_name == "share_opinion":
            extracted["opinion"] = text
        if intent_name == "raise_risk":
            extracted["risk"] = text
        if intent_name == "clarify_timeline":
            extracted["timeline"] = text
        if intent_name == "propose_action":
            extracted["action_item"] = text
    elif scenario.key == "ielts":
        if intent_name == "direct_answer":
            extracted["answer"] = text
        if intent_name == "give_reason":
            extracted["reason"] = text
        if intent_name == "give_example":
            extracted["example"] = text
        if intent_name == "compare_reflect":
            extracted["reflection"] = text

    return extracted


def missing_slots(session: Session) -> list[str]:
    return [slot for slot in session.scenario.required_slots if slot not in session.slots]


def estimate_phoneme_scores(text: str, confidence: float, wpm: int) -> list[dict[str, Any]]:
    lowered = text.lower()
    checks = [
        ("TH", r"\b(think|three|thanks|with|that|this|the|there)\b", "Put your tongue lightly between your teeth for /θ/ or /ð/."),
        ("R/L", r"\b(really|role|world|right|learn|clear|restaurant)\b", "Separate /r/ and /l/: curl the tongue slightly for /r/, touch the ridge for /l/."),
        ("V/W", r"\b(very|view|visit|work|would|water)\b", "For /v/, touch teeth to lower lip; for /w/, round your lips."),
        ("Final consonants", r"\b\w+(t|d|k|p|s|z)\b", "Keep final consonants audible, especially at the end of a sentence."),
        ("Word stress", r"\b(important|experience|recommend|proposal|comfortable|opportunity)\b", "Mark the stressed syllable and reduce unstressed vowels."),
    ]
    rows = []
    for label, pattern, tip in checks:
        if re.search(pattern, lowered):
            pace_penalty = 8 if wpm > 165 or wpm < 80 else 0
            score = clamp_score(confidence * 100 - pace_penalty - len(rows) * 2, 45, 98)
            rows.append({"unit": label, "gop": score, "tip": tip})
    if not rows:
        rows.append(
            {
                "unit": "Overall intelligibility",
                "gop": clamp_score(confidence * 100, 45, 96),
                "tip": "No high-risk phoneme was detected. Keep sentence stress steady.",
            }
        )
    return rows[:4]


def assess_pronunciation(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text", ""))
    tokens = words(text)
    duration = max(float(payload.get("durationSec") or 0), 0.1)
    confidence = float(payload.get("confidence") or 0.76)
    acoustic = payload.get("audioFeatures") or {}
    wpm = round(len(tokens) / duration * 60)
    filler_count = sum(1 for token in tokens if token in FILLERS)
    long_pause_count = int(acoustic.get("longPauseCount", 0))
    volume_stability = float(acoustic.get("volumeStability", 0.82))
    confidence_score = clamp_score(confidence * 100, 30, 99)
    pace_score = max(45, 100 - min(abs(wpm - 125), 90))
    gop_units = estimate_phoneme_scores(text, confidence, wpm)
    gop_average = statistics.mean(item["gop"] for item in gop_units)
    score = clamp_score(gop_average * 0.45 + confidence_score * 0.25 + pace_score * 0.2 + volume_stability * 10 - filler_count * 4 - long_pause_count * 3)

    if wpm < 85:
        pace_label = "偏慢"
    elif wpm > 165:
        pace_label = "偏快"
    else:
        pace_label = "自然"

    return {
        "score": score,
        "method": "GOP-style proxy" if not acoustic else "GOP acoustic adapter",
        "recognitionConfidence": confidence_score,
        "speechRateWpm": wpm,
        "pace": pace_label,
        "fillerCount": filler_count,
        "longPauseCount": long_pause_count,
        "phonemeScores": gop_units,
        "feedback": pronunciation_feedback(score, pace_label, filler_count, gop_units),
    }


def pronunciation_feedback(score: int, pace_label: str, filler_count: int, units: list[dict[str, Any]]) -> str:
    if score >= 86 and pace_label == "自然" and filler_count <= 1:
        return "发音清晰，语速稳定。下一步可以练更自然的重音、连读和停顿。"
    notes = []
    if score < 72:
        notes.append("可懂度偏低，建议放慢一点并突出句尾辅音。")
    if pace_label == "偏慢":
        notes.append("语速略慢，尝试按意群连续说完整句。")
    if pace_label == "偏快":
        notes.append("语速略快，关键词前后留出短暂停顿。")
    if filler_count > 1:
        notes.append("填充词较多，先想好句子主干再开口。")
    if units:
        weakest = min(units, key=lambda item: item["gop"])
        notes.append(f"重点练习 {weakest['unit']}：{weakest['tip']}")
    return " ".join(notes)


def find_corrections(text: str) -> list[dict[str, str]]:
    corrections: list[dict[str, str]] = []
    for pattern, replacement, reason, category in COMMON_CORRECTIONS:
        if pattern.search(text):
            corrections.append(
                {
                    "original": text,
                    "corrected": pattern.sub(replacement, text),
                    "reason": reason,
                    "category": category,
                    "timing": "after_turn",
                }
            )
    return corrections[:5]


def expression_tips(text: str, scenario: Scenario, intent_name: str, missing: list[str]) -> list[str]:
    lowered = text.lower()
    tips = []
    for rough, polished in scenario.phrase_bank.items():
        if rough in lowered:
            tips.append(f"把 “{rough}” 升级为 “{polished}”")
    if len(words(text)) < 7:
        tips.append("尝试用完整句回答：观点 + 原因或细节。")
    if missing:
        tips.append(f"本轮还可以补充：{scenario.slot_prompts[missing[0]]}")
    if scenario.key == "ielts" and intent_name not in {"give_reason", "give_example", "compare_reflect"}:
        tips.append("雅思回答建议加入 because / for example / compared with the past。")
    return tips[:4]


def rubric_scores(session: Session) -> dict[str, int]:
    if not session.turns:
        return {"pronunciation": 0, "fluency": 0, "grammar": 0, "scenarioFit": 0, "overall": 0}
    pronunciation = round(statistics.mean(t.pronunciation["score"] for t in session.turns))
    filler_total = sum(t.pronunciation["fillerCount"] for t in session.turns)
    avg_wpm = statistics.mean(t.pronunciation["speechRateWpm"] for t in session.turns)
    fluency = clamp_score(88 - filler_total * 3 - abs(avg_wpm - 125) * 0.18, 40, 98)
    correction_count = sum(len(t.corrections) for t in session.turns)
    grammar = clamp_score(94 - correction_count * 7, 40, 98)
    slot_completion = len(session.slots) / max(len(session.scenario.required_slots), 1)
    keyword_hits = len(set(words(" ".join(t.user_text for t in session.turns))).intersection(session.scenario.keywords))
    scenario_fit = clamp_score(50 + slot_completion * 34 + keyword_hits * 3 + len(session.turns) * 2, 45, 98)
    overall = round(pronunciation * 0.3 + fluency * 0.25 + grammar * 0.25 + scenario_fit * 0.2)
    return {
        "pronunciation": pronunciation,
        "fluency": fluency,
        "grammar": grammar,
        "scenarioFit": scenario_fit,
        "overall": overall,
    }


def dialogue_reply(session: Session, intent_name: str, missing: list[str]) -> str:
    if missing:
        return session.scenario.slot_prompts[missing[0]]
    turn_count = len(session.turns)
    if session.scenario.key == "ielts":
        followups = [
            "Do you think this will change in the future?",
            "Can you explain that in a little more detail?",
            "Would people in your country generally agree with you?",
        ]
    elif session.scenario.key == "meeting":
        followups = [
            "That makes sense. Who should own the next step?",
            "What evidence would help us make the decision?",
            "How would you explain this to a stakeholder?",
        ]
    elif session.scenario.key == "restaurant":
        followups = [
            "Great. Would you like anything else with that?",
            "Perfect. Shall I bring the bill now?",
            "Thanks. Your order is complete. Would you like to practice paying?",
        ]
    else:
        followups = [
            "Thanks, that is helpful. Could you add one specific example?",
            "Good. What was the result?",
            "What question would you like to ask next?",
        ]
    return followups[min(turn_count, len(followups) - 1)]


def openai_reply(session: Session, user_text: str, intent_name: str, missing: list[str]) -> tuple[str | None, int]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, 0
    started = time.perf_counter()
    history = []
    for turn in session.turns[-6:]:
        history.append({"role": "user", "content": turn.user_text})
        history.append({"role": "assistant", "content": turn.assistant_text})
    prompt = {
        "scenario": session.scenario.name,
        "assistant_role": session.scenario.role,
        "learner_goal": session.scenario.user_goal,
        "level": session.level,
        "detected_intent": intent_name,
        "filled_slots": session.slots,
        "missing_slots": missing,
        "rules": [
            "Reply as the role-play partner, not as a teacher.",
            "Keep the reply under 45 words.",
            "Ask exactly one natural follow-up question.",
            "Use the missing slot prompt if a required slot is still missing.",
            "Do not correct grammar inside the role-play reply.",
        ],
        "history": history,
        "learner_latest_message": user_text,
    }
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {"role": "system", "content": "You are a realistic English speaking practice partner."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0.7,
        "max_output_tokens": 120,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, int((time.perf_counter() - started) * 1000)
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                chunks.append(content.get("text", ""))
    text = " ".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()
    return text or None, int((time.perf_counter() - started) * 1000)


def start_session(payload: dict[str, Any]) -> dict[str, Any]:
    scenario = SCENARIOS.get(payload.get("scenario", "restaurant"), SCENARIOS["restaurant"])
    session_id = str(uuid.uuid4())
    session = Session(
        id=session_id,
        scenario=scenario,
        level=str(payload.get("level", "B1")),
        user_id=str(payload.get("userId") or "anonymous"),
    )
    SESSIONS[session_id] = session
    return {
        "sessionId": session_id,
        "scenario": scenario.name,
        "opening": scenario.opening,
        "goal": scenario.user_goal,
        "milestones": scenario.milestones,
        "requiredSlots": scenario.required_slots,
        "engine": {
            "asr": "Browser Web Speech API demo adapter",
            "llm": "OpenAI Responses API" if os.environ.get("OPENAI_API_KEY") else "local dialogue manager",
            "tts": "Browser SpeechSynthesis demo adapter",
            "pronunciation": "GOP-style scoring adapter",
        },
    }


def respond(payload: dict[str, Any]) -> dict[str, Any]:
    session = SESSIONS.get(payload.get("sessionId"))
    if not session:
        raise KeyError("Session not found")
    total_started = time.perf_counter()
    user_text = str(payload.get("text", "")).strip()
    if not user_text:
        return {"error": "empty_text"}

    nlu_started = time.perf_counter()
    intent_name = detect_intent(user_text, session.scenario)
    new_slots = extract_slots(user_text, session.scenario, intent_name)
    session.slots.update(new_slots)
    current_missing = missing_slots(session)
    nlu_ms = int((time.perf_counter() - nlu_started) * 1000)

    scoring_started = time.perf_counter()
    pronunciation = assess_pronunciation({**payload, "text": user_text})
    corrections = find_corrections(user_text)
    tips = expression_tips(user_text, session.scenario, intent_name, current_missing)
    scoring_ms = int((time.perf_counter() - scoring_started) * 1000)

    dm_started = time.perf_counter()
    fallback = dialogue_reply(session, intent_name, current_missing)
    dm_ms = int((time.perf_counter() - dm_started) * 1000)
    assistant_text, llm_ms = openai_reply(session, user_text, intent_name, current_missing)
    assistant_text = assistant_text or fallback
    backend_ms = int((time.perf_counter() - total_started) * 1000)

    pipeline = {
        "asrClientMs": int(payload.get("asrClientMs") or 0),
        "nluMs": nlu_ms,
        "scoringMs": scoring_ms,
        "dmMs": dm_ms,
        "llmMs": llm_ms,
        "backendMs": backend_ms,
        "target": "<=2000ms",
    }
    turn = Turn(
        user_text=user_text,
        assistant_text=assistant_text,
        intent=intent_name,
        slots=dict(session.slots),
        missing_slots=current_missing,
        pronunciation=pronunciation,
        corrections=corrections,
        expression_tips=tips,
        pipeline=pipeline,
    )
    session.turns.append(turn)
    scores = rubric_scores(session)
    return {
        "assistant": assistant_text,
        "intent": intent_name,
        "slots": session.slots,
        "missingSlots": current_missing,
        "slotCompletion": round(len(session.slots) / max(len(session.scenario.required_slots), 1), 2),
        "pronunciation": pronunciation,
        "corrections": corrections,
        "expressionTips": tips,
        "pipeline": pipeline,
        "latencyMs": backend_ms,
        "scores": scores,
        "turnCount": len(session.turns),
    }


def revise_turn(payload: dict[str, Any]) -> dict[str, Any]:
    session = SESSIONS.get(payload.get("sessionId"))
    if not session or not session.turns:
        raise KeyError("Session not found")
    revised = str(payload.get("text", "")).strip()
    if not revised:
        return {"error": "empty_text"}
    last = session.turns[-1]
    last.user_text = revised
    last.intent = detect_intent(revised, session.scenario)
    session.slots.update(extract_slots(revised, session.scenario, last.intent))
    last.slots = dict(session.slots)
    last.missing_slots = missing_slots(session)
    last.corrections = find_corrections(revised)
    last.expression_tips = expression_tips(revised, session.scenario, last.intent, last.missing_slots)
    return {
        "intent": last.intent,
        "slots": last.slots,
        "missingSlots": last.missing_slots,
        "corrections": last.corrections,
        "expressionTips": last.expression_tips,
        "scores": rubric_scores(session),
    }


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    session = SESSIONS.get(payload.get("sessionId"))
    if not session:
        raise KeyError("Session not found")
    scores = rubric_scores(session)
    correction_count = sum(len(t.corrections) for t in session.turns)
    avg_latency = round(statistics.mean(t.pipeline["backendMs"] for t in session.turns)) if session.turns else 0
    completion = round(len(session.slots) / max(len(session.scenario.required_slots), 1), 2)
    dimensions = [
        ("发音清晰度", scores["pronunciation"]),
        ("流利度", scores["fluency"]),
        ("语法准确度", scores["grammar"]),
        ("场景完成度", scores["scenarioFit"]),
    ]
    strongest = max(dimensions, key=lambda item: item[1])[0]
    weakest = min(dimensions, key=lambda item: item[1])[0]
    record = {
        "at": time.time(),
        "scenario": session.scenario.key,
        "overall": scores["overall"],
        "pronunciation": scores["pronunciation"],
        "grammar": scores["grammar"],
    }
    USER_PROGRESS.setdefault(session.user_id, []).append(record)
    recent = USER_PROGRESS.get(session.user_id, [])[-5:]
    progress_delta = recent[-1]["overall"] - recent[0]["overall"] if len(recent) > 1 else 0
    return {
        "scenario": session.scenario.name,
        "durationSec": round(time.time() - session.started_at),
        "turns": len(session.turns),
        "scores": scores,
        "strongest": strongest,
        "focus": weakest,
        "slotCompletion": completion,
        "filledSlots": session.slots,
        "correctionCount": correction_count,
        "averageLatencyMs": avg_latency,
        "progressDelta": progress_delta,
        "nextDrills": [
            f"围绕“{session.scenario.name}”复述今天 3 个回答，每次控制在 20-35 秒。",
            "重听自己的录音，检查是否包含观点、原因和具体例子。",
            f"下次重点提升：{weakest}。",
        ],
        "transcript": [
            {
                "user": t.user_text,
                "assistant": t.assistant_text,
                "intent": t.intent,
                "pronunciation": t.pronunciation,
                "pipeline": t.pipeline,
            }
            for t in session.turns
        ],
    }


def delete_user_data(payload: dict[str, Any]) -> dict[str, Any]:
    user_id = str(payload.get("userId") or "anonymous")
    removed_sessions = [sid for sid, session in SESSIONS.items() if session.user_id == user_id]
    for sid in removed_sessions:
        del SESSIONS[sid]
    USER_PROGRESS.pop(user_id, None)
    return {"deletedSessions": len(removed_sessions), "deletedProgress": True}


class PracticeHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        if path == "/":
            return str(STATIC_DIR / "index.html")
        return str(ROOT / path.lstrip("/"))

    def do_GET(self) -> None:
        if self.path == "/api/scenarios":
            json_response(self, 200, {"scenarios": scenario_catalog()})
            return
        if self.path == "/api/health":
            json_response(self, 200, {"ok": True, "sessions": len(SESSIONS)})
            return
        super().do_GET()

    def do_POST(self) -> None:
        try:
            payload = read_json(self)
            routes = {
                "/api/start": start_session,
                "/api/respond": respond,
                "/api/revise": revise_turn,
                "/api/summary": summarize,
                "/api/delete-user-data": delete_user_data,
            }
            if self.path not in routes:
                json_response(self, 404, {"error": "not_found"})
                return
            result = routes[self.path](payload)
            json_response(self, 400 if result.get("error") else 200, result)
        except KeyError as exc:
            json_response(self, 404, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - demo server should return visible errors.
            json_response(self, 500, {"error": str(exc)})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), PracticeHandler)
    print(f"Speaking practice app running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
