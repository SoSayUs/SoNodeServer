
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from accounts import views as account_views


from django.urls import path, re_path, include
from django.views.static import serve

urlpatterns = [
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
    ),
    path('admin/', admin.site.urls),
    path('logout/', account_views.logout_view),
    path('accounts/', include("accounts.urls")),
    path('network/', include("network.urls")),
    path('utils/', include("utils.urls")),
    path('', include("posts.urls")),
    path('', include("legis.urls")),

    re_path(r'^static/(?P<path>.*)$', serve,
            {'document_root': settings.STATIC_ROOT}),

]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# if settings.DEBUG:
# import debug_toolbar
# print('-----adding toolbar')
# urlpatterns += path('__debug__/', include(debug_toolbar.urls)),

