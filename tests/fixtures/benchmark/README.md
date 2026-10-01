# Benchmark fixtures

`answer_evaluation.py` is the EnterpriseRAG-Bench judge's prompt file, copied unchanged (MIT):
https://github.com/onyx-dot-app/EnterpriseRAG-Bench/blob/main/src/prompts/answer_evaluation.py
at commit `82954993d1` (2026-04-18), fetched 2026-09-30. `tests/test_eval_judge.py` checks that
our judge templates (GEN-9) carry the same text.
