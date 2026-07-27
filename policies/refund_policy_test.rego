package mandateguard.refund_test

import rego.v1

import data.mandateguard.refund

base_input := {
	"agent": {
		"id": "refund-agent-v1",
		"authenticated": true,
		"status": "ACTIVE",
	},
	"request": {
		"action": "refund_payment",
		"payment_id": "payment-demo-001",
		"customer_id": "customer-demo-001",
		"amount_minor": 5000,
		"currency": "USD",
	},
	"context": {"risk_mode": "NORMAL"},
}

with_agent(overrides) := result if {
	result := object.union(base_input, {"agent": object.union(base_input.agent, overrides)})
}

with_request(overrides) := result if {
	result := object.union(base_input, {"request": object.union(base_input.request, overrides)})
}

with_context(overrides) := result if {
	result := object.union(base_input, {"context": object.union(base_input.context, overrides)})
}

test_normal_refund_is_allowed if {
	result := refund.decision with input as base_input
	result.outcome == "ALLOW"
	result.reason_code == "REQUEST_ALLOWED"
	result.policy_version == "refund-governance-v1.0.0"
	result.effective_limits.approval_threshold_minor == 25000
	result.obligations.reserve_budget == true
	result.obligations.issue_single_use_permit == true
	result.obligations.approval.required == false
	count(result.obligations.budget_scopes) == 3
}

test_amount_above_threshold_is_held_for_approval if {
	request := with_request({"amount_minor": 25001})
	result := refund.decision with input as request
	result.outcome == "HOLD"
	result.reason_code == "APPROVAL_REQUIRED"
	result.obligations.reserve_budget == false
	result.obligations.approval.required == true
	result.obligations.approval.role == "REFUND_APPROVER"
	result.obligations.approval.recheck_before_execution == true
	count(result.obligations.budget_scopes) == 3
}

test_amount_at_approval_threshold_is_allowed if {
	request := with_request({"amount_minor": 25000})
	result := refund.decision with input as request
	result.outcome == "ALLOW"
	result.reason_code == "REQUEST_ALLOWED"
}

test_amount_above_hard_max_is_denied_not_held if {
	request := with_request({"amount_minor": 100001})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "HARD_MAX_EXCEEDED"
	result.obligations.budget_scopes == []
}

test_amount_at_hard_max_is_held_not_denied if {
	request := with_request({"amount_minor": 100000})
	result := refund.decision with input as request
	result.outcome == "HOLD"
	result.reason_code == "APPROVAL_REQUIRED"
}

test_wrong_action_is_denied if {
	request := with_request({"action": "travel_rebook"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "ACTION_UNSUPPORTED"
}

test_supported_action_outside_agent_mandate_is_denied if {
	request := with_agent({"id": "travel-agent-v1"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "ACTION_NOT_PERMITTED"
}

test_wrong_currency_is_denied if {
	request := with_request({"currency": "EUR"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "CURRENCY_UNSUPPORTED"
}

test_unauthenticated_agent_is_denied if {
	request := with_agent({"authenticated": false})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "AGENT_UNAUTHENTICATED"
}

test_runtime_revoked_agent_is_denied if {
	request := with_agent({"status": "REVOKED"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "AGENT_INACTIVE"
}

test_config_disabled_agent_is_denied if {
	request := with_agent({"id": "disabled-refund-agent-v1"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "AGENT_INACTIVE"
}

test_unknown_agent_is_denied if {
	request := with_agent({"id": "unknown-agent-v1"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "AGENT_UNKNOWN"
}

test_customer_scope_mismatch_is_denied if {
	request := with_request({"customer_id": "customer-outside-scope"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "CUSTOMER_SCOPE_MISMATCH"
}

test_wildcard_customer_scope_is_allowed if {
	agent_request := with_agent({"id": "rogue-refund-agent-v1"})
	request := object.union(agent_request, {"request": object.union(agent_request.request, {"customer_id": "any-customer"})})
	result := refund.decision with input as request
	result.outcome == "ALLOW"
}

test_elevated_mode_tightens_approval_threshold if {
	normal_request := with_request({"amount_minor": 15000})
	elevated_request := object.union(normal_request, {"context": {"risk_mode": "ELEVATED"}})
	normal_result := refund.decision with input as normal_request
	elevated_result := refund.decision with input as elevated_request
	normal_result.outcome == "ALLOW"
	elevated_result.outcome == "HOLD"
	elevated_result.effective_limits.approval_threshold_minor == 10000
}

test_elevated_mode_tightens_hard_max if {
	normal_request := with_request({"amount_minor": 60000})
	elevated_request := object.union(normal_request, {"context": {"risk_mode": "ELEVATED"}})
	normal_result := refund.decision with input as normal_request
	elevated_result := refund.decision with input as elevated_request
	normal_result.outcome == "HOLD"
	elevated_result.outcome == "DENY"
	elevated_result.reason_code == "HARD_MAX_EXCEEDED"
}

test_unknown_risk_mode_is_denied if {
	request := with_context({"risk_mode": "CRITICAL"})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "RISK_MODE_UNSUPPORTED"
}

test_missing_required_field_is_denied if {
	request := {
		"agent": base_input.agent,
		"request": {
			"action": "refund_payment",
			"payment_id": "payment-demo-001",
			"customer_id": "customer-demo-001",
			"currency": "USD",
		},
		"context": base_input.context,
	}
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "INPUT_INVALID"
}

test_fractional_minor_units_are_denied if {
	request := with_request({"amount_minor": 10.5})
	result := refund.decision with input as request
	result.outcome == "DENY"
	result.reason_code == "INPUT_INVALID"
}

test_empty_input_is_denied if {
	result := refund.decision with input as {}
	result.outcome == "DENY"
	result.reason_code == "INPUT_INVALID"
}

test_missing_policy_config_uses_static_default_deny if {
	result := refund.decision with input as base_input with data.mandateguard.config as {}
	result.outcome == "DENY"
	result.reason_code == "POLICY_DEFAULT_DENY"
	result.policy_version == "unavailable"
}

test_incompatible_config_schema_uses_static_default_deny if {
	bad_config := object.union(data.mandateguard.config, {"schema_version": "2.0"})
	result := refund.decision with input as base_input with data.mandateguard.config as bad_config
	result.outcome == "DENY"
	result.reason_code == "POLICY_DEFAULT_DENY"
}
