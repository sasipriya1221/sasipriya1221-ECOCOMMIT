# Evaluation Protocol

1. Development, validation and final-held-out sets are separate.
2. Final-held-out instructions are not used to tune prompts, thresholds or schema.
3. Results are machine-generated.
4. Failed cases are retained and documented.
5. Live model results are not replaced by mocked/provider-fixture results.
6. Checkpoint A is not marked PASSED until a real configured model is evaluated on unseen instructions and the acceptance criteria are met.
