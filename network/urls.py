
from django.urls import path, re_path
from . import views as chain_views


urlpatterns = [
    path('declare_node_state', chain_views.declare_node_state_view),
    re_path('get_broadcast_list/(?P<iden>(.*))', chain_views.get_broadcast_list_view),
    path('get_broadcast_list', chain_views.get_broadcast_list_view),
    path('get_current_node_list', chain_views.get_current_node_list_view),
    path('get_plugin_data', chain_views.get_plugin_data_view),
    path('get_chain_data', chain_views.get_chain_data_view),
    path('request_chain_path', chain_views.request_chain_path_view),

    path('broadcast_dataPackets', chain_views.broadcast_dataPackets_view),
    path('receive_data_packet', chain_views.receive_data_packet_view),
    path('receive_event', chain_views.receive_event_view),
    path('receive_posts_for_validating', chain_views.receive_posts_for_validating_view),
    path('receive_gathered_data', chain_views.receive_gathered_data_view),

    path('receive_data', chain_views.receive_data_view),
    path('request_data', chain_views.request_data_view),
    path('request_obj', chain_views.request_obj_view),
    path('receive_blocks', chain_views.receive_blocks_view),

    re_path('request_dp/(?P<packet_id>[\w-]+)', chain_views.request_dp_view),
    re_path('get_node_request/(?P<node_id>[\w-]+)', chain_views.get_node_request_view),
    re_path('is_data_processing/(?P<iden>(.*))', chain_views.is_data_processing_view),
    re_path('check_latest_data/(?P<model_type>[\w-]+)', chain_views.check_latest_data_view),
    path('check_if_exists', chain_views.check_if_exists_view),

]
