"""FastAPI application for HelloMate Mini App."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin_routes import create_admin_router
from app.api.routes import create_router
from app.config import Config
from app.database.db import Database
from app.services.background_worker import BackgroundWorker
from app.services.candidate_evaluation_service import CandidateEvaluationService
from app.services.contact_facts_service import ContactFactsService
from app.services.examples_service import ContactExamplesService
from app.services.fact_categories_service import FactCategoriesService
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.learning_proposals_service import LearningProposalsService
from app.services.memory_service import MemoryService
from app.services.model_decision_service import ModelDecisionService
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
from app.services.weather_service import WeatherService

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_api_app(config: Config, database: Database, processing_status_service=None) -> FastAPI:
    """Create the FastAPI app bound to the shared database."""

    profile_service = ProfileService(database.profiles, config.timezone_name)
    mood_service = MoodService(database.moods)
    memory_service = MemoryService(database.memory, config.memory_window_size)
    settings_service = SettingsService(
        database.settings,
        config.default_language,
        config.greeting_hour,
    )
    persona_service = PersonaService(
        settings_service=settings_service,
        owner_name=config.owner_name,
        bot_name=config.bot_name,
    )
    greeting_service = GreetingService(database.greetings, config.timezone)
    greeting_rules_service = GreetingRulesService(database.greeting_rules)
    weather_service = WeatherService(config.weather_city, config.timezone)

    from app.services.embedding_service import EmbeddingService
    from app.services.llm import LLMService
    from app.services.llm.factory import build_fallback_llm_provider, build_llm_provider
    from app.services.rag_service import RAGService

    llm_provider = build_llm_provider(config)
    fallback_llm_provider = build_fallback_llm_provider(config)
    llm_service = LLMService(llm_provider, database.feedback, fallback_llm_provider)
    embedding_service = EmbeddingService(
        base_url=config.llm_base_url,
        model=config.llm_embedding_model,
        api_key=config.llm_api_key,
        provider=config.llm_provider,
    )
    rag_service = RAGService(
        database.documents,
        embedding_service,
        chunk_size=config.rag_chunk_size,
        top_k=config.rag_top_k,
    )
    fact_categories_service = FactCategoriesService(database.fact_categories)
    facts_service = ContactFactsService(
        repository=database.facts,
        memory_service=memory_service,
        llm_service=llm_service,
        settings_service=settings_service,
        refresh_interval=config.facts_refresh_interval,
        enabled=config.facts_enabled and config.ai_replies_enabled,
        categories_service=fact_categories_service,
    )
    summary_service = SummaryService(
        memory_service=memory_service,
        llm_service=llm_service,
        settings_service=settings_service,
        window_size=config.memory_window_size,
        refresh_interval=config.summary_refresh_interval,
        max_chars=config.summary_max_chars,
        enabled=config.summary_enabled and config.ai_replies_enabled,
    )
    examples_service = ContactExamplesService(database.examples)
    learning_proposals_service = LearningProposalsService(
        database.learning_proposals, examples_service, facts_service
    )
    candidate_evaluation_service = CandidateEvaluationService(
        settings_service, config, database.background_jobs
    )
    reply_decision_service = ReplyDecisionService(
        database.reply_decisions, enabled=config.reply_decision_shadow_enabled
    )
    risk_routing_service = RiskRoutingService(
        settings_service, enabled=config.risk_routing_canary_enabled
    )
    suggestions_service = SuggestionsService(database.suggestions, database.feedback)
    owner_reply_pairing_service = OwnerReplyPairingService(
        database.owner_reply_pairs,
        suggestions_service,
        memory_service,
    )
    processing_status_service = processing_status_service or ProcessingStatusService()
    reply_service = ReplyService(
        llm_service=llm_service,
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        rag_service=rag_service,
        weather_service=weather_service,
        facts_service=facts_service,
        examples_service=examples_service,
        learning_proposals_service=learning_proposals_service,
        context_token_budget=config.context_token_budget,
        enabled=config.ai_replies_enabled,
    )
    shadow_review_service = ShadowReviewService(
        database.shadow_reviews,
        reply_service,
        candidate_evaluation_service,
        database.background_jobs,
    )
    model_decision_service = ModelDecisionService(
        database.model_decision_reports,
        candidate_evaluation_service,
        database.shadow_reviews,
    )

    dev_user_id = next(iter(config.admin_user_ids), None) if config.mini_app_dev else None
    background_worker = BackgroundWorker(
        database.background_jobs,
        {
            "candidate_evaluation": lambda payload: candidate_evaluation_service.evaluate(
                str(payload["candidate_id"])
            ),
            "shadow_review": lambda payload: shadow_review_service.run(int(payload["review_id"])),
        },
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        background_worker.start()
        try:
            yield
        finally:
            await background_worker.stop()
            close_provider = getattr(llm_provider, "aclose", None)
            if close_provider is not None:
                await close_provider()
            close_fallback = getattr(fallback_llm_provider, "aclose", None)
            if close_fallback is not None:
                await close_fallback()

    app = FastAPI(title="HelloMate Admin API", lifespan=lifespan)
    app.include_router(
        create_router(
            config.bot_token,
            profile_service,
            mood_service,
            memory_service,
            settings_service,
            mini_app_dev=config.mini_app_dev,
            dev_user_id=dev_user_id,
        ),
        prefix="/api",
    )
    app.include_router(
        create_admin_router(
            bot_token=config.bot_token,
            admin_user_ids=config.admin_user_ids,
            profile_service=profile_service,
            mood_service=mood_service,
            memory_service=memory_service,
            settings_service=settings_service,
            persona_service=persona_service,
            reply_service=reply_service,
            greeting_service=greeting_service,
            greeting_rules_service=greeting_rules_service,
            event_repository=database.events,
            facts_service=facts_service,
            fact_categories_service=fact_categories_service,
            examples_service=examples_service,
            suggestions_service=suggestions_service,
            summary_service=summary_service,
            feedback_repository=database.feedback,
            processing_status_service=processing_status_service,
            owner_reply_pairing_service=owner_reply_pairing_service,
            learning_proposals_service=learning_proposals_service,
            candidate_evaluation_service=candidate_evaluation_service,
            background_worker=background_worker,
            reply_decision_service=reply_decision_service,
            risk_routing_service=risk_routing_service,
            shadow_review_service=shadow_review_service,
            model_decision_service=model_decision_service,
            mini_app_dev=config.mini_app_dev,
            dev_user_id=dev_user_id,
        ),
        prefix="/api",
    )

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/")
        async def dashboard() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    return app
