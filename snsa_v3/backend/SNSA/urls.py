from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),

    # Root redirect → scanning
    path("", RedirectView.as_view(url="/scanning/", permanent=False)),

    # API
    path("api/", include("apps.scanning.urls")),
    path("api/", include("apps.core.urls")),

    # HTML views — operator
    path("scanning/", include("apps.scanning.urls_html")),

    # HTML views — supervisor
    path("supervisor/", include("apps.scanning.urls_supervisor")),

    # Auth
    path("login/",  auth_views.LoginView.as_view(),  name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
