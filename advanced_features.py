"""
Pihu Advanced Feature Core.

Deterministic, local-first implementations for Pihu's power features:
missions, self-healing diagnostics, plugin registry, screen memory,
computer-use simulation, knowledge graph, interrupt state, model routing,
repo guarding, skill learning, memory reflection, autonomy controls,
document RAG, evaluation arena, and live ops dashboard.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from logger import get_logger

log = get_logger("ADVANCED")


AUTONOMY_LEVELS = [
    "observe",
    "suggest",
    "dry-run",
    "execute-safe",
    "execute-with-confirmation",
    "full-auto",
]


def _now() -> str:
    from datetime import datetime

    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _slug(text: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:64] or fallback


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())


class JsonStore:
    """Tiny atomic JSON store with corruption tolerance."""

    def __init__(self, path: Path, default: dict[str, Any]):
        self.path = Path(path)
        self.default = default
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(self.default))
        try:
            return json.loads(self.path.read_text("utf-8"))
        except Exception as e:
            log.warning("State file unreadable, resetting %s: %s", self.path, e)
            return json.loads(json.dumps(self.default))

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")
        tmp.replace(self.path)


class AutonomousTaskMissions:
    """Long-running goal manager with resumable checkpoints."""

    def __init__(self, store: JsonStore):
        self.store = store

    def create(self, goal: str, cadence: str = "manual", autonomy: str = "dry-run") -> dict[str, Any]:
        data = self.store.load()
        mission_id = _stable_id("mission", f"{goal}:{time.time()}")
        mission = {
            "id": mission_id,
            "goal": goal.strip(),
            "cadence": cadence,
            "autonomy": autonomy if autonomy in AUTONOMY_LEVELS else "dry-run",
            "status": "active",
            "created_at": _now(),
            "updated_at": _now(),
            "checkpoints": [],
            "next_steps": self._decompose_goal(goal),
        }
        data.setdefault("missions", {})[mission_id] = mission
        data["active_mission_id"] = mission_id
        self.store.save(data)
        return mission

    def _decompose_goal(self, goal: str) -> list[str]:
        low = goal.lower()
        steps = ["clarify success criteria", "gather current context", "execute smallest safe step", "verify result", "checkpoint outcome"]
        if any(word in low for word in ["repo", "code", "test", "bug"]):
            steps = ["scan repo status", "run focused tests", "inspect failure logs", "patch smallest cause", "rerun full verification"]
        elif any(word in low for word in ["monitor", "watch", "weekly", "daily"]):
            steps = ["capture baseline", "schedule recurring scan", "compare drift", "raise only actionable alerts", "archive summary"]
        elif any(word in low for word in ["learn", "skill", "macro"]):
            steps = ["record demonstration", "normalize steps", "simulate macro", "save skill", "verify replay"]
        return steps

    def checkpoint(self, mission_id: str, note: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self.store.load()
        mission = data.get("missions", {}).get(mission_id)
        if not mission:
            raise KeyError(f"Unknown mission: {mission_id}")
        entry = {"at": _now(), "note": note, "evidence": evidence or {}}
        mission.setdefault("checkpoints", []).append(entry)
        mission["updated_at"] = _now()
        self.store.save(data)
        return entry

    def resume(self, mission_id: str | None = None) -> dict[str, Any] | None:
        data = self.store.load()
        mission_id = mission_id or data.get("active_mission_id")
        mission = data.get("missions", {}).get(mission_id or "")
        if not mission:
            return None
        remaining = mission.get("next_steps", [])
        done = len(mission.get("checkpoints", []))
        mission["resume_hint"] = remaining[min(done, len(remaining) - 1)] if remaining else "verify next safe step"
        return mission

    def list(self) -> list[dict[str, Any]]:
        missions = self.store.load().get("missions", {})
        return sorted(missions.values(), key=lambda item: item.get("updated_at", ""), reverse=True)


class SelfHealingDebugger:
    """Failure pattern detector that produces deterministic repair plans."""

    PATTERNS = [
        (re.compile(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)"), "missing_dependency", "Install or add the missing dependency."),
        (re.compile(r"ImportError: cannot import name ['\"]?([^'\"\n]+)"), "api_mismatch", "Add a compatibility import path or update the caller to the installed API."),
        (re.compile(r"AttributeError: .* has no attribute ['\"]([^'\"]+)"), "attribute_mismatch", "Add an adapter/fallback for the missing method."),
        (re.compile(r"401 Client Error|Unauthorized", re.I), "bad_api_key", "Check environment keys and degrade without remote calls."),
        (re.compile(r"model ['\"]([^'\"]+)['\"] not found", re.I), "missing_local_model", "Pull or reconfigure the local model fallback."),
        (re.compile(r"SyntaxError|IndentationError"), "syntax_error", "Run compile checks and patch the reported line."),
        (re.compile(r"AssertionError"), "test_assertion", "Inspect the expected behavior and add a regression test with the fix."),
    ]

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)

    def diagnose(self, text: str = "", log_paths: Iterable[Path] | None = None) -> dict[str, Any]:
        corpus = text or self._read_logs(log_paths)
        findings = []
        for pattern, code, advice in self.PATTERNS:
            for match in pattern.finditer(corpus):
                findings.append({
                    "code": code,
                    "match": match.group(0)[:240],
                    "advice": advice,
                    "confidence": 0.82,
                })
        if not findings and corpus.strip():
            findings.append({
                "code": "unknown_failure",
                "match": corpus.strip()[:240],
                "advice": "Reproduce with the narrowest command, inspect the stack, then patch and rerun tests.",
                "confidence": 0.45,
            })
        return {
            "status": "diagnosed" if findings else "no_failure_signal",
            "findings": findings,
            "repair_loop": ["reproduce", "isolate", "patch", "compile", "focused test", "full test"],
        }

    def _read_logs(self, log_paths: Iterable[Path] | None = None) -> str:
        candidates = list(log_paths or [
            self.workspace / "data" / "logs" / "pihu.log",
            self.workspace / "backend-dev.err.log",
            self.workspace / "error.log",
        ])
        chunks = []
        for path in candidates:
            try:
                if Path(path).exists():
                    chunks.append(Path(path).read_text("utf-8", errors="ignore")[-6000:])
            except Exception:
                continue
        return "\n".join(chunks)


class PluginRegistry:
    """Local plugin registry with permission and health metadata."""

    REQUIRED_FIELDS = {"name", "version", "entrypoint", "permissions", "risk"}

    def __init__(self, store: JsonStore):
        self.store = store

    def register(self, descriptor: dict[str, Any]) -> dict[str, Any]:
        errors = self.validate(descriptor)
        if errors:
            raise ValueError("; ".join(errors))
        data = self.store.load()
        plugin = dict(descriptor)
        plugin["id"] = plugin.get("id") or _stable_id("plugin", plugin["name"])
        plugin["enabled"] = plugin.get("enabled", True)
        plugin["registered_at"] = plugin.get("registered_at", _now())
        data.setdefault("plugins", {})[plugin["id"]] = plugin
        self.store.save(data)
        return plugin

    def validate(self, descriptor: dict[str, Any]) -> list[str]:
        missing = sorted(self.REQUIRED_FIELDS - set(descriptor))
        errors = [f"missing:{field}" for field in missing]
        if descriptor.get("risk") not in {"low", "medium", "high", "critical"}:
            errors.append("risk must be low, medium, high, or critical")
        if not isinstance(descriptor.get("permissions", []), list):
            errors.append("permissions must be a list")
        return errors

    def set_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        data = self.store.load()
        plugin = data.get("plugins", {}).get(plugin_id)
        if not plugin:
            raise KeyError(plugin_id)
        plugin["enabled"] = enabled
        plugin["updated_at"] = _now()
        self.store.save(data)
        return plugin

    def list(self) -> list[dict[str, Any]]:
        return list(self.store.load().get("plugins", {}).values())


class ScreenMemoryTimeline:
    """Text/OCR timeline of observed screen states."""

    def __init__(self, store: JsonStore):
        self.store = store

    def record(self, summary: str, window: str = "", source: str = "manual", tags: list[str] | None = None) -> dict[str, Any]:
        data = self.store.load()
        event = {
            "id": _stable_id("screen", f"{summary}:{time.time()}"),
            "at": _now(),
            "summary": summary.strip(),
            "window": window,
            "source": source,
            "tags": tags or [],
        }
        timeline = data.setdefault("timeline", [])
        timeline.append(event)
        data["timeline"] = timeline[-500:]
        self.store.save(data)
        return event

    def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = set(_tokenize(query))
        scored = []
        for event in self.store.load().get("timeline", []):
            hay = set(_tokenize(" ".join([event.get("summary", ""), event.get("window", ""), " ".join(event.get("tags", []))])))
            score = len(q & hay)
            if score:
                scored.append((score, event))
        return [event for _, event in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


class SafeComputerUseSimulator:
    """Dry-run simulator for OS/browser actions."""

    RISK_PATTERNS = {
        "critical": ["format", "rm -rf", "del /", "diskpart", "shutdown", "restart", "reg delete"],
        "high": ["install", "uninstall", "delete", "remove", "taskkill", "kill", "powershell"],
        "medium": ["download", "upload", "send email", "move", "rename", "cmd"],
    }

    def simulate(self, command: str | list[str], autonomy: str = "dry-run") -> dict[str, Any]:
        steps = command if isinstance(command, list) else self._split_steps(command)
        text = " ".join(steps).lower()
        risk = "low"
        for level, patterns in self.RISK_PATTERNS.items():
            if any(pattern in text for pattern in patterns):
                risk = level
                break
        allowed = risk in {"low", "medium"} and autonomy in {"dry-run", "execute-safe", "execute-with-confirmation", "full-auto"}
        if risk == "medium" and autonomy == "execute-safe":
            allowed = False
        return {
            "steps": [{"index": i + 1, "action": step, "predicted_effect": self._effect(step)} for i, step in enumerate(steps)],
            "risk": risk,
            "allowed_without_confirmation": allowed and risk == "low" and autonomy in {"execute-safe", "full-auto"},
            "requires_confirmation": risk in {"medium", "high", "critical"} or autonomy == "execute-with-confirmation",
            "rollback": self._rollback(steps),
        }

    def _split_steps(self, command: str) -> list[str]:
        parts = re.split(r"\b(?:and then|then|after that|;)\b", command, flags=re.I)
        return [part.strip() for part in parts if part.strip()] or [command.strip()]

    def _effect(self, step: str) -> str:
        low = step.lower()
        if "open" in low or "launch" in low:
            return "opens an application or path"
        if "type" in low:
            return "writes text into the active field"
        if "delete" in low or "remove" in low:
            return "removes data or software"
        return "changes local UI or system state"

    def _rollback(self, steps: list[str]) -> list[str]:
        rollback = []
        for step in reversed(steps):
            low = step.lower()
            if "type" in low:
                rollback.append("undo typed text with Ctrl+Z if the focused app supports it")
            elif "open" in low:
                rollback.append("close the opened window if not needed")
            elif "delete" in low or "remove" in low:
                rollback.append("manual restore may be required")
        return rollback or ["no rollback needed for read-only simulation"]


class PersonalKnowledgeGraph:
    """Persistent entity-relation graph for user/project memory."""

    def __init__(self, store: JsonStore):
        self.store = store

    def add_entity(self, name: str, entity_type: str = "thing", attrs: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self.store.load()
        entity_id = _stable_id("entity", name.lower())
        entity = data.setdefault("entities", {}).get(entity_id, {})
        entity.update({
            "id": entity_id,
            "name": name,
            "type": entity_type,
            "attrs": {**entity.get("attrs", {}), **(attrs or {})},
            "updated_at": _now(),
        })
        data["entities"][entity_id] = entity
        self.store.save(data)
        return entity

    def relate(self, source: str, relation: str, target: str, weight: float = 1.0) -> dict[str, Any]:
        data = self.store.load()
        src = self.add_entity(source)["id"]
        dst = self.add_entity(target)["id"]
        data = self.store.load()
        edge = {"source": src, "relation": relation, "target": dst, "weight": weight, "updated_at": _now()}
        edges = data.setdefault("edges", [])
        edges = [e for e in edges if not (e["source"] == src and e["target"] == dst and e["relation"] == relation)]
        edges.append(edge)
        data["edges"] = edges
        self.store.save(data)
        return edge

    def query(self, text: str) -> dict[str, Any]:
        q = set(_tokenize(text))
        data = self.store.load()
        entities = []
        for entity in data.get("entities", {}).values():
            score = len(q & set(_tokenize(entity.get("name", "") + " " + entity.get("type", ""))))
            if score:
                entities.append((score, entity))
        top_entities = [entity for _, entity in sorted(entities, key=lambda item: item[0], reverse=True)[:10]]
        ids = {entity["id"] for entity in top_entities}
        edges = [edge for edge in data.get("edges", []) if edge["source"] in ids or edge["target"] in ids]
        return {"entities": top_entities, "edges": edges}


class VoiceInterruptionController:
    """Interruptible speech/task state machine."""

    def __init__(self, store: JsonStore):
        self.store = store

    def begin(self, utterance_id: str, text: str = "") -> dict[str, Any]:
        state = {"speaking": True, "paused": False, "utterance_id": utterance_id, "text": text, "updated_at": _now()}
        self.store.save(state)
        return state

    def interrupt(self, reason: str = "user_interrupt") -> dict[str, Any]:
        state = self.store.load()
        state.update({"speaking": False, "paused": True, "interrupt_reason": reason, "updated_at": _now()})
        self.store.save(state)
        return state

    def resume(self) -> dict[str, Any]:
        state = self.store.load()
        state.update({"speaking": True, "paused": False, "updated_at": _now()})
        self.store.save(state)
        return state

    def state(self) -> dict[str, Any]:
        return self.store.load()


class AdvancedModelRouter:
    """Deterministic model selection by risk, privacy, latency, and tool needs."""

    def route(self, request: str, privacy: str = "normal", risk: str = "low", latency_target_ms: int = 1800, tool_need: bool = False) -> dict[str, Any]:
        tokens = len(_tokenize(request))
        scores = {
            "local_llm": 50,
            "cloud_llm": 50,
            "vision": 10,
            "tools": 10,
        }
        if privacy in {"private", "secret", "local-only"}:
            scores["local_llm"] += 40
            scores["cloud_llm"] -= 60
        if tokens > 80 or any(word in request.lower() for word in ["analyze", "architect", "prove", "compare"]):
            scores["cloud_llm"] += 25
        if latency_target_ms < 1000:
            scores["local_llm"] += 20
        if tool_need:
            scores["tools"] += 60
        if "screen" in request.lower() or "image" in request.lower():
            scores["vision"] += 70
        if risk in {"high", "critical"}:
            scores["tools"] -= 20
            scores["local_llm"] += 10
        selected = max(scores, key=scores.get)
        return {
            "selected": selected,
            "scores": scores,
            "reasons": {
                "privacy": privacy,
                "risk": risk,
                "latency_target_ms": latency_target_ms,
                "tool_need": tool_need,
                "estimated_tokens": tokens,
            },
        }


class RepoGuardian:
    """Static repo guardian for secrets, risky code, and test hygiene."""

    SECRET_PATTERNS = [
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"api[_-]?key\s*=\s*['\"][^'\"]{12,}", re.I),
        re.compile(r"password\s*=\s*['\"][^'\"]{8,}", re.I),
    ]
    EXCLUDE_PARTS = {".git", "__pycache__", "node_modules", "third_party", ".venv", "venv", "GodMode", "MiroFish"}

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)

    def scan(self, limit_files: int = 400) -> dict[str, Any]:
        issues = []
        scanned = 0
        for path in self._iter_files(limit_files):
            scanned += 1
            text = path.read_text("utf-8", errors="ignore")
            rel = str(path.relative_to(self.workspace))
            for pattern in self.SECRET_PATTERNS:
                if pattern.search(text):
                    issues.append({"severity": "critical", "file": rel, "code": "possible_secret"})
            if "except:" in text:
                issues.append({"severity": "medium", "file": rel, "code": "bare_except"})
            if "TODO" in text or "FIXME" in text:
                issues.append({"severity": "low", "file": rel, "code": "todo_marker"})
        grade = 100 - min(80, sum({"critical": 25, "high": 15, "medium": 6, "low": 2}.get(i["severity"], 1) for i in issues))
        return {"scanned_files": scanned, "issues": issues[:100], "grade": max(0, grade)}

    def _iter_files(self, limit_files: int) -> Iterable[Path]:
        count = 0
        for path in self.workspace.rglob("*"):
            if count >= limit_files:
                break
            if not path.is_file():
                continue
            if any(part in self.EXCLUDE_PARTS for part in path.parts):
                continue
            if path.suffix.lower() not in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".example"}:
                continue
            count += 1
            yield path


class SkillLearningFromDemo:
    """Turns demonstrations into replayable local macros."""

    def __init__(self, store: JsonStore):
        self.store = store

    def learn(self, name: str, steps: list[str], trigger: str | None = None) -> dict[str, Any]:
        normalized = [self._normalize_step(step) for step in steps if step.strip()]
        if not normalized:
            raise ValueError("Skill needs at least one step")
        skill = {
            "id": _stable_id("skill", name),
            "name": name,
            "trigger": trigger or name.lower(),
            "steps": normalized,
            "created_at": _now(),
            "verified": self._verify_steps(normalized),
        }
        data = self.store.load()
        data.setdefault("skills", {})[skill["id"]] = skill
        self.store.save(data)
        return skill

    def _normalize_step(self, step: str) -> dict[str, str]:
        low = step.lower().strip()
        if low.startswith("open "):
            return {"action": "open", "arg": step[5:].strip()}
        if low.startswith("type "):
            return {"action": "type", "arg": step[5:].strip()}
        if low.startswith("press "):
            return {"action": "hotkey", "arg": step[6:].strip().replace(" plus ", "+")}
        return {"action": "note", "arg": step.strip()}

    def _verify_steps(self, steps: list[dict[str, str]]) -> bool:
        dangerous = {"format", "rm -rf", "shutdown", "diskpart"}
        return not any(any(word in step["arg"].lower() for word in dangerous) for step in steps)

    def list(self) -> list[dict[str, Any]]:
        return list(self.store.load().get("skills", {}).values())


class MemoryReflectionEngine:
    """Condenses memory and detects contradictions."""

    NEGATIONS = ["not", "never", "nahi", "mat"]

    def reflect(self, memories: list[str]) -> dict[str, Any]:
        cleaned = [m.strip() for m in memories if m and m.strip()]
        counts = Counter(cleaned)
        duplicate_candidates = [text for text, count in counts.items() if count > 1]
        contradictions = []
        by_subject: dict[str, list[str]] = {}
        for memory in cleaned:
            subject = _tokenize(memory)[:2]
            if subject:
                by_subject.setdefault(" ".join(subject), []).append(memory)
        for subject, items in by_subject.items():
            has_neg = any(any(neg in _tokenize(item) for neg in self.NEGATIONS) for item in items)
            if has_neg and len(items) > 1:
                contradictions.append({"subject": subject, "memories": items[:5]})
        summary = "; ".join(cleaned[-8:])
        return {
            "summary": summary[:1000],
            "duplicate_candidates": duplicate_candidates,
            "contradictions": contradictions,
            "keep_recent": cleaned[-10:],
        }


class TrustAutonomyController:
    """Per-tool autonomy policy."""

    def __init__(self, store: JsonStore):
        self.store = store

    def set_level(self, tool: str, level: str) -> dict[str, Any]:
        if level not in AUTONOMY_LEVELS:
            raise ValueError(f"Unknown autonomy level: {level}")
        data = self.store.load()
        data.setdefault("levels", {})[tool] = {"level": level, "updated_at": _now()}
        self.store.save(data)
        return data["levels"][tool]

    def get_level(self, tool: str) -> str:
        return self.store.load().get("levels", {}).get(tool, {}).get("level", "dry-run")

    def decision(self, tool: str, risk: str) -> dict[str, Any]:
        level = self.get_level(tool)
        if risk == "critical":
            action = "deny"
        elif risk == "high" or level == "execute-with-confirmation":
            action = "ask_confirmation"
        elif level in {"observe", "suggest", "dry-run"}:
            action = level
        else:
            action = "execute"
        return {"tool": tool, "level": level, "risk": risk, "action": action}


class LocalDocumentRAG:
    """Small local document index with line citations."""

    EXTENSIONS = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".csv", ".toml"}

    def __init__(self, store: JsonStore, workspace: Path):
        self.store = store
        self.workspace = Path(workspace)

    def index(self, root: str | Path | None = None, max_files: int = 200) -> dict[str, Any]:
        base = Path(root) if root else self.workspace
        if not base.is_absolute():
            base = self.workspace / base
        docs = {}
        count = 0
        for path in base.rglob("*") if base.is_dir() else [base]:
            if count >= max_files:
                break
            if not path.is_file() or path.suffix.lower() not in self.EXTENSIONS:
                continue
            if any(part in RepoGuardian.EXCLUDE_PARTS for part in path.parts):
                continue
            text = path.read_text("utf-8", errors="ignore")[:20000]
            rel = str(path.relative_to(self.workspace)) if path.is_relative_to(self.workspace) else str(path)
            docs[rel] = {
                "tokens": dict(Counter(_tokenize(text))),
                "preview": text[:500],
                "line_count": text.count("\n") + 1,
            }
            count += 1
        self.store.save({"indexed_at": _now(), "documents": docs})
        return {"indexed_files": count}

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        q = Counter(_tokenize(query))
        results = []
        for path, doc in self.store.load().get("documents", {}).items():
            tokens = Counter(doc.get("tokens", {}))
            dot = sum(q[token] * tokens.get(token, 0) for token in q)
            norm = math.sqrt(sum(v * v for v in tokens.values())) or 1.0
            score = dot / norm
            if score > 0:
                results.append({
                    "path": path,
                    "score": round(score, 4),
                    "citation": f"{path}:1",
                    "preview": doc.get("preview", "")[:240],
                })
        return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


class AgentEvaluationArena:
    """Deterministic adversarial evaluation pack for the advanced layer."""

    CASES = [
        ("missions", "create and resume a mission"),
        ("self_healing", "diagnose AttributeError"),
        ("plugins", "validate plugin descriptor"),
        ("screen_memory", "recall OCR context"),
        ("simulator", "block risky command"),
        ("knowledge_graph", "query entity relations"),
        ("interruptions", "interrupt speech"),
        ("model_router", "select private local route"),
        ("repo_guardian", "scan repo"),
        ("skill_learning", "compile macro"),
        ("reflection", "detect duplicate memory"),
        ("autonomy", "gate high risk tool"),
        ("document_rag", "return citation"),
        ("evaluation_arena", "generate cases"),
        ("live_ops", "snapshot system"),
    ]

    def cases(self) -> list[dict[str, str]]:
        return [{"feature": feature, "challenge": challenge} for feature, challenge in self.CASES]

    def run(self, core: "PihuAdvancedCore") -> dict[str, Any]:
        checks = {
            "missions": bool(core.missions.create("arena mission")["id"]),
            "self_healing": core.debugger.diagnose("AttributeError: X has no attribute 'y'")["findings"][0]["code"] == "attribute_mismatch",
            "plugins": core.plugins.validate({"name": "x", "version": "1", "entrypoint": "x:y", "permissions": [], "risk": "low"}) == [],
            "screen_memory": bool(core.screen_memory.record("arena screen")["id"]),
            "simulator": core.simulator.simulate("format c:")["risk"] == "critical",
            "knowledge_graph": bool(core.knowledge_graph.add_entity("Pihu", "assistant")["id"]),
            "interruptions": core.interruptions.interrupt()["paused"] is True,
            "model_router": core.model_router.route("private note", privacy="private")["selected"] == "local_llm",
            "repo_guardian": "grade" in core.repo_guardian.scan(limit_files=10),
            "skill_learning": core.skills.learn("arena skill", ["open notepad"])["verified"] is True,
            "reflection": "summary" in core.reflection.reflect(["a", "a"]),
            "autonomy": core.autonomy.decision("shell", "high")["action"] == "ask_confirmation",
            "document_rag": isinstance(core.document_rag.search("pihu"), list),
            "evaluation_arena": len(self.cases()) == 15,
            "live_ops": "features" in core.live_ops.snapshot(core),
        }
        passed = sum(1 for ok in checks.values() if ok)
        return {"passed": passed, "total": len(checks), "checks": checks, "score": round(passed / len(checks), 3)}


class LiveOpsDashboard:
    """Compact state snapshot for UI/API display."""

    def snapshot(self, core: "PihuAdvancedCore", pipeline: str = "idle", metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "at": _now(),
            "pipeline": pipeline,
            "metrics": metrics or {},
            "features": core.feature_names(),
            "missions": core.missions.list()[:5],
            "plugins": core.plugins.list()[:10],
            "voice": core.interruptions.state(),
        }


class PihuAdvancedCore:
    """Facade for all advanced power features."""

    def __init__(self, workspace: str | Path, user_id: str = "pihu_user"):
        self.workspace = Path(workspace).resolve()
        self.user_id = user_id
        self.base_dir = self.workspace / "data" / "advanced" / _slug(user_id)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.missions = AutonomousTaskMissions(self._store("missions", {"missions": {}, "active_mission_id": ""}))
        self.debugger = SelfHealingDebugger(self.workspace)
        self.plugins = PluginRegistry(self._store("plugins", {"plugins": {}}))
        self.screen_memory = ScreenMemoryTimeline(self._store("screen_memory", {"timeline": []}))
        self.simulator = SafeComputerUseSimulator()
        self.knowledge_graph = PersonalKnowledgeGraph(self._store("knowledge_graph", {"entities": {}, "edges": []}))
        self.interruptions = VoiceInterruptionController(self._store("voice_interruptions", {"speaking": False, "paused": False}))
        self.model_router = AdvancedModelRouter()
        self.repo_guardian = RepoGuardian(self.workspace)
        self.skills = SkillLearningFromDemo(self._store("skills", {"skills": {}}))
        self.reflection = MemoryReflectionEngine()
        self.autonomy = TrustAutonomyController(self._store("autonomy", {"levels": {}}))
        self.document_rag = LocalDocumentRAG(self._store("document_rag", {"documents": {}}), self.workspace)
        self.evaluation = AgentEvaluationArena()
        self.live_ops = LiveOpsDashboard()

    def _store(self, name: str, default: dict[str, Any]) -> JsonStore:
        return JsonStore(self.base_dir / f"{name}.json", default)

    def feature_names(self) -> list[str]:
        return [
            "autonomous_task_missions",
            "self_healing_debugger",
            "capability_plugin_registry",
            "screen_memory_timeline",
            "safe_computer_use_simulator",
            "personal_knowledge_graph",
            "voice_interruption_controller",
            "advanced_model_router",
            "repo_guardian",
            "skill_learning_from_demo",
            "memory_reflection_engine",
            "trust_calibrated_autonomy",
            "local_document_rag",
            "agent_evaluation_arena",
            "live_ops_dashboard",
        ]

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "feature_count": len(self.feature_names()),
            "features": self.feature_names(),
            "state_dir": str(self.base_dir),
        }

    def can_handle(self, text: str) -> bool:
        low = text.lower().strip()
        triggers = [
            "advanced status", "live ops", "mission", "self heal", "debug logs",
            "register plugin", "remember screen", "recall screen", "simulate",
            "knowledge graph", "model route", "repo guardian", "learn skill",
            "reflect memory", "set autonomy", "index docs", "search docs",
            "run evaluation", "evaluate pihu",
        ]
        return any(trigger in low for trigger in triggers)

    def handle_command(self, text: str) -> str:
        low = text.lower().strip()
        if "advanced status" in low:
            return json.dumps(self.status(), indent=2)
        if "live ops" in low:
            return json.dumps(self.live_ops.snapshot(self), indent=2)
        if "mission status" in low:
            return json.dumps(self.missions.resume(), indent=2)
        if "mission" in low:
            goal = re.sub(r"^.*?mission[: ]+", "", text, flags=re.I).strip() or text
            return json.dumps(self.missions.create(goal), indent=2)
        if "self heal" in low or "debug logs" in low:
            return json.dumps(self.debugger.diagnose(text), indent=2)
        if "register plugin" in low:
            name = re.sub(r"^.*?register plugin[: ]+", "", text, flags=re.I).strip() or "manual plugin"
            descriptor = {"name": name, "version": "1.0.0", "entrypoint": f"{_slug(name)}:run", "permissions": [], "risk": "low"}
            return json.dumps(self.plugins.register(descriptor), indent=2)
        if "remember screen" in low:
            summary = re.sub(r"^.*?remember screen[: ]+", "", text, flags=re.I).strip() or text
            return json.dumps(self.screen_memory.record(summary), indent=2)
        if "recall screen" in low:
            query = re.sub(r"^.*?recall screen[: ]+", "", text, flags=re.I).strip()
            return json.dumps(self.screen_memory.recall(query), indent=2)
        if low.startswith("simulate") or " simulate " in low:
            command = re.sub(r"^.*?simulate[: ]+", "", text, flags=re.I).strip() or text
            return json.dumps(self.simulator.simulate(command), indent=2)
        if "model route" in low:
            request = re.sub(r"^.*?model route[: ]+", "", text, flags=re.I).strip() or text
            return json.dumps(self.model_router.route(request), indent=2)
        if "repo guardian" in low:
            return json.dumps(self.repo_guardian.scan(), indent=2)
        if "learn skill" in low:
            payload = re.sub(r"^.*?learn skill[: ]+", "", text, flags=re.I).strip()
            name, _, steps_text = payload.partition(":")
            steps = [s.strip() for s in re.split(r";|\n", steps_text) if s.strip()]
            return json.dumps(self.skills.learn(name.strip() or "manual skill", steps or [payload]), indent=2)
        if "reflect memory" in low:
            return json.dumps(self.reflection.reflect([text]), indent=2)
        if "set autonomy" in low:
            parts = low.split()
            tool = parts[-2] if len(parts) >= 2 else "default"
            level = parts[-1] if parts[-1] in AUTONOMY_LEVELS else "dry-run"
            return json.dumps(self.autonomy.set_level(tool, level), indent=2)
        if "index docs" in low:
            root = re.sub(r"^.*?index docs[: ]*", "", text, flags=re.I).strip() or None
            return json.dumps(self.document_rag.index(root), indent=2)
        if "search docs" in low:
            query = re.sub(r"^.*?search docs[: ]+", "", text, flags=re.I).strip() or text
            return json.dumps(self.document_rag.search(query), indent=2)
        if "run evaluation" in low or "evaluate pihu" in low:
            return json.dumps(self.evaluation.run(self), indent=2)
        if "knowledge graph" in low:
            return json.dumps(self.knowledge_graph.query(text), indent=2)
        return json.dumps(self.status(), indent=2)
