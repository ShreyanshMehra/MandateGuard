package mandateguard.refund

import rego.v1

# The static fallback is intentionally independent of configuration. If the
# versioned policy data is absent or malformed, OPA returns a safe denial rather
# than evaluating a partially configured mandate.
default decision := {
	"outcome": "DENY",
	"reason_code": "POLICY_DEFAULT_DENY",
	"public_explanation": "The request could not be authorized.",
	"operator_explanation": "Policy configuration is missing or invalid; MandateGuard failed closed.",
	"policy_version": "unavailable",
	"effective_limits": {},
	"obligations": {
		"reserve_budget": false,
		"budget_scopes": [],
		"approval": {
			"required": false,
			"role": null,
			"recheck_before_execution": false,
		},
		"issue_single_use_permit": false,
	},
}

config := data.mandateguard.config

deny_obligations := {
	"reserve_budget": false,
	"budget_scopes": [],
	"approval": {
		"required": false,
		"role": null,
		"recheck_before_execution": false,
	},
	"issue_single_use_permit": false,
}

# A deliberately small configuration contract keeps policy/config compatibility
# explicit. Detailed schema validation remains a deployment-time responsibility.
config_ready if {
	is_object(config)
	config.schema_version == "1.0"
	is_string(config.policy_version)
	count(config.policy_version) > 0
	config.supported_action == "refund_payment"
	config.supported_currency == "USD"
	is_string(config.approval_role)
	count(config.approval_role) > 0
	is_string(config.fleet_budget_scope)
	count(config.fleet_budget_scope) > 0
	is_object(config.agents)
	valid_limit_pair(config.risk_modes.NORMAL)
	valid_limit_pair(config.risk_modes.ELEVATED)
}

valid_limit_pair(limits) if {
	is_object(limits)
	is_number(limits.approval_threshold_minor)
	limits.approval_threshold_minor > 0
	limits.approval_threshold_minor == floor(limits.approval_threshold_minor)
	is_number(limits.hard_max_minor)
	limits.hard_max_minor > limits.approval_threshold_minor
	limits.hard_max_minor == floor(limits.hard_max_minor)
}

# Input is produced by the broker after identity verification. The policy still
# validates the complete shape and fails closed on missing or surprising values.
valid_input if {
	is_object(input)
	is_object(input.agent)
	is_string(input.agent.id)
	count(input.agent.id) > 0
	is_boolean(input.agent.authenticated)
	is_string(input.agent.status)
	count(input.agent.status) > 0
	is_object(input.request)
	is_string(input.request.action)
	count(input.request.action) > 0
	is_string(input.request.payment_id)
	count(input.request.payment_id) > 0
	is_string(input.request.customer_id)
	count(input.request.customer_id) > 0
	is_number(input.request.amount_minor)
	input.request.amount_minor > 0
	input.request.amount_minor == floor(input.request.amount_minor)
	is_string(input.request.currency)
	count(input.request.currency) > 0
	is_object(input.context)
	is_string(input.context.risk_mode)
	count(input.context.risk_mode) > 0
}

known_risk_mode if {
	input.context.risk_mode in {"NORMAL", "ELEVATED"}
}

registered_agent if {
	config.agents[input.agent.id]
}

agent_active if {
	input.agent.status == "ACTIVE"
	config.agents[input.agent.id].enabled == true
}

action_permitted if {
	input.request.action in config.agents[input.agent.id].allowed_actions
}

customer_in_scope if {
	"*" in config.agents[input.agent.id].customer_scopes
}

customer_in_scope if {
	input.request.customer_id in config.agents[input.agent.id].customer_scopes
}

risk_limits := config.risk_modes[input.context.risk_mode]

budget_scopes := [
	{
		"scope_type": "CUSTOMER",
		"scope_id": input.request.customer_id,
	},
	{
		"scope_type": "AGENT",
		"scope_id": input.agent.id,
	},
	{
		"scope_type": "FLEET",
		"scope_id": config.fleet_budget_scope,
	},
]

effective_limits := {
	"risk_mode": input.context.risk_mode,
	"currency": config.supported_currency,
	"approval_threshold_minor": risk_limits.approval_threshold_minor,
	"hard_max_minor": risk_limits.hard_max_minor,
}

allow_obligations := {
	"reserve_budget": true,
	"budget_scopes": budget_scopes,
	"approval": {
		"required": false,
		"role": config.approval_role,
		"recheck_before_execution": false,
	},
	"issue_single_use_permit": true,
}

hold_obligations := {
	# Holding does not reserve money. If a human approves, the broker must run
	# policy and budget checks again immediately before execution.
	"reserve_budget": false,
	"budget_scopes": budget_scopes,
	"approval": {
		"required": true,
		"role": config.approval_role,
		"recheck_before_execution": true,
	},
	"issue_single_use_permit": false,
}

decision := invalid_input_decision if {
	config_ready
	not valid_input
}

decision := evaluated_decision if {
	config_ready
	valid_input
}

# The else chain is the precedence contract. A hard limit, for example, must
# always deny instead of being weakened to a human-approval hold.
evaluated_decision := unauthenticated_decision if {
	not input.agent.authenticated
} else := unsupported_risk_mode_decision if {
	not known_risk_mode
} else := unknown_agent_decision if {
	not registered_agent
} else := inactive_agent_decision if {
	not agent_active
} else := unsupported_action_decision if {
	input.request.action != config.supported_action
} else := unpermitted_action_decision if {
	not action_permitted
} else := unsupported_currency_decision if {
	input.request.currency != config.supported_currency
} else := customer_scope_decision if {
	not customer_in_scope
} else := hard_max_decision if {
	input.request.amount_minor > risk_limits.hard_max_minor
} else := approval_decision if {
	input.request.amount_minor > risk_limits.approval_threshold_minor
} else := allow_decision

invalid_input_decision := {
	"outcome": "DENY",
	"reason_code": "INPUT_INVALID",
	"public_explanation": "The request is incomplete or invalid.",
	"operator_explanation": "One or more required policy-input fields are missing, empty, incorrectly typed, or amount_minor is not a positive integer.",
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

unauthenticated_decision := {
	"outcome": "DENY",
	"reason_code": "AGENT_UNAUTHENTICATED",
	"public_explanation": "The agent identity could not be verified.",
	"operator_explanation": "The broker supplied authenticated=false; no mandate or financial limits were evaluated.",
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

unsupported_risk_mode_decision := {
	"outcome": "DENY",
	"reason_code": "RISK_MODE_UNSUPPORTED",
	"public_explanation": "The request could not be evaluated under the current risk mode.",
	"operator_explanation": sprintf("Risk mode %q is unsupported; expected NORMAL or ELEVATED.", [input.context.risk_mode]),
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

unknown_agent_decision := {
	"outcome": "DENY",
	"reason_code": "AGENT_UNKNOWN",
	"public_explanation": "This agent is not authorized for financial actions.",
	"operator_explanation": sprintf("Agent %q has no mandate in policy %s.", [input.agent.id, config.policy_version]),
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

inactive_agent_decision := {
	"outcome": "DENY",
	"reason_code": "AGENT_INACTIVE",
	"public_explanation": "This agent is currently inactive or revoked.",
	"operator_explanation": sprintf("Agent %q is not active in both runtime identity state and the versioned mandate.", [input.agent.id]),
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

unsupported_action_decision := {
	"outcome": "DENY",
	"reason_code": "ACTION_UNSUPPORTED",
	"public_explanation": "This financial action is not supported.",
	"operator_explanation": sprintf("The MVP supports only %q; received %q.", [config.supported_action, input.request.action]),
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

unpermitted_action_decision := {
	"outcome": "DENY",
	"reason_code": "ACTION_NOT_PERMITTED",
	"public_explanation": "This agent is not permitted to perform the requested action.",
	"operator_explanation": sprintf("Agent %q does not have %q in its allowed_actions mandate.", [input.agent.id, input.request.action]),
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

unsupported_currency_decision := {
	"outcome": "DENY",
	"reason_code": "CURRENCY_UNSUPPORTED",
	"public_explanation": "This currency is not supported for refunds.",
	"operator_explanation": sprintf("Cross-currency governance is outside the MVP; expected %s and received %s.", [config.supported_currency, input.request.currency]),
	"policy_version": config.policy_version,
	"effective_limits": {},
	"obligations": deny_obligations,
}

customer_scope_decision := {
	"outcome": "DENY",
	"reason_code": "CUSTOMER_SCOPE_MISMATCH",
	"public_explanation": "The agent is not permitted to act on this customer.",
	"operator_explanation": sprintf("Customer %q is outside agent %q's configured customer_scopes.", [input.request.customer_id, input.agent.id]),
	"policy_version": config.policy_version,
	"effective_limits": effective_limits,
	"obligations": deny_obligations,
}

hard_max_decision := {
	"outcome": "DENY",
	"reason_code": "HARD_MAX_EXCEEDED",
	"public_explanation": "The refund exceeds the maximum permitted amount.",
	"operator_explanation": sprintf("Refund amount_minor %d exceeds the %s hard maximum %d under policy %s.", [input.request.amount_minor, input.context.risk_mode, risk_limits.hard_max_minor, config.policy_version]),
	"policy_version": config.policy_version,
	"effective_limits": effective_limits,
	"obligations": deny_obligations,
}

approval_decision := {
	"outcome": "HOLD",
	"reason_code": "APPROVAL_REQUIRED",
	"public_explanation": "The refund requires review before it can proceed.",
	"operator_explanation": sprintf("Refund amount_minor %d is above the %s automatic-approval threshold %d and does not exceed hard maximum %d.", [input.request.amount_minor, input.context.risk_mode, risk_limits.approval_threshold_minor, risk_limits.hard_max_minor]),
	"policy_version": config.policy_version,
	"effective_limits": effective_limits,
	"obligations": hold_obligations,
}

allow_decision := {
	"outcome": "ALLOW",
	"reason_code": "REQUEST_ALLOWED",
	"public_explanation": "The refund is within the agent's permitted mandate.",
	"operator_explanation": sprintf("Authenticated agent, action, customer scope, currency, and %s amount threshold checks passed under policy %s.", [input.context.risk_mode, config.policy_version]),
	"policy_version": config.policy_version,
	"effective_limits": effective_limits,
	"obligations": allow_obligations,
}
