from django.shortcuts import render
from utils.utils import prnt
from posts.utils import render_view, default_setup, nav_item, default_context
from .models import *

def sopay_view(request):
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    prnt('-sopay_view',style,user_id)
    
    include_nav = request.GET.get('include_nav', False)
    title = 'SoPay'
    r = default_setup(request, title, plugin='legis')
    if r:
        return r
    
    nav_options = []
    if include_nav == 'True':
        nav_options = [
                nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')
                ]
    posts = Wallet.objects.filter(User_obj__id=request.GET.get('user', None))
    context = default_context(request, posts, 'sopay_list', nav_options) 
    return render_view(request, context, feed='transactions')

def wallet_view(request, wallet_id):
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    prnt('-wallet_view',style,user_id)

    view = request.GET.get('view', 'transactions')
    include_nav = request.GET.get('include_nav', False)
    title = 'Wallet'
    r = default_setup(request, title, plugin='legis')
    if r:
        return r
    
    nav_options = []
    if include_nav == 'True':
        nav_options = [
            nav_item('link', 'Transactions', '?view=transactions', None),
            nav_item('link', 'Blocks', '?view=blocks', None),
            nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')
            ]
    if view == 'transactions':
        wallet = Wallet.objects.filter(id=wallet_id).first()
        posts = Transaction.objects.filter(Q(ReceiverWallet_obj=wallet)|Q(SenderWallet_obj=wallet))
        cards = 'wallet_txs'
    elif view == 'blocks':
        chain = Blockchain.objects.filter(genesisId=wallet_id).first()
        posts = Block.objects.filter(Blockchain_obj=chain).defer('data','extraData')
        cards = 'wallet_blocks'

    context = default_context(request, posts, cards, nav_options) 
    return render_view(request, context, feed='transactions')