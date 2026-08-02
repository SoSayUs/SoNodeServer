from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import ListView, TemplateView
from accounts import views as account_views

from django.urls import path, re_path, include

urlpatterns = [
    path('create_user', account_views.user_create_request_view),
    path('get_user_login', account_views.get_user_login_request_view),
    path('receive_user_login', account_views.receive_user_login_view),
    path('login-signup', account_views.login_signup_view),
    path('logout', account_views.logout_view),

    path('signup', account_views.signup_view),
    path('rename_setup', account_views.rename_setup_view),
    path('receive_rename', account_views.receive_rename_view),
    path('get_index', account_views.get_index_view),
    path('set_user_data', account_views.set_user_data_view),
    path('run_region_modal', account_views.run_region_modal_view),
    path('get_country_modal', account_views.get_country_modal_view),
    path('receive_interaction_data', account_views.receive_interaction_data_view),
    re_path('reaction/(?P<iden>[\w-]+)/(?P<item>[\w-]+)', account_views.reaction_view),
    re_path('get_region/(?P<country>(.*))', account_views.get_region_modal_view),
    re_path('username_avail', account_views.username_avail_view),
    path('deactivate_upk', account_views.deactivate_upk_view),

    path('verify_superuser', account_views.verify_superuser_view),
    path('set_sonet', account_views.set_sonet_view),
    re_path('quick_login/(?P<username>[\w-]+)/(?P<password>(.*))', account_views.quick_login_view),

]