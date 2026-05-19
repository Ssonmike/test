from django.urls import path
from . import views_supervisor

urlpatterns = [
    path("sessions/", views_supervisor.session_list_page, name="supervisor-sessions"),
]
