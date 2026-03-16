"""Root URL configuration for iMCP local development project."""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # Django built-in admin (provides login page used by the portal)
    path("admin/", admin.site.urls),

    # iMCP — all routes live under /imcp/
    path("imcp/", include("imcp.urls")),

    # Convenience redirect: / → /imcp/portal/
    path("", RedirectView.as_view(url="/imcp/portal/", permanent=False)),
]

# Serve uploaded spec files during local development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
