# Product Coverage — Failure Analysis

42 of 412 cases have at least one failed applicable check.

## Ranked remediation (by failing-case count)

1. **occupation_resolution** — 18 case(s). Improve occupation resolver (aliases, crosswalks, disambiguation).
1. **missing_source** — 13 case(s). Acquire a production source for this slice (no real data loaded).
1. **geography** — 9 case(s). Fix country detection / source precedence for the geography.
1. **routing** — 2 case(s). Tighten/extend router rules for these question phrasings.

## Failing cases

| id | question_family | geo | category | lane | evidence |
|---|---|---|---|---|---|
| pc_education_073 | education |  | missing_source | education | 0 |
| pc_education_075 | education |  | missing_source | education | 0 |
| pc_education_079 | education |  | missing_source | education | 0 |
| pc_education_083 | education |  | missing_source | education | 0 |
| pc_industry_context_157 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_158 | industry_context |  | occupation_resolution | structured_role | 0 |
| pc_industry_context_159 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_160 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_161 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_162 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_163 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_164 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_165 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_166 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_167 | industry_context |  | occupation_resolution | vector | 0 |
| pc_industry_context_168 | industry_context |  | occupation_resolution | vector | 0 |
| pc_cybersecurity_182 | cybersecurity |  | routing | structured_role | 0 |
| pc_compensation_183 | compensation | US | geography | compensation | 1 |
| pc_compensation_188 | compensation | UK | geography | compensation | 1 |
| pc_compensation_191 | compensation | US | missing_source | compensation | 0 |
| pc_compensation_192 | compensation | UK | missing_source | compensation | 0 |
| pc_compensation_196 | compensation | UK | geography | compensation | 2 |
| pc_compensation_204 | compensation | UK | geography | compensation | 1 |
| pc_compensation_208 | compensation | UK | geography | compensation | 3 |
| pc_compensation_212 | compensation | UK | geography | compensation | 2 |
| pc_future_growth_215 | future_growth | US | missing_source | forecast | 0 |
| pc_future_growth_223 | future_growth | US | missing_source | forecast | 0 |
| pc_future_growth_235 | future_growth | US | missing_source | forecast | 0 |
| pc_short_term_outlook_247 | short_term_outlook | US | missing_source | short_term_outlook | 0 |
| pc_short_term_outlook_255 | short_term_outlook | US | missing_source | short_term_outlook | 0 |
| pc_short_term_outlook_267 | short_term_outlook | US | geography | short_term_outlook | 1 |
| pc_annual_openings_279 | annual_openings | US | geography | openings | 1 |
| pc_annual_openings_287 | annual_openings | US | missing_source | openings | 0 |
| pc_annual_openings_299 | annual_openings | US | missing_source | openings | 0 |
| pc_shortages_317 | shortages | DE | geography | shortage | 1 |
| pc_transition_375 | career_transition |  | occupation_resolution | transition | 1 |
| pc_transition_376 | career_transition |  | occupation_resolution | transition | 1 |
| pc_transition_377 | career_transition |  | occupation_resolution | transition | 1 |
| pc_transition_378 | career_transition |  | occupation_resolution | transition | 1 |
| pc_transition_379 | career_transition |  | occupation_resolution | transition | 1 |
| pc_transition_380 | career_transition |  | occupation_resolution | transition | 1 |
| pc_unsupported_406 | unsupported |  | routing | short_term_outlook | 0 |
