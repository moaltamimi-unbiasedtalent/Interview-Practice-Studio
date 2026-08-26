"""Shared platform infrastructure for Interview OS Coach.

`src/core` holds **infrastructure only** — secret reading, configuration
composition, safe logging, usage records, generic errors and reusable security
primitives. It contains **no domain intelligence**: Career Intelligence's RAG and
Interview Practice's interview logic stay in their own modules and are never
combined here.
"""
