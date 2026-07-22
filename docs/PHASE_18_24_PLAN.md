# HelloMate — план развития Phase 18–24

_Статус: Phase 18–21C реализованы и deployed; Phase 21D candidate lab реализован locally, credential-registry deployment pending; Phase 22A–22C, Phase 23A–23C и Phase 24A–24C реализованы locally; Phase 24D proposal · Последнее обновление: 2026-07-22_

## 1. Цель

Следующий этап HelloMate — не добавление ещё одной отдельной AI-функции, а
создание замкнутого цикла улучшения качества:

```text
сообщение контакта
  -> черновик + trace
  -> решение владельца
  -> feedback
  -> eval dataset
  -> кандидат prompt/context/provider
  -> shadow evaluation
  -> безопасный rollout
```

Главное архитектурное решение этого плана:

> Сначала строится provider-neutral код для измерения, feedback и evals. Выбор
> основной модели — локальной, API или гибридной — принимается только в Phase 24
> по результатам одинаковых тестов.

До прохождения model decision gate текущий Ollama-провайдер и текущая модель
остаются рабочим baseline. План не требует немедленной миграции модели.

## 2. Текущая точка

В HelloMate уже реализованы:

- Telegram Business transport и режимы `auto` / `suggest` / `off`;
- Suggest Inbox;
- rolling summary;
- durable facts и пользовательские категории фактов;
- semantic recall по embeddings;
- owner style learning;
- positive и negative few-shot examples;
- persona playground;
- отдельные assistant profiles;
- экспорт истории контакта;
- SQLite/PostgreSQL-ready слой данных и Alembic.

Этого достаточно, чтобы начать собирать качественный обучающий сигнал. Сейчас
действия владельца ещё не образуют полный lifecycle: система не всегда знает,
был ли черновик принят, изменён, проигнорирован или заменён ответом владельца.
Также LLM provider возвращает только текст и не даёт единого результата с usage,
latency, model version и trace metadata.

## 3. Не-цели

В рамках Phase 18–23 не планируются:

- обучение foundation model с нуля;
- обязательный переход на конкретного API-провайдера;
- микросервисная архитектура или Kubernetes;
- перенос динамических фактов о контактах в веса модели;
- автоматическая отправка чувствительных сообщений без владельца;
- публикация реальных переписок или eval dataset в Git.

## 4. Принципы

1. **Сначала измерение.** Изменение prompt, context или модели не считается
   улучшением без eval и production feedback.
2. **Provider-neutral core.** Ollama и API-провайдеры реализуют один контракт.
3. **Memory stays data.** Факты, договорённости и личная история остаются в БД,
   а не обучаются в weights.
4. **Owner remains the authority.** Система может предложить правило или пример,
   но владелец подтверждает обучение.
5. **Privacy by default.** В traces не дублируется сырой текст переписки; реальные
   eval datasets локальны и исключены из Git.
6. **Single-server first.** Надёжность усиливается простым DB-backed worker без
   преждевременного усложнения инфраструктуры.
7. **Safe autonomy.** Уровень автоматизации зависит от риска и уверенности, а не
   только от силы модели.

## 5. Главные метрики

### Качество

- `acceptance_without_edit_rate` — доля принятых черновиков без изменения;
- `edited_acceptance_rate` — доля принятых после изменения;
- `owner_replacement_rate` — владелец ответил сам вместо черновика;
- `dismissal_rate` — доля отклонённых черновиков;
- `wrong_memory_rate` — использование неверной или чужой памяти;
- `unsupported_claim_rate` — выдуманные факты, обещания или состояние владельца;
- `style_match_score` — соответствие реальному стилю владельца;
- `policy_violation_rate` — нарушение openness, privacy или risk policy.

### Производительность и стоимость

- p50/p95 latency;
- input/output/cached tokens;
- стоимость одного сгенерированного и одного принятого ответа;
- error и fallback rate по провайдерам;
- длина очереди фоновых jobs и возраст самой старой задачи.

`acceptance_without_edit_rate` является основной продуктовой метрикой, но не
может оптимизироваться отдельно от safety-метрик: нейтральный, но неправильный
ответ не должен выигрывать только потому, что его удобно быстро отправить.

---

## Phase 18 — Feedback Foundation

_Статус: реализован и deployed в production (commit `094bace`, 2026-07-21)._

**Цель:** сделать каждую генерацию наблюдаемой, а действие владельца — пригодным
для анализа и будущего обучения.

### 18A. Унифицированный результат генерации

Добавить provider-neutral модели:

```python
@dataclass(frozen=True, slots=True)
class GenerationRequest:
    messages: list[dict[str, str]]
    purpose: str
    contact_user_id: int | None
    prompt_version: str
    context_policy_version: str


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    response_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    finish_reason: str | None
    latency_ms: int
```

Текущие Ollama/OpenAI adapters переводятся на этот контракт без изменения
пользовательского поведения. `ReplyService`, summary, facts, style и assistant
mode получают `GenerationResult.text`, а telemetry — metadata результата.

### 18B. Generation trace

Новая таблица `generation_runs`:

- `id`, `trace_id`, `user_id`;
- `purpose`: `reply`, `draft`, `preview`, `summary`, `facts`, `style`, `assistant`;
- provider/model;
- prompt/context policy versions;
- usage и latency;
- finish reason, error code, fallback chain;
- created timestamp.

Trace ссылается на существующие message/suggestion IDs. Полный prompt и текст
ответа не должны автоматически копироваться в telemetry-таблицу.

### 18C. Полный lifecycle Suggest Inbox

Добавить append-only `feedback_events`:

- `suggestion_created`;
- `viewed`;
- `copied`;
- `accepted_as_is`;
- `accepted_edited`;
- `saved_positive`;
- `saved_negative`;
- `dismissed`;
- `owner_replied`;
- `expired` / `superseded`.

Для edited/owner reply сохранять финальный текст в защищённом operational data,
связь с исходным suggestion и вычисляемые признаки:

- character и token edit distance;
- semantic similarity;
- время до решения;
- необязательная причина отклонения.

Причины отклонения в UI:

- не мой стиль;
- неправильно понял;
- выдумал факт;
- неверно использовал память;
- слишком открыто;
- слишком длинно;
- небезопасно отправлять;
- другое.

### 18D. Минимальная аналитика

В Mini App добавить карточки по периоду и контакту:

- создано черновиков;
- принято без изменений;
- принято после редактирования;
- отклонено;
- владелец ответил сам;
- median decision time;
- latency/error по provider/model.

### Definition of Done

- не менее 95% успешных генераций имеют trace;
- каждое действие Suggest Inbox создаёт feedback event;
- старые suggestions продолжают работать после миграции;
- raw prompt не попадает в обычные logs;
- существующие tests зелёные, добавлены repository/service/API tests;
- модель и production routing не изменены.

### Фактический результат

- `GenerationRequest` / `GenerationResult` добавлены в `app/models/generation.py`;
- Ollama и OpenAI-compatible adapters сохраняют provider/model, usage, finish reason и latency;
- добавлены `generation_runs`, `feedback_events`, `suggestion_outcomes` и Alembic migration `112233aabbcc`;
- Suggest Inbox записывает lifecycle feedback, причины решений, edit distances, decision time и similarity;
- Mini App показывает feedback/provider analytics и поддерживает accept/copy/dismiss/save с причиной;
- production migration прошла на `/opt/hellomate` на `contabo`, `hellomate-bot` запущен, Mini App отвечает HTTP 200;
- verification: 240 pytest tests passed, Ruff passed, Mini App JavaScript syntax passed.

---

## Phase 19 — HelloMate Eval Lab

**Цель:** сделать изменения prompt/context/model проверяемыми до production.

### 19A. Dataset format

Provider-neutral JSONL schema:

```json
{
  "case_id": "stable-id",
  "language": "ru",
  "relationship": "family",
  "openness": "neutral",
  "input": "...",
  "quoted_context": null,
  "memory_fixture": {},
  "expected_properties": [],
  "forbidden_properties": [],
  "reference_reply": null,
  "source": "synthetic|owner_approved"
}
```

- В Git хранятся только synthetic/regression fixtures.
- Реальные owner-approved cases находятся в ignored local data directory.
- Dataset делится на development, regression и закрытый holdout.
- Один и тот же контакт не должен случайно оказаться и в train/development, и в
  holdout при будущем fine-tuning.

### 19B. Набор graders

Детерминированные проверки:

- язык;
- максимальная длина;
- отсутствие запрещённых AI/meta tails;
- обязательный уточняющий вопрос при недостаточном контексте;
- отсутствие запрещённых раскрытий для `reserved`;
- отсутствие unsupported commitments.

Model-assisted graders:

- accuracy/helpfulness;
- groundedness относительно memory fixture;
- style/persona match;
- privacy boundary;
- эмоциональная уместность;
- сравнение кандидата с owner reference.

Каждый grader возвращает плавный score и краткую причину. Safety-критерии также
имеют hard fail и не усредняются с красивым стилем.

### 19C. Локальный eval runner

Команды проекта должны позволять:

```text
run one provider/model against a dataset
compare two prompt versions
compare two providers
emit JSON + human-readable report
fail CI on regression thresholds
```

CI выполняет только synthetic/regression dataset без сетевых секретов. Cloud и
live Ollama comparisons запускаются отдельно и сохраняют versioned report.

### Definition of Done

- существует воспроизводимый baseline текущей модели;
- есть минимум 50 разнообразных synthetic/regression cases;
- eval отчёт показывает scores, latency и usage по каждому case;
- CI ловит намеренно внесённую prompt regression;
- model decision всё ещё не принимается.

### Фактический результат (2026-07-21)

- Добавлен provider-neutral Eval Lab в `app/evals/` и CLI
  `scripts/run_eval.py`.
- В Git есть 50 synthetic regression cases и отдельный synthetic development
  dataset; owner-approved/holdout данные размещаются только в ignored
  `evals/owner_approved/`.
- Детерминированные graders проверяют язык, длину, AI/meta leakage,
  обязательное уточнение, reserved privacy, unsupported commitments и явные
  ожидаемые/запрещённые свойства. Hard fail не участвует в усреднении.
- Optional provider judge возвращает score + reason для accuracy/helpfulness,
  groundedness, style/persona, privacy и сравнения с reference reply.
- Runner формирует JSON и Markdown отчёты с per-case reply, scores, latency и
  usage; поддерживает provider/prompt comparison. CI запускает secret-free
  synthetic fixture baseline и падает при safety/regression failure.
- Live baseline текущего provider/model запускается локально через тот же CLI
  и сохраняется в ignored `evals/reports/`; модель и production routing не
  менялись.

### Processing status rollout (2026-07-21)

- Mini App показывает live-состояния contact reply pipeline: `queued`,
  `generating` и `failed`.
- «Подсказки» показывает состояние до появления готового draft, а «Контакты»
  показывает status badge для конкретного контакта.
- API и Telegram handler используют thread-safe in-process registry;
  завершённые suggestions по-прежнему сохраняются в существующей БД.
- Добавлены token checks, чтобы устаревшая debounce/generation task не могла
  перезаписать status нового сообщения.
- Verification: 246 pytest tests passed; production deployed to Contabo
  `/opt/hellomate`, commit `7c632b5`, container `hellomate-bot` up, Mini App
  HTTP 200, unauthenticated admin HTTP 401, no startup errors.

---

## Phase 20 — Context Compiler 2.0

**Цель:** управлять prompt как типизированным продуктовым артефактом, а не одной
нарастающей строкой.

### 20A. Context blocks

```python
@dataclass(frozen=True, slots=True)
class ContextBlock:
    kind: str
    content: str
    priority: int
    confidence: float | None
    source_id: str | None
    freshness_at: datetime | None
    sensitivity: str
    estimated_tokens: int
```

Источники: persona, owner identity, mood, summary, recall, facts, RAG, weather,
style, positive examples, negative examples, quoted message и live window.

### 20B. Budget и разрешение конфликтов

Compiler:

- применяет общий token budget;
- удаляет дубли;
- выбирает few-shot examples по близости к текущему запросу;
- понижает устаревшие/низкоуверенные факты;
- не смешивает утверждения владельца и контакта;
- детектирует противоречащие факты;
- сохраняет explainable список включённых/исключённых блоков.

### 20C. Temporal facts

Расширить факт метаданными:

- source message;
- confidence;
- first/last observed;
- valid from/until;
- owner confirmed;
- superseded by.

Изменяемые факты не перезаписываются молча. Новый факт может supersede старый,
а Playground показывает происхождение.

### 20D. Prompt registry

- стабильные `prompt_version` и `context_policy_version`;
- changelog причины изменения;
- возможность replay старой версии;
- никакого silent prompt mutation в production.

### Definition of Done

- ReplyService получает готовый compiled context;
- Playground показывает source, priority и inclusion reason;
- prompt помещается в заданный budget;
- конфликтующие факты имеют предсказуемое поведение;
- baseline eval не регрессирует, а целевые metrics улучшаются.

### Фактический результат (2026-07-21)

- `ReplyService` получает typed compiled context; Phase 20B добавил budget,
  deduplication, freshness/confidence penalties, conflict handling и
  explainable inclusion decisions.
- Активные facts теперь содержат source message, confidence, first/last
  observed, validity interval, owner confirmation и stable version ID. При
  изменении старый факт переносится в append-only history с указанием новой
  superseding version; provenance доступен через Admin API.
- Prompt registry фиксирует `reply-v1` и `context-compiler-v2` с changelog.
  Эти IDs передаются в generation traces для reply, draft, preview и rewrite,
  поэтому context/prompt changes больше не происходят silently.
- Playground уже возвращает source, priority, inclusion reason и token budget
  для каждого context block.
- Verification: targeted Ruff passed, 264 pytest tests passed, offline Eval Lab
  regression gate passed. Production deployment и migration `223344bbccdd`
  выполнены и подтверждены на Contabo.

---

## Phase 21 — Owner Learning

**Цель:** превращать реальное поведение владельца в подтверждаемое улучшение.

### 21A. Draft-to-owner pairing

Связывать suggestion с последующим owner-authored сообщением только когда:

- совпадает contact/chat;
- сообщение появилось в ограниченном временном окне;
- после suggestion не было нового входящего сообщения, меняющего контекст;
- владелец может исправить ошибочную связь.

Неуверенные пары не используются автоматически.

### 21B. Иерархический стиль

```text
global owner style
  -> relationship/persona style
    -> contact-specific delta
```

Так новый контакт получает разумный cold start, а контакт с богатой историей —
персональные особенности. `reserved` продолжает иметь приоритет над style mimicry.

### Фактический результат 21A–21B (2026-07-21)

- Добавлена reviewable таблица `owner_reply_pairs` (migration `334455ccddee`).
  Пара создаётся только при одном pending Suggest draft для того же контакта,
  ответе владельца в окне до двух часов и отсутствии нового сообщения контакта
  между draft и ответом владельца.
- В Mini App на вкладке «Активность» владелец видит evidence пары: сообщение
  контакта, черновик и свой ответ. Подтверждение создаёт `owner_replied`
  feedback; отклонение не использует пару; retract удаляет ошибочный signal из
  feedback/outcome metrics, сохраняя audit record. Никакое действие не
  отправляет сообщение и не меняет production prompt автоматически.
- Добавлена таблица `owner_style_profiles` (migration `445566ddeeff`). При
  включённом style learning reply context получает слои global →
  persona/relationship → contact-specific. В aggregate profiles попадают
  только opted-in контакты; `reserved` по-прежнему полностью отключает style
  mimicry. Все три слоя видны в contact detail Mini App.
- Verification: полный pytest suite, UI JavaScript syntax check, offline Eval
  Lab и миграции от предыдущего head прошли успешно. На Contabo commit
  `5c963f2` развёрнут, контейнер `hellomate-bot` healthy, Alembic head
  `445566ddeeff` подтверждён.

### 21C. Предложения обучения

Система может предлагать владельцу:

- новый positive example;
- новый negative example;
- правило стиля;
- boundary;
- исправление/подтверждение факта.

Каждое предложение показывает evidence и требует подтверждения. Никакие rules не
добавляются в production prompt скрытно.

### Фактический результат 21C (2026-07-21)

- Добавлена reviewable таблица `learning_proposals` (migration `556677ddeeff`)
  с типом, структурированным payload, evidence, статусом и ссылкой на применённый
  результат. Поддержаны positive/negative examples, style rules, boundaries и
  подтверждение/исправление фактов.
- Владелец видит предложение и его основание на вкладке «Активность» и отдельно
  подтверждает или отклоняет его. До подтверждения оно не меняет examples, facts
  или reply context. Подтверждённые examples записываются через curated-example
  lifecycle, facts получают `owner_confirmed`, а правила добавляются отдельным,
  видимым context block с меньшим приоритетом, чем accuracy и openness policy.
- Верification: 276 pytest tests и offline Eval Lab regression gate прошли
  локально. Production deployment и migration `556677ddeeff` остаются отдельным
  шагом.

### 21D. Candidate optimization

После накопления feedback разрешается shadow-выбор между несколькими уже
прошедшими eval кандидатами. Contextual bandit допустим только при условиях:

- нет влияния на hard safety routing;
- exploration сначала только в Suggest Mode;
- существует фиксированный holdout;
- можно мгновенно вернуться к baseline.

### Фактический результат 21D (2026-07-21)

- В Mini App добавлена вкладка «Модели»: владелец добавляет provider/model/base URL
  кандидата и запускает regression evaluation без изменения production routing.
- Eval использует только серверные credentials. Для платных провайдеров добавлен
  local-only registry `EVAL_PROVIDER_KEYS_JSON`; UI выбирает лишь credential ID,
  никогда не получает и не сохраняет API key.
- Первый live run `Qwen 14B` (`qwen2.5:14b`) завершился с `failed`, pass rate 46%,
  поэтому кандидат не может быть использован для shadow/canary routing. Второй
  идентичный кандидат был создан до добавления duplicate guard; теперь одинаковые
  provider/model/base URL/credential ID отклоняются.
- До следующего шага нужно: deploy credential-registry changes, добавить server-side
  key для платного provider, прогнать кандидата, который проходит hard safety gate,
  и только затем реализовывать Suggest-only shadow selection.

### Definition of Done

- владелец видит и подтверждает learning proposals;
- ошибочную feedback pair можно удалить;
- новые rules/examples имеют provenance;
- offline eval подтверждает улучшение до rollout;
- production auto не используется для неконтролируемого exploration.

---

## Phase 22 — Durable Intelligence

**Цель:** фоновые AI-задачи переживают restart и контролируют нагрузку.

### 22A. DB-backed jobs

Новая таблица `background_jobs`:

- type и payload reference;
- idempotency key;
- status;
- attempts/max attempts;
- run after;
- lease owner/lease expiry;
- last error;
- created/started/completed timestamps.

Jobs: summary, facts, style, embeddings, memory rebuild, offline eval export.

### 22B. Один worker

Для текущего deployment достаточно одного worker process/thread:

- bounded concurrency;
- retry с exponential backoff и jitter;
- dead-letter status;
- per-contact serialization там, где важен порядок;
- graceful shutdown;
- health/queue metrics.

Celery/Redis не добавляются без доказанной необходимости.

### Фактический результат 22A (2026-07-21)

- Добавлены `background_jobs` и migration `667788eeff00`: тип, JSON payload,
  idempotency key, статус, счётчик попыток, планируемое время запуска, lease,
  диагностическая ошибка и lifecycle timestamps.
- Repository поддерживает idempotent enqueue, атомарный lease, reclaim задачи с
  истекшим lease после restart, completion, retry scheduling и dead-letter
  transition. Payload предназначен для ссылок/ID, а не для копирования текста
  переписки.
- Верификация: repository tests и offline Eval Lab regression gate прошли.

### Фактический результат 22B (2026-07-22)

- Добавлен single-process `BackgroundWorker`: один leased job за раз, graceful
  shutdown через FastAPI lifespan, retry с exponential backoff и jitter,
  durable retry/dead-letter transitions.
- Candidate Lab evaluations теперь только ставятся в `background_jobs`; HTTP
  запрос возвращает `queued` сразу, поэтому долгий provider run больше не
  удерживает Mini App request и не приводит к Nginx 504.
- Mini App показывает queued/running/completed/failed состояния, обновляет
  результат во время фоновой проверки и позволяет удалить кандидата с
  подтверждением.
- Добавлен `/api/admin/background-jobs/health` с queue/dead-letter counts.
- Верификация: Ruff, JavaScript syntax check, 30 focused tests и offline Eval
  Lab regression gate прошли.

### 22C. Provider resilience

- переиспользуемые HTTP clients;
- connect/read timeout;
- concurrency limits;
- circuit breaker;
- provider health;
- контролируемый fallback;
- различение retryable и permanent errors.

### Фактический результат 22C (2026-07-22)

- Ollama и OpenAI-compatible providers используют reusable bounded HTTP client
  с отдельным connect/read timeout, ограничением одновременных запросов,
  exponential retry и jitter для transient network, rate-limit и 5xx ошибок.
- После повторяющихся transient failures включается короткий circuit breaker;
  permanent 4xx ошибки не повторяются.
- Добавлен opt-in controlled fallback через `LLM_FALLBACK_*`: он используется
  только после retryable failure primary provider. Пустая настройка сохраняет
  прежний primary-only routing.
- Provider lifecycle закрывает HTTP clients при shutdown и после candidate eval;
  generation trace сохраняет fallback chain без prompt или текста ответа.
- Верификация: Ruff, 27 focused tests и offline Eval Lab regression gate прошли.

### Definition of Done

- restart во время job не теряет задачу;
- повторное выполнение не создаёт дубликаты;
- очередь и dead letters видны в admin stats;
- отказ LLM provider не блокирует Telegram handlers;
- можно ограничить расход токенов фоновых задач.

---

## Phase 23 — Risk-aware Routing

**Цель:** автоматизация определяется риском и уверенностью, а не только настройкой
контакта.

### 23A. Reply decision

Перед генерацией формируется структурированный `ReplyDecision`:

```text
intent
risk_level
memory_confidence
requires_owner_knowledge
requires_external_action
recommended_mode
reasons
```

Hard rules имеют приоритет над model classifier.

### 23B. Risk classes

Высокий или повышенный риск:

- деньги, покупки и переводы;
- медицинские/юридические советы;
- обещания, встречи и договорённости без подтверждённой памяти;
- конфликт, сильные эмоции, интимные темы;
- личные секреты и чувствительные данные;
- запрос на внешнее действие;
- утверждение о текущем состоянии/местоположении владельца;
- недостаточный или противоречивый контекст.

### Фактический результат 23A–23B (2026-07-22)

- Добавлен explainable `ReplyDecision` с intent, risk level, memory confidence,
  owner/external action flags, recommended mode и списком hard-rule reasons.
- Детерминированные hard rules покрывают деньги, medical/legal topics, личные
  данные, external actions, owner availability/promises и emotional conflict.
- Решение записывается в shadow-only `reply_decisions` без текста входящего
  сообщения. `/api/admin/reply-decisions` показывает actual/recommended mode и
  `is_divergent` для анализа будущего canary.
- `REPLY_DECISION_SHADOW_ENABLED=false` отключает запись и оставляет полностью
  статическое legacy behavior. При включённом flag routing всё ещё не меняется.

### 23C. Routing

```text
low risk + high confidence     -> auto allowed
medium risk or uncertainty     -> suggest
high risk                      -> owner only
provider failure               -> configured fallback or suggest
```

Первый rollout — только shadow: решение рассчитывается и записывается, но не
меняет фактический mode. После анализа false positives/negatives включается
canary для выбранных контактов.

### Фактический результат 23C (2026-07-22)

- Добавлен opt-in canary через `RISK_ROUTING_CANARY_ENABLED=false` по умолчанию
  и список выбранных контактов в Mini App.
- Для canary-контакта routing может только понизить автоматизацию: `auto` →
  `suggest` при medium risk или `auto` → `off` при high risk. Он никогда не
  повышает `suggest`/`off` до `auto` и не переопределяет owner-only mode.
- Контакт включается в разделе «Настройки контакта» переключателем
  «Безопасный canary». Global flag выключает влияние immediately, сохраняя
  статическое behavior и список выбранных контактов для последующего review.
- Верификация: 42 hard-rule/canary and existing routing tests, Ruff, Mini App
  JavaScript syntax и offline Eval Lab regression gate прошли.

#### Canary rollout, test later

1. Оставить `RISK_ROUTING_CANARY_ENABLED=false` после deployment и собрать
   несколько дней shadow-only decisions.
2. Проверить amber divergences в «Риск-проверка, shadow»: money/medical/legal,
   availability и external-action messages должны быть объяснимы, а бытовые
   сообщения не должны часто попадать в risk.
3. Только после review поставить `RISK_ROUTING_CANARY_ENABLED=true`, restart
   service и включить «Безопасный canary» ровно для одного low-stakes контакта.
4. Наблюдать Suggest Inbox и owner feedback. При одном неверном downgrade
   выключить global flag: это мгновенно возвращает static routing для всех.
5. Расширять список контактов только после owner review; не включать canary для
   чувствительных контактов до достаточного количества корректных shadow cases.

### Definition of Done

- risk decision explainable;
- hard rules покрыты tests;
- shadow report показывает расхождения с решениями владельца;
- auto включается только после заданного safety threshold;
- один feature flag возвращает статическое поведение.

---

## Phase 24 — Provider Experiments и Model Decision Gate

**Цель:** выбрать модельную стратегию на данных HelloMate.

### 24A. Candidate matrix

Сравниваются минимум:

- текущий локальный baseline;
- один новый локальный open-weight кандидат;
- одна cost-efficient API-модель;
- при необходимости более сильная API-модель для сложных cases.

Все кандидаты получают один compiled context, одинаковые decoding constraints и
одинаковый eval dataset. Provider-specific возможности тестируются отдельным
экспериментом и не должны искажать baseline comparison.

### Фактический результат 24A (2026-07-22)

- Candidate Eval Lab сохраняет и показывает одинаковые quality/safety metrics
  для каждого completed candidate: pass rate, hard failures, total input/output
  tokens, mean latency и p95 latency.
- Новый `/api/admin/eval-candidates/matrix` возвращает compact provider-neutral
  comparison rows для будущего decision report. Он не меняет working model или
  routing.
- Верификация: 24 focused tests, Ruff, Mini App JavaScript syntax и offline
  Eval Lab regression gate прошли.

### 24B. Shadow и blind review

- production-сообщение обрабатывает активная модель;
- shadow candidates не отправляют ответы контакту;
- владелец может слепо сравнить ответы A/B без названия модели;
- сохраняются quality scores, latency и estimated cost;
- shadow content соблюдает privacy policy контакта.

### Фактический результат 24B (2026-07-22)

- В Candidate Lab добавлен owner-triggered blind A/B review: owner явно вводит
  контакт, сообщение и candidate (например, `gpt-5-mini`), после чего job
  генерирует baseline и candidate reply с одним compiled context.
- Результаты A/B случайно перемешиваются, не отправляются контакту и остаются
  owner-only operational data. Owner выбирает A, B или tie; после выбора
  сохраняется, выиграл ли baseline.
- Автоматическое копирование production messages в external provider намеренно
  не включено: первые reviews происходят только по прямому действию owner.
- Верификация: 33 focused tests, Ruff, Mini App JavaScript syntax и offline
  Eval Lab regression gate прошли.

### 24C. Decision criteria

Модель не выбирается по одному aggregate score. Обязательные измерения:

- acceptance / owner preference;
- groundedness и unsupported claims;
- style match;
- risk-policy compliance;
- p95 latency;
- cost per accepted reply;
- availability и fallback behavior;
- privacy constraints.

Возможные результаты gate:

1. **Local-first** — локальная модель проходит quality threshold.
2. **API-first** — качество API существенно лучше при приемлемой цене/privacy.
3. **Hybrid** — local для background/private/fallback, API для generation.
4. **Route by risk/complexity** — разные модели для разных классов запроса.

### Фактический результат 24C (2026-07-22)

- В Candidate Lab добавлен owner-triggered, versioned decision snapshot. Он
  объединяет regression safety, p95 latency и resolved blind A/B reviews для
  каждого кандидата, но не меняет active model, routing или fallback.
- Явные критерии `phase24c-v1`: 0 hard failures, 100% regression pass rate,
  минимум 5 resolved reviews, предпочтение кандидата минимум 60% и p95 не
  выше 15 секунд. Пока данных недостаточно, результат честно помечается
  `needs_owner_review`, а не делает вывод о модели.
- Cost и availability сохраняются как `not_measured`, пока эти данные не
  появятся в telemetry, поэтому snapshot не выдаёт непроверенные оценки за
  факты. Snapshot хранит только агрегированные metrics, без raw сообщений или
  A/B reply text.
- Mini App даёт кнопку «Сохранить snapshot» и показывает текущий статус,
  а новый snapshot остаётся owner-only audit record.

### 24D. Fine-tuning gate

Fine-tuning рассматривается только если:

- feedback dataset очищен и owner-approved;
- существует независимый holdout;
- prompt/context/retrieval улучшения достигли плато;
- ожидаемый выигрыш измерим;
- privacy и удаление данных определены;
- есть rollback к base model.

Fine-tuning может обучать стиль и форму ответа. Факты, отношения, планы и память
остаются во внешнем контексте.

### Definition of Done

- существует versioned comparison report;
- решение принято по заранее определённым thresholds;
- routing и fallback задокументированы;
- смена модели выполняется конфигурацией, а не переписыванием core;
- выбранная стратегия проходит regression и safety evals.

---

## 6. Рекомендуемый порядок реализации

| Slice | Содержание | Зависит от |
| --- | --- | --- |
| 18A | `GenerationResult` + adapters | — |
| 18B | `generation_runs` + instrumentation | 18A |
| 18C | `feedback_events` + Suggest lifecycle | 18B |
| 18D | Feedback analytics UI/API | 18C |
| 19A | Dataset schema + synthetic fixtures | 18A |
| 19B | Deterministic graders | 19A |
| 19C | Model-assisted graders + reports | 19B |
| 19D | Regression eval in CI | 19C |
| 20A | ContextBlock + compiler baseline | 19D |
| 20B | Budget, provenance, conflict rules | 20A |
| 20C | Temporal facts + prompt registry | 20B |
| 21A | Owner feedback pairing | 18C, 19D |
| 21B | Hierarchical style + proposals | 21A, 20C |
| 22A | `background_jobs` + worker | 18B |
| 22B | Перенос derived-memory tasks | 22A |
| 23A | RiskDecision shadow mode | 19D, 20C |
| 23B | Canary risk routing | 23A, 22B |
| 24A | Provider candidates + shadow | 18A, 19D, 22B |
| 24B | Blind review + decision report | 24A |

## 7. Первые 30 дней

### Неделя 1

- `GenerationRequest` / `GenerationResult`;
- Ollama/OpenAI adapters;
- trace ID и provider metadata;
- focused tests.

### Неделя 2

- migrations для `generation_runs` и `feedback_events`;
- Suggest Inbox actions;
- базовые acceptance/edit/dismiss metrics.

### Неделя 3

- dataset schema;
- первые 50 synthetic cases;
- deterministic graders;
- baseline report текущей модели.

### Неделя 4

- model-assisted graders;
- regression gate;
- первый prompt/context experiment без смены production model.

После первых 30 дней выбирается следующий акцент — Context Compiler, durable
jobs или owner learning — исходя из обнаруженных failure categories. Model
selection всё ещё остаётся Phase 24.

## 8. Rollout и rollback

Каждая фаза должна использовать:

- additive migration;
- feature flag;
- shadow mode перед изменением поведения;
- canary по выбранным контактам;
- сохранённый baseline configuration;
- один быстрый rollback switch;
- eval report до и после изменения.

План остаётся proposal для Phase 19–24. Выполненные slices отмечаются здесь
только после реализации, проверки и production rollout.

## 9. Внешние ориентиры

- OpenAI: eval → prompt/context → measurement → iteration:
  <https://developers.openai.com/api/docs/guides/model-optimization>
- OpenAI graders и правила проектирования оценок:
  <https://developers.openai.com/api/docs/guides/graders>
- OpenTelemetry Python для traces/metrics:
  <https://opentelemetry.io/docs/languages/python/>
- OpenTelemetry GenAI conventions следует использовать осторожно: часть
  conventions всё ещё может меняться:
  <https://opentelemetry.io/docs/specs/semconv/>
