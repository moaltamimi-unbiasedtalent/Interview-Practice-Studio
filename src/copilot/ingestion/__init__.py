"""Knowledge-base ingestion for Career Intelligence Copilot.

Pipeline: discover → load (PDF/TXT/MD/CSV) → clean → chunk → dedup. No
embeddings are created here (that belongs to the retrieval phase).
"""
