
from django.shortcuts import render
from django.conf import settings
from django.template.defaulttags import register
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

import django_rq
import datetime
from accounts.models import Notification, Play, User
from posts.forms import AgendaForm
from posts.models import Region, Post
from posts.utils import get_client_ip
from network.models import Node, Sonet
from utils.locked import hash_obj_id, convert_to_dict, get_signing_data

from utils.models import (
    assess_received_header,
    set_model_attrs, share_with_network,
    list_all_scrapers, super_share,
    sync_model, super_sync, register_new_user, 
    register_node_on_cloudflare
)
from utils.utils import (
    prnt, prntDebug, prntn, get_dynamic_model, 
    now_utc, get_or_create_model, 
    create_dynamic_model, string_to_dt, has_field, has_method, get_timeData, 
    timezonify, get_superuser_keys, 
    get_pointer_type, get_self_node,
    get_node, dt_to_string
)
from firebase_admin.messaging import Notification as fireNotification
from firebase_admin.messaging import Message as fireMessage
import time
import json
import random

@csrf_exempt
def is_sonet_view(request):
    prnt('-is_sonet_view')
    if Sonet.objects.exists():
        s = True
    else:
        s = False
    return JsonResponse({'message' : 'is_sonet', 'sonet' : s})

@csrf_exempt
def get_sonet_view(request):
    sonet = Sonet.objects.first()
    if sonet:
        return JsonResponse({'message' : 'success', 'sonet' : json.dumps(convert_to_dict(sonet)), 'signing_obj' : get_signing_data(sonet)})
    return JsonResponse({'message' : 'None'})

@csrf_exempt
def set_object_data_view(request):
    prnt('-set_obj_data_view')
    objData_json = 'objData_jsonxx'
    objData = 'objDataxx'
    good = 'unknown'
    err = 'x1'
    try:
        if request.method == 'POST':
            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)

            objData = received_data.get('objData')
            err = 'x2'
            objData_json = json.loads(objData)
            try:
                extra_objData = received_data.get('extra_objData')
                extra_objData_json = json.loads(extra_objData)
            except:
                pass
            do_super_share = received_data.get('super_share',True)
            from utils.utils import get_sigData
            if isinstance(objData_json, list) and all(get_pointer_type(x['id']) in ['UserPubKey','Node','Wallet'] for x in objData_json):
                err = 'x3'
                share_items = []
                order_map = {name: i for i, name in enumerate(['UserPubKey','Node','Wallet'])}
                objData_json.sort(key=lambda x: order_map.get(get_pointer_type(x['id']), float('inf')))
                upk_valid = False
                for x in objData_json:
                    prnt('x',x)
                    sig_data = get_sigData(x, first_key=True)
                    prnt("sig_data['pk']",sig_data['pk'])
                    if get_pointer_type(x['id']) == 'UserPubKey':
                        from accounts.models import UserPubKey
                        upk = UserPubKey.objects.filter(id=x['id']).first()
                        if not upk:
                            upk = UserPubKey(id=x['id'], User_obj_id=x['User_obj'])
                        for key in upk.User_obj.get_keys(dt=x['lastUpdate']):
                            prnt('k1',key.id)
                            if key.id == sig_data['pk']:
                                err = 'x3a'
                                upk, sigs, upk_valid, updatedDB = sync_model(upk, x)
                                if upk_valid:
                                    upk.boot()
                                    share_items.append(upk)
                                    break
                    elif get_pointer_type(x['id']) == 'Node':
                        node = Node.objects.filter(id=x['id']).first()
                        if not node:
                            node = Node(id=x['id'], User_obj_id=x['User_obj'])
                        if upk_valid:
                            if upk.verify(get_signing_data(x), get_sigData(x)['sig'], upk.publicKey):
                                err = 'x3b'
                                if upk.id == sig_data['pk']:
                                    obj, sigs = super_sync(node, x, do_save=False)
                                    prnt('super sync complete')
                                    obj.save(bypass_upk_block=True)
                                    from utils.models import save_sigs
                                    save_sigs(sigs)
                                    if upk.verify(get_signing_data(obj), get_sigData(x)['sig'], upk.publicKey):
                                        share_items.append(obj)
                                        
                    elif get_pointer_type(x['id']) == 'Wallet':
                        from transactions.models import Wallet
                        wallet = Wallet.objects.filter(id=x['id']).first()
                        if not wallet:
                            wallet = Wallet(id=x['id'], User_obj_id=x['User_obj'])
                        for key in wallet.User_obj.get_keys(dt=x['lastUpdate']):
                            prnt('k2',key.id)
                            if key.id == sig_data['pk']:
                                err = 'x3c'
                                obj, sigs, valid_obj, updatedDB = sync_model(wallet, x)
                                if valid_obj:
                                    share_items.append(obj)
                                    break
                err = 'x4'
                if len(share_items) == len(objData_json):
                    share_with_network(share_items, share_node=True)
                    return JsonResponse({'message' : 'Success', 'obj' : get_signing_data(obj)})
            elif assess_received_header(request.headers):
                prnt('set super object..',objData_json)
                err = 'x5'
                superKeys = get_superuser_keys(data=objData_json)
                prnt('superKeys',superKeys)
                sig_data = get_sigData(objData_json)
                prnt("sig_data['pk']",sig_data['pk'])
                if sig_data['pk'] in superKeys or objData_json['objType'] == 'Wallet': # later change to allow user modded items such as plugins - not with super share - wallet bypass for network setup
                    prnt('is super')
                    obj = get_or_create_model(objData_json['objType'], id=objData_json['id'])
                    if has_field(obj, 'created') and not obj.created:
                        obj.created = now_utc()
                    if has_field(obj, 'Block_obj') and obj.Block_obj:
                        obj.Block_obj = None
                    if has_field(obj, 'Validator_obj') and obj.Validator_obj:
                        obj.Validator_obj = None

                    err = obj
                    from utils.locked import verify_obj_to_data, convert_to_dict
                    if verify_obj_to_data(obj, objData_json):
                        if has_field(obj, 'Validator_obj'):
                            obj.Validator_obj = None
                        obj, sigs, valid_obj, updatedDB = sync_model(obj, objData_json, force_sync=True)
                        prntDebug('synced:',updatedDB,'valid_obj',valid_obj)
                        prnt('synced:',updatedDB,'valid_obj',valid_obj)
                        if valid_obj:
                            err = 'x6'
                            if has_method(obj, 'boot'):
                                obj.boot()
                            if do_super_share:
                                objs, good = super_share(obj, func='super', val_type='set_object', job_id=hash_obj_id('DataPacket', random_iden=True), adjust_created_time=False)
                                prnt('obj-good1',good)
                                if good:
                                    return JsonResponse({'message' : 'Success', 'obj' : get_signing_data(objs[0])})
                            else:
                                from utils.utils import get_latest_dataPacket, find_or_create_chain_from_object
                                dataPacket = get_latest_dataPacket(obj.networkChain)
                                dataPacket.add_item_to_share(obj)
                                network_chain, obj, commit_chain = find_or_create_chain_from_object(obj)
                                network_chain.add_item_to_queue(obj)
                                good = True
                                prnt('obj-good2',good)
                                if good:
                                    return JsonResponse({'message' : 'Success', 'obj' : get_signing_data(obj)})
                    
            return JsonResponse({'message' : 'A problem occured', 'obj':objData,  'err': f' -- is_good: {good} -- x: {err}'})
    except Exception as e:
        prnt('set obj fail','x:',err, str(e))
        return JsonResponse({'message' : f'A problem occured', 'err': f'{str(e)} -- objData: {objData} -- objData_json: {objData_json} -- good: {good} -- x: {err}'})
    
@csrf_exempt
def get_object_data_view(request, obj_type='Region'):
    prnt('-get_object_data_view',obj_type)
    err = 0
    e = 'x'
    try:
        if request.method == 'POST':
            err = 1

            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)

            obj_type = received_data.get('obj_type')
            obj_id = received_data.get('obj_id')
            if_empty = received_data.get('if_empty',False)
            prnt('obj_type,obj_id',obj_type,obj_id)
            err = 2
            if obj_id in [None, '0']: # used in node software
                obj = create_dynamic_model(obj_type)
                if has_method(obj,'initialize'):
                    obj.initialize()
                else:
                    obj.id = hash_obj_id(obj) # creating id for some models before data is assigned may result in discrepancy if id not rehashed after data assignment
                if obj_type == 'Node':
                    from accounts.models import UserPubKey
                    node_upk_obj = UserPubKey(id=hash_obj_id('UserPubKey'), nodeId=obj.id, keyType='node')
                    node_upk_obj.initialize()
                    from transactions.models import Wallet
                    wallet_obj = Wallet(Name='Rewards')
                    wallet_obj.id = hash_obj_id('Wallet')
                    return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj)), 'upk_signing_obj' : get_signing_data(node_upk_obj, sort_data=False), 'wallet_signing_obj' : get_signing_data(wallet_obj, sort_data=False)})
            elif obj_type == 'Node':
                err = 3
                obj = get_dynamic_model(obj_type, id=obj_id)
                if obj:
                    from accounts.models import UserPubKey
                    node_upk_obj = UserPubKey(id=hash_obj_id('UserPubKey'), nodeId=obj.id, keyType='node')
                    node_upk_obj.initialize()
                    from transactions.models import Wallet
                    wallet_obj = Wallet.objects.filter(User_obj=obj.User_obj, Name=f'Rewards-{obj.id}').first()
                    if not wallet_obj:
                        wallet_obj = Wallet(Name=f'Rewards-{obj.id}')
                        wallet_obj.id = hash_obj_id('Wallet')
                    return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj)), 'upk_signing_obj' : get_signing_data(node_upk_obj, sort_data=False), 'wallet_signing_obj' : get_signing_data(wallet_obj, sort_data=False)})

                elif if_empty:
                    obj = create_dynamic_model(obj_type, id=obj_id)
                    from accounts.models import UserPubKey
                    node_upk_obj = UserPubKey(id=hash_obj_id('UserPubKey'), nodeId=obj.id, keyType='node')
                    node_upk_obj.initialize()
                    from transactions.models import Wallet
                    wallet_obj = Wallet(Name=f'Rewards-{obj.id}')
                    wallet_obj.id = hash_obj_id('Wallet')
                    return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj)), 'upk_signing_obj' : get_signing_data(node_upk_obj, sort_data=False), 'wallet_signing_obj' : get_signing_data(wallet_obj, sort_data=False)})
            
            else:
                if assess_received_header(request.headers):
                    err = 4
                    obj = get_dynamic_model(obj_type, id=obj_id)
                    if obj and obj.modlVer != obj.latestVer:
                        err = 41
                        from utils.locked import skip_sign_fields
                        latest_fields = obj.get_version_fields(version=obj.latestVer)
                        latest_signing_fields = {key:value for key, value in latest_fields.items() if key not in skip_sign_fields}
                        return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj)), 'latest_fields':json.dumps(latest_fields), 'latest_signing_fields':json.dumps(latest_signing_fields)})
                    
                    elif if_empty:
                        obj = create_dynamic_model(obj_type, id=obj_id)
                        from accounts.models import UserPubKey
                        node_upk_obj = UserPubKey(id=hash_obj_id('UserPubKey'), nodeId=obj.id, keyType='node')
                        node_upk_obj.initialize()
                        from transactions.models import Wallet
                        wallet_obj = Wallet(Name='Rewards')
                        wallet_obj.id = hash_obj_id('Wallet')
                        return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj)), 'upk_signing_obj' : get_signing_data(node_upk_obj, sort_data=False), 'wallet_signing_obj' : get_signing_data(wallet_obj, sort_data=False)})
            return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj))})
        else:
            from utils.utils import is_id
            if obj_type == 'Earth':
                err = 5
                earthModel = Region(created=now_utc(), func='super', nameType='Planet', Name='Earth', ImgLinks={"flag":"img/earth_pic.jpg"})
                earthModel.id = hash_obj_id(earthModel)
                return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(earthModel), 'model_obj':json.dumps(convert_to_dict(earthModel))})
            elif is_id(obj_type):
                obj = get_dynamic_model(obj_type, id=obj_type)
                if obj:
                    return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj))})
                else:
                    return JsonResponse({'message' : 'Not found'})
            else:
                obj = create_dynamic_model(obj_type)
                if has_method(obj, 'initialize'):
                    obj.initialize()
                if obj_type == 'Node':
                    from accounts.models import UserPubKey
                    node_upk_obj = UserPubKey(id=hash_obj_id('UserPubKey'), nodeId=obj.id, keyType='node')
                    node_upk_obj.initialize()
                    from transactions.models import Wallet
                    wallet_obj = Wallet(Name='Rewards')
                    wallet_obj.id = hash_obj_id('Wallet')
                    return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj, sort_data=False), 'model_obj':json.dumps(convert_to_dict(obj)), 'upk_signing_obj' : get_signing_data(node_upk_obj, sort_data=False), 'wallet_signing_obj' : get_signing_data(wallet_obj, sort_data=False)})
            
                return JsonResponse({'message' : 'Success', 'signing_obj' : get_signing_data(obj), 'model_obj':json.dumps(convert_to_dict(obj))})

    except Exception as e:    
        prnt('get_object_data_view fail1',str(e))
    return JsonResponse({'message' : 'failed', 'err':f'fail1: err:{err}'})

@csrf_exempt
def get_object_id_view(request):
    prnt('-get_object_id_view')
    try:
        if request.method == 'POST':
            if assess_received_header(request.headers):
                raw_data = request.body.decode('utf-8')
                received_data = json.loads(raw_data)
                objData = received_data.get('objData')
                objData_json = json.loads(objData)
                obj_type = objData_json['objType']
                nodeData = received_data.get('nodeData')
                nodeData_json = json.loads(nodeData)
                operator = Node.objects.filter(id=nodeData_json['id']).first().User_obj
                obj = create_dynamic_model(obj_type, id=objData_json['id'])
                obj, sigs, updatedDB = set_model_attrs(obj, objData_json, operator)
                obj.id = hash_obj_id(obj)
                return JsonResponse({'message' : 'Success', 'obj' : get_signing_data(obj), 'obj_id':obj.id})
    except Exception as e:
        prnt('get_object_id_view fail',str(e))     
        return JsonResponse({'message' : 'A problem occured', 'err':str(e)})
    
@csrf_exempt
def can_you_see_me_view(request):
    prnt('-can_you_see_me')
    try:
        sender_ip = get_client_ip(request)  
        prnt('from:',sender_ip)
        requested_address = 'unknown'
        if request.method == 'POST':
            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)
            requested_address = received_data.get('requested_address','')
            prnt('requested_address',requested_address)
            import requests
            if requested_address:
                try:
                    is_https = True
                    r = requests.get(f'https://{requested_address}/utils/is_sonet', timeout=5)
                except:
                    is_https = False
                    r = requests.get(f'http://{requested_address}/utils/is_sonet', timeout=5)
                check_address = requested_address
            else:
                try:
                    is_https = True
                    r = requests.get(f'https://{sender_ip}/utils/is_sonet', timeout=5)
                except:
                    is_https = False
                    r = requests.get(f'http://{sender_ip}/utils/is_sonet', timeout=5)
                check_address = sender_ip
            prnt('r.status_code',r.status_code,now_utc())
            if r.status_code == 200:
                received_json = r.json()
                if received_json['message'] == 'is_sonet':
                    return JsonResponse({'message' : 'Success', 'requested_address' : requested_address, 'actual_address':sender_ip, 'check_address':check_address, 'is_https':is_https})
            return JsonResponse({'message' : 'error', 'requested_address' : requested_address, 'actual_address':sender_ip})
    except Exception as e:
        prnt('can_you_see_me fail', str(e))
        return JsonResponse({'message' : f'A problem occured','err':str(e), 'requested_address' : requested_address, 'actual_address':sender_ip})
    
@csrf_exempt
def myip_view(request):
    prnt('-myip_view')
    sender_ip = get_client_ip(request)
    prnt('sender_ip',sender_ip)
    return render(request, "utils/dummy.html", {"result": sender_ip})

@csrf_exempt
def fetch_cloudflare_bundle_view(request, node_id):
    prnt('-fetch_cloudflare_bundle_view',node_id)
    proceed = False
    if assess_received_header(request.headers):
        proceed = True
    else:
        try:
            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)
        except:
            received_data = json.loads(request.body)
        try:
            nodeData = json.loads(received_data.get('nodeData', {}))
            userData = json.loads(received_data.get('userData', {}))
            upkData = json.loads(received_data.get('upkData', {}))
            walletData = json.loads(received_data.get('walletData', {}))
        except:
            nodeData = json.loads(request.POST.get('nodeData', {}))
            userData = json.loads(request.POST.get('userData', {}))
            upkData = json.loads(request.POST.get('upkData', {}))
            walletData = json.loads(request.POST.get('walletData', {}))

        login_success, loginData = register_new_user(userData, upkData, {}, walletData, nodeData)
        if login_success:
            node = loginData['node']
            if node:
                proceed = True
            else:
                node = Node(id=nodeData['id'], User_obj_id=nodeData['User_obj']).only('User_obj')
                prnt('node',node)
                from utils.utils import get_sigData
                sig_data = get_sigData(nodeData, first_key=False)
                for key in node.User_obj.get_keys(dt=nodeData['lastUpdate']):
                    if key.publicKey == sig_data['pk']:
                        obj, sigs, valid_obj, updatedDB = sync_model(node, nodeData)
                        if valid_obj:
                            proceed = True

        if proceed:
            proceed = False
            dt = string_to_dt(request.header.get('dt'))
            now = now_utc()
            if dt >= now - datetime.timedelta(seconds=30) and dt < now + datetime.timedelta(seconds=2):
                senderId = request.header.get('senderId')
                prnt('senderId',senderId)
                sender_node = get_node(id=senderId)
                if sender_node and not sender_node.expelled_dt and sender_node.User_obj.verify_sig(request.header.get('dt'), request.header.get('dtsig'), simple_verify=True):
                    prnt('good')
                    proceed = True
                
    if proceed:
        from pathlib import Path
        bundle_zip = register_node_on_cloudflare(node_id)
        if bundle_zip and isinstance(bundle_zip, Path):
            from django.http import FileResponse
            response = FileResponse(open(bundle_zip, 'rb'), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{node_id}-cloudflare-tunnel.zip"'
            return response
        if bundle_zip and isinstance(bundle_zip, dict):
            return JsonResponse({'message' : 'wrong_node', 'correct_nodes': json.dumps(bundle_zip)})
        return JsonResponse({'message' : 'None'})

@csrf_exempt
def proxyme_view(request):
    prnt('-proxyme_view')
    if request.method == 'POST':
        if assess_received_header(request.headers):
            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)
            if 'region' in received_data:
                region = received_data['region']
            if 'country_code' in received_data:
                country_code = received_data['country_code']
            address = received_data['address']
            prnt('address',address)
            import requests
            r = requests.get(address, timeout=30)
            if r.status_code == 200:
                response = HttpResponse(r.content, status=r.status_code)
                for k, v in r.headers.items():
                    if k.lower() not in ['content-encoding', 'transfer-encoding', 'content-length', 'connection']:
                        response[k] = v
                return response
            else:
                return
            # response = HttpResponse(r.content, status=r.status_code)
            # for k, v in r.headers.items():
            #     if k.lower() not in ['content-encoding', 'transfer-encoding', 'content-length', 'connection']:
            #         response[k] = v
            # return response

@csrf_exempt
def request_web_data_view(request):
    prnt('-request_web_data_view')
    if request.method == 'POST':
        if assess_received_header(request.headers):
            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)
            if 'region' in received_data:
                region = received_data['region']
            if 'country_code' in received_data:
                country_code = received_data['country_code']
            # check self_node.region_data matches country_code
            address = received_data['address']
            prnt('address',address)
            import requests
            r = requests.get(address, timeout=30)

            response = HttpResponse(r.content, status=r.status_code)
            for k, v in r.headers.items():
                if k.lower() not in ['content-encoding', 'transfer-encoding', 'content-length', 'connection']:
                    response[k] = v
            return response

def calendar_widget_view(request):
    prnt('-calendar_widget_view')
    if request.method == 'POST':
        data = request.POST['date']
        date = datetime.datetime.strptime(data, '%Y-%m-%d')
        agenda = Agenda.objects.filter(date_time__gte=date).order_by('date_time').first()
        agendaItems = AgendaItem.objects.filter(agendaTime__agenda=agenda).select_related('agendaTime').order_by('position')
        form = AgendaForm()   
        try:
            theme = request.COOKIES['theme']
        except:
            theme = 'day'
        context = {
            "theme": theme,
            "agenda":agenda,
            "agendaItems":agendaItems,
            'agendaForm': form,
        }
        return render(request, "utils/agenda_widget.html", context)

def mobile_share_view(request, iden):
    prnt('-mobile_share_view')
    post = Post.objects.filter(id=iden).first()
    link = post.get_absolute_url()
    if link[0] == '/':
        link = 'https://myDomain.org' + link
    shareTitle = post.get_title() + ' ' + link
    try:    
        fcmDeviceId = request.COOKIES['fcmDeviceId']
        prnt(fcmDeviceId)
        device = FCMDevice.objects.filter(user=request.user, registration_id=fcmDeviceId).first()
        device.send_message(fireMessage(data={"share" : "True", "shareTitle":shareTitle}))
    except Exception as e:
        prnt('mobile_share_view err',str(e))
    return render(request, "utils/dummy.html", {"result": 'Success'})

def modal_picker_view(request, modal_type, iden):
    prnt('-modal_picker_view',modal_type,iden)
    title = ''
    obj = get_dynamic_model(iden, id=iden)
    if obj:
        title = obj._meta.object_name
    context = {
        'title': title,
        'obj': obj,
    }
    return render(request, f"modals/{modal_type}.html", context)

def default_modal_view(request, iden):
    return render(request, f"modals/{iden}.html")

def share_modal_view(request, iden):
    post = Post.objects.filter(id=iden).first()
    context = {
        'title': 'Share Post',
        'post': post,
    }
    return render(request, "modals/share_modal.html", context)

@register.filter
def to_percent(num1, num2):
    try:
        percent = (num1 + num2) / num1
    except:
        percent = '-'
    return percent

def post_insight_view(request, iden):
    post = Post.objects.filter(id=iden).first()
    context = {
        'title': 'Insight',
        'post': post,
    }
    return render(request, "modals/post_insight.html", context)

def post_more_options_view(request, iden):
    prnt('-post_more_options_view',iden, request.user.id)
    post = Post.objects.filter(id=iden).first()
    try:
        useraction = Play.objects.filter(User_obj__id=request.user.id, Post_obj=post).first()
    except:
        useraction = None
    context = {
        'title': 'More Options',
        'post': post,
        'useraction':useraction,
    }
    return render(request, "modals/post_more_options.html", context)

def generic_modal_data_view(request, func, iden):
    prnt('-generic_modal_data_view',iden)
    if func == 'modelData':
        title = 'Model Data'
        update = None
        post_dict = None
        if get_pointer_type(iden) == 'Post':
            post = Post.objects.filter(id=iden).first()
            if post:
                pointer = post.get_pointer()
                obj = convert_to_dict(pointer, withold_fields=False)
                if has_field(pointer, 'created'):
                    obj['created'] = pointer.created
                obj['updated_on_node'] = pointer.updated_on_node
                post_dict = convert_to_dict(post, withold_fields=False)
                post_dict['updated_on_node'] = post.updated_on_node
                if post.Update_obj:
                    update = convert_to_dict(post.Update_obj, withold_fields=False)
                    update['created'] = post.Update_obj.created
                    update['updated_on_node'] = post.Update_obj.updated_on_node
        else:
            pointer = get_dynamic_model(iden, id=iden)
            if pointer:
                obj = convert_to_dict(pointer, withold_fields=False)
                if has_field(pointer, 'created'):
                    obj['created'] = pointer.created
                obj['updated_on_node'] = pointer.updated_on_node

    context = {
        'title': title,
        'obj': obj,
        'post': post_dict,
        'update': update
    }
    return render(request, "modals/generic_modal.html", context)

def verify_post_view(request, iden):
    post = Post.all_objects.filter(id=iden).first()
    context = {
        'title': 'Verify Me',
        'post': post,
    }
    return render(request, "utils/verify_post.html", context)

def deep_link_android_asset_view(request):
    return render(request, "json/deep_link_android_asset.html", content_type="application/json")

def deep_link_iphone_asset_view(request):
    return render(request, "json/deep_link_iphone_asset.html", content_type="application/json")

def continue_reading_view(request, iden):
    topic = request.GET.get('topic', '')
    if 'statement-' in iden:
        from legis.models import Statement
        Id = iden.replace('statement-', '')
        hansard = Statement.objects.get(id=Id)
        context = {'h':hansard, 'topicList':topic}
    return render(request, "utils/read_more.html", context)

def show_all_view(request, iden, item):
    if iden[0] == 'h':
        Id = iden[2:]
        meeting = Meeting.objects.get(id=Id)
        if item == 'terms':
            setlist = meeting.list_all_terms()
        else:
            setlist = meeting.list_all_people()
        context = {'meeting':meeting,'setlist':setlist, 'item':item}
    if iden[0] == 'c':
        Id = iden[2:]
        committee = Committee.objects.get(id=Id)
        if item == 'terms':
            setlist = committee.list_all_terms()
        else:
            setlist = committee.list_all_people()
        context = {'committee':committee,'setlist':setlist, 'item':item}
    return render(request, "utils/show_all.html", context)


#----utils

def broadcast_datapackets_view(request):
    if request.user.is_superuser:
        from network.models import DataPacket, _OperationsChain_genesisId
        self_node = get_self_node()
        dataPackets = DataPacket.objects.filter(Node_obj=self_node, func='share').exclude(data={})
        for dp in dataPackets:
            if len(dp.data.keys()) > 0 or dp.chainId == _OperationsChain_genesisId:
                queue = django_rq.get_queue('low')
                queue.enqueue(dp.broadcast, job_timeout=120, result_ttl=3600)
    
def run_super_function_view(request, region, func, worker, super):
    prnt('-run_super_function_view', region, func, worker,super)
    if request.user and request.user.assess_super_status():
        start_time = timezonify('est', datetime.datetime.now())
        end_time = None
        import inspect
        def accepts_param(func, name):
            sig = inspect.signature(func)
            return name in sig.parameters
            
        all_files = list_all_scrapers()
        result = 'result to come'
        for file in all_files:
            try:
                a = file.find('/legis/generators/')+len('/legis/generators/')
                x = file[a:]
                words = x.split('/')
                txt = x.replace('/', '.').replace('.py','')
                if txt == region:
                    import importlib
                    scraperScripts = importlib.import_module('legis.generators.'+txt) 
                    approved_models = scraperScripts.approved_models
                    for f, models in approved_models.items():
                        if f == func:
                            prnt('RUNNING:', func, super, worker)
                            start_time = timezonify('est', datetime.datetime.now())
                            prnt('start_time',start_time)
                            cmd = getattr(scraperScripts, f)
                            from utils.cronjobs import clear_chrome
                            if super == 'Test' and worker == 'False':
                                if accepts_param(cmd, "as_rq"):
                                    result = cmd(special='testing', as_rq=False)
                                else:
                                    result = cmd(special='testing')
                                clear_chrome()
                            elif super == 'Test' and worker == 'True':
                                queue = django_rq.get_queue('low')
                                queue.enqueue(cmd, special='testing', job_timeout=scraperScripts.runTimes[f]*7)
                                queue = django_rq.get_queue('low')
                                queue.enqueue(clear_chrome, job_timeout=15)
                            elif super == 'Super' and worker == 'False':
                                if accepts_param(cmd, "as_rq"):
                                    result = cmd(special='super', as_rq=False)
                                else:
                                    result = cmd(special='super')
                                clear_chrome()
                            elif super == 'Super' and worker == 'True':
                                queue = django_rq.get_queue('low')
                                queue.enqueue(cmd, special='super', job_timeout=scraperScripts.runTimes[f]*7)
                                queue = django_rq.get_queue('low')
                                queue.enqueue(clear_chrome, job_timeout=15)
                            elif super == 'False' and worker == 'False':
                                if accepts_param(cmd, "as_rq"):
                                    result = cmd(as_rq=False)
                                else:
                                    result = cmd()
                                clear_chrome()
                            elif super == 'False' and worker == 'True':
                                queue = django_rq.get_queue('low')
                                queue.enqueue(cmd, job_timeout=scraperScripts.runTimes[f]*7)
                                queue = django_rq.get_queue('low')
                                queue.enqueue(clear_chrome, job_timeout=15)

                            prnt()
                            prnt('completed run')
                            end_time = timezonify('est', datetime.datetime.now())
                            prnt(end_time - start_time)
                            break
                    break
            except Exception as e:
                prnt('run_super_function_view fail', str(e))
                end_time = timezonify('est', datetime.datetime.now())
                return render(request, "utils/dummy.html", {"result": str(e) + ' - ' + str(end_time - start_time)})
        if not end_time:
            end_time = timezonify('est', datetime.datetime.now())
        return render(request, "utils/dummy.html", {"result": str(result) + ' - ' + str(end_time - start_time)})
    
def scrapers_view(request, region, test):
    if request.user and request.user.assess_super_status():
        prnt('-scrapers_view',region,test)
        all_files = list_all_scrapers()
        def get_models():
            from utils.utils import get_app_name
            m = []
            return reversed(m)
        scripts = {}
        for file in all_files:
            prnt('file',file)
            try:
                a = file.find('/legis/generators/')+len('/legis/generators/')
                x = file[a:]
                words = x.split('/')
                scraper_region = words[-2]
                if scraper_region == region:
                    prnt('found')
                    txt = x.replace('/', '.').replace('.py','')
                    scripts[txt] = []
                    import importlib
                    scraperScripts = importlib.import_module(txt) 
                    approved_models = scraperScripts.approved_models
                    for f, models in approved_models.items():
                        scripts[txt].append({txt:f})
            except Exception as e:
                prnt('scrapers_view err',str(e))
                pass
        return render(request, "utils/run_scrapers.html", {'scripts':scripts, 'region':region, 'test':test, 'models':get_models()})

def super_view(request):
    if request.user and request.user.assess_super_status(): # should have reduced options if superuser is not node operator
        from network.models import get_self_node
        self_node = get_self_node()
        if self_node:
            self_node_name = self_node.node_name
        else:
            self_node_name = 'node unknown'
        all_files = list_all_scrapers()
        regions = []
        for file in all_files:
            try:
                a = file.find('/regions/')+len('/regions/')
                x = file[a:]
                words = x.split('/')
                region = words[-2]
                regions.append(region)
            except Exception as e:
                prnt('super_view err',str(e))
                pass
        return render(request, "utils/super.html", {'utc':now_utc().strftime("%Y-%m-%d %H:%M:%S"), 'regions':regions, 'scripts':True, 'self_node_name':self_node_name, 'user':request.user})

def node_logs_view(request, logtype):
    if request.user and request.user.assess_super_status():
        from network.models import EventLog
        node = get_self_node()
        logs = EventLog.objects.filter(type__iexact=logtype, Node_obj=node).order_by('-created')
        return render(request, "utils/super.html", {'is_logs':True, 'logs':logs})
    
def show_log_view(request, iden):
    if iden.lower() in ['logbook', 'errors', 'tasks', 'requesteditems']:
        sorted_data = {}
        from network.models import EventLog
        log = EventLog.objects.filter(type__iexact=iden).first()
        if log:
            count = request.GET.get('count', 200)
            sorted_data = dict(sorted(log.data.items(), key=lambda item: item[1]))
            from itertools import islice
            sorted_data = "\n".join(f"{string_to_dt(key).strftime('%Y-%m-%d %H:%M')}: {value}" for key, value in islice(sorted_data.items(), count) )
        return JsonResponse({'message' : sorted_data})
    if request.user and request.user.assess_super_status():
        from network.models import EventLog
        log = EventLog.objects.filter(id=iden).first()
        if log:
            sorted_data = dict(
                sorted(
                    log.data.items(),
                    key=lambda item: string_to_dt(item[0]),
                    reverse=True
                )
            )
            return render(request, "utils/super.html", {'show_log':True, 'log':log, 'log_data':sorted_data})

@csrf_exempt
def workers_status_view(request):
    if get_client_ip(request) != '127.0.0.1':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    from django_rq import get_queue
    from rq.worker import Worker
    from utils.utils import self_is_active

    # prnt('self_is_active()1',self_is_active())
    # self_is_active(True)
    # prnt('self_is_active()2',self_is_active())
    # import os
    # import sys
    # prnt('pid', os.getpid(), 'mod', id(sys.modules[self_is_active.__module__]))

    workers = {
        'high':{'current':{},'queued':0},
        'main':{'current':{},'queued':0},
        'low':{'current':{},'queued':0},
        'chat':{'current':{},'queued':0},
        'super':{'current':{},'queued':0},
        'isActive': self_is_active()
        }
    # if not currently_running_only:
    for queue_name in workers:
        if queue_name != 'isActive':
            queue = get_queue(queue_name)
            conn = queue.connection
            # running
            for w in Worker.all(conn):
                if queue_name in [q.name for q in w.queues]:
                    job = w.get_current_job()
                    if job:
                        data = {}
                        if '.' in job.func_name:
                            x = job.func_name.rfind('.')+1
                            data["func"] = job.func_name[x:]
                        else:
                            data["func"] = job.func_name
                        data["args"] = ''
                        for a in job.args:
                            if a:
                                try:
                                    data["args"] = a.id
                                    break
                                except:
                                    pass
                        if not data["args"]:
                            data["args"] = dt_to_string(job.started_at) if job.started_at else '-'
                        workers[queue_name]['current'] = data
                    break
            job_ids = queue.job_ids
            for job_id in job_ids:
                job = queue.fetch_job(job_id)
                if job:
                    workers[queue_name]['queued'] += 1
    
    return JsonResponse(workers, safe=False)

def test_tasker_view(request):
    prnt('-test_tasker_view')
    if request.user and request.user.assess_super_status():
        from utils.models import tasker
        start_date = '%s-%s-%s-%s:00' %(2024, 11, 12, 10)
        start_date = '%s-%s-%s-%s:00' %(2024, 11, 23, 7)
        day = datetime.datetime.strptime(start_date, '%Y-%m-%d-%H:%M').astimezone(pytz.utc)  
        tasker(now_utc(), test=True)
        return JsonResponse({'message' : 'complete'})

def tidy_up_view(request):
    prnt('-tidy_up_view')
    if request.user and request.user.assess_super_status():
        from network.models import Tidy
        queue = django_rq.get_queue('low')
        queue.enqueue(Tidy()._add_all_jobs, all_jobs=True, job_timeout=60, result_ttl=60)
        return JsonResponse({'message' : 'running'})

def initial_setup_view(request):
    if request.user.is_superuser:
        from utils.utils import testing, debugging
        if testing() or debugging():
            earth = Region.objects.filter(nameType='Planet', Name='Earth').first()
            if not earth:
                earth = Region(created=now_utc(), func='super', nameType='Planet', Name='Earth', ImgLinks={"flag":"/static/img/earth_pic.jpg"})
                earth.save()
            na = Region.objects.filter(Name='North America', nameType='Continent', ParentRegion_obj=earth).first()
            if not na:
                na = Region(created=now_utc(), func='super', Name='North America', nameType='Continent', ParentRegion_obj=earth)
                na.save()
            usa = Region.objects.filter(Name='USA', nameType='Country', ParentRegion_obj=na).first()
            if not usa:
                usa = Region(is_supported=True, created=now_utc(), func='super', Name='USA', nameType='Country', ParentRegion_obj=na,  ImgLinks={"flag":"img/regions/usa/flag.jpg"})
                usa.save()
            from legis.models import Government
            gov = Government.objects.filter(Region_obj=usa).first()
            if not gov:
                gov = Government(Region_obj=usa, menuItem_array=['Bills', 'Debates', 'RollCalls', 'Officials'], Chamber_array=['Executive', 'House', 'Senate'])
                gov.save()
            can = Region.objects.filter(Name='Canada', nameType='Country', ParentRegion_obj=na).first()
            if not can:
                can = Region(is_supported=True, created=now_utc(), func='super', Name='Canada', nameType='Country',  ParentRegion_obj=na, ImgLinks={"flag":"img/regions/canada/flag.jpg"})
                can.save()
            gov = Government.objects.filter(Region_obj=can).first()
            if not gov:
                gov = Government(Region_obj=can, menuItem_array=['Bills', 'Debates', 'Motions', 'Officials'], Chamber_array=['House', 'Senate'])
                gov.save()
            node = Node.objects.filter(User_obj=request.user).first()
            if not node:
                node = Node(created=now_utc(), User_obj=request.user, activated_dt=now_utc(), address='127.0.0.1:3005', lastUpdate=now_utc())
                node.id = hash_obj_id(node)
                super(Node, node).save()
            for u in User.objects.all():
                u.boot()

            return JsonResponse({'message' : 'initial setup complete'})

def validate_test_data_view(request):
    if request.user.is_superuser:
        from utils.utils import testing, debugging
        prnt('-validate_test_data_view')
        if testing() or debugging():
            models = ['Region',
            'Update',
            'District',
            'Person',
            'Party',
            'Government',
            'RepVote',
            'Motion',
            'Committee',
            'Statement',
            'Meeting',
            'Bill',
            'Agenda',
            'Post',
            'Keyphrase',
            'KeyphraseTrend',
            'Election'
            ]
            for model in models:
                objs = get_dynamic_model(model, list=True)
                for obj in objs:
                    prnt('obj:',obj)
                    try:
                        if has_field(obj, 'boot'):
                            post = obj.boot()
                            if post:
                                post.validated = True
                                post.save()
                            if has_method(obj, 'upon_validation'):
                                obj.upon_validation()
                        elif obj._meta.object_name == 'Update':
                            obj.sync_with_post()
                        elif obj._meta.object_name == 'Post':
                            obj.validated = True
                            obj.save()
                    except Exception as e:
                        prnt('err',str(e))
                        time.sleep(2)

            return JsonResponse({'message' : 'complete'})
        return JsonResponse({'message' : 'is production'})

def resume_process_view(request, iden):
    prnt('-resume_process_view',iden)
    if request.user.assess_super_status():
        try:
            from network.models import EventLog
            log = EventLog.objects.filter(id=iden).first()
            if 'process' in log.type:
                func = log.type
                import importlib
                functions = importlib.import_module('network.models')
                cmd = getattr(functions, func)
                cmd(log.id)
            else:
                from utils.models import finishScript, list_all_scrapers
                all_files = list_all_scrapers()
                region = log.data['region_name'].lower()
                func = log.data['func']
                prnt('func',func)
                special = log.data['special']
                prnt('special',special)
                for file in all_files:
                    a = file.find('/regions/')+len('/regions/')
                    x = file[a:]
                    words = x.split('/')
                    txt = x.replace('/', '.').replace('.py','')
                    if region in txt:
                        import importlib
                        scraperScripts = importlib.import_module('regions.'+txt) 
                        approved_models = scraperScripts.approved_models
                        for f, models in approved_models.items():
                            if f == func:
                                finishScript(log, func=func, special=special)
            return JsonResponse({'message' : 'it is done'})
        except Exception as e:
            prnt('resume_process_view fail',str(e))
            return JsonResponse({'message' : 'fail', 'error':str(e)})

def resume_processes_view(request):
    if request.user.assess_super_status():
        from network.models import EventLog
        processes = EventLog.objects.filter(Q(type__icontains='process')|Q(type__icontains='scrape assignment'))
        data = {b:{'id':b.id,'type':b.type,'dt':b.created} for b in processes}
        self_node = get_self_node()
        return render(request, "utils/super.html", {'show_processes':True, 'data':data, 'self_node_name': self_node.node_name if self_node else 'node unknown'})

def invalidate_test_blocks_view(request):
    if request.user.assess_super_status():
        from utils.utils import testing, debugging
        if testing() or debugging():
            prnt('-invalidate_test_blocks_view')
            from network.models import Block
            noneBlocks = Block.objects.filter(validated=None).distinct('Blockchain_obj_id').order_by('Blockchain_obj_id','-index', '-created')[:50]
            failBlocks = Block.objects.filter(validated=False).distinct('Blockchain_obj_id').order_by('Blockchain_obj_id','-index', '-created')[:50]
            passBlocks = Block.objects.filter(validated=True).distinct('Blockchain_obj_id').order_by('Blockchain_obj_id','-index', '-created')[:50]
            prnt('passBlocks',passBlocks)
            noneBlockData = {b.Blockchain_obj:{'id':b.id,'index':b.index,'created':b.created} for b in noneBlocks}
            failBlockData = {b.Blockchain_obj:{'id':b.id,'index':b.index,'created':b.created} for b in failBlocks}
            passBlockData = {b.Blockchain_obj:{'id':b.id,'index':b.index,'created':b.created} for b in passBlocks}
            prnt('passBlockData',passBlockData)
            self_node = get_self_node()
            return render(request, "utils/super.html", {'show_blocks':True, 'noneBlockData':noneBlockData, 'failBlockData':failBlockData, 'passBlockData':passBlockData, 'self_node_name': self_node.node_name if self_node else 'node unknown'})

def make_not_valid_view(request, iden):
    prntDebug('-make_not_valid_view',iden)
    if request.user.assess_super_status():
        from utils.utils import testing, debugging
        if testing() or debugging():
            from network.models import Block
            block = Block.objects.filter(id=iden).first()
            if block:
                if testing():
                    block.is_not_valid()
                else:
                    queue = django_rq.get_queue('low')
                    queue.enqueue(block.is_not_valid, job_timeout=500)
                return JsonResponse({'message' : 'it is done'})
            return JsonResponse({'message' : 'block not found'})
        
def make_valid_unknown_view(request, iden):
    prntDebug('-make_valid_unknown_view')
    if request.user.assess_super_status():
        from utils.utils import testing, debugging
        if testing() or debugging():
            from network.models import Block
            block = Block.objects.filter(id=iden).first()
            if block:
                block.validated = None
                super(Block, block).save()
                return JsonResponse({'message' : 'it is done'})
            return JsonResponse({'message' : 'block not found'})
        
@csrf_exempt
def remove_false_blocks_view(request):
    prnt('-remove_false_blocks_view')
    if request.method == 'POST':
        if assess_received_header(request.headers, return_is_self=True):
            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)
            try:
                userData = json.loads(received_data.get('userData'))
            except Exception as e:
                prnt('err 1',str(e))
            nodeData = json.loads(received_data.get('nodeData'))
            try:
                requested_data = json.loads(received_data.get('request'))
                prntDebug('requested_data',requested_data)
            except Exception as e:
                prnt('err 21a',str(e))
            if 'signed' in requested_data:
                sig = requested_data['signed']
                del requested_data['signed']
                from network.models import Blockchain, Block
                self_node = get_self_node()
                if self_node and self_node.User_obj and self_node.User_obj.verify_sig(requested_data, sig, simple_verify=True):
                    if 'chainId' in requested_data:
                        chainId = requested_data['chainId']
                        prnt('chainId',chainId)
                        if chainId == 'all':
                            for b in Block.objects.filter(validated=False):
                                b.delete()
                        elif chainId:
                            chain = Blockchain.objects.filter(id=chainId).first()
                            for b in Block.objects.filter(Blockchain_obj=chain, validated=False):
                                b.delete()

                    return JsonResponse({'message' : 'Success'})
        return JsonResponse({'message' : 'Failure'})
        
def create_test_blocks_view(request):
    if request.user.assess_super_status():
        from utils.utils import testing, debugging, baseline_time
        if testing() or debugging():
            from network.models import _OperationsChain_genesisId, Block, Blockchain
            nodechain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
            if not nodechain:
                nodechain = Blockchain(genesisId=_OperationsChain_genesisId, genesisType=_OperationsChain_genesisId, genesisName=_OperationsChain_genesisId, created=baseline_time(), last_block_datetime=now_utc()-datetime.timedelta(days=2))
            nodechain.last_block_datetime=now_utc()-datetime.timedelta(days=2)
            nodechain.save()
            for node in Node.objects.all():
                nodechain.add_item_to_queue(node)
            chains = Blockchain.objects.all().order_by('genesisType','genesisName')
            chainData = {str(c).replace('chain:',''):{'length':c.chain_length,'id':c.id,'queue':len(c.queuedData)} for c in chains}
            unValBlocks = Block.objects.filter(validated=None)
            blockData = {b.Blockchain_obj:{'id':b.id} for b in unValBlocks}
            self_node = get_self_node()
            return render(request, "utils/super.html", {'show_chains':True, 'chainData':chainData, 'blockData':blockData, 'self_node_name': self_node.node_name if self_node else 'node unknown'})

def create_test_block_view(request, name):
    if request.user.assess_super_status():
        from utils.utils import testing, debugging
        if testing() or debugging():
            from network.models import Blockchain
            chain = Blockchain.objects.filter(id=name).first()
            if testing():
                result = chain.new_block_candidate(add_to_queue=False)
            else:
                result = 'running'
                queue = django_rq.get_queue('low')
                queue.enqueue(chain.new_block_candidate, job_timeout=500)
            return render(request, "utils/dummy.html", {"result": str(result)})

def check_validation_consensus_view(request, iden):
    if request.user.assess_super_status():
        is_valid = 'unknown'
        from network.models import Block
        from utils.locked import check_validation_consensus
        from utils.utils import testing, debugging
        block = Block.objects.filter(id=iden).first()
        if block: 
            if testing():
                is_valid, consensus_found, validations = check_validation_consensus(block, broadcast_if_unknown=False)
            else:
                queue = django_rq.get_queue('low')
                queue.enqueue(check_validation_consensus, block, broadcast_if_unknown=False, job_timeout=500)
        return render(request, "utils/dummy.html", {"result": str(is_valid)})
    
def get_assignment_view(request, iden):
    if request.user.assess_super_status():
        prnt('-get_assignment_view',iden)
        if str(iden) == '0':
            return render(request, "utils/dummy.html", {"result": str(0)})
        obj = get_dynamic_model(get_pointer_type(iden), id=iden)
        if obj:
            def convert(field):
                if not isinstance(field, str):
                    field = str(field)
                if 'false' in field.lower():
                    return False
                elif 'true' in field.lower():
                    return True
                elif 'none' in field.lower():
                    return None
                return field
            dt = convert(request.GET.get('dt', None))
            func = convert(request.GET.get('func', None))
            chainId = convert(request.GET.get('chainId', None))
            return_receiverTransaction = convert(request.GET.get('return_receiverTransaction', False))
            full_validator_list = convert(request.GET.get('full_validator_list', False))
            prnt('dt',dt,'func',func,'chainId',chainId,'scrapers_only','scrapers_only','return_receiverTransaction',return_receiverTransaction,'full_validator_list',full_validator_list,'strings_only','strings_only')
            from utils.locked import get_node_assignment
            return render(request, "utils/dummy.html", {"result": str(get_node_assignment(obj, dt=dt, func=func, chainId=chainId, return_receiverTransaction=return_receiverTransaction, full_validator_list=full_validator_list))})
        return render(request, "utils/dummy.html", {"result": str(obj)})
    
def get_model_fields_view(request):
    # if request.user and request.user.assess_super_status():
    from utils.utils import get_model_fields
    get_model_fields()
    return render(request, "utils/dummy.html", {"result": 'done'})

def supersign_view(request, iden):
    if request.user.assess_super_status():
        try:
            from accounts.models import SuperSign
            from accounts.forms import SuperSignForm
            from utils.models import get_operatorData, share_with_network
            operatorData = get_operatorData()
            if operatorData['userData']['id'] == request.user.id:
                if request.method == 'POST':
                    form = SuperSignForm(request.POST)
                    if form.is_valid():
                        form.Super_User_obj = request.user
                        form.save()
                        from utils.locked import sign_obj
                        form = sign_obj(form)
                        share_with_network(form)
                        return JsonResponse({'message': 'Form submitted successfully'})
                    else:
                        return JsonResponse({'errors': form.errors}, status=400)
                else:
                    obj = None
                    if iden:
                        obj = get_dynamic_model(iden, id=iden)
                    if obj:
                        ss = SuperSign.objects.filter(pointerId=obj.id).first()
                        if ss:
                            superForm = SuperSignForm(instance=ss)
                        else:
                            superForm = SuperSignForm(pointerId=obj.id)
                    else:
                        superForm = SuperSignForm()
                    try:
                        operator = get_self_node().User_obj.username
                    except:
                        operator = 'None'
                    context = {
                    'nodeOperator': operator,
                    'superForm': superForm,
                }
                return render(request, "forms/superform.html", context)
        except Exception as e:
            return JsonResponse({'message' : 'invalid', 'err':str(e)})

def remove_target_test_data_confirm_view(request, region, model):
    if request.user.assess_super_status():
        from utils.utils import testing, debugging
        if testing() or debugging():
            try:
                from network.models import Block
                if region.lower() == 'all':
                    if '_' in model:
                        if model == 'Block_unvalidated':
                            objs = Block.objects.exclude(validated=True)
                    return render(request, "utils/super.html", {'confirm':True, 'region':region, 'model':model, 'count':len(objs)})
                else:
                    country_obj = Region.supported_objects.filter(Name__iexact=region, modelType='country').first()
                    if '_' in model:
                        if model == 'Block_unvalidated':
                            objs = Block.objects.filter(Blockchain_obj__genesisId=country_obj.id).exclude(validated=True)
                    else:
                        objs = get_dynamic_model(model, list=True, Region_obj=country_obj)
                    return render(request, "utils/super.html", {'confirm':True, 'region':region, 'model':model, 'count':len(objs)})
            except Exception as e:
                return JsonResponse({'message' : f'error:{str(e)}'})
    
def remove_target_test_data_view(request, region, model):
    if request.user.assess_super_status() and False:
        from utils.utils import testing, debugging
        if testing() or debugging():
            prnt('get model:', model, region)
            try:
                if region.lower() == 'all':
                    if '_' in model:
                        if model == 'Block_unvalidated':
                            from network.models import Block, Validator
                            objs = Block.objects.exclude(validated=True)
                            for obj in objs:
                                prnt(obj)
                                for v in Validator.objects.filter(data__has_key=obj.id):
                                    prnt('v',v)
                                    v.delete(superDel=True)
                                obj.delete(superDel=True)
                else:
                    country_obj = Region.supported_objects.filter(Name__iexact=region, modelType='country').first()
                    if '_' in model:
                        if model == 'Block_unvalidated':
                            from network.models import Block, Validator
                            objs = Block.objects.filter(Blockchain_obj__genesisId=country_obj.id).exclude(validated=True)
                            for obj in objs:
                                prnt(obj)
                                for v in Validator.objects.filter(data__has_key=obj.id):
                                    prnt('v',v)
                                    v.delete()
                                obj.delete()
                    else:
                        objs = get_dynamic_model(model, list=True, Region_obj=country_obj)
                        for obj in objs:
                            prnt(obj)
                            obj.delete()
                return JsonResponse({'message' : 'complete'})
            except Exception as e:
                return JsonResponse({'message' : f'error:{str(e)}'})

def clear_test_data_view(request):
    if request.user.assess_super_status():
        from utils.utils import testing, debugging, get_model
        if testing() or debugging():
            from django.apps import apps
            models = [
            'Update',
            'Party',
            'Government',
            'RepVote',
            'Motion',
            'Committee',
            'Statement',
            'Meeting',
            'Bill',
            'BillText',
            'Action',
            'Agenda',
            'Post',
            'Keyphrase',
            'KeyphraseTrend',
            'Election',
            'District',
            'Person',
            ]
            for m in models:
                prnt('get model:', m)
                # try:
                #     m = apps.get_model('legis', m)
                # except:
                #     pass
    
                objs = get_dynamic_model(m, list=True)
                for obj in objs:
                    try:
                        # super(m, obj).delete()
                        super(get_model(obj._meta.object_name), obj).delete()
                    except Exception as e:
                        prnt('err x',str(e))
            prnt('done')
            return JsonResponse({'message' : 'complete'})
        return JsonResponse({'message' : 'is production'})


def tester_queue(obj=None):
    prnt('---tester_queue')
    result = {'start':'a'}

    from selenium import webdriver 
    from selenium.webdriver.common.by import By 
    from selenium.webdriver.support.ui import WebDriverWait 
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.keys import Keys
    from bs4 import BeautifulSoup


    import django_rq
    import requests
    # queue = django_rq.get_queue('low')
    import xml.etree.ElementTree as ET

    from network.models import Blockchain, Block, DataPacket, Plugin, _EarthChain_genesisId
    from utils.locked import verify_data, sign_obj, get_relevant_nodes, validate_obj
    from utils.models import open_browser, close_browser
    from transactions.models import Wallet, Tx
    from accounts.models import UserPubKey, User
    from posts.models import Post, Update, Spren, ImageFile
    from legis.models import  BillText, District, RepVote, Motion, Bill
    from posts.models import Region
    from utils.utils import superDelete, get_model_prefix, get_self_node, round_time, sigData_to_hash
    # # operatorData = get_operatorData()
    self_node = get_self_node()
    self_node_id = self_node.id
    # self_node_id = get_operator_obj("self_nodeId")

    # driver = open_browser('https://www.ourcommons.ca/PublicationSearch/en/?View=D&Item=&ParlSes=&oob=&Topic=&Proc=&Per=&Prov=&Cauc=&Text=&RPP=15&order=&targetLang=&SBS=0&MRR=150000&PubType=37&xml=1')
    # prnt('loaded')
    # time.sleep(10)
    # xml_container = driver.find_element(By.ID, 'webkit-xml-viewer-source-xml')
    # xml_text = xml_container.get_attribute('innerHTML')
    # close_browser(driver)
    # root = ET.fromstring(xml_text)
    # prnt('root',root)
    # for p in Bill.objects.all():
    #     # p.delete(force_delete=True)
    #     superDelete(p, force_delete=True)
    #     u = Update.objects.filter(pointerId=p.id)
    #     if u:
    #         u.delete(force_delete=True)
    # for p in BillText.objects.all():
    #     p.delete(force_delete=True)

    # for u in RepVote.objects.all():
    #     u.delete(force_delete=True)
        
    # for d in Motion.objects.all():
    #     # d.delete()
    #     superDelete(d, force_delete=True)
    
    # for u in Update.objects.filter():
    #     u.delete(force_delete=True)


    # for d in Party.objects.all():
    #     superDelete(d, force_delete=True)

    # for p in Post.objects.exclude(pointerType='Government'):
    #     super(Post, p).delete()
    # for u in Update.objects.filter(validated=False):
    #     validate_obj(obj=u, pointer=None, save_obj=True, verify_validator=False, update_pointer=True)

    # iden = 'updSo1IDBHpent6BbX7O4Eya'
    # u = Update.objects.filter(id=iden).first()
    # # v = validate_obj(obj=u, pointer=None, save_obj=False, verify_validator=False, update_pointer=False)
    # # prnt('v',v)

    # plugin_id = Plugin.objects.filter(app_name='legis').values('id').first()['id']

    # masterData = get_relevant_nodes(dt=u.created, blockchain=u.networkChain, plugin_id=plugin_id, sublist='maintainer')
    # prnt('masterData',masterData)


    # prompt = f'hello'
    # r = run_prompt(prompt)
    # prnt('r',r)


    def block_run(input_block):
        result = {}
        if not input_block.Tx_obj.SenderWallet_obj: # reward transactions
            prnt('input_block.Tx_obj',input_block.Tx_obj)
            carry_on = False
            if 'BlockReward' in input_block.Tx_obj.re and input_block.Tx_obj.re['BlockReward'] == input_block.id:
                # return_receiverTransaction = False
                carry_on = True
                if not opBlock_data:
                    opBlock_data = get_relevant_nodes(obj=input_block, blockchain=get_chain_id(input_block.Tx_obj.networkChain), plugin_id=get_plugin(input_block.networkChain, id=True))
                creator_nodes, validator_nodes = get_node_assignment(input_block, full_validator_list=True, opBlock_data=opBlock_data)
                result['s1'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}
            elif input_block.Tx_obj.ReceiverWallet_obj and input_block.Tx_obj.ReceiverWallet_obj.id == input_block.Blockchain_obj.genesisId:
                # return_receiverTransaction = True
                carry_on = True
                # if not opBlock_data:
                #     opBlock_data = get_relevant_nodes(dt=dt, genesisId=plugin_id, sublist='maintainer', strings_only=True, include_relays=False)
                creator_nodes, validator_nodes = get_node_assignment(input_block, chainId=input_block.Tx_obj.receiverNetworkChain, full_validator_list=True, opBlock_data=opBlock_data)
                result['s2'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}
            if carry_on:
                # creator_nodes, validator_nodes = get_node_assignment(self, return_receiverTransaction=return_receiverTransaction, full_validator_list=True, opBlock_data=opBlock_data)
                if fetch_broadcast_list:
                    broadcast_list = get_broadcast_list(input_block, relevant_nodes=opBlock_data['relevant_nodes'], peer_count=_number_of_peers, seed_nodes=creator_nodes, important_nodes=validator_nodes, loop=loop)
                # return creator_nodes, validator_nodes, broadcast_list
            else:
                input_block.is_not_valid(note='transaction_err2')
                prntDebug('px transaction_err2',input_block.id)
                # return [], [], {}
        else:
            # peer to peer transactions - will need work
            if not opBlock_data:
                opBlock_data = get_relevant_nodes(obj=input_block, genesisId=input_block.Blockchain_obj.genesisId)
            if input_block.Tx_obj.ReceiverWallet_obj == input_block.Blockchain_obj:
                # transaction_type = 'sender'
                creator_nodes, validator_nodes = get_node_assignment(input_block, chainId=input_block.Tx_obj.receiverNetworkChain, full_validator_list=True, opBlock_data=opBlock_data)
                result['s3'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}
                if fetch_broadcast_list:
                    broadcast_list = get_broadcast_list(input_block.Tx_obj, relevant_nodes=opBlock_data['relevant_nodes'], peer_count=_number_of_peers, seed_nodes=creator_nodes, important_nodes=validator_nodes, loop=loop)
                # return creator_nodes, validator_nodes, broadcast_list
            elif input_block.Tx_obj.SenderWallet_obj == input_block.Blockchain_obj:
                # transaction_type = 'receiver'
                creator_nodes, validator_nodes = get_node_assignment(input_block.Tx_obj, full_validator_list=True, opBlock_data=opBlock_data)
                if fetch_broadcast_list:
                    broadcast_list = get_broadcast_list(input_block.Tx_obj, relevant_nodes=opBlock_data['relevant_nodes'], peer_count=_number_of_peers, seed_nodes=creator_nodes, important_nodes=validator_nodes, loop=loop)
                # return creator_nodes, validator_nodes, broadcast_list
                result['s4'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}





        self = input_block.Tx_obj
        prnt('create receiverBlock tx')
        prnt('no ReceiverBlock 1')
        now = round_time(now_utc(), amount='10mins')
        creator_nodeId_list, validator_list = get_node_assignment(self, dt=now, chainId=self.receiverNetworkChain)
        prnt('creator_nodeId_list, validator_list',creator_nodeId_list, validator_list,'self_node.id',self_node.id)
        # receiverChain = self.ReceiverWallet_obj.get_chain()
        result['s5'] = {'creator_nodes':creator_nodeId_list,'validator_nodes':validator_list}



        self_node_id = get_operator_obj("self_nodeId")
        if self_node_id in selected_nodes:
            now = round_time(now_utc(), amount='10mins')
            creator_nodeId_list, validator_list = get_node_assignment(self, dt=now, chainId=self.receiverNetworkChain)
            from network.models import DataPacket, Node
            result['s6'] = {'creator_nodes':creator_nodeId_list,'validator_nodes':validator_list}







        block = input_block
        if block.Tx_obj:
            if transaction_type == 'sender':
                creator_nodes, validator_nodes = get_node_assignment(block.Tx_obj, opBlock_data=opBlock_data)
                result['s7'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}
            elif transaction_type == 'receiver':
                creator_nodes, validator_nodes = get_node_assignment(block, chainId=block.Tx_obj.receiverNetworkChain, opBlock_data=opBlock_data)
                result['s8'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}
            # else:
            #     creator_nodes, validator_nodes = get_node_assignment(block, opBlock_data=opBlock_data)
        else:
            creator_nodes, validator_nodes = get_node_assignment(block, opBlock_data=opBlock_data)
            result['s9'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}






                        
        prnt('create block')
        creator_nodes, validator_nodes = get_node_assignment(input_block)
        result['s10'] = {'creator_nodes':creator_nodes,'validator_nodes':validator_nodes}






        # prnt('rebroadcast_block')
        # new_block = None
        # for block in current_blocks:
        #     block_dt = block.DateTime
        #     opBlock_data = get_relevant_nodes(dt=(block.DateTime-datetime.timedelta(minutes=20)), genesisId=block.Blockchain_obj.genesisId, include_relays=True)
        #     creator_nodes, validator_nodes = get_node_assignment(block, opBlock_data=opBlock_data, full_creator_list=True)
        #     prnt('creator_nodes':creator_nodes)
        #     new_index = 1




        # prnt('dp.headers',dp.headers)
        # if 'Validators-Only' in dp.headers and dp.headers['Validators-Only'] == 'True':
        #     prnt('validators only')
        #     opBlock_data = get_relevant_nodes(dt=string_to_dt(dp.headers['Dt']), blockchain=dp.headers['Blockchainid'], strings_only=True, first_block_override=True)

        #     creator_nodes, validator_list = get_node_assignment(func=dp.headers['Packet-Id'],dt=string_to_dt(dp.headers['Dt']), chainId=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], opBlock_data=opBlock_data)
        #     broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], relevant_nodes=validator_list, loop=True, all_nodes=False, dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], plugin_id=dp.headers['Pluginid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays, opBlock_data=opBlock_data)
        # else:
        #     prnt('not validators only')
        #     broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], plugin_id=dp.headers['Pluginid'], include_relays=include_relays)
        # downstream_broadcast(broadcast_list, 'network/receive_blocks', received_json, headers=dp.headers, skip_self=True)
        # dp.rebroadcast_dt = now_utc()
        return result

    # bid = 'blcSo5E4X1jRnOXGTrrmvpBa'
    # b = Block.objects.filter(id=bid).first()
    # r = block_run(b)
    # result['gov1'] = r
    # bid = 'blcSo9eePhanpZIDH5Zc8qA5'
    # b = Block.objects.filter(id=bid).first()
    # r = block_run(b)
    # result['rew1'] = r
    # bid = 'blcSo40XMb0ZVreZwtXC4eq1'
    # b = Block.objects.filter(id=bid).first()
    # r = block_run(b)
    # result['ca1'] = r
    # bid = 'blcSo4KQQvaZXdMXJwcPiMwc'
    # b = Block.objects.filter(id=bid).first()
    # r = block_run(b)
    # result['ac1'] = r
    # bid = 'blcSon11GxFLYbs9wToOePTo'
    # b = Block.objects.filter(id=bid).first()
    # r = block_run(b)
    # result['son1'] = r
    # # r = block_run(block)
    # prnt()
    # prnt()

    # for r in result:
    #     prnt()
    #     prnt(r)
    #     prnt(result[r])
    # from utils.utils import get_plugin
    # from network.models import selectableChains
    # genesis_obj = get_dynamic_model('1walSomun8c2BnloWBKQNNTZa', id='1walSomun8c2BnloWBKQNNTZa')
    # x = get_plugin(genesis_obj, name=True)
    # prnt('x',x)
    # if x not in selectableChains:
    #     prnt('A')
    # else:
    #     prnt('B')
    

    # Tidy().unvalidator_run()
    # iden = 'sprSocmfhO3RHsdJCi4m5jjd'
    # s = Spren.objects.filter(id=iden).first()
    # prnt('s',s)
    # from legis.utils import summarize_bill
    # btext = BillText.objects.filter(id='1btxtSooT8iRgEkmlE2u2nGh2i').first()
    # s1 = summarize_bill(btext, test_run=True)
    # s2 = summarize_bill(btext, test_run=True)
    # s3 = summarize_bill(btext, test_run=True)
    # s4 = summarize_bill(btext, test_run=True)
    # s5 = summarize_bill(btext, test_run=True)
    # prnt('s1',s1.data)

    # dicts = [s1.data, s2.data, s3.data, s4.data, s5.data]
    
    # from itertools import combinations

    # prnt([(i, j) for (i, a), (j, b) in combinations(enumerate(dicts), 2) if a == b])


    d = {'bullets': {'init': {'code': '0', 'data': "- Bill introduced to improve mental health services at the Department of Veterans Affairs.\n- The bill was read twice and referred to the Committee on Veterans' Affairs."}, '\n SECTION 1.  Short title; table of contents.\n': {'code': '1807779', 'data': '- The Act is titled the "Building Resources and Access for Veterans\' Mental Health Engagement Act of 2025" or the "BRAVE Act of 2025."\n- It includes sections on workforce improvement, Vet Center infrastructure and technology, women veterans, other matters, and a title specifically focused on workforce improvement.\n- The workforce improvement section covers reports on market pay surveys, qualifications for appointees, coordination between the Veterans Health Administration and Readjustment Counseling Service, and more.'}, '\n SEC. 101.  Report on market pay surveys for Readjustment Counseling Service positions.\n': {'code': '3564507', 'data': '- Congress mandates the Secretary of Veterans Affairs to review market pay surveys for VA employees.\n- The report must assess pay disparities and identify staffing challenges within each district.\n- Reports must cover diverse geographic areas, including rural and urban settings.\n- Pay assessments should consider third-party data, location, qualifications, and incentives.'}, '\n SEC. 102.  Qualifications of appointees in occupations that support mental health programs.\n': {'code': '5524412', 'data': '- Section 7402(b)(8)(C) of the United States Code is modified to remove the restriction on the duration of a period and replace it with "for a reasonable period of time recommended by the Under Secretary for Health."\n- Section 7402(b)(11)(B) of the United States Code is amended to allow the Secretary to waive the requirement of licensure or certification for an individual licensed professional mental health counselor, provided that this waiver is for a reasonable period of time recommended by the Under Secretary for Health.'}, '\n SEC. 103.  Report on coordination of Veterans Health Administration with Readjustment Counseling Service.\n': {'code': '0274743', 'data': '- The Secretary of Veterans Affairs must submit a report within 60 days regarding coordination between the Veterans Health Administration and the Readjustment Counseling Service.\n- The report should assess each Director\'s adherence to policies ensuring support facilities are aligned with Vet Centers for better service, especially for veterans at high risk for suicide.\n- The report must include an analysis of various aspects including staff contact information updates, professional consultations, documentation of these consultations, and coordination with active duty members in the Transition Assistance Program.\n- "Vet Center" is defined as per section 1712A(h) of title 38, United States Code.'}, '\n SEC. 201.  Vet Center defined.\n': {'code': '9941820', 'data': '- "Vet Center" refers to a specific type of facility as defined in section 1712A(h) of title 38, United States Code.'}, '\n SEC. 202. Comptroller General report on Readjustment Counseling Service model for expansion of Vet Center footprint.\n': {'code': '5054748', 'data': "- The Comptroller General of the United States is required to submit a report within one year after the Act's enactment.\n- The report should evaluate the Department of Veterans Affairs' model for expanding Vet Center real property footprint.\n- Key aspects of the evaluation include demand in rural areas, frequency of reassessment, needs of veterans with high crisis line activity or suicides, mobile Vet Center trends, and unique needs of veterans in assessed areas."}, '\n SEC. 203.  Improvement of guidance and information to improve veteran outreach efforts by Vet Centers.\n': {'code': '1445696', 'data': '- The Secretary of Veterans Affairs must ensure Vet Centers have demographic data for eligible individuals to tailor outreach activities.\n- Guidance on assessing the effectiveness of outreach activities, including metrics and targets, will be provided to Vet Centers.\n- A process will be developed to assess barriers veterans and Armed Forces members face in obtaining services from Vet Centers.\n- A process will also be implemented to evaluate staff barriers in providing services.'}, '\n SEC. 204.  Report on information technology system of Readjustment Counseling Service.\n': {'code': '0474480', 'data': '- The Secretary of Veterans Affairs must submit a report within 60 days.\n- The report should identify whether the Department is retaining or replacing RCSNet.\n- If retaining RCSNet, provide rationale and steps to maintain or improve functionality with a timeline.\n- If replacing RCSNet, provide rationale, implementation steps including timeline and estimated cost.'}, '\n SEC. 301.  Study on effectiveness of suicide prevention and mental health outreach programs of Department of Veterans Affairs for women veterans.\n': {'code': '5580769', 'data': "- The Secretary of Veterans Affairs is tasked with conducting surveys and hosting listening sessions within 240 days of the Act's enactment to assess women veterans' perceptions of VA resources.\n- Surveys will evaluate effectiveness, tailoring, integration of military sexual trauma information, potential improvements, and demographic targeting.\n- Sessions must cover urban and rural areas, ensuring representation from various demographics.\n- A report detailing findings and intended steps for refining resources based on feedback is due within one year."}, '\n SEC. 302.  Requirement for Department of Veterans Affairs to modify the REACH VET program to incorporate risk factors weighted for women veterans.\n': {'code': '1210240', 'data': '- The Secretary of Veterans Affairs has 60 days to modify the REACH VET program.\n- The modifications should incorporate risk factors weighted for women.\n- These factors include military sexual trauma and intimate partner violence.'}, '\n SEC. 303.  Review of and report on reintegration and readjustment services for veterans and family members in group retreat settings.\n': {'code': '4045707', 'data': "- The Secretary of Veterans Affairs is required to review requests for reintegration and readjustment services for veterans and their family members in group retreat program settings.\n- The review should focus on determining if current retreat programming meets demand, specifically for women-only retreats, disabled access retreats, particularly wheelchair accessible retreats, and retreats for veterans with specific medical needs.\n- Not later than 120 days after the enactment of this Act, the Secretary must submit a report to the Senate and House Veterans' Affairs Committees on whether the provision of reintegration and readjustment services should be increased and made permanent."}, '\n SEC. 401.  Extension of Staff Sergeant Parker Gordon Fox Suicide Prevention Grant Program.\n': {'code': '3561791', 'data': '- Section 201 of the Commander John Scott Hannon Veterans Mental Health Care Improvement Act of 2019 is amended.\n- Subsection (c)(2)(A) has its funding increased from $750,000 to $1,000,000.\n- Subsection (j) extends the duration from three years to six years.'}, '\n SEC. 402.  Access to mental health residential rehabilitation treatment programs for veterans with spinal cord injury or disorder.\n': {'code': '6060502', 'data': "- The Secretary of Veterans Affairs is required to submit a plan within 60 days of the Act's enactment, detailing access to mental health residential treatment programs for veterans with spinal cord injuries or disorders.\n- The plan must include staffing plans, medical equipment needs assessment, and location assessments.\n- A pilot program begins within 120 days, providing mental health residential treatment at least three Department facilities.\n- A report on the plan implementation, pilot program results, and expansion plans is due one year after enactment."}, '\n SEC. 403.  Mental health consultations and outreach on mental health services for veterans receiving compensation for disabilities relating to mental health diagnoses.\n': {'code': '7726960', 'data': '- **Section Redesignation and Table Update**: Section 1167 of Title 38, United States Code, is redesignated as section 1169. The table of sections at the beginning of chapter 11 is updated by removing the old item for section 1167 and adding a new item for section 1169.\n\n- **Subsection Modifications**: Section 1169 is further modified:\n  - Subsection (a) is renamed to "Initial mental health consultations."\n  - Subsections (b) and (c) are redesignated as (c) and (d), respectively.\n  - A new subsection (b) is added, detailing annual mental health consultations and outreach.\n  - Subsection (c) is modified by inserting "or (b)" after "under subsection (a)" both places it appears.\n  - Subsection (d) is modified by inserting "or as requiring reevaluation of any entitlement of the veteran to compensation under this chapter" before the period at the end.\n\n- **Biennial Reports**: Section 1169 is further amended by adding a new subsection (e):\n  - The Secretary must conduct biennial reviews and reports on outreach effectiveness and mental health services.\n  - Reviews should cover feedback, consultations sought, and factors deterring veterans from seeking consultations.\n  - The Secretary must ensure veterans can provide feedback and analyze it for future improvements.'}, '\n SEC. 404.  Joint report on effectiveness of programs of Department of Veterans Affairs and Department of Defense that promote access to mental health services for transitioning members of the Armed Forces.\n': {'code': '4944600', 'data': "- The Secretary of Veterans Affairs and the Secretary of Defense must jointly submit a report within 180 days after the Act's enactment.\n- The report should detail actions taken or planned to improve mental health services for transitioning military members.\n- It must assess the response to recommendations from the Comptroller General in July 2024.\n- The report should identify any duplicative efforts or gaps and recommend changes, including legislative action if necessary."}}, 'status': 'The bill aims to improve mental health services for the Department of Veterans Affairs by enhancing workforce qualifications, expanding Vet Center infrastructure and technology, addressing specific needs of women veterans, ensuring access to specialized treatment programs, and promoting coordination between VA and DoD mental health resources.'}
    l = {'bullets': {'init': {'code': '0', 'data': "- Bill introduced to improve mental health services at the Department of Veterans Affairs.\n- The bill was read twice and referred to the Committee on Veterans' Affairs."}, '\n SECTION 1.  Short title; table of contents.\n': {'code': '1807779', 'data': '- The Act is titled the "Building Resources and Access for Veterans\' Mental Health Engagement Act of 2025" or the "BRAVE Act of 2025."\n- It includes sections on workforce improvement, Vet Center infrastructure and technology, women veterans, other matters, and a title specifically focusing on workforce improvement.\n- Key points include reports on market pay surveys, qualifications for mental health support roles, coordination between agencies, guidance for veteran outreach, IT system improvements, studies on suicide prevention programs for women veterans, modifications to the REACH VET program, reviews of reintegration services, grants for suicide prevention, access to residential rehabilitation, mental health consultations, and joint reports on mental health service effectiveness.'}, '\n SEC. 101.  Report on market pay surveys for Readjustment Counseling Service positions.\n': {'code': '3564507', 'data': '- Congress mandates the Secretary of Veterans Affairs to review market pay surveys for VA employees.\n- The report must assess pay disparities and identify staffing challenges within each district.\n- Reports must cover diverse geographic areas, including rural and urban settings.\n- Pay assessments should consider third-party data, location, qualifications, and incentives.'}, '\n SEC. 102.  Qualifications of appointees in occupations that support mental health programs.\n': {'code': '5524412', 'data': '- Section 7402(b)(8)(C) of the United States Code is modified to remove the restriction on the duration of a period and replace it with "for a reasonable period of time recommended by the Under Secretary for Health."\n- Section 7402(b)(11)(B) of the United States Code is amended to allow the Secretary to waive the requirement of licensure or certification for an individual licensed professional mental health counselor, provided that this waiver is for a reasonable period of time recommended by the Under Secretary for Health.'}, '\n SEC. 103.  Report on coordination of Veterans Health Administration with Readjustment Counseling Service.\n': {'code': '0274743', 'data': '- The Secretary of Veterans Affairs must submit a report within 60 days regarding coordination between the Veterans Health Administration and the Readjustment Counseling Service.\n- The report should assess each Director\'s adherence to policies ensuring support facilities are aligned with Vet Centers for better service, especially for veterans at high risk for suicide.\n- The report must include an analysis of various aspects including staff contact information updates, professional consultations, documentation of these consultations, and coordination with active duty members in the Transition Assistance Program.\n- "Vet Center" is defined as per section 1712A(h) of title 38, United States Code.'}, '\n SEC. 201.  Vet Center defined.\n': {'code': '9941820', 'data': '- "Vet Center" refers to a specific type of facility as defined in section 1712A(h) of title 38, United States Code.'}, '\n SEC. 202. Comptroller General report on Readjustment Counseling Service model for expansion of Vet Center footprint.\n': {'code': '5054748', 'data': "- The Comptroller General of the United States is required to submit a report within one year after the Act's enactment.\n- The report should evaluate the Department of Veterans Affairs' model for expanding Vet Center real property footprint.\n- Key aspects of the evaluation include demand in rural areas, frequency of reassessment, needs of veterans with high crisis line activity or suicides, mobile Vet Center trends, and unique needs of veterans in assessed areas."}, '\n SEC. 203.  Improvement of guidance and information to improve veteran outreach efforts by Vet Centers.\n': {'code': '1445696', 'data': '- The Secretary of Veterans Affairs must ensure Vet Centers have demographic data for eligible individuals to tailor outreach activities.\n- Guidance on assessing the effectiveness of outreach activities, including metrics and targets, will be provided to Vet Centers.\n- A process will be developed to assess barriers veterans and Armed Forces members face in obtaining services from Vet Centers.\n- A process will also be implemented to evaluate staff barriers in providing services.'}, '\n SEC. 204.  Report on information technology system of Readjustment Counseling Service.\n': {'code': '0474480', 'data': '- The Secretary of Veterans Affairs must submit a report within 60 days.\n- The report should identify whether the Department is retaining or replacing RCSNet.\n- If retaining RCSNet, provide rationale and steps to maintain or improve functionality with a timeline.\n- If replacing RCSNet, provide rationale, implementation steps including timeline and estimated cost.'}, '\n SEC. 301.  Study on effectiveness of suicide prevention and mental health outreach programs of Department of Veterans Affairs for women veterans.\n': {'code': '5580769', 'data': "- The Secretary of Veterans Affairs is tasked with conducting surveys and hosting listening sessions within 240 days of the Act's enactment to assess women veterans' perceptions of VA resources.\n- Surveys will evaluate effectiveness, tailoring, integration of military sexual trauma information, potential improvements, and demographic targeting.\n- Sessions must cover urban and rural areas, ensuring representation from various demographics.\n- A report detailing findings and intended steps for refining resources based on feedback is due within one year."}, '\n SEC. 302.  Requirement for Department of Veterans Affairs to modify the REACH VET program to incorporate risk factors weighted for women veterans.\n': {'code': '1210240', 'data': '- The Secretary of Veterans Affairs has 60 days to modify the REACH VET program.\n- The modifications should incorporate risk factors weighted for women.\n- These factors include military sexual trauma and intimate partner violence.'}, '\n SEC. 303.  Review of and report on reintegration and readjustment services for veterans and family members in group retreat settings.\n': {'code': '4045707', 'data': "- The Secretary of Veterans Affairs is required to review requests for reintegration and readjustment services for veterans and their family members in group retreat program settings.\n- The review should focus on determining if current retreat programming meets demand, specifically for women-only retreats, disabled access retreats, particularly wheelchair accessible retreats, and retreats for veterans with specific medical needs.\n- Not later than 120 days after the enactment of this Act, the Secretary must submit a report to the Senate and House Veterans' Affairs Committees on whether the provision of reintegration and readjustment services should be increased and made permanent."}, '\n SEC. 401.  Extension of Staff Sergeant Parker Gordon Fox Suicide Prevention Grant Program.\n': {'code': '3561791', 'data': '- Section 201 of the Commander John Scott Hannon Veterans Mental Health Care Improvement Act of 2019 is amended.\n- Subsection (c)(2)(A) has its funding increased from $750,000 to $1,000,000.\n- Subsection (j) extends the duration from three years to six years.'}, '\n SEC. 402.  Access to mental health residential rehabilitation treatment programs for veterans with spinal cord injury or disorder.\n': {'code': '6060502', 'data': "- The Secretary of Veterans Affairs is required to submit a plan within 60 days of the Act's enactment, detailing access to mental health residential treatment programs for veterans with spinal cord injuries or disorders.\n- The plan must include staffing plans, medical equipment needs assessment, and location assessments.\n- A pilot program begins within 120 days, providing mental health residential treatment at least three Department facilities.\n- A report on the plan implementation, pilot program results, and expansion plans is due one year after enactment."}, '\n SEC. 403.  Mental health consultations and outreach on mental health services for veterans receiving compensation for disabilities relating to mental health diagnoses.\n': {'code': '7726960', 'data': '- **Section Redesignation and Table Update**: Section 1167 of Title 38, United States Code, is redesignated as section 1169. The table of sections at the beginning of chapter 11 is updated by removing the old item for section 1167 and adding a new item for section 1169.\n\n- **Subsection Modifications**: Section 1169 is further modified:\n  - Subsection (a) is renamed to "Initial mental health consultations."\n  - Subsections (b) and (c) are redesignated as (c) and (d), respectively.\n  - A new subsection (b) is added, detailing annual mental health consultations and outreach.\n  - Subsection (c) is modified by inserting "or (b)" after "under subsection (a)" both places it appears.\n  - Subsection (d) is modified by inserting "or as requiring reevaluation of any entitlement of the veteran to compensation under this chapter" before the period at the end.\n\n- **Biennial Reports**: Section 1169 is further amended by adding a new subsection (e):\n  - The Secretary must conduct biennial reviews and reports on outreach effectiveness and mental health services.\n  - Reviews should cover feedback, consultations sought, and factors deterring veterans from seeking consultations.\n  - The Secretary must ensure veterans can provide feedback and analyze it for future improvements.'}, '\n SEC. 404.  Joint report on effectiveness of programs of Department of Veterans Affairs and Department of Defense that promote access to mental health services for transitioning members of the Armed Forces.\n': {'code': '4944600', 'data': "- The Secretary of Veterans Affairs and the Secretary of Defense must jointly submit a report within 180 days after the Act's enactment.\n- The report should detail actions taken or planned to improve mental health services for transitioning military members.\n- It must assess the response to recommendations from the Comptroller General in July 2024.\n- The report should identify any duplicative efforts or gaps and recommend changes, including legislative action if necessary."}}, 'status': 'The bill aims to improve mental health services for the Department of Veterans Affairs by enhancing workforce qualifications, expanding Vet Center infrastructure and technology, addressing specific needs of women veterans, ensuring access to specialized treatment programs, and promoting coordination between VA and DoD mental health resources.'}


    # ~:mismatch break!,field:,data,
    aa = {'bullets': {' SEC. 2.  Conveyance of Federal land to Ouray, Colorado.': {'code': '2435581', 'data': '- **Definitions**: The text defines terms such as "City," "Federal land," "Map," and "Secretary."\n- **Conveyance**: The Secretary is tasked with transferring all rights, title, and interests of the United States in Federal land to the City, including associated water rights.\n- **Requirements**: The conveyance must be made by quitclaim deed, subject to existing rights and a reversionary interest. It should be completed at no cost to the City.\n- **Costs and Responsibilities**: The Secretary will pay all costs except for surveys conducted by the City. The City assumes responsibility for repairs, operations, and maintenance of Full Moon Dam and related infrastructure.'}, ' SECTION 1.  Short title.': {'code': '9071327', 'data': '- The Crystal Reservoir Conveyance Act transfers federal land and associated water rights to the City of Ouray, Colorado.\n- The conveyed land includes the Crystal Reservoir site, Full Moon Dam, Full Moon Ditch, and related infrastructure.\n- The city assumes responsibility for repairs, operations, and maintenance of the dam and infrastructure.\n- The conveyance is subject to conditions ensuring the land remains open space for public recreational use.'}, 'init': {'code': '0', 'data': '- **Bill Introduction**: Introduced by Senators Bennett and Hickenlooper.\n- **Purpose**: To direct the Secretary of Agriculture to convey certain land managed by the Forest Service, including a reservoir, to the City of Ouray, Colorado.\n- **Committee Reference**: Referred to the Committee on Energy and Natural Resources.\n- **Reported with Amendment**: Reported by Senator Lee with an amendment that struck out all after the enacting clause and inserted italicized text.'}}, 'status': 'The bill directs the Secretary of Agriculture to convey to the City of Ouray, Colorado, certain land managed by the Forest Service, including a reservoir.'}
    ab = {'bullets': {' SEC. 2.  Conveyance of Federal land to Ouray, Colorado.': {'code': '2435581', 'data': '- **Definitions**: The text defines terms such as "City," "Federal land," "Map," and "Secretary."\n- **Conveyance**: The Secretary is tasked with transferring all rights, title, and interests of the United States in Federal land to the City, including associated water rights.\n- **Requirements**: The conveyance must be made by quitclaim deed, subject to existing rights and a reversionary interest. It should be completed at no cost to the City.\n- **Costs and Responsibilities**: The Secretary will pay all costs except for surveys conducted by the City. The City assumes responsibility for repairs, operations, and maintenance of Full Moon Dam and related infrastructure.'}, ' SECTION 1.  Short title.': {'code': '9071327', 'data': '- The Act is titled the "Crystal Reservoir Conveyance Act."\n- It authorizes the conveyance of federal land, including Crystal Reservoir and associated facilities, to the City of Ouray, Colorado.\n- The conveyance includes fee simple title and all water rights associated with the land.\n- The City must assume responsibility for repairs, operations, and maintenance of Full Moon Dam and related infrastructure.'}, 'init': {'code': '0', 'data': '- **Bill Introduction**: Introduced by Senators Bennett and Hickenlooper.\n- **Purpose**: To direct the Secretary of Agriculture to convey certain land managed by the Forest Service, including a reservoir, to the City of Ouray, Colorado.\n- **Committee Reference**: Referred to the Committee on Energy and Natural Resources.\n- **Reported with Amendment**: Reported by Senator Lee with an amendment that struck out all after the enacting clause and inserted italicized text.'}}, 'status': 'The bill directs the Secretary of Agriculture to convey to the City of Ouray, Colorado, certain land managed by the Forest Service, including a reservoir.'}
    # ~:---items do not match,{'objType': 'Spren', 'networkChain': 'regSoJjJHlFcVbpue8KG0lS', 'id': 'sprSokq6VO8UgpwzJBTzkQ7S', 'created': '2026-10-05T06:00:00.00Z', 'func': 'summarize_bills', 'CreatorNode_obj': 'nodSo4P4nQIHWZFavdJ', 'validatorNodeId': 'nodSo5bqKjLz8qZPzju', 'Validator_obj': None, 'Block_obj': None, 'modlVer': 1, 'Region_obj': 'regSoJjJHlFcVbpue8KG0lS', 'DateTime': '2026-09-30T23:00:00.00Z', 'pointerId': '1btxtSo26SOpdK02VDh3TFCiCf', 'pointerKey': 39, 're': '1bilSo8ZZloBrbIOSkuXp0Cju', 'type': 'Billtext', 'pointerType': 'Bill', 'data': {'status': 'The bill directs the Secretary of Agriculture to convey to the City of Ouray, Colorado, certain land managed by the Forest Service, including a reservoir.', 'bullets': {'init': {'code': '0', 'data': '- **Bill Introduction**: Introduced by Senators Bennett and Hickenlooper.\n- **Purpose**: To direct the Secretary of Agriculture to convey certain land managed by the Forest Service, including a reservoir, to the City of Ouray, Colorado.\n- **Committee Reference**: Referred to the Committee on Energy and Natural Resources.\n- **Reported with Amendment**: Reported by Senator Lee with an amendment that struck out all after the enacting clause and inserted italicized text.'}, ' SECTION 1.  Short title.': {'code': '9071327', 'data': '- The Act is titled the "Crystal Reservoir Conveyance Act."\n- It authorizes the conveyance of federal land, including Crystal Reservoir and associated facilities, to the City of Ouray, Colorado.\n- The conveyance includes fee simple title and all water rights associated with the land.\n- The City must assume responsibility for repairs, operations, and maintenance of Full Moon Dam and related infrastructure.'}, ' SEC. 2.  Conveyance of Federal land to Ouray, Colorado.': {'code': '2435581', 'data': '- **Definitions**: The text defines terms such as "City," "Federal land," "Map," and "Secretary."\n- **Conveyance**: The Secretary is tasked with transferring all rights, title, and interests of the United States in Federal land to the City, including associated water rights.\n- **Requirements**: The conveyance must be made by quitclaim deed, subject to existing rights and a reversionary interest. It should be completed at no cost to the City.\n- **Costs and Responsibilities**: The Secretary will pay all costs except for surveys conducted by the City. The City assumes responsibility for repairs, operations, and maintenance of Full Moon Dam and related infrastructure.'}}}, 'extra': None, 'signed': {'2026-10-05T06:00:16.41Z': {'pk': 'upkSoalMVn6hHQ1mq1xFPkz1', 'sig': 'MEUCIC0IIlyKhBP0yYAGMQkZoDVs_IYtxKuYK4YzA1HfEQyVAiEA-lpM9ZvaB2Bv_p-YVbEIeKsz0IvtWDch12p7I7ldjGE'}}}
    # ~:#---verify_obj_to_data,upk-,<QuerySet [<UserPubKey: UPK:upkSoalMVn6hHQ1mq1xFPkz1>]>
    aa = {'completed_model': 'True', 'has_transcript': 'True', 'HtmlURL': '', 'IsAudioOnly': 0, 'IsTelevised': 1, 'MeetingIsForSenateOrganization': '0', 'PdfURL': '/Content/House/451/Debates/163/HAN163-E.PDF', 'People': [{'{"Name": "Francis Scarpaleggia", "obj_id": "Francis Scarpaleggia"}': 16}, {'{"Name": "Kelly DeRidder", "obj_id": "Kelly DeRidder"}': 15}, {'{"Name": "Pierre Poilievre", "obj_id": "Pierre Poilievre"}': 15}, {'{"Name": "Kevin Lamoureux", "obj_id": "Kevin Lamoureux"}': 14}, {'{"Name": "Steven MacKinnon", "obj_id": "Steven MacKinnon"}': 14}, {'{"Name": "Jean-Yves Duclos", "obj_id": "Jean-Yves Duclos"}': 10}, {'{"Name": "Mario Simard", "obj_id": "Mario Simard"}': 10}, {'{"Name": "Mark Carney", "obj_id": "Mark Carney"}': 10}, {'{"Name": "Matt Strauss", "obj_id": "Matt Strauss"}': 9}, {'{"Name": "Marjorie Michel", "obj_id": "Marjorie Michel"}': 8}, {'{"Name": "Dan Albas", "obj_id": "Dan Albas"}': 7}, {'{"Name": "Fran\\u00e7ois-Philippe Champagne", "obj_id": "Fran\\u00e7ois-Philippe Champagne"}': 7}, {'{"Name": "Helena Konanz", "obj_id": "Helena Konanz"}': 7}, {'{"Name": "Luc Th\\u00e9riault", "obj_id": "Luc Th\\u00e9riault"}': 7}, {'{"Name": "Danielle Martin", "obj_id": "Danielle Martin"}': 6}, {'{"Name": "Jean-Denis Garon", "obj_id": "Jean-Denis Garon"}': 6}, {'{"Name": "Marie-H\\u00e9l\\u00e8ne Gaudreau", "obj_id": "Marie-H\\u00e9l\\u00e8ne Gaudreau"}': 6}, {'{"Name": "Abdelhaq Sari", "obj_id": "Abdelhaq Sari"}': 5}, {'{"Name": "Jagsharan Singh Mahal", "obj_id": "Jagsharan Singh Mahal"}': 5}, {'{"Name": "Luc Berthold", "obj_id": "Luc Berthold"}': 5}, {'{"Name": "Maggie Chi", "obj_id": "Maggie Chi"}': 5}, {'{"Name": "Eric St-Pierre", "obj_id": "Eric St-Pierre"}': 4}, {'{"Name": "Harb Gill", "obj_id": "Harb Gill"}': 4}, {'{"Name": "Michael Chong", "obj_id": "Michael Chong"}': 4}, {'{"Name": "Yves-Fran\\u00e7ois Blanchet", "obj_id": "Yves-Fran\\u00e7ois Blanchet"}': 4}, {'{"Name": "Brad Vis", "obj_id": "Brad Vis"}': 3}, {'{"Name": "Gabriel Ste-Marie", "obj_id": "Gabriel Ste-Marie"}': 3}, {'{"Name": "Gord Johns", "obj_id": "Gord Johns"}': 3}, {'{"Name": "Jamil Jivani", "obj_id": "Jamil Jivani"}': 3}, {'{"Name": "Jenny Kwan", "obj_id": "Jenny Kwan"}': 3}, {'{"Name": "Jo\\u00ebl Lightbound", "obj_id": "Jo\\u00ebl Lightbound"}': 3}, {'{"Name": "Ryan Turnbull", "obj_id": "Ryan Turnbull"}': 3}, {'{"Name": "Tom Kmiec", "obj_id": "Tom Kmiec"}': 3}, {'{"Name": "Alexandra Mend\\u00e8s", "obj_id": "Alexandra Mend\\u00e8s"}': 2}, {'{"Name": "Andr\\u00e9anne Larouche", "obj_id": "Andr\\u00e9anne Larouche"}': 2}, {'{"Name": "Anna Roberts", "obj_id": "Anna Roberts"}': 2}, {'{"Name": "Brad Redekopp", "obj_id": "Brad Redekopp"}': 2}, {'{"Name": "Dominic LeBlanc", "obj_id": "Dominic LeBlanc"}': 2}, {'{"Name": "Don Davies", "obj_id": "Don Davies"}': 2}, {'{"Name": "Gabriel Hardy", "obj_id": "Gabriel Hardy"}': 2}, {'{"Name": "Grant Jackson", "obj_id": "Grant Jackson"}': 2}, {'{"Name": "Jeremy Patzer", "obj_id": "Jeremy Patzer"}': 2}, {'{"Name": "John Brassard", "obj_id": "John Brassard"}': 2}, {'{"Name": "John Nater", "obj_id": "John Nater"}': 2}, {'{"Name": "Lena Metlege Diab", "obj_id": "Lena Metlege Diab"}': 2}, {'{"Name": "Michael Cooper", "obj_id": "Michael Cooper"}': 2}, {'{"Name": "Patrick Bonin", "obj_id": "Patrick Bonin"}': 2}, {'{"Name": "Sandra Cobena", "obj_id": "Sandra Cobena"}': 2}, {'{"Name": "Shannon Stubbs", "obj_id": "Shannon Stubbs"}': 2}, {'{"Name": "Tony Baldinelli", "obj_id": "Tony Baldinelli"}': 2}, {'{"Name": "Wayne Long", "obj_id": "Wayne Long"}': 2}, {'{"Name": "Adam van Koeverden", "obj_id": "Adam van Koeverden"}': 1}, {'{"Name": "Anita Anand", "obj_id": "Anita Anand"}': 1}, {'{"Name": "Bienvenu-Olivier Ntumba", "obj_id": "Bienvenu-Olivier Ntumba"}': 1}, {'{"Name": "Blake Richards", "obj_id": "Blake Richards"}': 1}, {'{"Name": "Chris Lewis", "obj_id": "Chris Lewis"}': 1}, {'{"Name": "Dalwinder Gill", "obj_id": "Dalwinder Gill"}': 1}, {'{"Name": "Dan Mazier", "obj_id": "Dan Mazier"}': 1}, {'{"Name": "Daniel Gobeil", "obj_id": "Daniel Gobeil"}': 1}, {'{"Name": "Doly Begum", "obj_id": "Doly Begum"}': 1}, {'{"Name": "Doug Eyolfson", "obj_id": "Doug Eyolfson"}': 1}, {'{"Name": "Elizabeth May", "obj_id": "Elizabeth May"}': 1}, {'{"Name": "Evan Solomon", "obj_id": "Evan Solomon"}': 1}, {'{"Name": "G\\u00e9rard Deltell", "obj_id": "G\\u00e9rard Deltell"}': 1}, {'{"Name": "Gary Anandasangaree", "obj_id": "Gary Anandasangaree"}': 1}, {'{"Name": "Ginette Petitpas Taylor", "obj_id": "Ginette Petitpas Taylor"}': 1}, {'{"Name": "Guillaume Desch\\u00eanes-Th\\u00e9riault", "obj_id": "Guillaume Desch\\u00eanes-Th\\u00e9riault"}': 1}, {'{"Name": "Heather McPherson", "obj_id": "Heather McPherson"}': 1}, {'{"Name": "Jacob Mantle", "obj_id": "Jacob Mantle"}': 1}, {'{"Name": "Jason Groleau", "obj_id": "Jason Groleau"}': 1}, {'{"Name": "John Williamson", "obj_id": "John Williamson"}': 1}, {'{"Name": "John-Paul Danko", "obj_id": "John-Paul Danko"}': 1}, {'{"Name": "Judy A. Sgro", "obj_id": "Judy A. Sgro"}': 1}, {'{"Name": "Julie Dzerowicz", "obj_id": "Julie Dzerowicz"}': 1}, {'{"Name": "Kelly Block", "obj_id": "Kelly Block"}': 1}, {'{"Name": "Leslie Church", "obj_id": "Leslie Church"}': 1}, {'{"Name": "Lisa Hepfner", "obj_id": "Lisa Hepfner"}': 1}, {'{"Name": "Marie-Gabrielle M\\u00e9nard", "obj_id": "Marie-Gabrielle M\\u00e9nard"}': 1}, {'{"Name": "Mario Beaulieu", "obj_id": "Mario Beaulieu"}': 1}, {'{"Name": "Mel Arnold", "obj_id": "Mel Arnold"}': 1}, {'{"Name": "Patrick Weiler", "obj_id": "Patrick Weiler"}': 1}, {'{"Name": "Peter Fragiskatos", "obj_id": "Peter Fragiskatos"}': 1}, {'{"Name": "Peter Schiefke", "obj_id": "Peter Schiefke"}': 1}, {'{"Name": "Rebecca Chartrand", "obj_id": "Rebecca Chartrand"}': 1}, {'{"Name": "Ruby Sahota", "obj_id": "Ruby Sahota"}': 1}, {'{"Name": "Sonia Sidhu", "obj_id": "Sonia Sidhu"}': 1}, {'{"Name": "Sophie Chatel", "obj_id": "Sophie Chatel"}': 1}, {'{"Name": "Steeve Lavoie", "obj_id": "Steeve Lavoie"}': 1}, {'{"Name": "Stephen Fuhr", "obj_id": "Stephen Fuhr"}': 1}, {'{"Name": "Tatiana Auguste", "obj_id": "Tatiana Auguste"}': 1}, {'{"Name": "Terry Sheehan", "obj_id": "Terry Sheehan"}': 1}, {'{"Name": "Tim Hodgson", "obj_id": "Tim Hodgson"}': 1}], 'statement_count': 318, 'subjects': ['Government Response to Petitions', 'Committees of the House [Fisheries and Oceans]', 'Committees of the House [Fisheries and Oceans]', 'Petitions [First Nations Education]', 'Abandoned Vessels', 'Questions on the Order Paper', 'Questions on the Order Paper', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', 'Aerospace Industry', 'The Economy', 'The Economy', 'BPW Montréal', 'Royal Canadian Air Force Foundation', 'Eric Bauza', 'Margaret Heinmiller', 'Service de police de la Ville de Montréal', 'Automotive Industry', 'Canadian Armed Forces Legend', 'Patricia May Martyn', 'The Economy', 'Hamilton Cardinals', 'The Economy', 'The Economy', 'Mille et une huîtres Event', 'The Economy', 'Ordine al Merito Award', 'Taxation', 'Taxation', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Finance', 'Finance', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'The Economy', 'The Economy', 'The Economy', 'The Economy', '\n      \n    Labour', '\n      \n    Labour', '\tIndigenous Affairs', '\tIndigenous Affairs', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', '\tOil and Gas Industry', '\tOil and Gas Industry', '\tOil and Gas Industry', '\tOil and Gas Industry', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Agriculture and Agri-Food', 'Agriculture and Agri-Food', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Foreign Affairs', 'Foreign Affairs', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Major Projects Office', 'Major Projects Office', 'Steel and Aluminum Industry', 'Steel and Aluminum Industry', 'Major Projects Office', 'Major Projects Office', 'Major Projects Office', 'Major Projects Office', 'Justice', 'Justice', 'Regional Economic Development', 'Regional Economic Development', 'Justice', 'Justice', 'Finance', 'Finance', 'Finance', 'Artificial Intelligence', 'Artificial Intelligence', 'Business of the House', 'Business of the House', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]'], 'Terms': [{'\n       Connected Care for Canadians Act': 121}, {'The Budget [Financial Statement of Minister of Finance]': 42}, {'S-5, An Act respecting the interoperability of health information technology and to prohibit data blocking by health information technology vendors': 38}, {'Public Services and Procurement': 30}, {'Connected Care for Canadians Act': 28}, {'Finance': 28}, {'The Economy': 10}, {'Immigration, Refugees and Citizenship': 8}, {'Major Projects Office': 6}, {'C-39, An Act respecting certain measures to strengthen the economy': 5}, {'\tOil and Gas Industry': 4}, {'Justice': 4}, {'C-72, An Act respecting the interoperability of health information technology and to prohibit data blocking by health information technology vendors': 3}, {'\tIndigenous Affairs': 2}, {'\n      \n    Labour': 2}, {'Agriculture and Agri-Food': 2}, {'Artificial Intelligence': 2}, {'Business of the House': 2}, {'Committees of the House [Fisheries and Oceans]': 2}, {'Foreign Affairs': 2}, {'Questions on the Order Paper': 2}, {'Regional Economic Development': 2}, {'Steel and Aluminum Industry': 2}, {'Taxation': 2}, {'Abandoned Vessels': 1}, {'Aerospace Industry': 1}, {'Automotive Industry': 1}, {'BPW Montréal': 1}, {'C-294, An Act to amend the Copyright Act (interoperability)': 1}, {'C-36, An Act to enact the Protecting Privacy and Consumer Data Act, to amend the Personal Information Protection and Electronic Documents Act and to make amendments to other Acts': 1}, {'C-41, An Act to amend the Criminal Code and An Act to amend the Criminal Code (medical assistance in dying) and to make related amendments to other Acts': 1}, {'Canadian Armed Forces Legend': 1}, {'Eric Bauza': 1}, {'Government Response to Petitions': 1}, {'Hamilton Cardinals': 1}, {'Margaret Heinmiller': 1}, {'Mille et une huîtres Event': 1}, {'Ordine al Merito Award': 1}, {'Patricia May Martyn': 1}, {'Petitions [First Nations Education]': 1}, {'Royal Canadian Air Force Foundation': 1}, {'Service de police de la Ville de Montréal': 1}], 'TypeId': 37}
    ab = {'completed_model': 'True', 'has_transcript': 'True', 'HtmlURL': '', 'IsAudioOnly': 0, 'IsTelevised': 1, 'MeetingIsForSenateOrganization': '0', 'PdfURL': '/Content/House/451/Debates/163/HAN163-E.PDF', 'People': [{'{"Name": "Francis Scarpaleggia", "obj_id": "Francis Scarpaleggia"}': 16}, {'{"Name": "Kelly DeRidder", "obj_id": "Kelly DeRidder"}': 15}, {'{"Name": "Pierre Poilievre", "obj_id": "Pierre Poilievre"}': 15}, {'{"Name": "Kevin Lamoureux", "obj_id": "Kevin Lamoureux"}': 14}, {'{"Name": "Steven MacKinnon", "obj_id": "Steven MacKinnon"}': 14}, {'{"Name": "Jean-Yves Duclos", "obj_id": "Jean-Yves Duclos"}': 10}, {'{"Name": "Mario Simard", "obj_id": "Mario Simard"}': 10}, {'{"Name": "Mark Carney", "obj_id": "Mark Carney"}': 10}, {'{"Name": "Matt Strauss", "obj_id": "Matt Strauss"}': 9}, {'{"Name": "Marjorie Michel", "obj_id": "Marjorie Michel"}': 8}, {'{"Name": "Dan Albas", "obj_id": "Dan Albas"}': 7}, {'{"Name": "Fran\\u00e7ois-Philippe Champagne", "obj_id": "Fran\\u00e7ois-Philippe Champagne"}': 7}, {'{"Name": "Helena Konanz", "obj_id": "Helena Konanz"}': 7}, {'{"Name": "Luc Th\\u00e9riault", "obj_id": "Luc Th\\u00e9riault"}': 7}, {'{"Name": "Tamara Kronis", "obj_id": "Tamara Kronis"}': 7}, {'{"Name": "Danielle Martin", "obj_id": "Danielle Martin"}': 6}, {'{"Name": "Jean-Denis Garon", "obj_id": "Jean-Denis Garon"}': 6}, {'{"Name": "Marie-H\\u00e9l\\u00e8ne Gaudreau", "obj_id": "Marie-H\\u00e9l\\u00e8ne Gaudreau"}': 6}, {'{"Name": "Abdelhaq Sari", "obj_id": "Abdelhaq Sari"}': 5}, {'{"Name": "Jagsharan Singh Mahal", "obj_id": "Jagsharan Singh Mahal"}': 5}, {'{"Name": "Luc Berthold", "obj_id": "Luc Berthold"}': 5}, {'{"Name": "Maggie Chi", "obj_id": "Maggie Chi"}': 5}, {'{"Name": "Brendan Hanley", "obj_id": "Brendan Hanley"}': 4}, {'{"Name": "Eric St-Pierre", "obj_id": "Eric St-Pierre"}': 4}, {'{"Name": "Harb Gill", "obj_id": "Harb Gill"}': 4}, {'{"Name": "Michael Chong", "obj_id": "Michael Chong"}': 4}, {'{"Name": "Yves-Fran\\u00e7ois Blanchet", "obj_id": "Yves-Fran\\u00e7ois Blanchet"}': 4}, {'{"Name": "Brad Vis", "obj_id": "Brad Vis"}': 3}, {'{"Name": "Gabriel Ste-Marie", "obj_id": "Gabriel Ste-Marie"}': 3}, {'{"Name": "Gord Johns", "obj_id": "Gord Johns"}': 3}, {'{"Name": "Jamil Jivani", "obj_id": "Jamil Jivani"}': 3}, {'{"Name": "Jenny Kwan", "obj_id": "Jenny Kwan"}': 3}, {'{"Name": "Jo\\u00ebl Lightbound", "obj_id": "Jo\\u00ebl Lightbound"}': 3}, {'{"Name": "Ryan Turnbull", "obj_id": "Ryan Turnbull"}': 3}, {'{"Name": "Tom Kmiec", "obj_id": "Tom Kmiec"}': 3}, {'{"Name": "Alexandra Mend\\u00e8s", "obj_id": "Alexandra Mend\\u00e8s"}': 2}, {'{"Name": "Andr\\u00e9anne Larouche", "obj_id": "Andr\\u00e9anne Larouche"}': 2}, {'{"Name": "Anna Roberts", "obj_id": "Anna Roberts"}': 2}, {'{"Name": "Brad Redekopp", "obj_id": "Brad Redekopp"}': 2}, {'{"Name": "Dominic LeBlanc", "obj_id": "Dominic LeBlanc"}': 2}, {'{"Name": "Don Davies", "obj_id": "Don Davies"}': 2}, {'{"Name": "Gabriel Hardy", "obj_id": "Gabriel Hardy"}': 2}, {'{"Name": "Grant Jackson", "obj_id": "Grant Jackson"}': 2}, {'{"Name": "Jeremy Patzer", "obj_id": "Jeremy Patzer"}': 2}, {'{"Name": "John Brassard", "obj_id": "John Brassard"}': 2}, {'{"Name": "John Nater", "obj_id": "John Nater"}': 2}, {'{"Name": "Lena Metlege Diab", "obj_id": "Lena Metlege Diab"}': 2}, {'{"Name": "Michael Cooper", "obj_id": "Michael Cooper"}': 2}, {'{"Name": "Patrick Bonin", "obj_id": "Patrick Bonin"}': 2}, {'{"Name": "Sandra Cobena", "obj_id": "Sandra Cobena"}': 2}, {'{"Name": "Shannon Stubbs", "obj_id": "Shannon Stubbs"}': 2}, {'{"Name": "Tony Baldinelli", "obj_id": "Tony Baldinelli"}': 2}, {'{"Name": "Wayne Long", "obj_id": "Wayne Long"}': 2}, {'{"Name": "Adam van Koeverden", "obj_id": "Adam van Koeverden"}': 1}, {'{"Name": "Anita Anand", "obj_id": "Anita Anand"}': 1}, {'{"Name": "Bienvenu-Olivier Ntumba", "obj_id": "Bienvenu-Olivier Ntumba"}': 1}, {'{"Name": "Blake Richards", "obj_id": "Blake Richards"}': 1}, {'{"Name": "Chris Lewis", "obj_id": "Chris Lewis"}': 1}, {'{"Name": "Clifford Small", "obj_id": "Clifford Small"}': 1}, {'{"Name": "Dalwinder Gill", "obj_id": "Dalwinder Gill"}': 1}, {'{"Name": "Dan Mazier", "obj_id": "Dan Mazier"}': 1}, {'{"Name": "Daniel Gobeil", "obj_id": "Daniel Gobeil"}': 1}, {'{"Name": "Doly Begum", "obj_id": "Doly Begum"}': 1}, {'{"Name": "Doug Eyolfson", "obj_id": "Doug Eyolfson"}': 1}, {'{"Name": "Elizabeth May", "obj_id": "Elizabeth May"}': 1}, {'{"Name": "Evan Solomon", "obj_id": "Evan Solomon"}': 1}, {'{"Name": "Frank Caputo", "obj_id": "Frank Caputo"}': 1}, {'{"Name": "G\\u00e9rard Deltell", "obj_id": "G\\u00e9rard Deltell"}': 1}, {'{"Name": "Gary Anandasangaree", "obj_id": "Gary Anandasangaree"}': 1}, {'{"Name": "Ginette Petitpas Taylor", "obj_id": "Ginette Petitpas Taylor"}': 1}, {'{"Name": "Guillaume Desch\\u00eanes-Th\\u00e9riault", "obj_id": "Guillaume Desch\\u00eanes-Th\\u00e9riault"}': 1}, {'{"Name": "Heather McPherson", "obj_id": "Heather McPherson"}': 1}, {'{"Name": "Jacob Mantle", "obj_id": "Jacob Mantle"}': 1}, {'{"Name": "Jason Groleau", "obj_id": "Jason Groleau"}': 1}, {'{"Name": "Jill McKnight", "obj_id": "Jill McKnight"}': 1}, {'{"Name": "John Williamson", "obj_id": "John Williamson"}': 1}, {'{"Name": "John-Paul Danko", "obj_id": "John-Paul Danko"}': 1}, {'{"Name": "Judy A. Sgro", "obj_id": "Judy A. Sgro"}': 1}, {'{"Name": "Julie Dzerowicz", "obj_id": "Julie Dzerowicz"}': 1}, {'{"Name": "Kelly Block", "obj_id": "Kelly Block"}': 1}, {'{"Name": "Leslie Church", "obj_id": "Leslie Church"}': 1}, {'{"Name": "Lisa Hepfner", "obj_id": "Lisa Hepfner"}': 1}, {'{"Name": "Marie-Gabrielle M\\u00e9nard", "obj_id": "Marie-Gabrielle M\\u00e9nard"}': 1}, {'{"Name": "Mario Beaulieu", "obj_id": "Mario Beaulieu"}': 1}, {'{"Name": "Mel Arnold", "obj_id": "Mel Arnold"}': 1}, {'{"Name": "Patrick Weiler", "obj_id": "Patrick Weiler"}': 1}, {'{"Name": "Peter Fragiskatos", "obj_id": "Peter Fragiskatos"}': 1}, {'{"Name": "Peter Schiefke", "obj_id": "Peter Schiefke"}': 1}, {'{"Name": "Rebecca Chartrand", "obj_id": "Rebecca Chartrand"}': 1}, {'{"Name": "Ruby Sahota", "obj_id": "Ruby Sahota"}': 1}, {'{"Name": "Sonia Sidhu", "obj_id": "Sonia Sidhu"}': 1}, {'{"Name": "Sophie Chatel", "obj_id": "Sophie Chatel"}': 1}, {'{"Name": "Steeve Lavoie", "obj_id": "Steeve Lavoie"}': 1}, {'{"Name": "Stephen Fuhr", "obj_id": "Stephen Fuhr"}': 1}, {'{"Name": "Tatiana Auguste", "obj_id": "Tatiana Auguste"}': 1}, {'{"Name": "Terry Sheehan", "obj_id": "Terry Sheehan"}': 1}, {'{"Name": "Tim Hodgson", "obj_id": "Tim Hodgson"}': 1}], 'statement_count': 318, 'subjects': ['Government Response to Petitions', 'Committees of the House [Fisheries and Oceans]', 'Committees of the House [Fisheries and Oceans]', 'Petitions [First Nations Education]', 'Abandoned Vessels', 'Questions on the Order Paper', 'Questions on the Order Paper', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', '\n       Connected Care for Canadians Act', 'Aerospace Industry', 'The Economy', 'The Economy', 'BPW Montréal', 'Royal Canadian Air Force Foundation', 'Eric Bauza', 'Margaret Heinmiller', 'Service de police de la Ville de Montréal', 'Automotive Industry', 'Canadian Armed Forces Legend', 'Patricia May Martyn', 'The Economy', 'Hamilton Cardinals', 'The Economy', 'The Economy', 'Mille et une huîtres Event', 'The Economy', 'Ordine al Merito Award', 'Taxation', 'Taxation', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Finance', 'Finance', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'The Economy', 'The Economy', 'The Economy', 'The Economy', '\n      \n    Labour', '\n      \n    Labour', '\tIndigenous Affairs', '\tIndigenous Affairs', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', '\tOil and Gas Industry', '\tOil and Gas Industry', '\tOil and Gas Industry', '\tOil and Gas Industry', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Immigration, Refugees and Citizenship', 'Agriculture and Agri-Food', 'Agriculture and Agri-Food', 'Finance', 'Finance', 'Finance', 'Finance', 'Finance', 'Foreign Affairs', 'Foreign Affairs', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Public Services and Procurement', 'Major Projects Office', 'Major Projects Office', 'Steel and Aluminum Industry', 'Steel and Aluminum Industry', 'Major Projects Office', 'Major Projects Office', 'Major Projects Office', 'Major Projects Office', 'Justice', 'Justice', 'Regional Economic Development', 'Regional Economic Development', 'Justice', 'Justice', 'Finance', 'Finance', 'Finance', 'Artificial Intelligence', 'Artificial Intelligence', 'Business of the House', 'Business of the House', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'Connected Care for Canadians Act', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]', 'The Budget [Financial Statement of Minister of Finance]'], 'Terms': [{'\n       Connected Care for Canadians Act': 121}, {'The Budget [Financial Statement of Minister of Finance]': 42}, {'S-5, An Act respecting the interoperability of health information technology and to prohibit data blocking by health information technology vendors': 38}, {'Public Services and Procurement': 30}, {'Connected Care for Canadians Act': 28}, {'Finance': 28}, {'The Economy': 10}, {'Immigration, Refugees and Citizenship': 8}, {'Major Projects Office': 6}, {'C-39, An Act respecting certain measures to strengthen the economy': 5}, {'\tOil and Gas Industry': 4}, {'Justice': 4}, {'C-72, An Act respecting the interoperability of health information technology and to prohibit data blocking by health information technology vendors': 3}, {'\tIndigenous Affairs': 2}, {'\n      \n    Labour': 2}, {'Agriculture and Agri-Food': 2}, {'Artificial Intelligence': 2}, {'Business of the House': 2}, {'Committees of the House [Fisheries and Oceans]': 2}, {'Foreign Affairs': 2}, {'Questions on the Order Paper': 2}, {'Regional Economic Development': 2}, {'Steel and Aluminum Industry': 2}, {'Taxation': 2}, {'Abandoned Vessels': 1}, {'Aerospace Industry': 1}, {'Automotive Industry': 1}, {'BPW Montréal': 1}, {'C-294, An Act to amend the Copyright Act (interoperability)': 1}, {'C-36, An Act to enact the Protecting Privacy and Consumer Data Act, to amend the Personal Information Protection and Electronic Documents Act and to make amendments to other Acts': 1}, {'C-41, An Act to amend the Criminal Code and An Act to amend the Criminal Code (medical assistance in dying) and to make related amendments to other Acts': 1}, {'Canadian Armed Forces Legend': 1}, {'Eric Bauza': 1}, {'Government Response to Petitions': 1}, {'Hamilton Cardinals': 1}, {'Margaret Heinmiller': 1}, {'Mille et une huîtres Event': 1}, {'Ordine al Merito Award': 1}, {'Patricia May Martyn': 1}, {'Petitions [First Nations Education]': 1}, {'Royal Canadian Air Force Foundation': 1}, {'Service de police de la Ville de Montréal': 1}], 'TypeId': 37}
    

    import json
    from difflib import SequenceMatcher

    def char_match(d1, d2):
        a = json.dumps(d1, sort_keys=True, ensure_ascii=False)
        b = json.dumps(d2, sort_keys=True, ensure_ascii=False)
        return SequenceMatcher(None, a, b, autojunk=False).ratio()  # 0.0 to 1.0
        
    from difflib import SequenceMatcher
    def value_match(d1, d2):
        try:
            keys = d1.keys() | d2.keys()
            if not keys:
                return 1.0
            total = 0.0
            for k in keys:
                if k in d1 and k in d2:
                    total += SequenceMatcher(None, str(d1[k]), str(d2[k]), autojunk=False).ratio()
            return total / len(keys)
        except Exception as e:
            prnt('err',str(e))
        return 0

    # # # prnt('char_match',char_match(d, l))
    # # prnt('0',value_match(d, l))
    # prnt('a',value_match(aa, ab))
    # # # prnt('b',value_match(ba, bb))
    # prnt('a2',char_match(aa, ab))
    # # # prnt('b2',char_match(ba, bb))

    # xml = 'https://www.senate.gov/legislative/LIS/roll_call_votes/vote1192/vote_119_2_00180.xml'
    # # try:
    # #     r = requests.get(xml)
    # #     root = ET.fromstring(r.content)
    # # except:
    # driver = open_browser(xml)
    # prnt('loaded')
    # time.sleep(4)
    # # element_present = EC.presence_of_element_located((By.XPATH, '/html/body'))
    # # WebDriverWait(driver, 10).until(element_present)

    # xml_container = driver.find_element(By.ID, 'webkit-xml-viewer-source-xml')
    # xml_text = xml_container.get_attribute('innerHTML')
    # close_browser(driver)
    # root = ET.fromstring(xml_text)

    # soup = BeautifulSoup(driver.page_source, 'html.parser')
    # prnt('soup',soup)
    # close_browser(driver)
    # root = ET.fromstring(driver.page_source)
    prnt()
    # prnt('root',root)
        
        
    
    prnt('done tester_queue')
    return result

def tester_queue_view(request):
    if request:
        user = request.GET.get('user', None)
        if user:
            user = User.objects.filter(id=user).first()
        if user and user.assess_super_status():
            prnt('---tester_queue_view')

            start_time = now_utc()
            prnt('HELLLOO!!')
            import django_rq
            queue = django_rq.get_queue('low')
            # queue.enqueue(tester_queue, job_timeout=1200)
            queue.enqueue(tester_queue, job_timeout=3600)
            from network.models import Tidy, Validator, _OperationsChain_genesisId
            # from posts.models import Region
            from transactions.models import Wallet,Tx
            from utils.locked import create_keys, sign_obj
            from utils.models import run_prompt
            from utils.utils import get_plugin
            self_node = get_self_node()



            # prompt = f'hello'
            # r = run_prompt(prompt)
            # prnt('r',r)


                

            end_time = now_utc()
            prnt(end_time - start_time)
            return render(request, "utils/dummy.html", {"result": 'Success'})

def daily_summarizer_view(request):
    if request.user.is_superuser:
        daily_summarizer(None)
        # queue = django_rq.get_queue('default')
        # queue.enqueue(send_notifications, job_timeout=500)
        return render(request, "utils/dummy.html", {"result": 'Success'})

def run_notifications_view(request):
    if request.user.is_superuser:
        send_notifications()
        # queue = django_rq.get_queue('default')
        # queue.enqueue(send_notifications, job_timeout=500)
        return render(request, "utils/dummy.html", {"result": 'Success'})

def add_test_notification_view(request):
    if request.user.is_superuser:
        # prnt('-test notification')

        u = User.objects.all().first()
        u.alert('%s-%s' %(datetime.datetime.now(), 'test notify'), None, 'test body')

        # request.user.alert('new test notification', '/', 'test body')
        return render(request, "utils/dummy.html", {"result": 'Success'})

def remove_notification_view(request, iden):
    n = Notification.objects.filter(id=iden, user=request.user).first()
    n.new = False
    n.save()
    return render(request, "utils/dummy.html", {"result": 'Success'})

def html_playground_view(request):
    prnt('html_playground_view')
    # if request.user.is_superuser:
    # return render(request, "utils/playground.html")

    prntn('rendering')
    return render(request, "utils/testing.html", context={})
    



