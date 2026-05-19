from django.urls import path
from . import views

urlpatterns = [
    # New BCD-compliant API
    path("hu/lookup/", views.hu_lookup, name="hu-lookup"),
    path("hu/<int:session_id>/", views.session_detail, name="session-detail"),
    path("hu/<int:session_id>/scan/", views.scan_endpoint, name="scan-endpoint"),
    path("hu/<int:session_id>/complete/", views.complete_endpoint, name="complete-endpoint"),

    # Legacy/debug
    path("scanning/sessions/", views.list_sessions, name="sessions-list"),
]
