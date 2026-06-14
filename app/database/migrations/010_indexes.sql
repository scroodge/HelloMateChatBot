-- Indexes for per-user, time-ordered queries used by the memory window,
-- mood history, RAG retrieval, and the admin console stats/monitoring screens.

CREATE INDEX IF NOT EXISTS idx_conversation_messages_user_created
    ON conversation_messages(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_mood_entries_user_recorded
    ON mood_entries(user_id, recorded_at);

CREATE INDEX IF NOT EXISTS idx_documents_user
    ON documents(user_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document
    ON document_chunks(document_id);
