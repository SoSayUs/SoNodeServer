
from legis import views

from django.urls import path, re_path

urlpatterns = [

    re_path('sovote/(?P<region>[\w-]+)', views.legislature_view),
    re_path('sovote', views.legislature_view, {'region':None}),
    path('someta', views.someta_view),
    re_path('profile/(?P<region>[\w-]+)/(?P<name>(.*))/(?P<iden>(.*))', views.representative_view),

    path('debates', views.house_or_senate_hansards_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/debates', views.house_or_senate_hansards_view),
    
    re_path('(?P<region>[\w-]+)/(?P<chamber>[\w-]+)-meeting/(?P<govNumber>\d+)/(?P<session>\d+)/(?P<iden>(.*))/', views.debate_view, {'year':None, 'month':None, 'day':None, 'hour':None, 'minute':None}),
    re_path('(?P<region>[\w-]+)/(?P<chamber>[\w-]+)-meeting/(?P<govNumber>\d+)/(?P<session>\d+)/(?P<iden>(.*))/(?P<year>\d+)-(?P<month>\d+)-(?P<day>\d+)/(?P<hour>\d+):(?P<minute>\d+)', views.debate_view),
    path('citizenry', views.citizenry_view),
    re_path('(?P<region>[\w-]+)/citizenry', views.citizenry_view),
    path('citizen-debates', views.citizen_debates_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/citizen-debates', views.citizen_debates_view),
    path('citizen-bills', views.citizen_bills_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/citizen-bills', views.citizen_bills_view),
    path('polls', views.polls_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/polls', views.polls_view),
    path('petitions', views.petitions_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/petitions', views.petitions_view),
    re_path('(?P<region>[\w-]+)/legislature', views.legislature_view),
    re_path('legislature', views.legislature_view, {'region':'none'}),
    
    path('agendas', views.agendas_view, {'chamber':'all', 'region':'none'}),
    re_path('(?P<region>[\w-]+)/agendas', views.agendas_view, {'chamber':'all'}),
    re_path('(?P<region>[\w-]+)/(?P<chamber>[\w-]+)-agendas', views.agendas_view),
    # re_path('(?P<region>[\w-]+)/agenda-item/(?P<chamber>[\w-]+)/(?P<year>\d+)-(?P<month>\d+)-(?P<day>\d+)/(?P<hour>\d+):(?P<minute>\d+)', views.agenda_watch_view),
    # re_path('(?P<region>[\w-]+)/topic/(?P<keyword>(.*))', views.topic_view),

    path('officials', views.officials_list, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/officials', views.officials_list),
    re_path('bill/(?P<region>[\w-]+)/(?P<chamber>[a-zA-Z -]+)/(?P<govNumber>\d+)/(?P<session>\d+)/(?P<numcode>(.*))', views.bill_view),
    path('bills', views.bills_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/bills', views.bills_view),
    path('house-bills', views.bills_view, {'region':'none'}),
    path('senate-bills', views.bills_view, {'region':'none'}),
    path('elections', views.elections_view, {'region':'none'}),
    re_path('(?P<region>[\w-]+)/elections', views.elections_view),
    re_path('election/(?P<chamber>[\w-]+)/(?P<region>(.*))/(?P<iden>\d+)', views.candidates_view),

    path('committees', views.latest_committees_view, {'chamber':'all', 'region':'none'}),
    re_path('(?P<region>[\w-]+)/committees', views.latest_committees_view, {'chamber':'all'}),
    re_path('(?P<chamber>[\w-]+)-committees', views.latest_committees_view, {'region':'none'}),
    re_path('(?P<chamber>[\w-]+)-committee/(?P<govNumber>\d+)/(?P<session>\d+)/(?P<iden>[\w-]+)', views.committee_view),
    
    path('motions', views.motions_view, {'region':'none','type':'motion'}),
    re_path('(?P<region>[\w-]+)/motions', views.motions_view, {'type':'motion'}),
    re_path('(?P<region>[\w-]+)/(?P<chamber>[\w-]+)-motion/(?P<govNumber>\d+)/(?P<session>\d+)/(?P<number>(.*))', views.motion_view, {'type':'motion'}),
    path('rollcalls', views.motions_view, {'region':'none','type':'rollcall'}),
    re_path('(?P<region>[\w-]+)/rollcalls', views.motions_view, {'type':'rollcall'}),
    re_path('(?P<region>[\w-]+)/(?P<chamber>[\w-]+)-rollcall/(?P<govNumber>\d+)/(?P<session>\d+)/(?P<number>(.*))', views.motion_view, {'type':'rollcall'}),
    
]