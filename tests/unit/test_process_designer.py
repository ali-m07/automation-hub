from automation_hub.projects.processes import router


def test_process_admin_permissions():
    assert router._can_manage({"role": "admin", "modules": []})
    assert router._can_manage({"role": "user", "modules": ["process_designer_admin"]})
    assert not router._can_manage({"role": "user", "modules": ["process_designer"]})


def test_global_field_is_visible_to_module_user():
    row = {"scope_type": "global", "scope_modules_json": "[]"}
    user = {"role": "user", "modules": ["feedback_180"]}
    assert router._scope_visible(row, user, "feedback_180")


def test_scoped_field_requires_matching_module():
    row = {
        "scope_type": "modules",
        "scope_modules_json": '["feedback_180"]',
    }
    assert router._scope_visible(
        row,
        {"role": "user", "modules": ["feedback_180"]},
        "feedback_180",
    )
    assert not router._scope_visible(
        row,
        {"role": "user", "modules": ["creative_psd"]},
        "creative_psd",
    )


def test_slug_normalizes_shared_keys():
    assert router._slug("Employee Department", "field") == "Employee_Department"
