from automation_hub.projects.feedback import router


def test_safe_html_removes_scripts():
    result = router._safe_html("<h2>Hello</h2><script>alert(1)</script>")
    assert "<h2>Hello</h2>" in result
    assert "<script" not in result


def test_form_field_user_picker_and_condition_are_sanitized():
    result = router._clean_form_field(
        {
            "label": "Approver",
            "type": "user_picker",
            "user_source": "ldap",
            "condition_field": "department",
            "condition_operator": "equals",
            "condition_value": "Finance",
        },
        0,
    )
    assert result["key"] == "Approver"
    assert result["type"] == "user_picker"
    assert result["user_source"] == "ldap"
    assert result["condition_value"] == "Finance"


def test_manager_transition_requires_ticket_manager():
    transition = {"approver_type": "manager"}
    ticket = {"manager_username": "manager@example.com"}
    assert router._can_transition(
        transition, ticket, {"username": "manager@example.com", "role": "user"}
    )
    assert not router._can_transition(
        transition, ticket, {"username": "other@example.com", "role": "user"}
    )


def test_transition_condition():
    rule = {
        "condition_field": "amount",
        "condition_operator": "equals",
        "condition_value": "100",
    }
    assert router._condition_matches(rule, {"amount": 100})
    assert not router._condition_matches(rule, {"amount": 200})


def test_blank_builder_has_no_generated_workflow():
    workflow = router._default_workflow()
    assert workflow["statuses"] == []
    assert workflow["screens"] == []
    assert workflow["transitions"] == []
