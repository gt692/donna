from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/",      admin.site.urls),
    path("auth/",       include("apps.core.urls",      namespace="core")),
    path("dashboard/",  include("apps.dashboard.urls",  namespace="dashboard")),
    path("worktrack/",  include("apps.worktrack.urls",  namespace="worktrack")),
    path("crm/",        include("apps.crm.urls",        namespace="crm")),
    # Wurzel-Redirect auf Dashboard
    path("", lambda request: __import__("django.shortcuts", fromlist=["redirect"]).redirect("dashboard:home")),
]

if settings.DEBUG:
    import debug_toolbar
    from django.conf.urls.static import static
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
