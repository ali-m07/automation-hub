"""Integration tests for job status and cancellation."""

from unittest.mock import patch

from automation_hub.services.job_queue import create_job


def test_job_status_and_cancel(authenticated_client):
    queue_id = create_job("admin@test.com", "file_copy", {"source": "sample.txt"})

    response = authenticated_client.get(f"/api/jobs/{queue_id}")
    assert response.status_code == 200
    assert response.json()["progress"] == 0
    assert response.json()["job_type"] == "file_copy"

    with patch("automation_hub.services.job_queue.get_celery_app", create=True):
        response = authenticated_client.post(f"/api/jobs/{queue_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_list_jobs_is_scoped_to_current_user(authenticated_client):
    own_job = create_job("admin@test.com", "creative_psd", {})
    other_job = create_job("someone@example.com", "creative_psd", {})

    response = authenticated_client.get("/api/jobs")
    assert response.status_code == 200
    job_ids = {job["id"] for job in response.json()["jobs"]}
    assert own_job in job_ids
    assert other_job not in job_ids
