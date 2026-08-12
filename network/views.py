
from .models import Blockchain, Block, Node
from accounts.models import User, UserPubKey
from legis.models import Government
from posts.models import Region
from network.models import _OperationsChain_genesisId, DataPacket, EventLog, Sonet
from utils.models import (prnt, prntDebug, testing, get_self_node, assess_received_header, get_operator_obj,
    get_dynamic_model, set_model_attrs, share_with_network, now_utc, get_or_create_model, has_field,
    string_to_dt, get_model, dt_to_string, exists_in_worker, get_timeData, process_received_data
    )
from utils.locked import convert_to_dict, get_signing_data
import datetime
import json
import django_rq
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

run_as_worker = False if testing() else True


@csrf_exempt
def get_broadcast_list_view(request, iden=None):
    prnt('-get_broadcast_list_view')
    try:
        A = 'start'
        obj = 'objx'
        obj_json = 'jsonx'
        try:
            if not get_self_node().activated_dt:
                return JsonResponse({'message' : 'deactivated_node'})
            if request.method == 'POST' and assess_received_header(request.headers) or request.user.is_superuser:
                A = '1'
                if request.method == 'POST':
                    raw_data = request.body.decode('utf-8')
                    received_data = json.loads(raw_data)
                    obj_json = json.loads(received_data.get('obj'))
                    dt = received_data.get('dt', None)
                    obj = get_dynamic_model(obj_json['objType'], id=obj_json['id'])
                elif iden:
                    A = '2'
                    obj = get_dynamic_model(iden, id=iden)
                    dt = None
                A = '3'
                if obj.User_obj.verify_sig(obj_json):
                    A = '4'
                    from utils.locked import get_node_assignment, get_broadcast_list
                    starting_nodes, validator_nodes = get_node_assignment(obj, dt=dt)
                    broadcast_list = get_broadcast_list(obj, dt=dt)
                    A = '5'
                    return JsonResponse({'message' : 'Success', 'obj' : get_signing_data(obj), 'starting_node' : starting_nodes[0], 'starting_nodes':starting_nodes, 'broadcast_list' : broadcast_list, 'validator_list' : validator_nodes})
                else:
                    return JsonResponse({'message' : 'Not valid', 'obj' : json.dumps(obj_json), 'err':str(A)})
            else:
                return JsonResponse({'message' : 'Not post'})
        except Exception as e:
            prnt('get_broadcast_list_view err 1',str(e))
            try:
                x = request.POST.get('obj')
            except Exception as x:
                x = str(x)
            return JsonResponse({'message': 'failed1', 'err': str(e) + 'A:' + A + '__' + str(obj_json) + '--' + x})
    except Exception as e:
        prnt('get_broadcast_list_view err 2',str(e))
        return JsonResponse({'message': 'failed2', 'err': str(e) + 'A:' + A + '__' + str(obj_json)})

@csrf_exempt
def get_current_node_list_view(request):
    prnt('-get_current_node_list_view')
    try:
        if not get_self_node().activated_dt:
            return JsonResponse({'message' : 'deactivated_node'})
        from utils.locked import get_relevant_nodes_from_block
        from network.models import NodeRecord, _EarthChain_genesisId
        dt = now_utc()
        record = NodeRecord.objects.filter(chainId=_EarthChain_genesisId, DateTime__lte=dt, is_valid=True).first()
        node_data = get_relevant_nodes_from_block(include_relays=True, strings_only=True)
        addresses = {}
        for key, value in node_data['relevant_nodes'].items():
            addresses[key] = value

        return JsonResponse({'message' : 'Success', 'node_data' : json.dumps(record.data), 'node_addresses' : json.dumps(addresses)})
    except Exception as e:
        prnt('get_current_node_list_view err',str(e))
        return JsonResponse({'message' : 'Fail', 'error' : str(e)})


@csrf_exempt # redundant but used by node software
def get_node_request_view(request, node_id):
    prnt('-get_node_request view')
    try:
        
        if node_id == 'self':
            nodeId = get_operator_obj('local_nodeId')
            node_obj = get_or_create_model('Node', id=nodeId)
            response = JsonResponse({'message' : 'Success', 'nodeData' : get_signing_data(node_obj), 'fullNodeData' : json.dumps(convert_to_dict(node_obj, full_pk=True))})
            return response
        elif assess_received_header(request.headers):
            try:
                sonet = get_signing_data(Sonet.objects.first())
            except:
                sonet = None
            node_obj = Node.objects.filter(id=node_id).first()
            if node_obj:
                return JsonResponse({'message' : 'Success', 'nodeData' : get_signing_data(node_obj), 'fullNodeData' : json.dumps(convert_to_dict(node_obj, full_pk=True)), 'sonet' : sonet})
            else:
                node_id = node_id
                node_obj = Node(id=node_id)
                prnt('return 2')
                return JsonResponse({'message' : 'Node not found', 'nodeData' : get_signing_data(node_obj), 'fullNodeData' : json.dumps(convert_to_dict(node_obj, full_pk=True)), 'sonet' : sonet})
    except Exception as e:
        return JsonResponse({'message' : 'Fail', 'error' : str(e)})

@csrf_exempt
def declare_node_state_view(request):
    prnt('-declare_node_state_view', now_utc())
    objData_json = 'objData_jsonxx'
    objData = 'objDataxx'
    is_valid = 'is_validxx'
    user = 'userxx'
    x = 'x1'
    try:
        if request.method == 'POST':
            x = 'xx1'
            if assess_received_header(request.headers, allow_inactive=True):
                x = 'xx2'
                try:
                    received_json = json.loads(request.body.decode('utf-8'))
                except Exception as e:
                    prnt('declare_node_state_view err1',str(e))
                try:
                    source = received_json.get('source')
                    prnt('received -source',source)
                except Exception as e:
                    prnt('declare_node_state_view err2',str(e))
                objData = received_json.get('objData')
                objData_json = json.loads(objData)
                x = 'x2'
                broadcast_to_network = received_json.get('broadcast_to_network',True)
                x = x + objData_json['id']
                try:
                    is_self = received_json.get('is_self')
                except Exception as e:
                    prnt('declare_node_state_view err 3',str(e))
                    is_self = False
                
                from utils.locked import verify_data
                from utils.models import save_sigs, has_profanity
                from network.models import _OperationsChain_genesisId
                self_node = get_self_node()
                if is_self:
                    if has_profanity(objData_json['node_name'], level=3):
                        return JsonResponse({'message' : 'profanity'})
                    else:
                        node_obj = get_or_create_model('Node', id=objData_json['id'])
                        x = 'x2a'
                        prnt('node_obj',node_obj,'self_node',self_node)
                        if node_obj.id == self_node.id:
                            x = 'x4'
                            if verify_data(get_signing_data(objData_json), objData_json['signed']):
                                node, sigs, updatedDB = set_model_attrs(node_obj, objData_json, get_missing_blocks=True)
                                prntDebug('save node')
                                node_is_valid = verify_data(get_signing_data(node), objData_json['signed'])
                                prnt('node_is_valid',node_is_valid, 'updatedDB',updatedDB)
                                if node_is_valid:
                                    node.save(bypass_lock=True, bypass_upk_block=True)
                                    share_with_network(node)
                                    save_sigs(sigs)
                                    nodeChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
                                    if nodeChain:
                                        nodeChain.add_item_to_queue(node_obj)
                                    x = 'x6'
                                    return JsonResponse({'message' : 'Success', 'obj' : get_signing_data(node_obj)})
                elif self_node.activated_dt:
                    if has_profanity(objData_json['node_name'], level=3):
                        return JsonResponse({'message' : 'profanity'})
                    else:
                        node_obj = get_or_create_model('Node', id=objData_json['id'])
                        if str(broadcast_to_network).lower() == 'true':
                            x = 'x7'
                            queue = django_rq.get_queue('main')
                            queue.enqueue(node_obj.broadcast_state, node_data=objData_json, job_timeout=200, result_ttl=3600)

                        x = 'x2ac'
                        if verify_data(get_signing_data(objData_json), objData_json['signed']):
                            node, sigs, updatedDB = set_model_attrs(node_obj, objData_json, get_missing_blocks=True, debug=True)
                            prntDebug('save node', convert_to_dict(node))
                            node_is_valid = verify_data(get_signing_data(node), objData_json['signed'])
                            prnt('node_is_valid',node_is_valid, 'updatedDB',updatedDB)
                            if node_is_valid:
                                node.save(bypass_lock=True, bypass_upk_block=True)
                                share_with_network(node)
                                save_sigs(sigs)
                                if not node.activated_dt:
                                    nodeChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
                                    if nodeChain:
                                        nodeChain.add_item_to_queue(node)
                                return JsonResponse({'message' : 'Success', "nodeId": get_operator_obj('self_nodeId')})
                        return JsonResponse({'message' : 'A problem occured', 'obj':objData,  'err': f'-- is_valid: {is_valid} -- user: {user} -- x: {x}'})
                else:
                    return JsonResponse({'message' : 'self_not_active'})
        return JsonResponse({'message' : 'A problem occured', 'err': f'-- is_valid: {is_valid} -- user: {user} -- x: {x}'})
    except Exception as e:
        prnt('declare_node_state_view fail 1',x,'/',str(e))
        return JsonResponse({'message' : f'A problem occured', 'err': f'{str(e)} -- objData: {objData} -- objData_json: {objData_json}  -- is_valid: {is_valid} -- user: {user} -- x: {x}'})
    
@csrf_exempt
def receive_disavow(request):
    # if enough nodes disavow self_node:
    # operatorData = get_operatorData()
    # operatorData['disavowed'] = True
    # write_operatorData(operatorData)
    pass

@csrf_exempt
def check_if_exists_view(request):
    prnt('-check_if_exists_view')
    from posts.utils import get_client_ip
    sender_ip = get_client_ip(request) 
    if str(sender_ip) == '127.0.0.1' and request.method == 'POST' or assess_received_header(request.headers, allow_inactive=True):

        raw_data = request.body.decode('utf-8')
        received_data = json.loads(raw_data)
        obj_type = received_data.get('type')
        fields = received_data.get('fields', [])
        id_only = received_data.get('id_only', True)
        withold_fields = received_data.get('withold_fields', True)
        prnt('withold_fields',withold_fields,'id_only',id_only,'fields',fields)
        prnt('obj_type',obj_type)
        if obj_type == 'Blockchain':
            genesisId = received_data.get('genesisId')
            obj = get_dynamic_model(obj_type, genesisId=genesisId)
        elif obj_type == 'Block':
            obj_id = received_data.get('obj_id')
            if obj_id:
                obj = Block.objects.filter(id=obj_id).first()
                prnt('obj',obj)
                latest_block = None
                if obj:
                    latest_block = Block.objects.filter(Blockchain_obj=obj.Blockchain_obj, validated=True).order_by('-DateTime').values('id','index').first()
                prnt('latest_block0',latest_block)
                latest_block_index = 0
                if latest_block:
                    latest_block_index = latest_block['index']
            else:
                blockchainId = received_data.get('blockchainId')
                index = received_data.get('index')
                prnt('blockchainId',blockchainId,'index',index)
                obj = get_dynamic_model(obj_type, networkChain=blockchainId, index=index)
                prnt('obj',obj)
                latest_block = Block.objects.filter(networkChain=blockchainId, validated=True).order_by('-index').first()
                prnt('latest_block1',latest_block)
                if latest_block:
                    prnt(latest_block.notes)
                latest_block_index = 0
                if latest_block and 'unsupported_chain' not in latest_block.notes:
                    latest_block_index = latest_block.index
                elif obj:
                    latest_block = Block.objects.filter(Blockchain_obj=obj.Blockchain_obj, validated=True).exclude(notes__unsupported_chain=True).order_by('-DateTime').first()
                    prnt('latest_block2',latest_block)
                    if latest_block:
                        prnt(latest_block.notes)
                        latest_block_index = latest_block.index
                
            if not obj:
                return JsonResponse({'message' : 'Not Found', 'latest_index' : latest_block_index})
            if fields:
                return JsonResponse({'message' : 'Success', 'obj_id' : obj.id, 'latest_index' : latest_block_index, 'requested_fields':{f:getattr(obj, f) for f in fields if has_field(obj, f)}})
            elif withold_fields and id_only:
                return JsonResponse({'message' : 'Success', 'obj_id' : obj.id, 'latest_index' : latest_block_index})
            else:
                return JsonResponse({'message' : 'Success', 'obj' : json.dumps(convert_to_dict(obj, withold_fields=withold_fields)), 'latest_index' : latest_block_index})
        else:
            obj_id = received_data.get('obj_id')
            if not obj_type or obj_type == 'unknown':
                obj_type = obj_id
            obj = get_dynamic_model(obj_type, id=obj_id)

        if obj:
            if fields:
                return JsonResponse({'message' : 'Success', 'obj_id' : obj.id, 'requested_fields':{f:getattr(obj, f) for f in fields if has_field(obj, f)}})
            elif withold_fields and id_only:
                return JsonResponse({'message' : 'Success', 'obj_id' : obj.id})
            else:
                return JsonResponse({'message' : 'Success', 'obj' : json.dumps(convert_to_dict(obj, withold_fields=withold_fields))})
        else:
            prntDebug('obj not found')
            return JsonResponse({'message' : 'Not Found'})

@csrf_exempt
def broadcast_dataPackets_view(request):
    prnt('-broadcast_dataPackets_view')
    # when self_node declares self inactive
    if request.method == 'POST':
        try:
            if assess_received_header(request.headers):
                from network.models import DataPacket

                raw_data = request.body.decode('utf-8')
                received_data = json.loads(raw_data)
                prnt('received_data',received_data) # not receiveing data from node
                if received_data.get('cmd') == 'Broadcast':
                    requested_cmds = json.loads(received_data.get('request'))
                    if string_to_dt(requested_cmds['dt']) >= now_utc() - datetime.timedelta(hours=2):
                        self_node = get_self_node()
                        from utils.models import get_sigData
                        sig_data = get_sigData(requested_cmds)
                        if self_node.User_obj.verify_sig(requested_cmds, sig_data['sig'], sig_data['pk'], keyType='node'):
                            dataPackets = DataPacket.objects.filter(Node_obj=self_node, func='share').exclude(networkChain='chnSoaS7wdvCeJrlED0bpfYY') # op chain datapacket
                            prnt('dataPackets to broadcast',dataPackets)
                            success = None
                            for dp in dataPackets:
                                if len(dp.data.keys()) > 0 or dp.chainId == _OperationsChain_genesisId:
                                    result = dp.broadcast_dp() # this will need to be a worker, node should check is_data_processing
                                    if success == None or success == True:
                                        success = result
                            return JsonResponse({'message' : 'Success', 'result':success})
                    return JsonResponse({'message' : 'Invalid'})
        except Exception as e:
            prnt('broadcast_dataPackets_view fail',str(e))
            return JsonResponse({'message' : 'Fail', 'err':str(e)})

@csrf_exempt
def request_dp_view(request, packet_id):
    prnt('-request_dp_view',packet_id)
    # when self_node declares self inactive
    if request.method == 'POST':
        try:
            if assess_received_header(request.headers):
                queued_job = False
                sender_id = request.headers.get("Senderid")
                chat_queue = django_rq.get_queue("chat")
                if not exists_in_worker('broadcast_dp', queue=chat_queue, iden=packet_id, packet_id=packet_id, target_node=sender_id):
                    from network.models import DataPacket
                    dp = DataPacket.objects.filter(id=packet_id).defer('data').first()
                    if dp:
                        prnt('add to chat worker')
                        chat_queue.enqueue(dp.broadcast_dp, iden=packet_id, packet_id=packet_id, target_node=sender_id, job_timeout=360, result_ttl=3600)
                        queued_job = True
                        return JsonResponse({'message' : 'Success', 'queued_job':queued_job, "nodeId": get_operator_obj('self_nodeId')})
                    else:
                        return JsonResponse({'message' : 'Not Found', 'packet_id':packet_id, "nodeId": get_operator_obj('self_nodeId')})
        except Exception as e:
            prnt('request_dp_view fail',str(e))
            return JsonResponse({'message' : 'Fail', 'err':str(e), "nodeId": get_operator_obj('self_nodeId')})
        

@csrf_exempt
def request_chain_path_view(request):
    prnt('-request_chain_path_view')
    try:
        if not get_self_node().activated_dt:
            return JsonResponse({'message' : 'deactivated_node'})
        if request.method == 'POST':
            if assess_received_header(request.headers, if_self_active=True, allow_inactive=True):
                raw_data = request.body.decode('utf-8')
                received_data = json.loads(raw_data)
                prnt('received_data',type(received_data),received_data)
                blockchainId = received_data.get('blockchainId', None)
                count = int(received_data.get('count', 50))
                start = received_data.get('start', None)
                hash_history = received_data.get('hash_history', None)
                prntDebug('blockchainId',blockchainId,'count',count,'start',start)
                if blockchainId:
                    chain = Blockchain.objects.filter(id=blockchainId).exists()
                    if not chain:
                        return JsonResponse({'message' : 'Chain Not Found', 'blockchainId' : blockchainId})
                    result = []
                    if start:
                        start_block = Block.objects.filter(networkChain=blockchainId, hash=start, validated=True).values('index','hash').first()
                        if start_block:
                            preceeding = Block.objects.filter(networkChain=blockchainId, index__lt=start_block['index'], validated=True).values('hash').order_by('-index')[:int(count/2)]
                            proceeding = Block.objects.filter(networkChain=blockchainId, index__gt=start_block['index'], validated=True).values('hash').order_by('index')[:int(count/2)]
                            result = [b['hash'] for b in reversed(preceeding)] + [start_block['hash']] + [b['hash'] for b in proceeding]
                            prnt('result2:',result)
                    elif hash_history:
                        block = Block.objects.filter(networkChain=blockchainId, hash__in=hash_history, validated=True).values("id","index").order_by('-index').first()
                        if block:
                            blocks = Block.objects.filter(networkChain=blockchainId, index__gte=block['index'], validated=True).values("id","hash").order_by('index','created')[:count]
                            result = [b['hash'] for b in blocks]
                    else:
                        blocks = Block.objects.filter(networkChain=blockchainId, validated=True).values('hash').order_by('-index')[:count]
                        result = [b['hash'] for b in reversed(blocks)]
                        prnt('result1:',result)
                    return JsonResponse({'message' : 'Success', 'result': json.dumps(result)})
    except Exception as e:
        prnt('request_chain_path_view fail',str(e))
        return JsonResponse({'message' : 'Error', 'blockchainId' : blockchainId, 'error': str(e)})

@csrf_exempt
def is_data_processing_view(request, iden):
    prnt('-is_data_processing_view',iden) # only used by nodemanager for syncDB, normal data process runs on low
    if assess_received_header(request.headers):
        dp = DataPacket.objects.filter(id=iden).first()
        if dp:
            if 'completed' in dp.func:
                return JsonResponse({'message' : 'Success', 'result':'completed', 'iden': dp.id})
            elif 'fail' in dp.func:
                return JsonResponse({'message' : 'Success', 'result':'failed', 'status': dp.func, 'iden': dp.id})
            else:
                queue = django_rq.get_queue('main')
                if not exists_in_worker('process_received_data', queue=queue, id=dp.id):
                    queue.enqueue(process_received_data, dp.id, downstream_worker=False, skip_log_check=True, job_timeout=3000, result_ttl=3600)
                    return JsonResponse({'message' : 'Success', 'result':'running', 'iden': dp.id, 'added_to_queue':True})
                else:
                    return JsonResponse({'message' : 'Success', 'result':'running', 'iden': dp.id, 'added_to_queue':False})
        else:
            prnt('no dp')
            return JsonResponse({'message' : 'not found', 'result':'not running'})
    return JsonResponse({'message' : 'fail', 'result':'error'})

@csrf_exempt
def check_latest_data_view(request, model_type):
    prnt('-check_latest_data_view',model_type)
    if assess_received_header(request.headers, return_is_self=True):
        latest_obj_count = 'x'
        if 'Blocks' in model_type:
            if model_type == 'User_Blocks':
                latest_obj = Block.objects.filter(Blockchain_obj__genesisType='User', validated=True).order_by('-DateTime').first()
            elif model_type == 'Wallet_Blocks':
                # was causing datetime issues because of multiple chains, just gets the very first block for syncing
                latest_obj = Block.objects.filter(Blockchain_obj__genesisType='Wallet', validated=True).order_by('-DateTime').first()
            else:
                a = model_type.find('-')
                genesisId = model_type[:a]
                prnt('genesisId',genesisId)
                latest_obj = Block.objects.filter(Blockchain_obj__genesisId=genesisId, validated=True).exclude(notes__unsupported_chain=True).order_by('-DateTime').first()
                prnt('latest_obj1',latest_obj)
        elif model_type == 'Users-Keys':
            latest_obj = None
            date_data = []
            latest_user = User.objects.order_by('-lastUpdate').first()
            if latest_user:
                date_data.append([latest_user, latest_user.lastUpdate])
            latest_key = UserPubKey.objects.exclude(Block_obj=None).order_by('-lastUpdate').first()
            if latest_key:
                date_data.append([latest_key, latest_key.lastUpdate])
            if date_data:
                try:
                    latest_obj, latest_obj_dt = max(date_data, key=lambda x: x[1])
                except:
                    pass

        else:
            model = get_model(model_type)
            if has_field(model, 'Validator_obj') and has_field(model, 'Block_obj'):
                latest_obj = model.objects.exclude(Block_obj=None).exclude(Validator_obj=None).order_by(*get_timeData(model(), sort='updated', querying=True)).first()
            elif has_field(model, 'Validator_obj'):
                latest_obj = model.objects.exclude(Validator_obj=None).order_by(*get_timeData(model(), sort='updated', querying=True)).first()
            elif has_field(model, 'Block_obj'):
                latest_obj = model.objects.exclude(Block_obj=None).order_by(*get_timeData(model(), sort='updated', querying=True)).first()
            else:
                latest_obj = model.objects.order_by(*get_timeData(model(), sort='updated', querying=True)).first()
        if latest_obj:
            return JsonResponse({'message' : 'Success', 'model_type':model_type, 'update_dt' : dt_to_string(get_timeData(latest_obj, sort='created')), 'obj_count':latest_obj_count})
        else:
            return JsonResponse({'message' : 'Not Found'})

@csrf_exempt
def receive_data_view(request):
    # from sonodeManager
    prnt('-receive_data_view')
    try:
        if request.method == 'POST':
            if assess_received_header(request.headers):
                func = 'process_received_data'
                if assess_received_header(request.headers, return_is_self=True) or Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).count() == 0:
                    self_node = None
                    self_node_id = get_operator_obj('self_nodeId')
                    prnt('self_node_id',self_node_id)
                    if self_node_id:
                        self_node = Node.objects.filter(id=self_node_id).only('id').first()
                    if self_node:
                        prnt('self_nodexx',self_node.id)
                        packet_creator = self_node.id
                    elif not Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).count():
                        packet_creator = None
                    else:
                        packet_creator = 'from_header'
                    prnt('packet_creator',packet_creator)

                    run_as_worker = True
                    if run_as_worker:
                        dp, is_last = receive_data(request, dp_name='process_received_data', packet_creator=packet_creator)
                        prnt('last:',is_last,'dp',dp,'dpfunc:',dp.func)
                        if is_last and dp and "completed" not in dp.func:
                            if 'received_data' not in dp.func:
                                dp.func = dp.func + '_' + func
                                dp.save()
                            queue = django_rq.get_queue("main")
                            if not exists_in_worker('process_received_data', queue=queue, id=dp.id):
                                queue.enqueue(process_received_data, dp.id, downstream_worker=False, skip_log_check=True, get_missing_blocks=False, override_completed=True, job_timeout=3000, result_ttl=3600)

                            return JsonResponse({'message' : 'Success', 'iden': dp.id})
                else:
                    dp, is_last = receive_data(request, dp_name='process_received_data')
                    prnt('last:',is_last,'dp',dp,'dpfunc:',dp.func)
                    if is_last and dp and "completed" not in dp.func:
                        if 'received_data' not in dp.func:
                            dp.func = dp.func + '_' + func
                            dp.save()
                        queue = django_rq.get_queue('low')
                        if not exists_in_worker('process_received_data', queue=queue, id=dp.id):
                            queue.enqueue(process_received_data, dp.id, job_timeout=600, result_ttl=3600)
                    return JsonResponse({'message' : 'Success', 'iden': dp.id})

    except Exception as e:
        return JsonResponse({'message' : 'Fail', 'error' : str(e)})
    return JsonResponse({'message' : 'Fail', 'error' : 'None'})

max_obj_send_count = 150

@csrf_exempt
def request_data_view(request):
    prnt('--request_data_view')
    e = 'e'
    err = 'x'
    try:
        if not get_self_node().activated_dt:
            return JsonResponse({'message' : 'deactivated_node'})
        if request.method == 'POST':
            if assess_received_header(request.headers, if_self_active=True, allow_inactive=True):
                proceed = False
                raw_data = request.body.decode('utf-8')
                received_data = json.loads(raw_data)

                try:
                    userData = json.loads(received_data.get('userData'))
                except Exception as e:
                    pass
                try:
                    nodeData = json.loads(received_data.get('nodeData'))
                    senderId = nodeData['id']
                except Exception as e:
                    pass
                    nodeData = {}
                    senderId = received_data.get('senderId')
                prnt('senderId',senderId)
                
                try:
                    requested_data = json.loads(received_data.get('request'))
                    prntDebug('requested_data_len',sum(items if isinstance(items, int) else len(items) for items in requested_data.values()),'requested_data',str(requested_data)[:1000])
                except Exception as e:
                    pass
                if 'hashed' in requested_data:
                    hashed = requested_data['hashed']
                else:
                    hashed = None

                obj_type = requested_data['type']
                prnt(f'obj_type:{obj_type}-- hello Im here!! senderId:{senderId}')
                err = 'validating request'
                received_dt = string_to_dt(request.headers.get('Signed-Dt'))
                if received_dt < now_utc() + datetime.timedelta(minutes=1) and received_dt >= now_utc() - datetime.timedelta(minutes=4):
                    if 'requested_update_dt' in requested_data and requested_data['requested_update_dt']:
                        requested_update_dt = string_to_dt(requested_data['requested_update_dt'])
                    else:
                        requested_update_dt = None
                    try:
                        sigData = get_sigData(requested_data)
                        sig = sigData['sig']
                    except:
                        sig = requested_data['signed']
                    requesting_node = Node.objects.filter(id=senderId).first()
                    from utils.locked import sort_for_sign, verify_data
                    if requesting_node:
                        err = 'node found'
                        if not requesting_node.expelled_dt and hashed and requesting_node.User_obj.verify_sig(hashed, sig, simple_verify=True, keyType='node', signed_dt=request.headers.get('Signed-Dt'), nodeId=senderId) or not requesting_node.expelled_dt and requesting_node.User_obj.verify_sig(sort_for_sign(requested_data), sig, simple_verify=True, keyType='node', signed_dt=request.headers.get('Signed-Dt'), nodeId=senderId):
                            proceed = True
                            err = 'request valid'
                    elif userData:
                        user = User.objects.filter(id=userData['id']).first()
                        if user and nodeData:
                            err = 'creating node'
                            if user.verify_sig(sort_for_sign(requested_data), sig, simple_verify=True, keyType='node', signed_dt=request.headers.get('Signed-Dt'), nodeId=senderId):
                                if user.verify_sig(get_signing_data(nodeData), get_sigData(nodeData['signed'])['sig'], keyType='node', signed_dt=request.headers.get('Signed-Dt'), nodeId=senderId):
                                    node = get_or_create_model(nodeData['objType'], id=nodeData['id'])
                                    from utils.models import sync_model
                                    node, sigs, valid_obj, updatedDB = sync_model(node, nodeData)
                                    if valid_obj:
                                        proceed = True
                                        err = 'node created'
                        else:
                            err = 'attempting to create objs' # likely not working
                            if verify_data(get_signing_data(userData), get_sigData(userData['signed'])['sig']):
                                if verify_data(get_signing_data(nodeData), get_sigData(nodeData['signed'])['sig']):
                                    err = 'creation data valid'
                                    user = User()
                                    for key, value in userData.items():
                                        if value != 'None':
                                            if value == 'Val:N':
                                                value = None
                                            elif str(value).lower() == 'false':
                                                value = False
                                            elif str(value).lower() == 'true':
                                                value = True
                                            setattr(user, key, value)
                                    user.save(share=False, is_new=True)
                                    user, sigs, valid_obj, updatedDB = sync_model(user, userData)
                                    if valid_obj:
                                        err = 'user good'
                                        node = get_or_create_model(nodeData['objType'], id=nodeData['id'])
                                        node, sigs, valid_obj, updatedDB = sync_model(node, nodeData)
                                        if valid_obj:
                                            err = 'node good'
                                            # proceed = True
                if not proceed:
                    prnt('not proceeding')
                else:
                    from itertools import islice
                    err = 'proceeding'
                    data_to_send = []
                    found_items = []
                    not_found = []
                    validators = []
                    max_send = False
                    index = 0
                    total_mbs = 0
                    to_send_items = []
                    sending_idens = []
                    compressed_data = []
                    from utils.models import is_id, to_megabytes, logEvent, compress_data, get_model_prefix, seperate_by_type, sigData_to_hash
                    from utils.locked import check_commit_data
                    if obj_type == 'Blockchain':
                        genesisId = requested_data['genesisId']
                        try:
                            if is_id(genesisId):
                                chain = Blockchain.objects.filter(genesisId=genesisId).first()
                            else:
                                chain = Blockchain.objects.filter(genesisName=genesisId).first()
                            if not chain:
                                return JsonResponse({'message' : 'Not Found', 'type':obj_type, 'genesisId' : genesisId})
                            else:
                                gen = chain.get_genesis_pointer()
                                return JsonResponse({'message' : 'Success', 'type':obj_type, 'content' : json.dumps([convert_to_dict(gen)]), 'blockchain_obj' : json.dumps(convert_to_dict(chain))})
                        except Exception as e:
                            return JsonResponse({'message' : 'Not Found', 'type':obj_type, 'genesisId' : genesisId, 'error' : str(e)})
                    elif obj_type == 'Block':

                        if 'blockchainId' in requested_data:
                            blockchainId = requested_data['blockchainId']
                        else:
                            blockchainId = None
                        if 'iden' in requested_data:
                            iden = requested_data['iden']
                        else:
                            iden = None
                        if 'include_content' in requested_data:
                            include_content = requested_data['include_content']
                        else:
                            include_content = False
                        if 'include_validators' in requested_data:
                            include_validators = requested_data['include_validators']
                        else:
                            include_validators = True
                        if 'item_count' in requested_data:
                            item_count = requested_data['item_count']
                        else:
                            item_count = 3
                        if 'items' in requested_data:
                            requested_items = requested_data['items']
                        else:
                            requested_items = {}
                        if 'hash_history' in requested_data:
                            hash_history = requested_data['hash_history']
                        else:
                            hash_history = []
                        if 'index' in requested_data:
                            index = requested_data['index']
                            try:
                                index = int(index)
                            except Exception as e:
                                prnt('err 7421', str(e))
                        else:
                            index = 1
                        if 'force_check' in requested_data:
                            force_check = requested_data['force_check']
                        else:
                            force_check = False
                        prntDebug('blockchainId',blockchainId,'include_validators',include_validators,'index',index,type(index))
                        chain = None
                        if blockchainId:
                            chain = Blockchain.objects.filter(id=blockchainId).first()
                            if not chain:
                                return JsonResponse({'message' : 'Not Found', 'type':obj_type, 'blockchainId' : blockchainId})
                        try:
                            blocks = None
                            if not blocks and iden:
                                if isinstance(iden, list):
                                    blocks = Block.objects.filter(id__in=iden).defer("data","extraData","notes")
                                else:
                                    blocks = [Block.objects.filter(id=iden).defer("data","extraData","notes").first()]
                            if not blocks and requested_items:
                                prnt('3 requested_items:',requested_items)
                                if isinstance(requested_items, list):
                                    blocks = Block.objects.filter(id__in=requested_items).defer("data","extraData","notes").order_by('index', 'created')
                                elif isinstance(requested_items, dict):
                                    from itertools import chain as chain_tool
                                    blocks = Block.objects.filter(id__in=list(chain_tool.from_iterable(requested_items.values()))).defer("data","extraData","notes").order_by('index', 'created')
                                else:
                                    blocks = [Block.objects.filter(id=requested_items).defer("data","extraData","notes").order_by('index', 'created').first()]
                            if chain:
                                if not blocks and isinstance(index, int):
                                    blocks = Block.objects.filter(Blockchain_obj=chain, index__gte=index, validated=True).defer("data","extraData","notes").order_by('index', 'created')
                                if not blocks and is_id(index):
                                    block = Block.objects.filter(Blockchain_obj=chain, id=index).defer("data","extraData","notes").order_by('index', 'created').first()
                                    if block:
                                        index = block.index
                                        blocks = [block]
                                if not blocks and isinstance(index, str):
                                    block = []
                                    block = Block.objects.filter(Blockchain_obj=chain, hash=index).defer("data","extraData","notes").order_by('-index').first()
                                    if block:
                                        index = block.index
                                        blocks = Block.objects.filter(Blockchain_obj=chain, index__gte=block.index, validated=True).defer("data","extraData","notes").order_by('index','created')[:item_count]
                                if not blocks and hash_history:
                                    block = Block.objects.filter(Blockchain_obj=chain, hash__in=hash_history, validated=True).defer("data","extraData","notes").order_by('-index').first()
                                    if block:
                                        index = block.index
                                        blocks = Block.objects.filter(Blockchain_obj=chain, index__gte=index, validated=True).defer("data","extraData","notes").order_by('index','created')
                            prnt('blocks',blocks)
                            if not blocks:
                                return JsonResponse({'message' : 'Not Found', 'type':obj_type, 'blockchainId' : blockchainId, 'index' : index})
                            elif item_count == 'single' or item_count == 1:
                                
                                block_content = []
                                block = blocks[0]
                                index = block.index
                                prnt('block in question',block)
                                transaction_obj = None
                                transaction_data = block.get_transaction_data()
                                if transaction_data:
                                    transaction_obj = json.dumps(transaction_data)
                                if block and str(include_content) == 'True':
                                    prnt('block and include_content')
                                    block_content = block.get_full_data()
                                    if transaction_obj:
                                        block_content.insert(0, transaction_data)
                                    block_content.insert(0, convert_to_dict(block, exclude=['notes','validations']))
                                elif block and str(include_validators) == 'True':
                                    prnt('block and include_validators')
                                    block_content = block.get_validators()
                                    if transaction_obj:
                                        block_content.insert(0, transaction_data)
                                    block_content.insert(0, convert_to_dict(block, exclude=['notes','validations']))
                                if str(include_content).lower() == 'true':
                                    block_content = compress_data(block_content)
                                else:
                                    block_content = json.dumps(block_content)
                                future_block_count = Block.objects.filter(networkChain=block.networkChain, index__gt=block.index, validated=True).exists() 
                                if future_block_count:
                                    end_of_chain = False
                                else:
                                    end_of_chain = True
                                return JsonResponse({'message' : 'Success', 'type':obj_type, 'block_obj' : json.dumps(convert_to_dict(block, exclude=['notes','validations'])), 'transaction_obj':transaction_obj, 'index' : index, 'content' : block_content, 'force_check':force_check, 'end_of_chain':end_of_chain})
                            elif item_count:
                                prntDebug('else items',item_count)
                                if any(b for b in blocks if b.index >= index):
                                    blocks = [b for b in blocks if b.index >= index]
                                prntDebug('blocks',blocks)
                                block_list = []
                                block_idens = []
                                end_of_chain = True
                                for block in blocks[:item_count]:
                                    if block.index > index:
                                        index = block.index
                                    opBlock = Block.objects.filter(id=block.opBlockId).values('hash').first()
                                    future_block_count = Block.objects.filter(networkChain=block.networkChain, index__gt=block.index, validated=True).count() 
                                    data = {
                                        'block_dict' : convert_to_dict(block, exclude=['notes','validations']),
                                        'block_transaction' : block.get_transaction_data(),
                                        'validations' : block.get_validators(),
                                        'block_data' : [],
                                        'future_block_count':future_block_count,
                                        'opBlock':block.opBlockId,
                                        'opBlock_hash':opBlock['hash'] if opBlock else None
                                    }
                                    block_list.append(data)
                                    block_idens.append(block.id)
                                    prntDebug('b add', block.index)
                                    if future_block_count:
                                        end_of_chain = False
                                    else:
                                        end_of_chain = True
                                block_list = json.dumps(block_list)
                                prntDebug('sending block_list',str(block_list)[:1000])
                                if len(blocks) > 1 or str(include_content).lower() == 'true':
                                    block_list = compress_data(block_list)
                                return JsonResponse({'message' : 'Success', 'type' : 'Blocks', 'blockchainId' : block.networkChain, 'genesisId':block.Blockchain_obj.genesisId, 'block_idens':block_idens, 'block_list' : block_list, 'index' : index, 'end_of_chain' : end_of_chain, 'force_check':force_check})
                        except Exception as e:
                            prnt('request data fail 7531',str(e))
                            return JsonResponse({'message' : 'Not Found', 'type':obj_type, 'blockchainId' : blockchainId, 'index' : index, 'error' : str(e)})
                    elif obj_type == 'Transaction':
                        iden = requested_data['iden']
                        block_type = requested_data['block_type']
                        from transactions.models import Transaction
                        tx = Transaction.objects.filter(id=iden).first()
                        if not tx:
                            return JsonResponse({'message' : 'Not Found', 'tx' : None})
                        if block_type == 'receiver':
                            blocks = Block.objects.filter(Transaction_obj=tx).exclude(id=tx.senderBlockId)
                        elif block_type == 'sender':
                            blocks = Block.objects.filter(id=tx.senderBlockId)
                        else:
                            blocks = Block.objects.filter(Transaction_obj=tx)
                        if not blocks:
                            return JsonResponse({'message' : 'Not Found', 'tx' : tx.id})
                        prntDebug('blocks',blocks)
                        block_list = []
                        block_idens = []
                        for block in blocks:
                            if block.index > index:
                                index = block.index
                            opBlock = Block.objects.filter(id=block.opBlockId).values('hash').first()
                            future_block_count = Block.objects.filter(networkChain=block.networkChain, index__gt=block.index, validated=True).count() 
                            data = {
                                'block_dict' : convert_to_dict(block),
                                'block_transaction' : block.get_transaction_data(),
                                'validations' : block.get_validators(),
                                'block_data' : [],
                                'future_block_count':future_block_count,
                                'opBlock':block.opBlockId,
                                'opBlock_hash':opBlock['hash'] if opBlock else None
                            }
                            block_list.append(data)
                            block_idens.append(block.id)
                        block_list = json.dumps(block_list)
                        prntDebug('sending block_list',str(block_list)[:1000])
                        if len(blocks) > 2:
                            block_list = compress_data(block_list)
                        return JsonResponse({'message' : 'Success', 'type' : 'Blocks', 'blockchainId' : block.networkChain, 'genesisId':block.Blockchain_obj.genesisId, 'block_idens':block_idens, 'block_list' : block_list, 'index' : index, 'end_of_chain' : True if any(b for b in blocks if b.index == block.Blockchain_obj.chain_length) else False, 'force_check':False})
                

                    elif obj_type == 'multi':
                        requested_items = requested_data['items']
                        if 'exclude' in requested_data:
                            exclude = requested_data['exclude']
                        else:
                            exclude = []
                        if 'obj_count' in requested_data:
                            obj_count = requested_data['obj_count']
                        else:
                            obj_count = 'x'
                        if 'index' in requested_data:
                            index = int(requested_data['index'])
                        from posts.models import Update
                        for objType, idList in islice(requested_items.items(), index, index+max_obj_send_count):
                            if requested_update_dt:
                                model = get_model(obj_type)
                                timeField = get_timeData(model(), sort='updated', first_string=True)
                                filter_kwargs = {"id__in": idList, f"{timeField}__gte": requested_update_dt}
                                models = get_dynamic_model(objType, list=True, order_by='created', exclude={"id__in": exclude}, **filter_kwargs)
                            else:
                                models = get_dynamic_model(objType, list=True, exclude={"id__in": exclude}, id__in=idList)
                            if models:
                                for obj in models:
                                    if verify_obj_to_data(obj, obj):
                                        if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj not in validators and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj) and verify_obj_to_data(obj.Validator_obj, obj.Validator_obj):
                                            if obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                                data_to_send.append(obj.Validator_obj)
                                                found_items.append(obj.Validator_obj.id)
                                            # if not validator, add to missing_items
                                        if obj._meta.object_name == 'Person':
                                            update = Update.objects.filter(pointerId=obj.id, validated=True).order_by('-DateTime').first()
                                            if update and update not in data_to_send and update not in exclude:
                                                data_to_send.append(update)
                                                found_items.append(update.id)
                                                if update.Validator_obj and update.Validator_obj not in data_to_send and update.Validator_obj.id not in exclude:
                                                    data_to_send.append(update.Validator_obj)
                                                    found_items.append(update.Validator_obj.id)
                                                # if not validator, add to missing_items
                                        data_to_send.append(obj)
                                        found_items.append(obj.id)
                                        if len(data_to_send) >= max_obj_send_count:
                                            max_send = True
                                            break
                            if objType == 'User': # include upk
                                if requested_update_dt:
                                    model = get_model(obj_type)
                                    timeField = get_timeData(model(), sort='updated', first_string=True)
                                    filter_kwargs = {"User_obj__id__in": idList, f"{timeField}__gte": requested_update_dt}
                                    models = get_dynamic_model('UserPubKey', list=True, order_by='created', exclude={"id__in": exclude}, **filter_kwargs)
                                else:
                                    models = get_dynamic_model('UserPubKey', list=True, exclude={"id__in": exclude}, User_obj__id__in=idList)
                                if models:
                                    for obj in models:
                                        if verify_obj_to_data(obj, obj):
                                            if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj not in validators and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj) and verify_obj_to_data(obj.Validator_obj, obj.Validator_obj):
                                                if obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                                    data_to_send.append(obj.Validator_obj)
                                                    found_items.append(obj.Validator_obj.id)
                                            # if not validator, add to missing_items
                                            data_to_send.append(obj)
                                            found_items.append(obj.id)
                                            if len(data_to_send) >= max_obj_send_count:
                                                max_send = True
                            if len(data_to_send) >= max_obj_send_count:
                                break
                        
                        for objType, idList in islice(requested_items.items(), index, index+max_obj_send_count):
                            for i in idList:
                                if i not in found_items:
                                    not_found.append(i)
                        if not_found:
                            delLogs = EventLog.objects.filter(type='Deletion_Log', data__has_any_key=not_found)
                            not_found_list = not_found
                            for log in delLogs:
                                add_to_send = False
                                for i in not_found_list:
                                    if i in log:
                                        not_found.remove(i)
                                        add_to_send = True
                                if add_to_send:
                                    data_to_send.append(log)
                        prntDebug('not_found_len',not_found,'found_items_len',len(found_items),'found_items',found_items)
                        total_mbs = 0
                        to_send_items = []
                        sending_idens = []
                        for d in data_to_send:
                            if d.id not in exclude:
                                mbs = to_megabytes(d)
                                if (total_mbs + mbs) < 45:
                                    total_mbs += mbs
                                    to_send_items.append(convert_to_dict(d))
                                    sending_idens.append(d.id)
                                else:
                                    max_send = True
                                    break
                        if to_send_items:
                            if max_send:
                                index = len(to_send_items)
                            compressed_data = compress_data(to_send_items)
                            # logEvent('returning_request_data', code='7193', extra={'returned_data':sending_idens})
                            return JsonResponse({'message' : 'Success', 'type':obj_type, 'content' : compressed_data, 'not_found' : not_found, 'returning_idens':sending_idens, 'index':index})
                        else:
                            return JsonResponse({'message' : 'Not Found', 'type':obj_type})
                    elif obj_type == 'Users-Keys':
                        if 'exclude' in requested_data:
                            exclude = requested_data['exclude']
                        else:
                            exclude = []
                        items = requested_data['items']
                        index = 'NA'
                        for model_type in ['User','UserPubKey']:
                            if items == 'All':
                                index = requested_data['index']
                                if requested_update_dt:
                                    models = get_dynamic_model(model_type, list=[int(index), int(index) + max_obj_send_count], order_by='created', exclude={"id__in": exclude}, last_update__gte=requested_update_dt)
                                else:
                                    models = get_dynamic_model(model_type, list=[int(index), int(index) + max_obj_send_count], order_by='created', exclude={"id__in": exclude})
                            else:
                                if requested_update_dt:
                                    models = get_dynamic_model(model_type, list=True, order_by='created', exclude={"id__in": exclude}, last_update__gte=requested_update_dt, id__in=items)
                                else:
                                    models = get_dynamic_model(model_type, list=True, order_by='created', exclude={"id__in": exclude}, id__in=items)
                            if models:
                                for obj in models:
                                    if verify_obj_to_data(obj, obj):
                                        if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj not in validators and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj) and verify_obj_to_data(obj.Validator_obj, obj.Validator_obj):
                                            if obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                                data_to_send.append(obj.Validator_obj)
                                                found_items.append(obj.Validator_obj.id)
                                        data_to_send.append(obj)
                                        found_items.append(obj.id)
                        if items != 'All':
                            for i in items:
                                if i not in found_items:
                                    not_found.append(i)
                            if not_found:
                                delLogs = EventLog.objects.filter(type='Deletion_Log', data__has_any_key=not_found)
                                not_found_list = not_found
                                for log in delLogs:
                                    add_to_send = False
                                    for i in not_found_list:
                                        if i in log:
                                            not_found.remove(i)
                                            add_to_send = True
                                    if add_to_send:
                                        data_to_send.append(log)
                        if data_to_send:
                            if len(data_to_send) >= max_obj_send_count:
                                index = int(index) + max_obj_send_count
                            else:
                                index == 'NA'
                            for d in data_to_send:
                                if d.id not in exclude:
                                    mbs = to_megabytes(d)
                                    if (total_mbs + mbs) < 45:
                                        total_mbs += mbs
                                        to_send_items.append(convert_to_dict(d))
                                        sending_idens.append(d.id)
                                    else:
                                        max_send = True
                                        break
                            prnt('to_send_items',to_send_items)
                            compressed_data = compress_data(to_send_items)
                            return JsonResponse({'message' : 'Success', 'type':obj_type, 'content' : compressed_data, 'not_found' : not_found, 'returning_idens':sending_idens, 'index' : index})
                        else:
                            return JsonResponse({'message' : 'Not Found', 'type':obj_type, 'index' : index})
                    elif 'Blocks' in obj_type:
                        a = obj_type.find('_')
                        genesisType = obj_type[:a]

                        if 'index' in requested_data:
                            index = requested_data['index']
                        else:
                            index = 0
                        prnt('hIYA','index',index,'requested_update_dt',requested_update_dt)
                        if requested_update_dt:
                            blocks = Block.objects.filter(Blockchain_obj__genesisType=genesisType, validated=True, DateTime__gte=requested_update_dt).order_by('DateTime','index').values('id', 'DateTime')
                            requested_update_dt = dt_to_string(requested_update_dt)
                            index = int(index) + max_obj_send_count
                        else:
                            blocks = Block.objects.filter(Blockchain_obj__genesisType=genesisType, validated=True).order_by('DateTime','index').values('id', 'DateTime')
                            index = int(index) + max_obj_send_count
                        if blocks:
                            result = [{dt_to_string(obj['DateTime']): obj['id']} for obj in blocks]
                            prnt('count',len(result))
                            if len(blocks) < max_obj_send_count:
                                index = 'end'
                            return JsonResponse({'message' : 'Success', 'type':obj_type, 'block_ids' : json.dumps(result), 'index' : index, 'requested_update_dt' : requested_update_dt})
                        elif int(index) >= max_obj_send_count:
                            return JsonResponse({'message' : 'Success', 'type':obj_type, 'block_ids' : json.dumps([]), 'index' : 'end', 'requested_update_dt' : requested_update_dt})
                        else:
                            prnt('no models found')
                            return JsonResponse({'message' : 'None Found', 'type':obj_type})
                    else:
                        items = requested_data['items']
                        prnt('elsea',obj_type,items)
                        if 'exclude' in requested_data:
                            exclude = requested_data['exclude']
                        else:
                            exclude = []
                        if 'obj_count' in requested_data:
                            obj_count = requested_data['obj_count']
                        else:
                            obj_count = 'x'
                        index = 'NA'
                        if items == 'All':
                            index = requested_data['index']
                            if requested_update_dt:
                                model = get_model(obj_type)
                                timeField = get_timeData(model(), sort='updated', first_string=True)
                                filter_kwargs = {f"{timeField}__gte": requested_update_dt}
                                models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count], order_by='created', **filter_kwargs)
                            else:
                                models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count])
                            index = int(index) + max_obj_send_count
                            if models:
                                for obj in models:
                                    if obj.id not in exclude and verify_obj_to_data(obj, obj):
                                        data_to_send.append(obj)
                                    if has_field(obj, 'Validator_obj') and obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                        data_to_send.append(obj.Validator_obj)
                        elif obj_type == 'Region' and items == 'networkSupported':
                            index = requested_data['index']
                            if requested_update_dt:
                                models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count], order_by='created', last_update__gte=requested_update_dt, is_supported=True)
                            else:
                                models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count], is_supported=True)
                            index = int(index) + max_obj_send_count
                            if models:
                                for obj in models:
                                    if obj.id not in exclude and verify_obj_to_data(obj, obj):
                                        data_to_send.append(obj)
                                    if has_field(obj, 'Validator_obj') and obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                        data_to_send.append(obj.Validator_obj)
                        elif obj_type == 'Validators_only':
                            vals = []
                            for objType, idList in items.items():
                                val_idens = [i for i in idList if i.startswith(get_model_prefix('Validator'))]
                                validated_idens = [i for i in idList if not i.startswith(get_model_prefix('Validator'))] # get validators for these items
                                if val_idens:
                                    objs = Validator.objects.filter(id__in=val_idens).exclude(id__in=exclude)
                                    for obj in objs:
                                        vals.append(obj)
                                if validated_idens:
                                    for model_name, iden_list in seperate_by_type(validated_idens).items():
                                        objs = get_dynamic_model(model_name, list=True, exclude={"id__in": exclude}, id__in=iden_list)
                                        for obj in objs:
                                            if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj not in vals and obj.Validator_obj.is_valid and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj):
                                                vals.append(obj.Validator_obj)
                                            elif has_field(obj, 'validations'):
                                                validators = Validator.objects.filter(id__in=[v_id for v_id in obj.validations])
                                                for v in validators:
                                                    vals.append(v)
                            data_to_send = [obj for obj in vals if verify_obj_to_data(obj, obj)]
                            if data_to_send:
                                for d in data_to_send:
                                    if d.id not in exclude:
                                        mbs = to_megabytes(d)
                                        if (total_mbs + mbs) < 45:
                                            total_mbs += mbs
                                            to_send_items.append(convert_to_dict(d))
                                            sending_idens.append(d.id)
                                        else:
                                            max_send = True
                                            break
                                compressed_data = compress_data(to_send_items)
                            return JsonResponse({'message' : 'Success', 'type':'Validator', 'content' : compressed_data, 'returning_idens':sending_idens, 'index' : index})

                        else:
                            if 'index' in requested_data:
                                index = int(requested_data['index'])
                            else:
                                index = 0
                            if obj_type == 'User': # include upk
                                if isinstance(items, dict):
                                    if obj_type in items:
                                        items = items[obj_type]
                                if requested_update_dt:
                                    model = get_model(obj_type)
                                    timeField = get_timeData(model(), sort='updated', first_string=True)
                                    filter_kwargs = {"id__in": idList, f"{timeField}__gt": requested_update_dt}
                                    models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count], order_by='created', exclude={"id__in": exclude}, **filter_kwargs)
                                else:
                                    models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count], exclude={"id__in": exclude}, id__in=idList)
                                if models:
                                    for obj in models:
                                        if verify_obj_to_data(obj, obj):
                                            if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj not in validators and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj) and verify_obj_to_data(obj.Validator_obj, obj.Validator_obj):
                                                if obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                                    data_to_send.append(obj.Validator_obj)
                                                    found_items.append(obj.Validator_obj.id)
                                            # if not validator, add to missing_items
                                            if obj._meta.object_name == 'Person':
                                                update = Update.objects.filter(pointerId=obj.id, validated=True).order_by('-DateTime').first()
                                                if update and update not in data_to_send and update not in exclude:
                                                    data_to_send.append(update)
                                                    found_items.append(update.id)
                                                    if update.Validator_obj and update.Validator_obj not in data_to_send and update.Validator_obj.id not in exclude:
                                                        data_to_send.append(update.Validator_obj)
                                                        found_items.append(update.Validator_obj.id)
                                                    # if not validator, add to missing_items
                                            data_to_send.append(obj)
                                            found_items.append(obj.id)
                                if requested_update_dt:
                                    model = get_model(obj_type)
                                    timeField = get_timeData(model(), sort='updated', first_string=True)
                                    filter_kwargs = {"User_obj__id__in": found_items, f"{timeField}__gt": requested_update_dt}
                                    models = get_dynamic_model('UserPubKey', list=True, order_by='created', exclude={"id__in": exclude}, **filter_kwargs)
                                else:
                                    models = get_dynamic_model('UserPubKey', list=True, exclude={"id__in": exclude}, User_obj__id__in=found_items)
                                if models:
                                    for obj in models:
                                        if verify_obj_to_data(obj, obj):
                                            if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj not in validators and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj) and verify_obj_to_data(obj.Validator_obj, obj.Validator_obj):
                                                if obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                                    data_to_send.append(obj.Validator_obj)
                                                    found_items.append(obj.Validator_obj.id)
                                                # if not validator, add to missing_items
                                            data_to_send.append(obj)
                                            found_items.append(obj.id)

                            else:
                                if isinstance(items, dict):
                                    if obj_type in items:
                                        items = items[obj_type]
                                if requested_update_dt:
                                    model = get_model(obj_type)
                                    timeField = get_timeData(model(), sort='updated', first_string=True)
                                    filter_kwargs = {f"{timeField}__gte": requested_update_dt, "id__in":items}
                                    models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count], order_by='created', exclude={"id__in": exclude}, **filter_kwargs)
                                else:
                                    models = get_dynamic_model(obj_type, list=[int(index), int(index) + max_obj_send_count], exclude={"id__in": exclude}, id__in=items)
                                if models:
                                    for obj in models:
                                        if verify_obj_to_data(obj, obj):
                                            if has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj not in validators and obj.id in obj.Validator_obj.data and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj) and verify_obj_to_data(obj.Validator_obj, obj.Validator_obj):
                                                if obj.Validator_obj not in data_to_send and obj.Validator_obj.id not in exclude:
                                                    data_to_send.append(obj.Validator_obj)
                                                    found_items.append(obj.Validator_obj.id)
                                                # if not validator, add to missing_items
                                            data_to_send.append(obj)
                                            found_items.append(obj.id)
                        if data_to_send:
                            prnt('has models', len(models), 'data_to_send',len(data_to_send))
                            total_mbs = 0
                            to_send_items = []
                            sending_idens = []
                            if data_to_send:
                                for d in data_to_send:
                                    if d.id not in exclude:
                                        mbs = to_megabytes(d)
                                        if (total_mbs + mbs) < 45:
                                            total_mbs += mbs
                                            to_send_items.append(convert_to_dict(d))
                                            sending_idens.append(d.id)
                                        else:
                                            max_send = True
                                            break
                            if max_send:
                                index = len(to_send_items)
                            if to_send_items:
                                compressed_data = compress_data(to_send_items)
                            else:
                                compressed_data = []
                            prnt('returning...', total_mbs)
                            return JsonResponse({'message' : 'Success', 'type':obj_type, 'content' : compressed_data, 'returning_idens':sending_idens, 'index' : index})
                        else:
                            if index >= max_obj_send_count:
                                return JsonResponse({'message' : 'Success', 'type':obj_type, 'index':'end'})
                            else:
                                prnt('no models found')
                                return JsonResponse({'message' : 'None Found', 'type':obj_type})
            else:
                return JsonResponse({'message' : 'Fail', 'err' : 'header assessment'})
    except Exception as ex:
        e = str(ex)
        prnt('request data fail 10',str(e))
        pass
    try:
        if not e:
            e = 'wtf?'
    except Exception as e:
        e = 'wtf@!'
        prnt('e',e)
    try:
        return JsonResponse({'message' : 'Fail', 'err' : str(e) + ' -- ' + err})
    except Exception as e:
        return JsonResponse({'message' : 'Fail', 'err2' : str(e) + ' -- ' + err})


@csrf_exempt
def receive_posts_for_validating_view(request):
    prnt('-receive_posts_for_validating_view')
    if request.method != "POST":
        return JsonResponse({"message": "not post method"})

    if assess_received_header(request.headers):
        try:
            dp, is_last = receive_data(request, dp_name='process_posts_for_validating')
            prnt('last:',is_last,'dp',dp,'dpfunc:',dp.func)
            if is_last and dp:
                if 'posts_for_validating' not in dp.func:
                    # only one creator_node, must validate itself
                    dp.func = 'process_posts_for_validating'
                    dp.save(update_fields=['func'])
                if 'completed' not in dp.func and 'failed' not in dp.func or dp.updated_on_node < now_utc() - datetime.timedelta(minutes=15):
                    prnt('add to low worker')
                    queue = django_rq.get_queue('low')
                    if not exists_in_worker('process_posts_for_validating', queue=queue, id=dp.id):
                        from utils.locked import process_posts_for_validating
                        queue.enqueue(process_posts_for_validating, dp.id, job_timeout=600, result_ttl=3600)
            if is_last and dp and dp.updated_on_node < now_utc() - datetime.timedelta(minutes=15):
                status = 'too_soon'
            elif is_last and dp and 'completed' in dp.func:
                status = 'completed'
            elif is_last and dp and 'error' in dp.func or is_last and dp and 'fail' in dp.func:
                status = dp.func
            elif not dp:
                status = 'no_dp'
            else:
                status = 'processing'
            highest_chunk = 'x'
            if dp and 'upload_id' in dp.data and dp.data["upload_id"]:
                def is_int(s):
                    try:
                        int(s)
                        return True
                    except ValueError:
                        return False
                try:
                    highest_chunk = max((k for k in dp.data if is_int(k)), key=lambda k: int(k), default=None)
                    prnt('highest_chunk',highest_chunk)
                except Exception as e:
                    prnt('highest_chunk err x23', str(e))
            return JsonResponse({'message' : 'Success', "nodeId": get_operator_obj('self_nodeId'), 'status':status, 'dp':dp.id, 'last_chunk':highest_chunk})
        except Exception as e:
            return JsonResponse({"message": "failure", "nodeId": get_operator_obj('self_nodeId'), 'error':str(e)})
    
@csrf_exempt
def receive_gathered_data_view(request):
    prnt('-receive_gathered_data_view')
    if request.method != "POST":
        return JsonResponse({"message": "not post method"})

    if assess_received_header(request.headers):
        try:
            dp, is_last = receive_data(request, dp_name='process_posts_for_validating')
            prnt('last:',is_last,'dp',dp,'dpfunc:',dp.func)
            if is_last and dp:
                if 'process_gathered_data' not in dp.func:
                    # only one creator_node, must validate itself
                    dp.func = 'process_gathered_data'
                    dp.save(update_fields=['func'])
                if 'completed' not in dp.func and 'failed' not in dp.func or dp.updated_on_node < now_utc() - datetime.timedelta(minutes=15):
                    prnt('add to low worker')
                    queue = django_rq.get_queue('low')
                    if not exists_in_worker('process_gathered_data', queue=queue, id=dp.id):
                        from utils.locked import process_gathered_data
                        queue.enqueue(process_gathered_data, dp.id, job_timeout=600, result_ttl=3600)
            if is_last and dp and dp.updated_on_node < now_utc() - datetime.timedelta(minutes=15):
                status = 'too_soon'
            elif is_last and dp and 'completed' in dp.func:
                status = 'completed'
            elif is_last and dp and 'error' in dp.func or is_last and dp and 'fail' in dp.func:
                status = dp.func
            elif not dp:
                status = 'no_dp'
            else:
                status = 'processing'
            highest_chunk = 'x'
            if dp and 'upload_id' in dp.data and dp.data["upload_id"]:
                def is_int(s):
                    try:
                        int(s)
                        return True
                    except ValueError:
                        return False
                try:
                    highest_chunk = max((k for k in dp.data if is_int(k)), key=lambda k: int(k), default=None)
                    prnt('highest_chunk',highest_chunk)
                except Exception as e:
                    prnt('highest_chunk err x44', str(e))
            return JsonResponse({'message' : 'Success', "nodeId": get_operator_obj('self_nodeId'), 'status':status, 'dp':dp.id, 'last_chunk':highest_chunk})
        except Exception as e:
            return JsonResponse({"message": "failure", "nodeId": get_operator_obj('self_nodeId'), 'error':str(e)})
    

@csrf_exempt
def receive_event_view(request):
    prnt("-receive_event_view")

    if request.method != "POST":
        return JsonResponse({"message": "not post method"})
    
    if assess_received_header(request.headers):
        try:
            func = request.headers.get("func")
            job_id = request.headers.get("Job-Id")
            job_dt = request.headers.get("Job-Dt")
            sender_id = request.headers.get("Senderid")
            log = EventLog.objects.filter(jobId=job_id, created=string_to_dt(job_dt), func__contains=f"assigned_job:{func}", Node_obj__id=sender_id).only('func').first()
            if log:
                log.func = log.func.replace('assigned','completed')
                log.save(update_fields=['func'])
                try:
                    body_text = request.body.decode("utf-8")
                    received_data = json.loads(body_text)
                    log.data = received_data['content']
                    log.save(update_fields=['data'])
                except Exception as e:
                    prnt('receive_event_view err',str(e))

            
            return JsonResponse({"message": "Success", "nodeId": get_operator_obj('self_nodeId')})
        except Exception as e:
            return JsonResponse({"message": "failure", 'error':str(e), "nodeId": get_operator_obj('self_nodeId')})


@csrf_exempt
def receive_blocks_view(request):
    prnt('--receive_blocks_view',now_utc())

    if request.method != "POST":
        return JsonResponse({"message": "not post method"})

    allow_inactive = False
    if request.headers.get('genesisId') == _OperationsChain_genesisId:
        allow_inactive = True
    if assess_received_header(request.headers, allow_inactive=allow_inactive):
        try:
            dp, is_last = receive_data(request, dp_name='process_received_blocks')
            prnt('last:',is_last,'dp',dp,'dpfunc:',dp.func)
            if is_last and dp:
                if all(c not in dp.func for c in ('completed', 'failed', 'chunked')) or dp.updated_on_node < now_utc() - datetime.timedelta(minutes=20):
                    if not dp.rebroadcast_dt or dp.rebroadcast_dt < now_utc() - datetime.timedelta(hours=1):
                        chat_queue = django_rq.get_queue("chat")
                        if not exists_in_worker('rebroadcast_block', queue=chat_queue, id=dp.id):
                            from utils.models import rebroadcast_block
                            prnt('add to chat worker')
                            chat_queue.enqueue(rebroadcast_block, dp.id, job_timeout=240, result_ttl=3600)

            if is_last and dp and dp.updated_on_node < now_utc() - datetime.timedelta(minutes=25):
                status = 'too_soon'
            elif is_last and dp and 'completed' in dp.func:
                status = 'completed'
            elif is_last and dp and 'error' in dp.func or is_last and dp and 'fail' in dp.func:
                status = dp.func
            elif not dp:
                status = 'no_dp'
            else:
                status = 'processing'
            highest_chunk = 'x'
            if dp and 'upload_id' in dp.data and dp.data["upload_id"]:
                def is_int(s):
                    try:
                        int(s)
                        return True
                    except ValueError:
                        return False
                try:
                    highest_chunk = max((k for k in dp.data if is_int(k)), key=lambda k: int(k), default=None)
                    prnt('highest_chunk',highest_chunk)
                except Exception as e:
                    prnt('highest_chunk err x56', str(e))
            return JsonResponse({"message": "Success", "nodeId": get_operator_obj('self_nodeId'), 'status':status, 'dp':dp.id, 'last_chunk':highest_chunk})
        except Exception as e:
            return JsonResponse({"message": "failure", "nodeId": get_operator_obj('self_nodeId'), 'error':str(e)})

@csrf_exempt
def receive_data_packet_view(request):
    prnt("--receive_data_packet")

    if request.method != "POST":
        return JsonResponse({"message": "not post method"})
    
    if assess_received_header(request.headers):
        try:
            dp, is_last = receive_data(request, dp_name='process_data_packet')
            prnt('last:',is_last,'dp',dp,'dpfunc:',dp.func)
            if is_last and dp:
                if all(c not in dp.func for c in ('completed', 'failed', 'chunked')):
                # if 'completed' not in dp.func and 'failed' not in dp.func:
                    if not dp.rebroadcast_dt or dp.rebroadcast_dt < now_utc() - datetime.timedelta(hours=1):
                    
                        chat_queue = django_rq.get_queue("chat")
                        if not exists_in_worker('rebroadcast_dp', queue=chat_queue, id=dp.id):
                            from utils.models import rebroadcast_dp
                            prnt('add to chat worker')
                            chat_queue.enqueue(rebroadcast_dp, dp.id, job_timeout=240, result_ttl=3600)

            if is_last and dp and dp.updated_on_node < now_utc() - datetime.timedelta(minutes=15):
                status = 'too_soon'
            elif is_last and dp and 'completed' in dp.func:
                status = 'completed'
            elif is_last and dp and 'error' in dp.func or is_last and dp and 'fail' in dp.func:
                status = dp.func
            elif not dp:
                status = 'no_dp'
            else:
                status = 'processing'
            highest_chunk = 'x'
            if dp and 'upload_id' in dp.data and dp.data["upload_id"]:
                def is_int(s):
                    try:
                        int(s)
                        return True
                    except ValueError:
                        return False
                try:
                    highest_chunk = max((k for k in dp.data if is_int(k)), key=lambda k: int(k), default=None)
                    prnt('highest_chunk',highest_chunk)
                except Exception as e:
                    prnt('highest_chunk err x65', str(e))
            return JsonResponse({"message": "Success", "nodeId": get_operator_obj('self_nodeId'), 'status':status, 'dp':dp.id, 'last_chunk':highest_chunk})
        except Exception as e:
            return JsonResponse({"message": "failure", "nodeId": get_operator_obj('self_nodeId'), 'error':str(e)})


def receive_data(request, dp_name='func', packet_creator='from_header', model_type='DataPacket'):
    upload_id = request.headers.get("X-Upload-ID")
    part_number = request.headers.get("X-Part-Number")
    is_last = request.headers.get("X-Last-Part", "false").lower() == "true"
    part_number = int(part_number) if part_number and part_number.isdigit() else None
    packet_id = request.headers.get("Packet-Id")
    sender_id = request.headers.get("Senderid")
    if packet_creator == 'from_header':
        packet_creator = request.headers.get("Packet-Creator")
        prnt('packet_creator',packet_creator)
        if not packet_creator:
            packet_creator = sender_id
    dt = request.headers.get("dt")
    signed_dt = request.headers.get("Signed-Dt")
    prnt('dt',dt,'signed_dt',signed_dt,'part_number',part_number,'is_last',is_last,'sender_id',sender_id,'packet_id',packet_id)
    region_id = request.headers.get("Region-Id")
    func = request.headers.get("func")
    task = int(request.headers.get("task", 1))
    job_id = request.headers.get("Job-Id")
    blockId = request.headers.get("Blockid")
    if blockId:
        dp_name = f'{dp_name}:{blockId}'
    if func:
        dp_name = f'{dp_name}:{func}'
    
    raw_body = request.body
    body_text = ""
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        prnt("decode fail", e)
        return JsonResponse({"message": "fail", "error": "invalid body"}, status=400)

    dp = DataPacket.objects.filter(id=packet_id).first()
    if dp and dp.data and dp.headers and 'chunked' not in dp.func:
        return dp, True
    if not dp:
        dp = DataPacket(
            id=packet_id,
            func=dp_name,
            jobId=job_id,
            task=task,
            created=now_utc(),
            headers=dict(request.headers),
            data={},
        )
    dp.Node_obj_id = packet_creator
    if 'history' not in dp.notes:
        dp.notes['history'] = []
    dp.notes['history'].append({'received':dt_to_string(now_utc()), 'sender':sender_id, 'packet_creator':packet_creator})
    
    headers_dict = dict(request.headers)
    dp.headers = headers_dict
    if upload_id and part_number is not None:
        dp.data["upload_id"] = upload_id
        dp.data[str(part_number)] = body_text
    else:
        # single-part payload
        try:
            received_data = json.loads(body_text)
        except Exception:
            received_data = body_text
        received_data["headers"] = headers_dict
        dp.data = received_data
    if is_last:
        dp.func = dp.func.replace(':chunked','')
    elif 'chunked' not in dp.func:
        dp.func = f"{dp.func}:chunked"
    dp.save()
    return dp, is_last



def get_chain_data_view(request):
    prnt('-get_supported_chains_view')
    # returns genesisId of supported region chains, genesisId == region.id
    from network.models import mandatoryChains, specialChains, _EarthChain_genesisId, _SonetChain_genesisName
    mainChain_data = {i:i for i in mandatoryChains}
    mainChain_data[_SonetChain_genesisName] = Sonet.objects.values('id').first()['id']
    earth = Region.objects.filter(id=_EarthChain_genesisId, Validator_obj__is_valid=True).first()
    prnt('earth',earth)
    prnt('_EarthChain_genesisId',_EarthChain_genesisId)
    for r in Region.objects.all():
        prnt('regions:',r.id,r.Name, r.Validator_obj)
    from accounts.models import User, UserPubKey
    from network.models import Node
    prnt('users:',User.objects.all())
    prnt('upks:',UserPubKey.objects.all())
    prnt('nodes:',Node.objects.all())
    if earth:
        regions = {'Earth':{'type':earth.nameType,'id':earth.id,'children':[]}}
        def get_children(parent, children_list, support_found=False):
            children = Region.objects.filter(ParentRegion_obj=parent, Validator_obj__is_valid=True).order_by('Name')
            for child in children:
                has_support = support_found
                gov = Government.objects.filter(Region_obj=child).exclude(Block_obj=None).first()
                data = {child.Name:{'obj_type':child._meta.object_name,'type':child.nameType,'id':child.id,'reqs':{},'children':[]}}
                if child.data and 'reqs' in child.data:
                    data[child.Name]['reqs'] = child.data['reqs']
                if gov:
                    govData = {gov.gov_level:{'obj_type':gov._meta.object_name,'type':'Government','id':gov.id,'regionId':gov.Region_obj.id,'children':[]}}
                
                    data[child.Name]['children'].append(govData)
                if not has_support and child.is_supported:
                    has_support = True
                if not has_support or has_support and child.is_supported:
                    children_list.append(data)
                    new_list = data[child.Name]['children']
                    xlist = get_children(child, new_list, support_found=has_support)
                    new_list = data[child.Name]['children'] = xlist
                elif has_support and child.is_supported:
                    children_list.append(data)
                
            return children_list

        xlist = get_children(earth, regions['Earth']['children'])
        regions['Earth']['children'] = xlist
        prnt('regions',regions)
        plugin_data = []
        from network.models import Plugin
        plugins = Plugin.objects.exclude(Block_obj=None)
        if plugins:
            for p in plugins:
                data = {'Title':p.Title,'AbbrTitle':p.AbbrTitle,'Subtitle':p.Subtitle,'Description':p.Description,'id':p.id,'user_facing':p.user_facing,'model_prefixes':p.model_prefixes,'user_id':p.User_obj.id,'user_name':p.User_obj.username}
                plugin_data.append(data)
        try:
            sonet = get_signing_data(Sonet.objects.first())
        except:
            sonet = None
        return JsonResponse({'mandatoryChains' : json.dumps(mainChain_data), 'specialChains' : json.dumps(specialChains), 'regionChains' : json.dumps(regions), 'plugins' : json.dumps(plugin_data), 'sonet' : sonet})
    
def get_plugin_data_view(request):
    prnt('-get_plugin_data_view')
    # returns genesisId of supported region chains, genesisId == region.id
    from network.models import Plugin
    plugins = Plugin.objects.all()
    if plugins:
        plugin_data = []
        for p in plugins:
            data = {'Title':p.Title,'AbbrTitle':p.AbbrTitle,'Subtitle':p.Subtitle,'Description':p.Description,'id':p.id,'user_facing':p.user_facing,'model_prefixes':p.model_prefixes,'user_id':p.User_obj.id,'user_name':p.User_obj.username}
            plugin_data.append(data)
        try:
            sonet = get_signing_data(Sonet.objects.first())
        except:
            sonet = None
        return JsonResponse({'plugins' : json.dumps(plugin_data), 'sonet' : sonet})

