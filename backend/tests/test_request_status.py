from backend.api.unified_requests import normalize_request_status


def test_non_delete_requests_are_not_awaiting_approval():
    assert normalize_request_status("in_progress", []) == "in_progress"
    assert normalize_request_status("pending", [{"status": "completed"}, {"status": "pending"}]) == "in_progress"


def test_delete_requests_stay_awaiting_approval_until_approved():
    assert normalize_request_status("awaiting_approval", []) == "awaiting_approval"
    assert normalize_request_status("awaiting_approval", [{"status": "completed"}]) == "awaiting_approval"


def test_completed_requests_include_results_when_all_tasks_done():
    assert normalize_request_status("in_progress", [{"status": "completed"}, {"status": "completed"}]) == "completed"
