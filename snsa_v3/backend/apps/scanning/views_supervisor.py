import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import ScanSession

logger = logging.getLogger("apps.scanning")


@login_required
def session_list_page(request):
    sessions = (
        ScanSession.objects
        .select_related("operator")
        .prefetch_related("content_items")
        .order_by("-created_at")[:100]
    )
    template = (
        "supervisor/_session_table.html"
        if request.headers.get("HX-Request")
        else "supervisor/session_list.html"
    )
    return render(request, template, {"sessions": sessions})
