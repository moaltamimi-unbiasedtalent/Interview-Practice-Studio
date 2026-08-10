# Requirement traceability — Interview Practice Studio

Maps each assignment requirement to concrete evidence in the repository. A
requirement is marked **Complete** only where implementation and test/evaluation
evidence actually exist. "Manual verification still required" flags anything a
human should confirm (e.g. live behaviour, visual/UX).

## Mandatory requirements

| Requirement | M/O | Implementation | File evidence | Test evidence | Evaluation evidence | Manual verification still required | Status |
|---|---|---|---|---|---|---|---|
| Interview-preparation research & scope | M | Generic, profession-neutral scope | `CLAUDE.md`, `docs/architecture.md` | n/a | n/a | Review scope narrative | Complete |
| Streamlit front end | M | Single-page routed UI | `app.py`, `.streamlit/config.toml` | `tests/test_app_smoke.py` | n/a | Visual/UX in browser | Complete |
| OpenRouter API integration | M | Typed non-streaming client | `src/openrouter_client.py`, `src/config.py` | `tests/test_openrouter_client.py` | n/a | One confirmed live call | Complete |
| Approved OpenRouter model | M | 3 approved model ids | `src/constants.py` (`APPROVED_MODELS`) | `tests/test_config.py`, `tests/test_models.py` | n/a | — | Complete |
| Five system-prompt techniques | M | 5 distinct techniques | `src/prompts.py`, `src/prompt_registry.py` | `tests/test_prompts.py` | `evaluations/prompt_comparison.*` | Live comparison metrics | Complete |
| Security guard | M | Validation, injection, scope, output | `src/security.py` | `tests/test_security.py`, `tests/test_jailbreak_runner.py` | `evaluations/jailbreak_test_results.xlsx` (29/29) | — | Complete |
| User/system/assistant roles | M | Role-separated messages | `src/prompts.py` (`build_task_messages`) | `tests/test_prompts.py`, `tests/test_generic_professions.py` | n/a | — | Complete |
| Model settings | M | Model, technique, temperature, max tokens | `src/models.py` (`ModelSettings`), `app.py` | `tests/test_models.py` | `evaluations/model_settings_comparison.*` | Live sweep metrics | Complete |
| Working interview-preparation flow | M | Strategy → Q&A → report state machine | `src/session_manager.py`, `src/*_service.py` | `tests/test_session_manager.py`, service tests | n/a | End-to-end live run | Complete |

## Optional tasks implemented

| Requirement | M/O | Implementation | File evidence | Test evidence | Evaluation evidence | Manual verification still required | Status |
|---|---|---|---|---|---|---|---|
| Multiple difficulty levels | O | easy/moderate/hard | `src/constants.py` (`DIFFICULTY_LEVELS`), `src/ui_helpers.py` | `tests/test_models.py` | n/a | — | Complete |
| Concise vs detailed responses | O | response-detail levels | `src/constants.py` (`RESPONSE_DETAIL_LEVELS`), `src/prompts.py` | `tests/test_models.py` | n/a | — | Complete |
| Multiple interviewer personas | O | 6 personas incl. Phase-8 additions | `src/constants.py` (`INTERVIEWER_PERSONAS`), `src/prompts.py` | `tests/test_taxonomy_extension.py` | n/a | — | Complete |
| Adjustable model settings | O | UI sidebar controls | `app.py` (`render_developer_settings`) | `tests/test_app_smoke.py` | n/a | Visual check | Complete |
| Two or more structured JSON outputs | O | 4 domain schemas + usage/pricing | `src/models.py` | `tests/test_models.py`, `tests/test_response_parser.py` | n/a | — | Complete |
| Job-description context | O | Optional JD field, used in prompts | `app.py`, `src/prompts.py` | `tests/test_interview_service.py` | n/a | — | Complete |
| Multiple model choices | O | 3 models in selector | `src/ui_helpers.py`, `app.py` | `tests/test_app_smoke.py` | n/a | — | Complete |
| Prompt pricing & usage output | O | Cost precedence + usage panel | `src/pricing_service.py`, `app.py` | `tests/test_pricing_service.py` | n/a | Live cost display | Complete |
| Jailbreak testing exported to Excel | O | 29-case battery → xlsx + csv | `scripts/run_jailbreak_tests.py` | `tests/test_jailbreak_runner.py` | `evaluations/jailbreak_test_results.{xlsx,csv}` | — | Complete |
| Full conversational chatbot | O | `st.chat_message`/`st.chat_input` flow | `app.py` (`render_interview`) | `tests/test_app_smoke.py` | n/a | Live multi-turn run | Complete |
| Prompt-performance comparison | O | 5-technique comparison script + Prompt Lab | `scripts/compare_prompts.py`, `app.py` | `tests/test_prompt_comparison.py` | `evaluations/prompt_comparison.*` | Live comparison metrics | Complete (see note) |
| Interview Deep Dive (branching) | O | Bounded topic branching from an evaluated answer | `src/session_manager.py`, `src/interview_service.py` (`generate_branch_question`), `src/models.py` (`BranchQuestion`), `app.py` | `tests/test_branching.py` | n/a | Live end-to-end deep dive | Complete |

## Notes

- **Prompt/model-setting evaluation metrics.** The comparison *infrastructure*
  is complete and tested offline. The committed `evaluations/prompt_comparison.*`
  and `evaluations/model_settings_comparison.*` record a run whose status is
  `completed` but whose model calls did not return usable metrics (all
  `valid_json = false`, no tokens/cost). To populate real comparative figures,
  re-run with a funded key (`--run --confirm`). See
  `docs/prompt_engineering.md`.
- **Live behaviour** across all rows above is exercised only via the gated,
  chargeable paths; automated tests deliberately mock the network.
