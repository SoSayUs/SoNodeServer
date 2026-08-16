


from transactions import views

from django.urls import path, re_path

urlpatterns = [

    path('sopay', views.sopay_view),
    re_path('wallet/(?P<wallet_id>(.*))', views.wallet_view),
]