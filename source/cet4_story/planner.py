from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARTICLE_COUNT = 137
CAPACITIES = [45] * 99 + [44] * 38
ARC_LENGTHS = [14] * 9 + [11]
REVIEW_OFFSETS = [0, 1, 3, 7, 14, 30]
CONTEXT_REVIEW_LIMIT = 18


@dataclass(frozen=True)
class Arc:
    english: str
    chinese: str
    theme: str
    setting: str
    goal: str
    conflict: str
    outcome: str
    keywords: tuple[str, ...]


ARCS = [
    Arc("New Ground", "新的起点", "大学生活与个人成长", "Harbor City University", "make campus information easier to use", "confidence and unequal access", "the students commit to a shared project", ("university", "college", "campus", "student", "dormitory", "youth", "growth", "grow", "confidence", "personal", "individual", "independent", "adapt", "freshman", "leader", "宿舍", "大学", "成长")),
    Arc("Learning How to Learn", "学会学习", "学习方法与教育", "the library and classrooms", "turn an idea into evidence", "weak research and ineffective habits", "the team adopts deliberate, verifiable methods", ("learn", "study", "education", "teach", "school", "academic", "research", "knowledge", "memory", "library", "book", "read", "write", "exam", "class", "skill", "method", "language", "学习", "教育")),
    Arc("Promises and Pressure", "承诺与压力", "友谊、家庭与人际关系", "dormitories and family homes", "keep relationships honest while work intensifies", "family duties and unspoken resentment", "roles are renegotiated without ending the friendship", ("friend", "family", "relationship", "parent", "mother", "father", "child", "emotion", "trust", "communicate", "love", "marriage", "home", "affection", "person", "care", "家庭", "朋友")),
    Arc("The First Real Deadline", "第一个真实期限", "求职、职场与职业发展", "a career fair and civic-tech internship", "deliver useful work for real users", "career pressure and a rushed release", "the team accepts professional accountability", ("career", "job", "work", "office", "business", "profession", "employ", "manager", "interview", "company", "industry", "trade", "service", "contract", "customer", "职业", "工作", "[经]")),
    Arc("Across Borders", "跨越边界", "旅行、交通与文化交流", "rail routes and an exchange campus", "adapt the project across languages and systems", "transport disruption and cultural assumptions", "Aisha becomes a continuing collaborator", ("travel", "transport", "train", "flight", "journey", "culture", "foreign", "international", "language", "ship", "road", "vehicle", "hotel", "country", "geography", "traffic", "旅行", "文化")),
    Arc("The Cost of Always Being Busy", "忙碌的代价", "健康、运动与生活习惯", "a clinic, sports center, and park", "restore sustainable habits and accessible participation", "Daniel hides stress until a preventable setback", "health becomes a product and team requirement", ("health", "sport", "exercise", "medical", "body", "habit", "sleep", "stress", "diet", "disease", "doctor", "hospital", "food", "drug", "mental", "physical", "健康", "运动", "[医]")),
    Arc("What the System Remembers", "系统记住了什么", "科学、技术与互联网", "an innovation lab and online workspace", "build a secure and accessible service", "a data leak reveals weak consent", "the launch pauses for a responsible redesign", ("science", "technology", "computer", "internet", "data", "digital", "online", "software", "network", "machine", "device", "physics", "chemical", "calculate", "system", "engineering", "energy", "技术", "科学", "[计]", "[化]", "[机]")),
    Arc("The River Answers Back", "河流的回应", "环境、自然与可持续发展", "the river district and field station", "test an environmental model with residents", "flooding exposes missing local knowledge", "the plan is rebuilt with community evidence", ("environment", "nature", "climate", "river", "water", "energy", "pollution", "sustainable", "ecology", "animal", "plant", "earth", "air", "weather", "agriculture", "forest", "ocean", "环境", "自然", "[农]")),
    Arc("Who Pays and Who Decides", "谁承担，谁决定", "社会问题、经济与公共生活", "city hall and local businesses", "fund a fair public service", "scarce money and competing interests", "trade-offs and evidence are made public", ("society", "public", "economy", "economic", "government", "law", "money", "market", "community", "social", "politic", "legal", "finance", "tax", "policy", "citizen", "社会", "经济", "[法]", "[经]")),
    Arc("A Choice That Has a Cost", "有代价的选择", "心理、决策、责任与人生选择", "graduation and Harbor City's first workplace", "publish results and choose responsible next steps", "fear, ambition, and irreversible consequences", "the friends take separate but connected paths", ("decision", "choice", "responsibility", "psychology", "mind", "future", "moral", "life", "graduate", "think", "behavior", "conscious", "emotion", "value", "duty", "ethic", "sacrifice", "risk", "责任", "选择")),
]

BEATS = [
    ("A Signal", "一个信号", "The characters encounter the arc's central problem through a concrete consequence."),
    ("The First Promise", "第一次承诺", "They define an immediate goal and commit resources before all risks are visible."),
    ("A Missing Voice", "缺席的声音", "A person affected by the plan reveals information the group overlooked."),
    ("Evidence on the Table", "摆上桌面的证据", "The team gathers and compares evidence instead of relying on assumptions."),
    ("The Trial Run", "第一次试行", "A limited attempt produces useful results as well as a new constraint."),
    ("Pressure Builds", "压力上升", "Time, money, health, or trust makes the original plan harder to maintain."),
    ("The Disagreement", "分歧", "Two defensible priorities conflict and the characters must explain their motives."),
    ("What the Numbers Hide", "数字隐藏了什么", "Quantitative evidence is checked against lived experience and context."),
    ("A Better Question", "更好的问题", "The group reframes the problem after recognizing a false assumption."),
    ("The Second Attempt", "第二次尝试", "A revised approach is tested under more realistic conditions."),
    ("Outside Pressure", "外部压力", "An institution or stakeholder imposes a condition the team cannot ignore."),
    ("The Decision", "决定", "The characters choose a course of action and accept a specific cost."),
    ("Consequences", "后果", "The decision changes relationships, evidence, and the next available choices."),
    ("The Bridge Forward", "通向下一程", "The arc closes with an unresolved consequence that launches the next stage."),
]


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _frequency(row: dict[str, str]) -> int:
    values: list[int] = []
    for field in ("ecdict_bnc_frequency", "ecdict_contemporary_frequency"):
        try:
            value = int(float(row.get(field, "") or 0))
        except ValueError:
            value = 0
        if value > 0:
            values.append(value)
    return min(values) if values else 10_000_000


def _stable_number(value: str) -> int:
    return int(hashlib.sha1(value.encode("utf-8")).hexdigest()[:12], 16)


def _theme_score(row: dict[str, str], arc: Arc) -> int:
    lemma = row["lemma"].casefold()
    text = " ".join((lemma, row.get("english_definition", ""), row.get("chinese_meaning", ""))).casefold()
    score = 0
    for keyword in arc.keywords:
        key = keyword.casefold()
        if lemma == key:
            score += 8
        elif key in text:
            score += 1
    return score


def _chapter_arcs() -> tuple[list[int], list[list[int]]]:
    chapter_to_arc: list[int] = []
    arc_chapters: list[list[int]] = []
    chapter = 1
    for arc_index, length in enumerate(ARC_LENGTHS):
        chapters = list(range(chapter, chapter + length))
        arc_chapters.append(chapters)
        chapter_to_arc.extend([arc_index] * length)
        chapter += length
    assert chapter == ARTICLE_COUNT + 1
    return chapter_to_arc, arc_chapters


STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "being", "used",
    "one", "two", "three", "have", "has", "having", "make", "made", "something",
    "someone", "somebody", "thing", "things", "which", "when", "where", "what",
    "very", "more", "most", "less", "than", "not", "without", "about", "also",
    "especially", "usually", "relating", "characterized", "quality", "state", "act",
    "person", "people", "form", "manner", "degree", "part", "given", "such",
}


def _tokens(row: dict[str, str]) -> set[str]:
    text = " ".join((row.get("lemma", ""), row.get("english_definition", ""))).casefold()
    return {
        token for token in re.findall("[a-z][a-z-]{2,}", text)
        if token not in STOPWORDS
    }


def allocate(rows: list[dict[str, str]]) -> tuple[dict[str, int], list[list[dict[str, str]]]]:
    if len(rows) != sum(CAPACITIES) or len(rows) != 6127:
        raise ValueError(f"Expected 6,127 targets; got {len(rows)}")
    chapter_to_arc, arc_chapters = _chapter_arcs()
    assigned: list[list[dict[str, str]]] = [[] for _ in range(ARTICLE_COUNT)]
    mapping: dict[str, int] = {}
    token_cache = {row["vocabulary_id"]: _tokens(row) for row in rows}
    theme_scores = {
        row["vocabulary_id"]: [_theme_score(row, arc) for arc in ARCS]
        for row in rows
    }
    chapter_terms: list[Counter[str]] = []
    for chapter in range(1, ARTICLE_COUNT + 1):
        arc_index = chapter_to_arc[chapter - 1]
        beat_index = arc_chapters[arc_index].index(chapter)
        arc = ARCS[arc_index]
        beat = BEATS[beat_index]
        seed_text = " ".join((
            arc.english, arc.theme, arc.setting, arc.goal, arc.conflict, arc.outcome,
            beat[0], beat[2], " ".join(arc.keywords),
        )).casefold()
        seed_tokens = [token for token in re.findall("[a-z][a-z-]{2,}", seed_text) if token not in STOPWORDS]
        chapter_terms.append(Counter(seed_tokens))

    def available(chapter_number: int) -> bool:
        return len(assigned[chapter_number - 1]) < CAPACITIES[chapter_number - 1]

    def choose(chapters: list[int], row: dict[str, str]) -> int:
        possible = [chapter for chapter in chapters if available(chapter)]
        if not possible:
            possible = [chapter for chapter in range(1, ARTICLE_COUNT + 1) if available(chapter)]
        vocabulary_id = row["vocabulary_id"]
        word_tokens = token_cache[vocabulary_id]

        def affinity(chapter: int) -> int:
            terms = chapter_terms[chapter - 1]
            return sum(1 + min(terms[token], 3) for token in word_tokens if token in terms)

        return min(
            possible,
            key=lambda chapter: (
                -affinity(chapter),
                len(assigned[chapter - 1]) / CAPACITIES[chapter - 1],
                _stable_number(f"{vocabulary_id}:{chapter}"),
            ),
        )

    ordered = sorted(
        rows,
        key=lambda row: (
            -max(theme_scores[row["vocabulary_id"]]),
            -len(token_cache[row["vocabulary_id"]]),
            _frequency(row),
            _stable_number(row["vocabulary_id"]),
        ),
    )
    for row in ordered:
        scores = theme_scores[row["vocabulary_id"]]
        best = max(scores)
        candidate_arcs = [index for index, score in enumerate(scores) if score == best and best > 0]
        if candidate_arcs:
            arc_index = min(
                candidate_arcs,
                key=lambda index: sum(len(assigned[ch - 1]) for ch in arc_chapters[index])
                / sum(CAPACITIES[ch - 1] for ch in arc_chapters[index]),
            )
            chapter = choose(arc_chapters[arc_index], row)
        else:
            chapter = choose(list(range(1, ARTICLE_COUNT + 1)), row)
        assigned[chapter - 1].append(row)
        mapping[row["vocabulary_id"]] = chapter
        chapter_terms[chapter - 1].update(token_cache[row["vocabulary_id"]])

    assert all(len(words) == capacity for words, capacity in zip(assigned, CAPACITIES, strict=True))
    assert len(mapping) == 6127
    for words in assigned:
        words.sort(key=lambda row: (_frequency(row), row["lemma"].casefold()))
    return mapping, assigned


def _article_id(chapter: int) -> str:
    return f"CH{chapter:03d}"


def build_reviews(
    rows: list[dict[str, str]], mapping: dict[str, int]
) -> tuple[list[dict[str, Any]], dict[int, list[str]]]:
    due: dict[int, list[tuple[dict[str, str], int, int]]] = {
        chapter: [] for chapter in range(1, ARTICLE_COUNT + 1)
    }
    for row in rows:
        learned = mapping[row["vocabulary_id"]]
        for stage, offset in enumerate(REVIEW_OFFSETS[1:], start=2):
            target = learned + offset
            if target <= ARTICLE_COUNT:
                due[target].append((row, learned, stage))

    contextual: dict[int, set[str]] = {}
    for chapter, items in due.items():
        ranked = sorted(
            items,
            key=lambda item: (
                _frequency(item[0]),
                _stable_number(f"review:{chapter}:{item[0]['vocabulary_id']}"),
            ),
        )
        contextual[chapter] = {
            item[0]["vocabulary_id"] for item in ranked[:CONTEXT_REVIEW_LIMIT]
        }

    schedule: list[dict[str, Any]] = []
    story_review_ids: dict[int, list[str]] = {chapter: [] for chapter in due}
    methods = ["cloze", "collocation", "active_recall"]
    for row in rows:
        vocabulary_id = row["vocabulary_id"]
        learned = mapping[vocabulary_id]
        schedule.append({
            "vocabulary_id": vocabulary_id,
            "lemma": row["lemma"],
            "learning_date": "",
            "review_stage": 1,
            "planned_review_date": "",
            "actual_review_date": "",
            "review_method": "new_story_context",
            "mastery_status": "unassessed",
            "source_article": _article_id(learned),
            "target_article": _article_id(learned),
            "learning_chapter": learned,
            "planned_review_chapter": learned,
            "interval_days": 0,
        })
        for stage, offset in enumerate(REVIEW_OFFSETS[1:], start=2):
            target = learned + offset
            target_article = _article_id(target) if target <= ARTICLE_COUNT else ""
            if target <= ARTICLE_COUNT and vocabulary_id in contextual[target]:
                method = "story_context"
                story_review_ids[target].append(vocabulary_id)
            else:
                method = methods[(stage - 2) % len(methods)]
            schedule.append({
                "vocabulary_id": vocabulary_id,
                "lemma": row["lemma"],
                "learning_date": "",
                "review_stage": stage,
                "planned_review_date": "",
                "actual_review_date": "",
                "review_method": method,
                "mastery_status": "unassessed",
                "source_article": _article_id(learned),
                "target_article": target_article,
                "learning_chapter": learned,
                "planned_review_chapter": target,
                "interval_days": offset,
            })
    assert len(schedule) == 6127 * 6
    return schedule, story_review_ids


def _plot_summary(arc: Arc, beat_index: int) -> str:
    _, _, action = BEATS[beat_index]
    return (
        f"At {arc.setting}, the group works to {arc.goal}. {action} "
        f"The immediate pressure comes from {arc.conflict}; the chapter must move toward "
        f"{arc.outcome} without resolving the entire arc early."
    )


def plan_curriculum(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    master_path = project_root / "vocabulary_master.csv"
    master_fields, rows = _read_csv(master_path)
    mapping, assigned = allocate(rows)
    schedule, story_reviews = build_reviews(rows, mapping)
    chapter_to_arc, arc_chapters = _chapter_arcs()

    curriculum_rows: list[dict[str, Any]] = []
    for chapter in range(1, ARTICLE_COUNT + 1):
        arc_index = chapter_to_arc[chapter - 1]
        arc = ARCS[arc_index]
        beat_index = arc_chapters[arc_index].index(chapter)
        beat_en, beat_zh, _ = BEATS[beat_index]
        new_ids = [row["vocabulary_id"] for row in assigned[chapter - 1]]
        review_ids = story_reviews[chapter]
        curriculum_rows.append({
            "article_id": _article_id(chapter),
            "chapter_number": chapter,
            "english_title": f"{arc.english}: {beat_en}",
            "chinese_title": f"{arc.chinese}：{beat_zh}",
            "theme": arc.theme,
            "plot_summary": _plot_summary(arc, beat_index),
            "new_vocabulary_ids": "|".join(new_ids),
            "review_vocabulary_ids": "|".join(review_ids),
            "planned_new_count": len(new_ids),
            "planned_review_count": len(review_ids),
            "status": "planned",
            "estimated_story_words": 380,
            "estimated_pages": 3,
            "arc_number": arc_index + 1,
            "story_day": chapter,
        })

    allocation_rows = [{
        "vocabulary_id": row["vocabulary_id"],
        "lemma": row["lemma"],
        "planned_article": _article_id(mapping[row["vocabulary_id"]]),
        "first_actual_article": "",
        "article_id": "",
        "occurrence_count": 0,
        "original_form": "",
        "matched_form": "",
        "context_sentence": "",
        "coverage_status": "planned",
        "match_method": "",
        "review_note": "",
    } for row in rows]

    for row in rows:
        row["assigned_article"] = _article_id(mapping[row["vocabulary_id"]])
        row["status"] = "planned"
    _write_csv(master_path, master_fields, rows)

    curriculum_fields = [
        "article_id", "chapter_number", "english_title", "chinese_title", "theme",
        "plot_summary", "new_vocabulary_ids", "review_vocabulary_ids",
        "planned_new_count", "planned_review_count", "status", "estimated_story_words",
        "estimated_pages", "arc_number", "story_day",
    ]
    _write_csv(project_root / "curriculum_plan.csv", curriculum_fields, curriculum_rows)
    _write_csv(
        project_root / "vocabulary_allocation.csv",
        [
            "vocabulary_id", "lemma", "planned_article", "first_actual_article",
            "article_id", "occurrence_count", "original_form", "matched_form",
            "context_sentence", "coverage_status", "match_method", "review_note",
        ],
        allocation_rows,
    )
    _write_csv(
        project_root / "review_schedule.csv",
        [
            "vocabulary_id", "lemma", "learning_date", "review_stage",
            "planned_review_date", "actual_review_date", "review_method",
            "mastery_status", "source_article", "target_article", "learning_chapter",
            "planned_review_chapter", "interval_days",
        ],
        schedule,
    )

    report = {
        "articles": ARTICLE_COUNT,
        "targets": len(rows),
        "chapters_with_45_new": sum(value == 45 for value in CAPACITIES),
        "chapters_with_44_new": sum(value == 44 for value in CAPACITIES),
        "review_rows": len(schedule),
        "story_context_review_assignments": sum(len(ids) for ids in story_reviews.values()),
        "estimated_story_pdf_pages": ARTICLE_COUNT * 3,
        "estimated_exercise_pages": ARTICLE_COUNT,
        "estimated_answer_pages": (ARTICLE_COUNT + 3) // 4,
    }
    return report
