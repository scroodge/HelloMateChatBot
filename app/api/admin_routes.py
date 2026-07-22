"""Admin-only API routes for the HelloMate owner console (Phase 7A/7B/7C).

All routes under /admin require the caller to be a registered admin_user_id.
Auth is via Telegram Mini App initData in the X-Telegram-Init-Data header.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from app.api.auth import validate_init_data
from app.database.repositories.events import EventRepository
from app.database.repositories.feedback import FeedbackRepositoryImpl
from app.services.background_worker import BackgroundWorker
from app.services.candidate_evaluation_service import CandidateEvaluationService
from app.services.contact_facts_service import ContactFactsService
from app.services.examples_service import ContactExamplesService
from app.services.fact_categories_service import FactCategoriesService
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.learning_proposals_service import LearningProposalsService
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.owner_reply_pairing_service import OwnerReplyPairingService
from app.services.persona_service import PersonaService
from app.services.processing_status_service import ProcessingStatusService
from app.services.profile_service import ProfileService
from app.services.reply_decision_service import ReplyDecisionService
from app.services.reply_service import ReplyService
from app.services.risk_routing_service import RiskRoutingService
from app.services.settings_service import SettingsService
from app.services.shadow_review_service import ShadowReviewService
from app.services.suggestions_service import SuggestionsService
from app.services.summary_service import SummaryService

logger = logging.getLogger(__name__)


def _owner_style_scope_key(settings: object) -> str | None:
    preset = (getattr(settings, "persona_preset", None) or "").strip().casefold()
    if preset:
        return f"persona:{preset}"
    relationship = (getattr(settings, "persona_relationship", None) or "").strip().casefold()
    return f"relationship:{relationship[:80]}" if relationship else None


async def _send_document_via_bot(
    bot_token: str, chat_id: int, filename: str, content: bytes, caption: str = ""
) -> None:
    """Send an in-memory file to a chat via the Telegram Bot API (sendDocument).

    Used so the Mini App can deliver a real file into the owner's chat with the
    bot — blob downloads are blocked inside the Telegram in-app webview.
    """
    files = {"document": (filename, content, "application/json")}
    data: dict[str, object] = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendDocument",
            data=data,
            files=files,
        )
        response.raise_for_status()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PersonaWriteRequest(BaseModel):
    raw_prompt: str | None = None
    preset: str | None = None
    relationship: str | None = None
    tone: str | None = None
    topics: list[str] | None = None
    boundaries: list[str] | None = None
    clear_raw: bool = False
    clear_structured: bool = False


class PersonaTestRequest(BaseModel):
    user_id: int
    message: str
    system_prompt_override: str | None = None


class UserSettingsWriteRequest(BaseModel):
    language: str | None = None
    greeting_enabled: bool | None = None
    greeting_hour: int | None = None
    use_starters: bool | None = None
    greeting_text: str | None = None
    business_reply_mode: str | None = None  # "auto" | "suggest" | "off" | null=inherit global
    openness: str | None = None  # "open" | "neutral" | "reserved" | null=inherit global
    style_learning_enabled: bool | None = None


class ContactFactWriteRequest(BaseModel):
    value: str


class FactCategoryWriteRequest(BaseModel):
    label: str
    multi: bool = False
    key: str | None = None  # auto-derived from label if omitted


class ContactExampleWriteRequest(BaseModel):
    contact_message: str
    reply_text: str
    kind: str = "positive"  # "positive" | "negative"


class SuggestionSaveRequest(BaseModel):
    # Optional edits before saving the suggestion as a few-shot example.
    contact_message: str | None = None
    reply_text: str | None = None
    kind: str = "positive"  # "positive" | "negative"
    reason: str | None = None


class SuggestionAcceptRequest(BaseModel):
    reply_text: str | None = None
    reason: str | None = None


class SuggestionDismissRequest(BaseModel):
    reason: str | None = None


class OwnerReplyPairRejectRequest(BaseModel):
    reason: str | None = None


class LearningProposalWriteRequest(BaseModel):
    user_id: int
    kind: str
    payload: dict[str, str]
    evidence: dict[str, str]

class CandidateWriteRequest(BaseModel):
    name: str
    provider: str
    model: str
    base_url: str = ""
    credential_id: str = "default"


class RiskCanaryContactRequest(BaseModel):
    enabled: bool


class ShadowReviewRequest(BaseModel):
    user_id: int
    candidate_id: str
    message_text: str


class ShadowReviewResolveRequest(BaseModel):
    winner: str


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_admin_router(
    bot_token: str,
    admin_user_ids: set[int],
    profile_service: ProfileService,
    mood_service: MoodService,
    memory_service: MemoryService,
    settings_service: SettingsService,
    persona_service: PersonaService,
    reply_service: ReplyService,
    greeting_service: GreetingService,
    greeting_rules_service: GreetingRulesService,
    event_repository: EventRepository | None = None,
    facts_service: ContactFactsService | None = None,
    fact_categories_service: FactCategoriesService | None = None,
    examples_service: ContactExamplesService | None = None,
    suggestions_service: SuggestionsService | None = None,
    summary_service: SummaryService | None = None,
    feedback_repository: FeedbackRepositoryImpl | None = None,
    processing_status_service: ProcessingStatusService | None = None,
    owner_reply_pairing_service: OwnerReplyPairingService | None = None,
    learning_proposals_service: LearningProposalsService | None = None,
    candidate_evaluation_service: CandidateEvaluationService | None = None,
    background_worker: BackgroundWorker | None = None,
    reply_decision_service: ReplyDecisionService | None = None,
    risk_routing_service: RiskRoutingService | None = None,
    shadow_review_service: ShadowReviewService | None = None,
    *,
    mini_app_dev: bool = False,
    dev_user_id: int | None = None,
) -> APIRouter:
    """Build admin API routes with injected services."""

    router = APIRouter(prefix="/admin", tags=["admin"])
    memory_rebuild_tasks: dict[int, asyncio.Task[None]] = {}
    memory_rebuild_status: dict[int, dict[str, Any]] = {}

    # -----------------------------------------------------------------------
    # Auth dependency
    # -----------------------------------------------------------------------

    def _get_admin_user_id(x_telegram_init_data: str | None = Header(default=None)) -> int:
        parsed = validate_init_data(x_telegram_init_data or "", bot_token)
        if parsed is not None and "user_id" in parsed:
            caller_id = int(parsed["user_id"])
        elif mini_app_dev and dev_user_id is not None:
            caller_id = dev_user_id
        else:
            raise HTTPException(status_code=401, detail="Invalid Telegram init data")
        if admin_user_ids and caller_id not in admin_user_ids:
            raise HTTPException(status_code=403, detail="Admin access required")
        return caller_id

    AdminUser = Depends(_get_admin_user_id)

    # -----------------------------------------------------------------------
    # 7A: Contacts roster
    # -----------------------------------------------------------------------

    @router.get("/activity")
    async def get_activity(caller_id: int = AdminUser) -> dict[str, Any]:
        """Return an owner-safe operational feed for the Mini App Activity page."""
        if feedback_repository is None:
            return {
                "generated_at": datetime.now().astimezone().isoformat(),
                "live": [],
                "recent": [],
            }

        def contact_name(user_id: int | None) -> str | None:
            if user_id is None:
                return None
            profile = profile_service.get_profile(user_id)
            return profile.display_name if profile and profile.display_name else f"ID {user_id}"

        live = []
        if processing_status_service is not None:
            live = [
                {
                    "user_id": status.user_id,
                    "display_name": contact_name(status.user_id),
                    "status": status.status,
                    "updated_at": status.updated_at.isoformat(),
                    "error": status.error,
                }
                for status in processing_status_service.list()
            ]

        recent = []
        for run in feedback_repository.recent_generation_runs():
            recent.append(
                {
                    **run,
                    "display_name": contact_name(run["user_id"]),
                }
            )
        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "live": live,
            "recent": recent,
        }

    @router.get("/owner-reply-pairs")
    async def list_owner_reply_pairs(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Pending owner-reply pairings. They require explicit confirmation to learn."""
        if owner_reply_pairing_service is None or suggestions_service is None:
            return []
        result = []
        for pair in owner_reply_pairing_service.list_reviewable():
            suggestion = suggestions_service.get(pair.suggestion_id)
            if suggestion is None:
                continue
            profile = profile_service.get_profile(pair.user_id)
            result.append(
                {
                    "id": pair.id,
                    "user_id": pair.user_id,
                    "display_name": profile.display_name if profile else f"ID {pair.user_id}",
                    "contact_message": suggestion.contact_message,
                    "draft_text": suggestion.draft_text,
                    "owner_reply_text": pair.owner_reply_text,
                    "confidence": pair.confidence,
                    "status": pair.status,
                    "created_at": pair.created_at.isoformat(),
                }
            )
        return result

    @router.post("/owner-reply-pairs/{pair_id}/confirm")
    async def confirm_owner_reply_pair(pair_id: int, caller_id: int = AdminUser) -> dict[str, bool]:
        if owner_reply_pairing_service is None:
            raise HTTPException(status_code=503, detail="Owner learning is not enabled")
        if not owner_reply_pairing_service.confirm(pair_id):
            raise HTTPException(status_code=404, detail="Pair is not pending")
        return {"confirmed": True}

    @router.post("/owner-reply-pairs/{pair_id}/reject")
    async def reject_owner_reply_pair(
        pair_id: int,
        request: OwnerReplyPairRejectRequest,
        caller_id: int = AdminUser,
    ) -> dict[str, bool]:
        if owner_reply_pairing_service is None:
            raise HTTPException(status_code=503, detail="Owner learning is not enabled")
        if not owner_reply_pairing_service.reject(pair_id, request.reason):
            raise HTTPException(status_code=404, detail="Pair is not pending")
        return {"rejected": True}

    @router.post("/owner-reply-pairs/{pair_id}/retract")
    async def retract_owner_reply_pair(
        pair_id: int,
        request: OwnerReplyPairRejectRequest,
        caller_id: int = AdminUser,
    ) -> dict[str, bool]:
        if owner_reply_pairing_service is None:
            raise HTTPException(status_code=503, detail="Owner learning is not enabled")
        if not owner_reply_pairing_service.retract(pair_id, request.reason):
            raise HTTPException(status_code=404, detail="Pair is not confirmed")
        return {"retracted": True}

    @router.get("/learning-proposals")
    async def list_learning_proposals(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        if learning_proposals_service is None:
            return []
        result = []
        for proposal in learning_proposals_service.list_reviewable():
            profile = profile_service.get_profile(proposal.user_id)
            result.append(
                {
                    "id": proposal.id,
                    "user_id": proposal.user_id,
                    "display_name": profile.display_name if profile else f"ID {proposal.user_id}",
                    "kind": proposal.kind,
                    "payload": proposal.payload,
                    "evidence": proposal.evidence,
                    "status": proposal.status,
                    "created_at": proposal.created_at.isoformat(),
                    "applied_reference": proposal.applied_reference,
                }
            )
        return result

    @router.get("/eval-candidates")
    async def list_eval_candidates(caller_id: int = AdminUser) -> list[dict[str, object]]:
        return candidate_evaluation_service.list() if candidate_evaluation_service else []

    @router.get("/eval-candidates/matrix")
    async def eval_candidate_matrix(caller_id: int = AdminUser) -> list[dict[str, object]]:
        return candidate_evaluation_service.matrix() if candidate_evaluation_service else []

    @router.get("/background-jobs/health")
    async def background_jobs_health(caller_id: int = AdminUser) -> dict[str, object]:
        if background_worker is None:
            raise HTTPException(status_code=503, detail="Background worker is not enabled")
        return background_worker.health()

    @router.get("/reply-decisions")
    async def recent_reply_decisions(caller_id: int = AdminUser) -> list[dict[str, object]]:
        return reply_decision_service.recent() if reply_decision_service else []

    @router.get("/risk-routing")
    async def risk_routing_status(caller_id: int = AdminUser) -> dict[str, object]:
        if risk_routing_service is None:
            raise HTTPException(status_code=503, detail="Risk routing is not enabled")
        return {
            "enabled": risk_routing_service.enabled,
            "contact_ids": sorted(risk_routing_service.contacts()),
        }

    @router.get("/risk-routing/contacts/{user_id}")
    async def risk_routing_contact_status(
        user_id: int, caller_id: int = AdminUser
    ) -> dict[str, bool]:
        if risk_routing_service is None:
            raise HTTPException(status_code=503, detail="Risk routing is not enabled")
        return {"enabled": risk_routing_service.is_contact_enabled(user_id)}

    @router.put("/risk-routing/contacts/{user_id}")
    async def update_risk_routing_contact(
        user_id: int, request: RiskCanaryContactRequest, caller_id: int = AdminUser
    ) -> dict[str, bool]:
        if risk_routing_service is None:
            raise HTTPException(status_code=503, detail="Risk routing is not enabled")
        return {"enabled": risk_routing_service.set_contact(user_id, request.enabled)}

    @router.get("/shadow-reviews")
    async def list_shadow_reviews(caller_id: int = AdminUser) -> list[dict[str, object]]:
        return shadow_review_service.recent() if shadow_review_service else []

    @router.post("/shadow-reviews")
    async def create_shadow_review(
        request: ShadowReviewRequest, caller_id: int = AdminUser
    ) -> dict[str, object]:
        if shadow_review_service is None:
            raise HTTPException(status_code=503, detail="Shadow reviews are not enabled")
        try:
            review = shadow_review_service.queue(
                request.user_id, request.candidate_id, request.message_text
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"id": review.id, "status": review.status}

    @router.post("/shadow-reviews/{review_id}/resolve")
    async def resolve_shadow_review(
        review_id: int, request: ShadowReviewResolveRequest, caller_id: int = AdminUser
    ) -> dict[str, object]:
        if shadow_review_service is None:
            raise HTTPException(status_code=503, detail="Shadow reviews are not enabled")
        try:
            result = shadow_review_service.resolve(review_id, request.winner)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Shadow review not found or not ready")
        return result

    @router.get("/eval-candidates/defaults")
    async def eval_candidate_defaults(caller_id: int = AdminUser) -> dict[str, object]:
        if candidate_evaluation_service is None:
            raise HTTPException(status_code=503, detail="Candidate lab is not enabled")
        return {
            **candidate_evaluation_service.defaults(),
            "credential_ids": candidate_evaluation_service.credential_ids(),
        }

    @router.post("/eval-candidates")
    async def add_eval_candidate(
        request: CandidateWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, object]:
        if candidate_evaluation_service is None:
            raise HTTPException(status_code=503, detail="Candidate lab is not enabled")
        try:
            return candidate_evaluation_service.add(
                request.name,
                request.provider,
                request.model,
                request.base_url,
                request.credential_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/eval-candidates/{candidate_id}")
    async def delete_eval_candidate(
        candidate_id: str, caller_id: int = AdminUser
    ) -> dict[str, bool]:
        if candidate_evaluation_service is None:
            raise HTTPException(status_code=503, detail="Candidate lab is not enabled")
        if not candidate_evaluation_service.delete(candidate_id):
            raise HTTPException(status_code=404, detail="Candidate not found")
        return {"deleted": True}

    @router.post("/eval-candidates/{candidate_id}/evaluate")
    async def evaluate_candidate(
        candidate_id: str, caller_id: int = AdminUser
    ) -> dict[str, object]:
        if candidate_evaluation_service is None:
            raise HTTPException(status_code=503, detail="Candidate lab is not enabled")
        try:
            result = candidate_evaluation_service.enqueue_evaluation(candidate_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return result

    @router.post("/learning-proposals")
    async def create_learning_proposal(
        request: LearningProposalWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        if learning_proposals_service is None:
            raise HTTPException(status_code=503, detail="Learning proposals are not enabled")
        try:
            proposal = learning_proposals_service.propose(
                request.user_id, request.kind, request.payload, request.evidence
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"id": proposal.id, "status": proposal.status}

    @router.post("/learning-proposals/{proposal_id}/approve")
    async def approve_learning_proposal(
        proposal_id: int, caller_id: int = AdminUser
    ) -> dict[str, bool]:
        if learning_proposals_service is None:
            raise HTTPException(status_code=503, detail="Learning proposals are not enabled")
        if not learning_proposals_service.approve(proposal_id):
            raise HTTPException(status_code=404, detail="Proposal is not pending")
        return {"approved": True}

    @router.post("/learning-proposals/{proposal_id}/reject")
    async def reject_learning_proposal(
        proposal_id: int, caller_id: int = AdminUser
    ) -> dict[str, bool]:
        if learning_proposals_service is None:
            raise HTTPException(status_code=503, detail="Learning proposals are not enabled")
        if not learning_proposals_service.reject(proposal_id):
            raise HTTPException(status_code=404, detail="Proposal is not pending")
        return {"rejected": True}

    @router.get("/users")
    async def list_users(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Return all contacts the bot has interacted with.

        Sourced from user_profiles (a row is created on the first message) so
        contacts appear in the roster even before any setting is edited. Any
        settings-only users (edited but never profiled) are unioned in too.
        """
        profiles = {p.user_id: p for p in profile_service.list_profiles()}
        settings_by_id = {s.user_id: s for s in settings_service.list_all_user_settings()}
        user_ids = (set(profiles) | set(settings_by_id)) - admin_user_ids

        result = []
        for user_id in user_ids:
            profile = profiles.get(user_id)
            settings = settings_by_id.get(user_id) or settings_service.get_user_settings(user_id)
            _, persona_source = persona_service.resolve(user_id, language=settings.language)
            result.append(
                {
                    "user_id": user_id,
                    "display_name": profile.display_name if profile else None,
                    "language": settings.language,
                    "greeting_enabled": settings.greeting_enabled,
                    "persona_source": persona_source,
                    "last_seen_at": profile.last_seen_at.isoformat() if profile else None,
                    "reply_mode": settings_service.get_business_reply_mode(user_id),
                    "openness": settings_service.get_openness(user_id),
                    "examples_count": (
                        examples_service.repository.count_examples(user_id)
                        if examples_service is not None
                        else 0
                    ),
                    "llm_status": (
                        processing_status_service.get(user_id).status
                        if processing_status_service and processing_status_service.get(user_id)
                        else None
                    ),
                    "llm_status_updated_at": (
                        processing_status_service.get(user_id).updated_at.isoformat()
                        if processing_status_service and processing_status_service.get(user_id)
                        else None
                    ),
                }
            )
        result.sort(
            key=lambda r: (r["last_seen_at"] is None, r["last_seen_at"] or ""),
            reverse=True,
        )
        return result

    @router.get("/users/{user_id}")
    async def get_user(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Return full info for a single contact."""
        settings = settings_service.get_user_settings(user_id)
        profile = profile_service.get_profile(user_id)
        prompt, persona_source = persona_service.resolve(user_id, language=settings.language)
        recent_mood = mood_service.latest_mood(user_id)
        recent_messages = memory_service.repository.list_messages(user_id, limit=5)

        topics_parsed = None
        if settings.persona_topics:
            try:
                topics_parsed = json.loads(settings.persona_topics)
            except (json.JSONDecodeError, TypeError):
                topics_parsed = None

        boundaries_parsed = None
        if settings.persona_boundaries:
            try:
                boundaries_parsed = json.loads(settings.persona_boundaries)
            except (json.JSONDecodeError, TypeError):
                boundaries_parsed = None

        contact_facts = facts_service.facts_structured(user_id) if facts_service is not None else {}

        style = memory_service.get_style_profile(user_id)
        relationship_scope = _owner_style_scope_key(settings)
        global_style = memory_service.get_owner_style_profile("global")
        relationship_style = (
            memory_service.get_owner_style_profile(relationship_scope)
            if relationship_scope
            else None
        )

        examples = (
            [
                {
                    "id": ex.id,
                    "contact_message": ex.contact_message,
                    "reply_text": ex.reply_text,
                    "kind": ex.kind,
                }
                for ex in examples_service.list_examples(user_id)
            ]
            if examples_service is not None
            else []
        )

        return {
            "user_id": user_id,
            "display_name": profile.display_name if profile else None,
            "timezone": profile_service.effective_timezone(user_id) if profile else None,
            "language": settings.language,
            "greeting_enabled": settings.greeting_enabled,
            "greeting_hour": settings.greeting_hour,
            "use_starters": settings.use_starters,
            "greeting_text": settings.greeting_text,
            "business_reply_mode": settings.business_reply_mode,
            "effective_business_reply_mode": settings_service.get_business_reply_mode(user_id),
            "openness": settings.openness,
            "effective_openness": settings_service.get_openness(user_id),
            "style_learning_enabled": settings.style_learning_enabled,
            "style_profile": style.profile if style else None,
            "style_profiles": {
                "global": global_style.profile if global_style else None,
                "relationship": relationship_style.profile if relationship_style else None,
                "contact": style.profile if style else None,
            },
            "persona": {
                "source": persona_source,
                "resolved_prompt": prompt,
                "raw_prompt": settings.persona_prompt,
                "preset": settings.persona_preset,
                "relationship": settings.persona_relationship,
                "tone": settings.persona_tone,
                "topics": topics_parsed,
                "boundaries": boundaries_parsed,
            },
            "latest_mood": recent_mood.mood if recent_mood else None,
            "recent_messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                for m in recent_messages
            ],
            "facts": contact_facts,
            "examples": examples,
        }

    @router.get("/users/{user_id}/messages")
    async def list_user_messages(
        user_id: int,
        limit: int = Query(default=30, ge=1, le=100),
        before_id: int | None = Query(default=None, ge=1),
        caller_id: int = AdminUser,
    ) -> dict[str, Any]:
        """Return a paginated conversation history page for one contact."""
        messages, has_more = memory_service.messages_before(
            user_id, before_id=before_id, limit=limit
        )
        return {
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "authored_by": m.authored_by,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
            "has_more": has_more,
            "next_before_id": messages[0].id if has_more and messages else None,
            "total": memory_service.count_messages(user_id),
        }

    def _build_export(user_id: int) -> dict[str, Any]:
        """Assemble a contact's full history as an LLM-loadable dict (oldest-first)."""
        from datetime import datetime

        export_cap = 5000
        total = memory_service.count_messages(user_id)
        offset = max(0, total - export_cap)
        messages = memory_service.messages_slice(user_id, offset=offset, limit=export_cap)
        profile = profile_service.get_profile(user_id)
        return {
            "contact": {
                "user_id": user_id,
                "display_name": profile.display_name if profile else None,
            },
            "exported_at": datetime.now().astimezone().isoformat(),
            "message_count": len(messages),
            "total_messages": total,
            "truncated": total > len(messages),
            "messages": [
                {
                    "role": m.role,
                    "authored_by": m.authored_by,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }

    def _export_filename(payload: dict[str, Any], user_id: int) -> str:
        from datetime import datetime

        name = (payload.get("contact") or {}).get("display_name") or f"id_{user_id}"
        safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_")
        return f"chat_{safe or user_id}_{datetime.now().strftime('%Y-%m-%d')}.json"

    @router.get("/users/{user_id}/export")
    async def export_user_history(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Export a contact's full conversation history as JSON, loadable into an LLM.

        Messages are oldest-first with role + authored_by + content + timestamp,
        so the file can be fed straight back as chat context. Capped to the most
        recent 5000 messages to bound payload size.
        """
        return _build_export(user_id)

    @router.post("/users/{user_id}/export/send")
    async def send_export_to_chat(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Send the contact's history as a .json document to the owner's bot chat.

        Reliable file delivery for Telegram: the in-app webview blocks blob
        downloads, so the bot DMs the file to the caller (the owner) instead.
        """
        payload = _build_export(user_id)
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        filename = _export_filename(payload, user_id)
        caption = f"История чата: {payload['message_count']} сообщений"
        try:
            await _send_document_via_bot(bot_token, caller_id, filename, content, caption)
        except Exception as exc:
            logger.exception("Failed to send export document to %s", caller_id)
            raise HTTPException(status_code=502, detail="Не удалось отправить файл в чат") from exc
        return {"sent": True, "message_count": payload["message_count"], "filename": filename}

    # -----------------------------------------------------------------------
    # 7B: Prompt playground
    # -----------------------------------------------------------------------

    @router.get("/presets")
    async def list_presets(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Return all available persona presets."""
        return persona_service.list_presets()

    @router.post("/persona/test")
    async def test_persona(
        request: PersonaTestRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Dry-run a persona: generate a reply without recording it to memory.

        If system_prompt_override is provided it replaces the resolved persona prompt.
        Returns the reply, assembled messages, latency, and context-block provenance.
        """
        if not reply_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="AI replies are not enabled (AI_REPLIES_ENABLED=false)",
            )

        result = await reply_service.preview_reply(
            request.user_id,
            request.message,
            system_prompt_override=request.system_prompt_override,
        )
        return result

    # -----------------------------------------------------------------------
    # 7C: Write endpoints
    # -----------------------------------------------------------------------

    @router.put("/users/{user_id}/persona")
    async def set_persona(
        user_id: int, request: PersonaWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Update persona for a contact.

        - raw_prompt sets the full system prompt (overrides structured)
        - clear_raw removes the raw prompt
        - structured fields (preset/relationship/tone/topics/boundaries) build a prompt
        - clear_structured removes all structured fields
        """
        try:
            if request.clear_raw:
                persona_service.set_raw_prompt(user_id, None)

            if request.clear_structured:
                persona_service.clear_structured(user_id)

            if request.raw_prompt is not None:
                persona_service.set_raw_prompt(user_id, request.raw_prompt)

            if any(
                v is not None
                for v in [
                    request.preset,
                    request.relationship,
                    request.tone,
                    request.topics,
                    request.boundaries,
                ]
            ):
                persona_service.set_structured(
                    user_id,
                    preset=request.preset,
                    relationship=request.relationship,
                    tone=request.tone,
                    topics=request.topics,
                    boundaries=request.boundaries,
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        settings = settings_service.get_user_settings(user_id)
        prompt, source = persona_service.resolve(user_id, language=settings.language)
        return {"user_id": user_id, "resolved_prompt": prompt, "source": source}

    @router.put("/users/{user_id}/settings")
    async def update_user_settings(
        user_id: int, request: UserSettingsWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Update per-user bot settings (language, greeting, starters, reply mode)."""
        from dataclasses import replace

        current = settings_service.get_user_settings(user_id)
        # business_reply_mode and openness can be explicitly cleared to null
        # (inherit global), so they are handled separately from the simple path.
        nullable_keys = {"business_reply_mode", "openness"}
        simple_fields = {
            k: v
            for k, v in request.model_dump().items()
            if v is not None and k not in nullable_keys
        }
        updated = replace(current, **simple_fields)

        if "business_reply_mode" in request.model_fields_set:
            mode = request.business_reply_mode
            if mode is not None and mode not in {"auto", "suggest", "off"}:
                raise HTTPException(
                    status_code=422,
                    detail="business_reply_mode must be 'auto', 'suggest', 'off', or null",
                )
            updated = replace(updated, business_reply_mode=mode)

        if "openness" in request.model_fields_set:
            openness = request.openness
            if openness is not None and openness not in {"open", "neutral", "reserved"}:
                raise HTTPException(
                    status_code=422,
                    detail="openness must be 'open', 'neutral', 'reserved', or null",
                )
            updated = replace(updated, openness=openness)

        try:
            saved = settings_service.save_user_settings(updated)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "user_id": saved.user_id,
            "language": saved.language,
            "greeting_enabled": saved.greeting_enabled,
            "greeting_hour": saved.greeting_hour,
            "use_starters": saved.use_starters,
            "greeting_text": saved.greeting_text,
            "business_reply_mode": saved.business_reply_mode,
            "effective_business_reply_mode": settings_service.get_business_reply_mode(user_id),
            "openness": saved.openness,
            "effective_openness": settings_service.get_openness(user_id),
            "style_learning_enabled": saved.style_learning_enabled,
        }

    # -----------------------------------------------------------------------
    # 11: Contact facts
    # -----------------------------------------------------------------------

    @router.get("/users/{user_id}/facts")
    async def get_facts(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Return all durable facts extracted for a contact (key -> {multi, values})."""
        if facts_service is None:
            return {}
        return facts_service.facts_structured(user_id)

    @router.get("/users/{user_id}/facts/{key}/history")
    async def get_fact_history(
        user_id: int, key: str, caller_id: int = AdminUser
    ) -> list[dict[str, object]]:
        """Return replaced versions of one fact for provenance review."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        return facts_service.fact_history(user_id, key)

    @router.put("/users/{user_id}/facts/{key}")
    async def set_fact(
        user_id: int, key: str, request: ContactFactWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Set (single) or append (multi-valued) a fact for a contact."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        try:
            facts_service.set_fact(user_id, key, request.value.strip())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return facts_service.facts_structured(user_id)

    @router.delete("/users/{user_id}/facts/{key}/value")
    async def remove_fact_value(
        user_id: int, key: str, value: str, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Remove a single value from a multi-valued fact."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        facts_service.remove_fact_value(user_id, key, value)
        return facts_service.facts_structured(user_id)

    @router.delete("/users/{user_id}/facts/{key}")
    async def delete_fact(user_id: int, key: str, caller_id: int = AdminUser) -> dict[str, Any]:
        """Delete a fact (all values) for a contact."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        facts_service.delete_fact(user_id, key)
        return facts_service.facts_structured(user_id)

    @router.delete("/users/{user_id}/facts")
    async def clear_facts(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Delete all facts for a contact."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        facts_service.clear_facts(user_id)
        return {}

    async def _run_memory_rebuild(user_id: int, part: str) -> None:
        assert summary_service is not None
        assert facts_service is not None
        try:
            summary = None
            if part in {"summary", "all"}:
                memory_rebuild_status[user_id] = {
                    "status": "running",
                    "part": part,
                    "stage": "summary",
                }
                summary = await summary_service.rebuild(user_id)
            if part in {"facts", "all"}:
                memory_rebuild_status[user_id] = {
                    "status": "running",
                    "part": part,
                    "stage": "facts",
                }
                await facts_service.rebuild(user_id)
            memory_rebuild_status[user_id] = {
                "status": "completed",
                "part": part,
                "message_count": memory_service.count_messages(user_id),
                "summary": summary,
                "facts": (
                    facts_service.facts_structured(user_id) if part in {"facts", "all"} else None
                ),
            }
        except Exception:
            logger.exception("Failed to rebuild memory for contact %s", user_id)
            memory_rebuild_status[user_id] = {
                "status": "failed",
                "part": part,
                "detail": "Не удалось пересобрать память",
            }

    @router.post("/users/{user_id}/memory/rebuild")
    async def rebuild_derived_memory(
        user_id: int,
        part: str = Query(default="all", pattern="^(facts|summary|all)$"),
        caller_id: int = AdminUser,
    ) -> dict[str, Any]:
        """Start a partial or full rebuild while preserving messages and curated data."""
        if summary_service is None or facts_service is None:
            raise HTTPException(status_code=503, detail="Memory rebuild is not available")
        if memory_service.count_messages(user_id) == 0:
            raise HTTPException(status_code=422, detail="У контакта нет истории сообщений")
        existing = memory_rebuild_tasks.get(user_id)
        if existing is not None and not existing.done():
            raise HTTPException(status_code=409, detail="Пересборка уже выполняется")

        first_stage = "summary" if part in {"summary", "all"} else "facts"
        memory_rebuild_status[user_id] = {
            "status": "running",
            "part": part,
            "stage": first_stage,
        }
        task = asyncio.create_task(_run_memory_rebuild(user_id, part))
        memory_rebuild_tasks[user_id] = task
        return {"status": "started", "part": part, "stage": first_stage}

    @router.get("/users/{user_id}/memory/rebuild")
    async def get_memory_rebuild_status(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Return the latest background rebuild status for a contact."""
        return memory_rebuild_status.get(user_id, {"status": "idle"})

    # -----------------------------------------------------------------------
    # Few-shot examples (curated ideal replies)
    # -----------------------------------------------------------------------

    def _examples_payload(user_id: int) -> list[dict[str, Any]]:
        assert examples_service is not None
        return [
            {
                "id": ex.id,
                "contact_message": ex.contact_message,
                "reply_text": ex.reply_text,
                "kind": ex.kind,
            }
            for ex in examples_service.list_examples(user_id)
        ]

    @router.get("/users/{user_id}/examples")
    async def get_examples(user_id: int, caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Return curated few-shot examples for a contact."""
        if examples_service is None:
            return []
        return _examples_payload(user_id)

    @router.post("/users/{user_id}/examples")
    async def add_example(
        user_id: int, request: ContactExampleWriteRequest, caller_id: int = AdminUser
    ) -> list[dict[str, Any]]:
        """Add a curated (contact message -> ideal reply) example."""
        if examples_service is None:
            raise HTTPException(status_code=503, detail="Examples service not enabled")
        try:
            examples_service.add_example(
                user_id, request.contact_message, request.reply_text, request.kind
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _examples_payload(user_id)

    @router.delete("/users/{user_id}/examples/{example_id}")
    async def delete_example(
        user_id: int, example_id: int, caller_id: int = AdminUser
    ) -> list[dict[str, Any]]:
        """Delete a single example for a contact."""
        if examples_service is None:
            raise HTTPException(status_code=503, detail="Examples service not enabled")
        examples_service.delete_example(user_id, example_id)
        return _examples_payload(user_id)

    @router.delete("/users/{user_id}/examples")
    async def clear_examples(user_id: int, caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Delete all examples for a contact."""
        if examples_service is None:
            raise HTTPException(status_code=503, detail="Examples service not enabled")
        examples_service.clear_examples(user_id)
        return []

    # -----------------------------------------------------------------------
    # Suggest inbox
    # -----------------------------------------------------------------------

    @router.get("/suggestions")
    async def list_suggestions(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Return pending suggestions (drafted replies awaiting review)."""
        if suggestions_service is None:
            return []
        profiles = {p.user_id: p for p in profile_service.list_profiles()}
        out = []
        if processing_status_service is not None:
            for status in processing_status_service.list():
                profile = profiles.get(status.user_id)
                out.append(
                    {
                        "id": None,
                        "user_id": status.user_id,
                        "display_name": profile.display_name if profile else None,
                        "contact_message": status.message,
                        "draft_text": None,
                        "status": status.status,
                        "error": status.error,
                        "created_at": status.updated_at.isoformat(),
                    }
                )
        for s in suggestions_service.list_pending():
            suggestions_service.viewed(s.id)
            profile = profiles.get(s.user_id)
            out.append(
                {
                    "id": s.id,
                    "user_id": s.user_id,
                    "display_name": profile.display_name if profile else None,
                    "contact_message": s.contact_message,
                    "draft_text": s.draft_text,
                    "status": "ready",
                    "error": None,
                    "created_at": s.created_at.isoformat(),
                }
            )
        return out

    @router.post("/suggestions/{suggestion_id}/dismiss")
    async def dismiss_suggestion(
        suggestion_id: int,
        request: SuggestionDismissRequest | None = None,
        caller_id: int = AdminUser,
    ) -> dict[str, Any]:
        """Mark a suggestion as dismissed (removes it from the inbox)."""
        if suggestions_service is None:
            raise HTTPException(status_code=503, detail="Suggestions service not enabled")
        suggestions_service.dismiss(suggestion_id, reason=request.reason if request else None)
        return {"pending": suggestions_service.count_pending()}

    @router.post("/suggestions/{suggestion_id}/copy")
    async def copy_suggestion(suggestion_id: int, caller_id: int = AdminUser) -> dict[str, bool]:
        if suggestions_service is None or suggestions_service.get(suggestion_id) is None:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        suggestions_service.copied(suggestion_id)
        return {"recorded": True}

    @router.post("/suggestions/{suggestion_id}/accept")
    async def accept_suggestion(
        suggestion_id: int, request: SuggestionAcceptRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        if suggestions_service is None:
            raise HTTPException(status_code=503, detail="Suggestions service not enabled")
        suggestion = suggestions_service.get(suggestion_id)
        if suggestion is None:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        suggestions_service.accept(
            suggestion_id, request.reply_text or suggestion.draft_text, request.reason
        )
        return {"pending": suggestions_service.count_pending()}

    @router.post("/suggestions/{suggestion_id}/save")
    async def save_suggestion_as_example(
        suggestion_id: int, request: SuggestionSaveRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Save a suggestion (optionally edited) as a few-shot example, then resolve it."""
        if suggestions_service is None or examples_service is None:
            raise HTTPException(status_code=503, detail="Suggestions service not enabled")
        suggestion = suggestions_service.get(suggestion_id)
        if suggestion is None:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        contact_message = request.contact_message or suggestion.contact_message
        reply_text = request.reply_text or suggestion.draft_text
        try:
            examples_service.add_example(
                suggestion.user_id, contact_message, reply_text, request.kind
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        suggestions_service.mark_saved(
            suggestion_id, kind=request.kind, final_text=reply_text, reason=request.reason
        )
        return {"pending": suggestions_service.count_pending()}

    @router.get("/analytics/feedback")
    async def feedback_analytics(
        user_id: int | None = Query(default=None),
        days: int = Query(default=30, ge=1, le=365),
        caller_id: int = AdminUser,
    ) -> dict[str, Any]:
        if feedback_repository is None:
            return {
                "created": 0,
                "accepted_as_is": 0,
                "accepted_edited": 0,
                "dismissed": 0,
                "owner_replied": 0,
                "median_decision_seconds": None,
                "providers": [],
            }
        from datetime import datetime, timedelta

        return feedback_repository.analytics(
            user_id=user_id, since=datetime.now().astimezone() - timedelta(days=days)
        )

    # -----------------------------------------------------------------------
    # Custom fact categories (global, owner-defined)
    # -----------------------------------------------------------------------

    @router.get("/fact-categories")
    async def list_fact_categories(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Return all owner-defined custom fact categories."""
        if fact_categories_service is None:
            return []
        return fact_categories_service.list_categories()

    @router.post("/fact-categories")
    async def add_fact_category(
        request: FactCategoryWriteRequest, caller_id: int = AdminUser
    ) -> list[dict[str, Any]]:
        """Add a custom fact category (global, LLM will auto-extract it)."""
        if fact_categories_service is None:
            raise HTTPException(status_code=503, detail="Fact categories service not enabled")
        try:
            fact_categories_service.add_category(
                request.label, multi=request.multi, key=request.key
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return fact_categories_service.list_categories()

    @router.delete("/fact-categories/{key}")
    async def delete_fact_category(key: str, caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Delete a custom fact category (does not delete already-stored facts)."""
        if fact_categories_service is None:
            raise HTTPException(status_code=503, detail="Fact categories service not enabled")
        from app.services.contact_facts_service import KNOWN_KEYS

        if key in KNOWN_KEYS:
            raise HTTPException(status_code=422, detail="Cannot delete a built-in fact key.")
        fact_categories_service.delete_category(key)
        return fact_categories_service.list_categories()

    # -----------------------------------------------------------------------
    # 12: Learned owner style
    # -----------------------------------------------------------------------

    @router.delete("/users/{user_id}/style")
    async def clear_style(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Clear the learned owner-style profile for a contact (it will re-learn)."""
        memory_service.delete_style_profile(user_id)
        return {"user_id": user_id, "style_profile": None}

    @router.get("/settings")
    async def get_global_settings(caller_id: int = AdminUser) -> dict[str, Any]:
        """Return all global bot settings."""
        return settings_service.list_bot_settings()

    @router.put("/settings/{key}")
    async def set_global_setting(
        key: str, value: str, caller_id: int = AdminUser
    ) -> dict[str, str]:
        """Set a global bot setting."""
        settings_service.set_bot_setting(key, value)
        return {"key": key, "value": value}

    # -----------------------------------------------------------------------
    # 7D: Stats
    # -----------------------------------------------------------------------

    @router.get("/stats")
    async def get_stats(days: int = 30, caller_id: int = AdminUser) -> dict[str, Any]:
        """Return usage stats for the last N days (default 30)."""
        from datetime import datetime, timedelta

        since = datetime.now() - timedelta(days=days)

        if event_repository is None:
            return {"error": "event_repository not configured", "days": days}

        type_counts = event_repository.type_counts(since=since)
        messages_per_user = event_repository.counts_per_user("message_received", since=since)
        replies_per_user = event_repository.counts_per_user("ai_reply_sent", since=since)

        # Source contacts from profiles (created on first message) so everyone
        # the bot has seen shows up, plus any users that have event activity.
        profiles = {p.user_id: p for p in profile_service.list_profiles()}
        contact_ids = (
            set(profiles) | set(messages_per_user) | set(replies_per_user)
        ) - admin_user_ids

        per_user = []
        for user_id in contact_ids:
            profile = profiles.get(user_id)
            per_user.append(
                {
                    "user_id": user_id,
                    "display_name": profile.display_name if profile else None,
                    "messages": messages_per_user.get(user_id, 0),
                    "ai_replies": replies_per_user.get(user_id, 0),
                    "last_seen_at": (profile.last_seen_at.isoformat() if profile else None),
                }
            )

        per_user.sort(key=lambda x: x["messages"], reverse=True)

        # Phase 13: semantic recall index coverage (all-time, not period-bound).
        recall_indexed_messages, recall_indexed_contacts = memory_service.recall_index_stats()

        # Phase 14: curated few-shot examples coverage (all-time).
        examples_total, examples_contacts = (
            examples_service.global_stats() if examples_service is not None else (0, 0)
        )

        return {
            "period_days": days,
            "since": since.isoformat(),
            "totals": type_counts,
            "contacts": per_user,
            "recall": {
                "indexed_messages": recall_indexed_messages,
                "indexed_contacts": recall_indexed_contacts,
            },
            "examples": {
                "total": examples_total,
                "contacts": examples_contacts,
            },
        }

    return router
