
from accounts import views as account_views
from posts import views as posts_views

from django.urls import path, re_path
urlpatterns = [
    path('', posts_views.splash_view),
    path('splash', posts_views.splash_view),
    path('following', posts_views.following_view),
    path('privacy_policy', account_views.privacy_policy_view),
    path('values', account_views.values_view),
    path('hero', account_views.hero_view),
    path('get-the-app', account_views.get_app_view),
    path('test', posts_views.test_view),
    
    re_path('set-region', account_views.user_set_region_view),
    re_path('user/settings', account_views.user_settings_view),
    re_path('so/(?P<username>(.*))', account_views.user_view),
    re_path('so%7C(?P<username>(.*))', account_views.user_view),
    re_path('u/(?P<username>(.*))', account_views.user_view),
    re_path('u%7C(?P<username>(.*))', account_views.user_view),
    re_path('subregions_modal/(?P<region>[\w-]+)/(?P<regionType>[\w-]+)/(?P<baseLink>(.*))', posts_views.subregions_modal_view),
    
    re_path('search/(?P<keyword>(.*))', posts_views.search_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/search/(?P<keyword>(.*))', posts_views.search_view),
    path('region', posts_views.region_view),
    
]