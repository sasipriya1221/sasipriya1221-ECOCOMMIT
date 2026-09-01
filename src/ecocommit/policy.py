from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ._canonical import sha256_hex
from .contracts import ClauseType, DecisionStatus, EconomicIntentContract


class PolicyMappingError(ValueError):
    pass


class PolicyClass(str, Enum):
    PRODUCT_SCOPE = "PRODUCT_SCOPE"
    QUANTITY_LIMIT = "QUANTITY_LIMIT"
    PURCHASE_AMOUNT_LIMIT = "PURCHASE_AMOUNT_LIMIT"
    COUNTERPARTY_RESTRICTION = "COUNTERPARTY_RESTRICTION"
    TIME_WINDOW = "TIME_WINDOW"
    CERTIFICATION_REQUIREMENT = "CERTIFICATION_REQUIREMENT"
    REVERSIBILITY_REQUIREMENT = "REVERSIBILITY_REQUIREMENT"
    AUTHORIZATION_REQUIREMENT = "AUTHORIZATION_REQUIREMENT"
    EXECUTION_CONDITION = "EXECUTION_CONDITION"
    EXCEPTION_RULE = "EXCEPTION_RULE"
    DEPENDENCY_RULE = "DEPENDENCY_RULE"


class PolicyObligation(BaseModel):
    """Restricted policy representation derived from a validated A contract.

    ``normalized_value`` remains descriptive input. It is deliberately not an
    exposure ceiling and is never consumed by the exposure calculator.
    """

    model_config = ConfigDict(frozen=True)

    obligation_id: str = Field(min_length=16)
    contract_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    clause_id: str = Field(min_length=1)
    policy_class: PolicyClass
    normalized_value: str = Field(min_length=1)
    negated: bool
    depends_on: tuple[str, ...] = ()
    exception_to: tuple[str, ...] = ()


class PolicyClassMapper:
    """Fail-closed mapper: candidate-provided policy labels grant no authority."""

    _CLASS_BY_CLAUSE: dict[ClauseType, PolicyClass] = {
        ClauseType.PRODUCT: PolicyClass.PRODUCT_SCOPE,
        ClauseType.QUANTITY: PolicyClass.QUANTITY_LIMIT,
        ClauseType.AMOUNT: PolicyClass.PURCHASE_AMOUNT_LIMIT,
        ClauseType.COUNTERPARTY: PolicyClass.COUNTERPARTY_RESTRICTION,
        ClauseType.TEMPORAL: PolicyClass.TIME_WINDOW,
        ClauseType.CERTIFICATION: PolicyClass.CERTIFICATION_REQUIREMENT,
        ClauseType.REVERSIBILITY: PolicyClass.REVERSIBILITY_REQUIREMENT,
        ClauseType.AUTHORIZATION: PolicyClass.AUTHORIZATION_REQUIREMENT,
        ClauseType.CONDITION: PolicyClass.EXECUTION_CONDITION,
        ClauseType.EXCEPTION: PolicyClass.EXCEPTION_RULE,
        ClauseType.DEPENDENCY: PolicyClass.DEPENDENCY_RULE,
    }

    def map_contract(
        self,
        contract: EconomicIntentContract,
        validation_status: DecisionStatus,
    ) -> tuple[PolicyObligation, ...]:
        if validation_status != DecisionStatus.VALIDATED:
            raise PolicyMappingError("only a VALIDATED contract may enter policy mapping")

        contract_hash = contract.canonical_hash()
        obligations: list[PolicyObligation] = []
        for clause in contract.clauses:
            policy_class = self._CLASS_BY_CLAUSE.get(clause.clause_type)
            if policy_class is None:
                raise PolicyMappingError(f"unsupported clause type: {clause.clause_type}")

            # The interpreter is allowed to echo the deterministic label, but a
            # conflicting label is rejected rather than used as a policy override.
            if clause.policy_class is not None and clause.policy_class != policy_class.value:
                raise PolicyMappingError(
                    f"clause {clause.clause_id!r} supplied policy class "
                    f"{clause.policy_class!r}; deterministic class is {policy_class.value!r}"
                )

            obligation_id = sha256_hex(
                {
                    "contract_hash": contract_hash,
                    "clause_id": clause.clause_id,
                    "policy_class": policy_class.value,
                }
            )
            obligations.append(
                PolicyObligation(
                    obligation_id=obligation_id,
                    contract_hash=contract_hash,
                    clause_id=clause.clause_id,
                    policy_class=policy_class,
                    normalized_value=clause.normalized_value,
                    negated=clause.negated,
                    depends_on=tuple(clause.depends_on),
                    exception_to=tuple(clause.exception_to),
                )
            )
        return tuple(obligations)
