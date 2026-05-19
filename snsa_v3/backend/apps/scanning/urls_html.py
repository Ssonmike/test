from django.urls import path
from . import views_html

urlpatterns = [
    path("", views_html.hu_lookup_page, name="hu-lookup-page"),
    path("sessions/<int:session_id>/", views_html.session_scan_page, name="session-scan-page"),
    path("sessions/<int:session_id>/scan/", views_html.session_scan_page, name="session-scan-action"),
    path("sessions/<int:session_id>/confirm/", views_html.session_confirm_page, name="session-confirm-page"),
    path("sessions/<int:session_id>/complete/", views_html.session_complete_page, name="session-complete-page"),
    path("sessions/<int:session_id>/no-serialization/", views_html.session_no_serialization_page, name="session-no-serialization-page"),
    path("sessions/<int:session_id>/retry/", views_html.session_retry_page, name="session-retry-page"),
    path("sessions/<int:session_id>/push-failed/", views_html.session_retry_page, name="session-push-failed-page"),
]
