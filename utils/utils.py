
# accessed by node manager, be careful about loading packages

from django.db import models
from django.db.models import Q
import django_rq

import datetime
from zoneinfo import ZoneInfo
import pytz
import time
import re
import random
import json
import os
from cryptography.fernet import Fernet
from unidecode import unidecode
import gzip
import base64
import zlib
from pathlib import Path

from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from cryptography.fernet import Fernet

from utils.models import testing, debugging, connect_to_node, get_operator_obj, get_operatorData, request_items, find_or_create_chain_from_object, logError, logEvent, sync_model
from utils.locked import dt_to_string, load_key

current_version = 0.1



import logging
logger = logging.getLogger("django")

def prnt(*args):
    msg = ','.join(f"{i}" for i in args)
    logger.info(f'~:{msg}')


def prntDev(*args):
    if testing():
        msg = '*' + ','.join(str(i) for i in args)
        # print(f'p2:{msg}')
        logger.info(f'~:{msg}')
        # prnt('#',','.join(f"{i}" for i in args))

def prntDebug(*args):
    if debugging() or testing():
        msg = '#' + ','.join(str(i) for i in args)
        logger.info(f'~:{msg}')

def prntn(*args):
    msg = ','.join(f"{i}" for i in args)
    # print(f'p1:{msg}')
    logger.info(f'\n~:{msg}')

def prntDevn(*args):
    if testing():
        msg = '*' + ','.join(str(i) for i in args)
        logger.info(f'\n~:{msg}')

def prntDebugn(*args):
    if debugging() or testing():
        msg = '#' + ','.join(str(i) for i in args)
        logger.info(f'\n~:{msg}')

def string_to_dt(dt_str):
    if isinstance(dt_str, datetime.datetime):
        return dt_str
    if dt_str and isinstance(dt_str, str):
        if dt_str == 'Val:N':
            return None
        if 'Z' in dt_str:
            dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '0+00:00'))
            return dt
        return datetime.datetime.fromisoformat(dt_str)
    return None

def now_utc():
    return datetime.datetime.now(pytz.utc)   

def is_timezone_aware(dt):
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None

def baseline_time():
    from network.models import Sonet
    return Sonet.objects.first().created

def is_dt_string(val):
    if not isinstance(val, str) or len(val) not in [23, 26, 32]:
        return False
    try:
        from dateutil.parser import parse
        parse(val)
        return True
    except Exception:
        return False

def safe_dt(dt):
    if isinstance(dt, datetime.datetime):
        return dt
    if not value_is_none(dt) and isinstance(dt, str):
        try:
            return string_to_dt(dt)
        except:
            pass
    return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

def declare_var(var, val=None):
    if var is None:
        var = val
    return var


def get_timeData(obj, sort='created', querying=False, descending=True, first_string=False):
    # prntDebug('-get_timeData', obj)
    if sort == 'created':
        x = ['created', 'DateTime']
    elif sort == 'updated':
        x = ['lastUpdate', 'created', 'DateTime']
    else:
        x = sort
    if querying or first_string:
        z = 0
        for i in reversed(x):
            if not has_field(obj, i):
                x.remove(i)
            z += 1
        if first_string:
            return x[0]
        if descending:
            x = ['-' + item for item in x]
        return x
    else:
        for i in x:
            if has_field(obj, i):
                if isinstance(obj, models.Model):
                    return getattr(obj, i)
                elif isinstance(obj, dict):
                    try:
                        return string_to_dt(obj[i])
                    except Exception as e:
                        prnt('get_timeData err', str(e))
                        return None
    return None

def chunk_list(data, chunk_size=500):
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]

def chunk_dict(data, chunk_size=500):
    if isinstance(data, dict):
        keys = list(data.keys())
        for i in range(0, len(keys), chunk_size):
            yield {key: data[key] for key in keys[i:i + chunk_size]}
    elif isinstance(data, list):
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]





def string_to_64_char_hash(s): #unused?
    import hashlib
    hash_object = hashlib.sha256(s.encode('utf-8'))
    hex_dig = hash_object.hexdigest()
    return hex_dig

def process_received_dp(data, msg='unspecified', skip_log_check=False, override_completed=False):
    prnt('-process_received_dp')
    from network.models import DataPacket
    def reassemble_chunks(received_data):
        upload_id = received_data.get("upload_id")
        headers = received_data.get("headers", {}) 
        parts = {int(k): v for k, v in received_data.items() if k.isdigit()}
        if not parts:
            raise ValueError("No parts found in received_data")

        ordered = [parts[k] for k in sorted(parts)]
        full_text = "".join(ordered).strip()

        prnt("assembled length:", len(full_text))
        prnt("first_100_chars:", full_text[:100])

        parsed = json.loads(full_text)
        parsed["headers"] = headers
        return upload_id, parsed
    
    def verify_hash(received_data):
        # should also verify publicKey matches senderId
        if 'signed' in received_data: # should always have signed but something didnt, was erroring
            import hashlib
            from utils.locked import sort_for_sign, verify_data
            sig = received_data['signed']
            del received_data['signed']
            received_hashed = received_data['hashed']
            del received_data['hashed']
            headers = None
            if 'headers' in received_data:
                headers = received_data['headers']
                if 'Senderid' in headers:
                    prnt('senderid',headers['Senderid'])
                del received_data['headers']
            actual_hash = hashlib.md5(str(sort_for_sign(received_data)).encode('utf-8')).hexdigest()
            if headers:
                received_data['headers'] = headers
            if actual_hash != received_hashed:
                prnt('fail verify_hash1', 'actual_hash:',actual_hash,'received_hashed:',received_hashed)
                prnt('sort_for_sign(received_data):',sort_for_sign(received_data))
                return False
            if not verify_data(actual_hash, received_data['pubKey'], sig, skip_sort=True):
                prnt('fail verify_hash2', 'actual_hash:',actual_hash,'sig:',sig,"received_data['pubKey']",received_data['pubKey'])
                return False
        return True

    if isinstance(data, str) and is_id(data) and get_pointer_type(data) == 'DataPacket':
        dp = DataPacket.objects.filter(id=data).first()
        prntDebug('dp0',dp)
        if not dp:
            return {}
        data = dp.data
    elif isinstance(data, str) and is_id(data) and get_pointer_type(data) == 'EventLog':
        dp = DataPacket.objects.filter(id=data).first()
        prntDebug('dp1',dp)
        if not dp:
            return {}
        data = dp.data
    elif isinstance(data, models.Model) and data._meta.object_name == 'DataPacket':
        dp = data
        data = dp.data
        prntDebug('data2',dp)
    elif isinstance(data, list):
        prntDebug('list',str(data)[:250])
        return {'data':{'content':data}}
    elif data:
        prnt('returing data',str(data)[:250])
        return {'data':{'content':data}}
    else:
        prntDebug('else')
        dp = None
        data = {}
    if dp and 'completed' in dp.func and not override_completed:
        prnt('already completed',dp.func)
        return {} 
    if dp and 'chunked' in dp.func:
        prnt('is chunked')
        connect_to_node(dp.headers['Senderid'], f'network/request_dp/{dp.id}', timeout=(10,15), attempts=2)
        return {} 

    if dp:
        prnt('creator node:',dp.Node_obj)
        if skip_log_check:
            proceed = True
        else:
            x = 1
            proceed = False
            if verify_hash(dp.data):
                proceed = True
        if not proceed:
            dp.completed(f'{msg}-x:{x}')
            prntDebug('r1')
            return None
        if 'upload_id' in data:
            uid, data = reassemble_chunks(data)
        prntDebug('r2')
        return {'dp':dp, 'data':data}
    if 'upload_id' in data:
        uid, data = reassemble_chunks(data)
    prntDebug('r3')
    return {'data':data}

def err(err, code):
    return err + str(code)

def to_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    elif isinstance(value, str):
        from dateutil.parser import parse
        return parse(value)
    else:
        raise ValueError("Value must be a datetime object or a string")

def str_to_hash(text):
    import hashlib
    text_bytes = str(text).encode('utf-8')
    sha256_hash = hashlib.sha256(text_bytes).hexdigest()
    return sha256_hash

def hash_to_int(hash_string, length):
    filtered_hash = re.sub(r'[^a-fA-F0-9]', '', hash_string)
    hash_int = int(filtered_hash, 16)
    if length == 0:
        return 0
    else:
        return hash_int % length

def date_to_int(date):
    if isinstance(date, str):
        date = string_to_dt(date)
    if not testing():
        from network.models import Sonet
        start_dt = Sonet.objects.first().created
    else:
        start_dt = now_utc() - datetime.timedelta(weeks=1)
    time_difference = date - start_dt
    minutes_difference = time_difference.total_seconds() /60/60
    return int(minutes_difference)

def round_time(dt=None, dir='down', amount='hour'):
    if not dt:
        dt = now_utc()
    if isinstance(dt, str):
        dt = string_to_dt(dt)
    def reduce_hours(dt, hr):
        dt = dt - datetime.timedelta(minutes=dt.minute, seconds=dt.second, microseconds=dt.microsecond)
        hour = dt.hour
        while hour % hr != 0:
            hour -= 1
        dt = dt.replace(hour=hour)
        return dt
    def round_mins(dt, mins, dir='down'):
        r = dt - datetime.timedelta(minutes=(dt.minute % mins), seconds=dt.second, microseconds=dt.microsecond)
        if dir == 'up':
            r = r  + datetime.timedelta(minutes=mins)
        return r
    if dir == 'down':
        if amount == 'hour':
            return dt - datetime.timedelta(minutes=dt.minute, seconds=dt.second, microseconds=dt.microsecond)
        elif amount == 'evenhour':
            return reduce_hours(dt, 2)
        elif amount == '10mins':
            return round_mins(dt, 10)
        elif 'hours' in amount:
            x = amount.find('-')
            hr = int(amount[:x])
            return reduce_hours(dt, hr)
        elif amount == 'day':
            return dt - datetime.timedelta(hours=dt.hour, minutes=dt.minute, seconds=dt.second, microseconds=dt.microsecond)
        elif amount == 'week':
            return (dt - datetime.timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif amount == 'month':
            return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif dir == 'up':
        if amount == '10mins':
            return round_mins(dt, 10, dir='up')

def value_is_none(value):
    if value in ['',{},[],0,None,'Val:N']:
        return True
    if isinstance(value, list):
        if all([value_is_none(v) for v in value]):
            return True
    return False

def to_megabytes(instance):
    from django.core.serializers import serialize
    import sys
    try:
        if not isinstance(instance, dict) and not isinstance(instance, str):
            data = serialize('json', [instance])
        else:
            data = instance
        size_in_bytes = sys.getsizeof(data)
        size_in_kilobytes = size_in_bytes / 1024 
        size_in_megabytes = size_in_kilobytes / 1024
        return size_in_megabytes
    except Exception as e:
        prnt('to_mb err',str(e))
        return 0

def get_latest_dataPacket(chain='All'):
    prnt('-get_latest_dataPacket',chain)
    from network.models import _OperationsChain_genesisId, DataPacket, Blockchain
    self_node = get_self_node()
    # chainId = chain
    if isinstance(chain, models.Model):
        if chain._meta.object_name != 'Blockchain':
            if has_field(chain, 'networkChain'):
                chain = Blockchain.objects.filter(id=chain.networkChain).defer('queuedData').first()
        if chain and chain.genesisId == _OperationsChain_genesisId:
            chain = 'All'
        elif chain:
            chain = chain.id
        else:
            return None
    elif is_id(chain):
        pointer = get_pointer_type(chain)
        if pointer in ['User', 'Node']:
            chain = 'All'
    dataPacket = DataPacket.objects.filter(networkChain=chain, func='share', created__gte=now_utc()-datetime.timedelta(days=7)).first()
    if not dataPacket:
        try:
            dataPacket = DataPacket(networkChain=chain, Node_obj=self_node, func='share')
            dataPacket.save()
        except Exception as e:
            prnt('get_latest_dataPacket err',str(e))
            return None
    if dataPacket and not dataPacket.Node_obj and self_node:
        dataPacket.Node_obj = self_node
        dataPacket.save()
    return dataPacket

def get_node_list(sort='-lastUpdate'):
    from network.models import Node
    nodes = Node.objects.exclude(Block_obj=None).exclude(activated_dt=None).filter(suspended_dt=None).order_by(sort)
    node_list = []
    for node in nodes:
        node_list.append(node)
    return nodes

def get_self_node(operatorData=None):
    # prntDev('-get_self_node')
    from network.models import Node
    try:
        try:
            self_node_id = get_operator_obj('self_nodeId', operatorData=operatorData)
            return Node.objects.filter(id=self_node_id).only('id','address','User_obj','Block_obj','chain_array').first()
        except:
            pass
        if testing():
            return Node.objects.first()
    except Exception as e:
        prnt('get_self_node err',str(e))
    return None

# avoid this
def get_user(node=None, user_id=None, node_id=None, public_key=None, obj=None, target=None, request_missing=True):
    prnt('-get user, id:',user_id, 'public_key:', public_key,'node',node, 'node_id',node_id,'obj',obj,'target',target)
    from accounts.models import User, UserPubKey
    from network.models import Node
    user = None
    operatorData = None
    if user_id:
        model_type = get_pointer_type(user_id)
        if model_type == 'User':
            user = User.objects.filter(id=user_id).first()
    if not user and public_key:
        if is_id(public_key):
            iden = public_key
        else:
            iden = hash_upk_id(public_key)
        upk = UserPubKey.objects.filter(id=iden).only('User_obj').first()
        prnt('upk 5092',upk)
        if upk:
            user = upk.User_obj
    if not user and node_id:
        node = Node.objects.filter(id=node_id).only('User_obj').first()
        if node:
            user = node.User_obj
    if not user and node:
        user = User.objects.filter(id=node.User_obj.id).first()
        if not user:
            if not operatorData:
                operatorData = get_operatorData()
            user = User.objects.filter(id=operatorData['user_id']).first()
    if not user and request_missing:
        # this is likely not used and should remain not used
        prnt('get_user() not found, request_missing')
        try:
            if not operatorData:
                operatorData = get_operatorData()
            if not target:
                nodes = operatorData['ip_master_list']
                random.shuffle(nodes)
                for i in node:
                    if i != operatorData['address']:
                        target = i
                        break
            
            from utils.locked import sign_obj
            userData = json.dumps(sign_obj(operatorData['userData']))
            upkData = json.dumps(sign_obj(operatorData['upkData']))
            nodeData = get_self_node(operatorData=operatorData)
            signedNode = sign_obj(nodeData)
            selfNode = json.dumps(signedNode)
            signedRequest = json.dumps(sign_obj({'type':'User','items' : 'All', 'index' : 0,'dt':dt_to_string(round_time(dt=now_utc(), dir='down', amount='evenhour')),'obj_updated_on_node':None}))
            data = {'userData':userData, 'upkData':upkData, 'nodeData':selfNode, 'request':signedRequest}
            success, response = connect_to_node(target, 'network/request_data', data)
            if success:
                user = get_user(node=node, user_id=user_id, public_key=public_key, request_missing=False)
        except Exception as e:
            prnt('fail4902756',str(e))
            if testing():
                user = User.objects.all().first()
    return user

def get_node(id=None, address=None, publicKey=None):
    # prnt('-get_node',id,address,publicKey)
    from network.models import Node
    if id:
        return Node.objects.filter(id=id).first()
    elif address:
        return Node.objects.filter(address=address).first()
    elif publicKey: # not recommended
        user = get_user(public_key=publicKey)
        return Node.objects.filter(User_obj=user).first()

def accessed(node=None, response_time=None, update_data=None):
    # prnt('-accessed', node)
    if node:
        node.accessed(response_time=response_time)
    return node

def deactivate(node=None, update_data=None):
    from network.models import Node, NodeReview
    update = None
    if update_data: # dont use this
        try:
            node = Node.objects.filter(id=update_data['TargetNode_obj']).first()
            suspended_dt = convert_to_datetime(update_data['suspended_dt'])
            if node.get_last_accessed().accessed < suspended_dt:
                nodeUpdates = NodeReview.objects.exclude(suspended_dt=None).filter(TargetNode_obj__id=update_data['TargetNode_obj']) # suspended_dt removed from nodeReview
                for update in nodeUpdates:
                    update.delete()
                update = NodeReview()
                for field in update_data:
                    setattr(update, field, update_data[field])
                update.save()
        except:
            pass
    elif node:
        node.deactivate()
    return update

def find_or_create_chain_from_json(genesisId=None, obj=None):
    from network.models import Node, Blockchain
    network_chain = None
    if genesisId:
        network_chain = Blockchain.objects.filter(genesisId=genesisId).first()
    if not network_chain:
        genesisObj = get_dynamic_model(get_pointer_type(genesisId), id=genesisId)
        if not genesisObj:
            request_items([genesisId], Node.objects.exclude(activated_dt=None).filter(chain_array__contains=genesisId, suspended_dt=None))
            genesisObj = get_dynamic_model(get_pointer_type(genesisId), id=genesisId)
        if genesisObj:
            network_chain, obj, secondChain = find_or_create_chain_from_object(genesisObj)
    return network_chain

def convert_to_datetime(data): # repeated above, both used
    if isinstance(data, datetime.datetime):
        return data
    try:
        dt = datetime.datetime.strptime(data, 'datetime.datetime(%Y, %m, %d, %H, %M, tzinfo=<%Z>)')
    except:
        dt = string_to_dt(data)
    return dt


def modelData_to_hash(obj): # unused
    if not isinstance(obj, dict):
        data = convert_to_dict(obj)
    else:
        data = obj
    del data['hash']
    del data['updated_on_node']
    del data['signed']
    del data['publicKey']
    return hashlib.sha256(str(data).encode()).hexdigest()

def quick_hash(data):
    import xxhash
    import base62
    hash_hex = xxhash.xxh128(str(data)).hexdigest()
    hash_int = int(hash_hex, 16)
    return base62.encode(hash_int)

def sigData_to_hash(obj, exclude_fields=None):
    import hashlib
    from utils.locked import get_signing_data
    # prntDebug('-get_sigData_to_hash')
    data = get_signing_data(obj, exclude_fields=exclude_fields)
    text_bytes = str(data).encode('utf-8')
    hashed = hashlib.sha256(text_bytes).hexdigest()
    return hashed

def data_sort_priority(entry, version=None):
    # prnt('-data_sort_priority',entry)
    # sort received data in order for adding to database
    # needs to be reworked to handle by plugin, not hardcoded like this
    type_order = {'UserPubKey': 0, 'User': 1, 'Validator': 2, 'Node':3, 'NodeReview': 4, 'Sonet':4, 'Wallet':5, 'Transaction':6, 'Block':7, 'Region':8,
                'District':9, 'Government':10, 'Person':11, 'Party':12, 
                'Bill':13, 'Committee':14, 'Meeting':15, 'Statement':16, 'Motion':17, 'RepVote':18, 'Agenda':19, 'BillText':20, 'Update':21,'Spren':22,'Notification':23,'UserVote':24}
    
    def parse_datetime(value):
        if isinstance(value, str) and value.lower() != 'none':
            try:
                return string_to_dt(value).timestamp()
            except ValueError:
                pass  # Invalid date format, will return inf
        return float('inf')  # Fallback

    if isinstance(entry, dict):
        type_priority = type_order.get(entry.get('objType', ''), float('inf'))
        datetime_keys = ['created', 'lastUpdate']
        datetime_priority = next(
            (parse_datetime(entry[key]) for key in datetime_keys if key in entry and entry[key] not in (None, 'None')),
            float('inf')
        )
                
    elif is_id(entry):
        type_priority = type_order.get(get_pointer_type(entry), float('inf'))
        datetime_priority = float('inf')
    elif isinstance(entry, list):
        result = sorted(entry, key=lambda x: type_order.get(get_app_name(model_name=x, am_i_model=True), float('inf')))
        datetime_priority = float('inf')
        return result
    return (type_priority, datetime_priority)

def exists_in_worker(func, queue=None, queue_name=['main','high','low'], currently_running_only=False, job_count=1, **args):
    prnt('-exists_in_worker',func,queue,queue_name,args)
    from rq.job import Job
    from django_rq import get_connection, get_scheduler, get_queue
    from rq.worker import Worker
    workers = []
    try:
        if queue:
            workers.append(queue)
        elif isinstance(queue_name, list):
            for q in queue_name:
                workers.append(get_queue(q))
        else:
            workers.append(get_queue(queue_name))
    except Exception as e:
        prnt('exists_in_worker fail 1', str(e))
        return False
    
    def normalize(val):
        if isinstance(val, (str, int)):
            return val
        elif isinstance(val, dict):
            return frozenset((normalize(k), normalize(v)) for k, v in val.items())
        elif isinstance(val, (list, tuple)):
            return tuple(normalize(x) for x in val)
        # sets → frozenset of normalized items
        elif isinstance(val, set):
            return frozenset(normalize(x) for x in val)
        return val

    def job_matches(job, input_args):
        if isinstance(input_args, dict):
            input_values = list(input_args.values())
        elif isinstance(input_args, (list, tuple, set)):
            input_values = list(input_args)
        else:
            input_values = [input_args]
        combined = list(job.args) + list(job.kwargs.values())
        combined_norm = [normalize(x) for x in combined]
        input_norm = [normalize(x) for x in input_values]
        return all(val in combined_norm for val in input_norm)

    found_jobs = 0

    for queue in workers: # currently running
        conn = queue.connection
        for w in Worker.all(conn):
            if queue_name in [q.name for q in w.queues]:
                job = w.get_current_job()
                if job:
                    prnt('current job.func_name',job.func_name, 'req_kw:',{k:v for k, v in args.items()}, 'job.args:',job.args, 'kw:',[k for k in job.kwargs.values()])
                    if job.func_name.endswith(func):
                        found_jobs += 1
                        if found_jobs >= job_count:
                            prnt('return 2 true')
                            return True

                
    if not currently_running_only:
        for queue in workers:
            total_jobs = 0
            job_ids = queue.job_ids
            for job_id in job_ids:
                job = queue.fetch_job(job_id)
                if job:
                    total_jobs += 1
                    if total_jobs >= 90:
                        prntDebug('return 7 true')
                        return True

                    if job.func_name.endswith(func):
                        if job_matches(job, args):
                            found_jobs += 1
                            if found_jobs >= job_count:
                                prnt('return 4 true')
                                return True
                    
        # scheduler not setup properly on linux, maybe works on mac
        try:
            for queue in workers:
                connection = get_connection(queue.name)
                scheduler = get_scheduler(queue.name, connection)
                scheduled_jobs = scheduler.get_jobs()
                for job in scheduled_jobs:
                    if job.func_name.endswith(func):
                        if job_matches(job, args):
                            found_jobs += 1
                            if found_jobs >= job_count:
                                prnt('return 5 true')
                                return True
        except Exception as e:
            pass
    if found_jobs >= job_count:
        prntDebug('return 6 true')
        return True
    prntDebug('cont8 false')
    return False

def get_chain_id(genesisId):
    from network.models import Blockchain
    from utils.locked import hash_obj_id
    return hash_obj_id(Blockchain, specific_data={'genesisId': genesisId, 'objType': 'Blockchain'})

def get_post_id(pointerId):
    prnt('-get_post_id',{'objType': 'Post', 'pointerId': pointerId})
    from posts.models import Post
    from utils.locked import hash_obj_id
    return hash_obj_id(Post, specific_data={'objType': 'Post', 'pointerId': pointerId})

# only used one in accounts.views - i think not used anymore
def check_dataPacket(obj):
    from network.models import Blockchain
    # from posts.models import has_field
    if has_field(obj, 'blockchainId'):
        chainId = obj.blockchainId
    elif has_field(obj, 'networkChain'):
        chain = Blockchain.objects.filter(genesisType=obj.networkChain, genesisId=obj.id).first()
        if chain:
            chainId = chain.id
        else:
            chainId = 'All'
    else:
        chainId = 'All'
    dataPacket = get_latest_dataPacket(chainId)
    if not obj:
        return False
    elif obj.id in dataPacket.data:
        return True
    else:
        return False

def has_profanity(text, level=2):
    from utils.profanity_filter.tiered_profanity_filter import run_me
    return run_me(text, level)

def func_accepts_var(func, var):
    import inspect
    return var in inspect.signature(func).parameters

def any_field_contains(obj, name):
    name_lower = name.lower()
    if isinstance(obj, models.Model):
        if has_field(obj, name):
            return name
        if has_field(obj, name_lower):
            return name_lower
        for field in obj._meta.concrete_fields:
            field_name = field.name.lower()
            if name_lower in field_name:
                return field.name

    if isinstance(obj, dict):
        if obj.get(name, False):
            return name
        elif obj.get(name_lower, False):
            return name_lower
        else:
            if any(f for f in obj if name in f.lower()):
                for f in obj:
                    field_name = f.lower()
                    if field_name in name_lower:
                        return f
    return False

def has_field(model, field_name, exclude_method=False):
    # prnt('-has_field',field_name,model,type(model))
    if is_model_or_instance(model):
        if exclude_method:
            try:
                return any([f.name for f in model._meta.get_fields() if f.name == field_name])
            except Exception as e:
                prnt('has_field err 6892',str(e))
        return hasattr(model, field_name)
    elif isinstance(model, dict):
        if exclude_method:
            try:
                return any([f for f in model if f == field_name])
            except Exception as e:
                prnt('has_field err 6893',str(e))
        if model.get(field_name, None):
            return True
        else:
            return False

def is_model_or_instance(model):
    if isinstance(model, models.Model):
        return True
    if isinstance(model, type) and issubclass(model, models.Model):
        return True
    return False

def has_method(model, method_name):
    return callable(getattr(model, method_name, None))

def rgetattr(obj, path):
    for part in path.split('.'):
        obj = getattr(obj, part)
    return obj

def get_model_prefix(obj):
    # returns 'sta', 'vot' etc.
    if isinstance(obj, dict):
        return get_app_name(obj['objType'], return_prefix=True)
    elif isinstance(obj, str):
        return get_app_name(obj, return_prefix=True)
    else:
        return get_app_name(obj._meta.object_name, return_prefix=True)
    
def get_pointer_type(iden):
    # prntDebug('-get_pointer_type',iden)
    if isinstance(iden, models.Model):
        return iden._meta.object_name
    elif isinstance(iden, dict):
        return iden['objType']
    elif isinstance(iden, str) and not is_id(iden) and get_app_name(model_name=iden, am_i_model=True) == iden:
        return iden
    if not iden or 'So' not in iden:
        return None
    x = iden.find('So')
    prefix = iden[:x]
    return get_app_name(prefix=prefix) 

def get_chain_type(iden):
    # prnt('-get_chain_type Type')
    if isinstance(iden, models.Model):
        iden = iden.id
        if has_field(iden, 'networkChain'):
            return iden.networkChain
    elif isinstance(iden, dict):
        iden = iden['id']
        if 'networkChain' in iden:
            return iden['networkChain']
    if not iden or 'So' not in iden:
        return None
    m = get_model(iden)()
    if has_field(m, 'networkChain'):
        return m.networkChain
    return None

def get_chainName(obj):
    if obj._meta.object_name == 'Region':
        return obj.Name
    elif obj._meta.object_name == 'User':
        return obj.username
    elif obj._meta.object_name == 'Wallet':
        return obj.User_obj.username
    elif obj._meta.object_name == 'Sonet':
        return 'Sonet'
    elif has_field(obj, 'networkChain'):
        from network.models import Blockchain
        chain = Blockchain.objects.filter(id=obj.networkChain).only('genesisName').first()
        if chain:
            return chain.genesisName
    return None

def seperate_by_type(obj_list, include_only=None, exclude=None):
    include_only = declare_var(include_only, {})
    exclude = declare_var(exclude, {})
    prntDebug('-seperate_by_type',str(obj_list)[:100])
    obj_types = {}
    models = {}
    skipping_models = []
    if not obj_list:
        return obj_types
    
    obj_list = sorted(obj_list, key=data_sort_priority)
    # prntDebug('obj_list',obj_list)
    for i in obj_list:
        err = '_'
        skip = False
        obj_type = None
        value = None
        if is_id(i):
            obj_type = get_pointer_type(i)
            value = i
            if obj_type not in models:
                model = get_model(obj_type)
                models[obj_type] = model
            else:
                model = models[obj_type]
            model = model()
        elif isinstance(i, models.Model):
            obj_type = i._meta.object_name
            value = i.id
            model = i
        # prntDebug('value',value,'model',model,'obj_type',obj_type,'obj_types',obj_types,'skipping_models',skipping_models)
        if value and obj_type not in skipping_models:
            if obj_type in obj_types:
                obj_types[obj_type].append(value)
            else:
                err += '0'
                if not skip and include_only:
                    err += '1'
                    if 'fields' in include_only:
                        if isinstance(include_only['fields'], dict):
                            for field_name, field_value in include_only['fields'].items():
                                if not has_field(model, field_name) or getattr(model, field_name) != field_value:
                                    err += 'A'
                                    skip = True
                                    break
                        elif isinstance(include_only['fields'], list):
                            for field in include_only['fields']:
                                if not has_field(model, field):
                                    err += 'B'
                                    skip = True
                                    break
                    if not skip and 'has_field' in include_only:
                        for field in include_only['has_field']:
                            if not has_field(model, field):
                                err += 'C'
                                skip = True
                                break
                    if not skip and 'has_method' in include_only:
                        for method in include_only['has_method']:
                            if not has_method(model, method):
                                err += 'D'
                                skip = True
                                break
                # prntDebug('skip',skip,'exclude',exclude)
                err += '2'
                if not skip and exclude:
                    err += '3'
                    if 'fields' in exclude:
                        if isinstance(exclude['fields'], dict):
                            for field_name, field_value in exclude['fields'].items():
                                if field_value.startswith('!'):
                                    field_value = field_value.replace('!','')
                                    if has_field(model, field_name) and getattr(model, field_name) != field_value:
                                        err += 'A'
                                        skip = True
                                        break
                                else:
                                    if has_field(model, field_name) and getattr(model, field_name) == field_value:
                                        err += 'B'
                                        skip = True
                                        break
                        elif isinstance(exclude['fields'], list):
                            for field in exclude['fields']:
                                # prnt('field',field)
                                if isinstance(field, dict):
                                    for field_name, field_value in field.items():
                                        # prnt('field_name',field_name,'field_value',field_value)
                                        if field_value.startswith('!'):
                                            field_value = field_value.replace('!','')
                                            # prnt('getattr(model, field_name)',getattr(model, field_name))
                                            if has_field(model, field_name) and getattr(model, field_name) != field_value:
                                                err += 'C'
                                                skip = True
                                                break
                                        else:
                                            if has_field(model, field_name) and getattr(model, field_name) == field_value:
                                                err += 'D'
                                                skip = True
                                                break
                                else:
                                    if has_field(model, field):
                                        err += 'E'
                                        skip = True
                                if skip:
                                    break
                if skip:
                    skipping_models.append(obj_type)
                prntDebug('\nerr',err,'obj_type',obj_type,'value',value,'skip',skip)
                if obj_type and value and not skip:
                    if obj_type in obj_types:
                        obj_types[obj_type].append(value)
                    else:
                        obj_types[obj_type] = [value]
    prntDebug('obj_types',obj_types)
    return obj_types

def is_locked(obj, skip=[]):
    # prnt('-check is_locked')
    value = False
    try:
        err = '1a'
        if has_field(obj, 'is_modifiable') and obj.is_modifiable and (not has_field(obj, 'proposed_modification') or not value_is_none(obj.proposed_modification)):
            err += 'b'
            return False
        err = '3'
        if has_field(obj, 'Block_obj') and obj.Block_obj and obj.Block_obj.validated:
            err += 'e'
            value = True
        err += '4'
        if not value and 'Validator_obj' not in skip and has_field(obj, 'Validator_obj') and obj.Validator_obj:
            err += 'f'
            if obj.Validator_obj.is_valid and obj.Validator_obj.data[obj.id] == sigData_to_hash(obj):
                err += 'g'
                value = True
        err += '5'
        if not value and has_field(obj, 'ReceiverBlock_obj'):
            err += 'h'
            if obj.ReceiverBlock_obj and obj.ReceiverBlock_obj.validated:
                err += 'i'
                value = True
        err += '6'
        if not value and has_field(obj, 'SenderBlock_obj'):
            err += 'j'
            if obj.SenderBlock_obj and obj.SenderBlock_obj.validated:
                err += 'k'
                value = True
        err += '7'
        if not value and has_field(obj, 'validated') and obj.validated:
            err += 'l'
            value = True
        err += '8'
        if not value and has_method(obj, 'committed_data_matches'):
            err += 'c'
            if obj.committed_data_matches():
                err += 'd'
                value = False
        err += '9'
    except Exception as e:
        prnt('is_locked error9673945',str(e), 'err',err, obj,has_field(obj, 'Validator_obj'))
        # from utils.locked import convert_to_dict
        # logError(str(e), code='9673945', func='is_locked', extra={'err':err,'dict':str(convert_to_dict(obj))[:500]})
    prnt('is locked?', obj.id, value, err)
    return value

def is_obj_commit_valid(obj):
    prnt('-is_obj_commit_valid')
    if has_field(obj, 'Block_obj') and obj.Block_obj and obj.Block_obj.validated:
        if has_field(obj, 'Validator_obj'):
            if not obj.Validator_obj or not obj.Validator_obj.is_valid:
                return False
        from utils.locked import check_commit_data
        if check_commit_data(obj, obj.Block_obj.data[obj.id]):
            return True
        else:
            return False
    else:
        return True

def parse_input(value):
    try:
        if str(value) == '[]':
            return []
    except:
        pass
    try:
        import ast
        parsed_value = ast.literal_eval(value)
        return parsed_value
    except:
        pass
    try:
        parsed_value = json.loads(value)
        return parsed_value
    except:
        pass
    return value

def is_id(obj):
    # prnt('-is_id')
    # prefix = plugin num + 2 to 3 class chars followed by "So"
    max_length = 35 # character length - does not include prefix - ID_LENGTH of 25
    min_length = 13 # ID_LENGTH of 10
    
    if isinstance(obj, str) and 'So' in obj[:10] and any(obj[i:i+2] == 'So' and obj[i+2:].isalnum() and min_length <= len(obj[i+2:]) <= max_length for i in range(10)):
        return True
    return False

def get_sigData(received_data, first_key=False):
    if isinstance(received_data, dict) and 'signed' in received_data:
        received_data = received_data['signed']
    elif isinstance(received_data, models.Model) and has_field(received_data, 'signed'):
        received_data = received_data.signed
    if first_key == 'all':
        # not used anywhere
        ...
    elif first_key:
        last_key = list(received_data)[0]
    else:
        last_key = list(received_data)[-1]
    pkey = received_data[last_key]['pk']
    if 'sig' in received_data[last_key]:
        sig = received_data[last_key]['sig']
    else:
        sig = None
    if 'publicKey' in received_data[last_key]:
        publicKey = received_data[last_key]['publicKey']
    else:
        publicKey = None
    if 'req' in received_data[last_key]:
        req = received_data[last_key]['req']
    else:
        req = None
    dt = last_key
    return {'dt':string_to_dt(dt),'pk':pkey,'sig':sig,'publicKey':publicKey,'req':req}

def resolve_target_keys(data, signature=None):
    if signature and isinstance(signature, dict):
        return {signature[i]['pk'] for i in signature}
    elif not signature and isinstance(data, dict) and 'signed' in data:
        return {data['signed'][i]['pk'] for i in data['signed']}
    return None

def get_model_fields(obj=None):
    # prnt('-get_model_fields')
    # for use when updating model fields
    model_list = get_app_name(return_model_list=True)
    for key in model_list:
        if key != 'apps':
            model = get_model(key)
            obj = model() 
            objFields = {'objType':obj._meta.object_name} # latestVer not included
            if has_field(model,'is_modifiable'):
                objFields['is_modifiable'] = obj.is_modifiable
            if has_field(model,'networkChain'):
                objFields['networkChain'] = obj.networkChain
            if has_field(model,'commitChain'):
                objFields['commitChain'] = obj.commitChain
            from django.forms.models import model_to_dict
            objFields.update(model_to_dict(obj))
            for i in ['is_staff', 'is_active', 'groups', 'user_permissions']:
                if i in objFields:
                    objFields.pop(i)
            for i in objFields:
                if str(objFields[i]).endswith('None>'):
                    objFields[i] = None
            try:
                objFields['iden_length'] = obj.iden_length
            except:
                pass
            if 'signed' in objFields:
                objFields.pop('signed')
                objFields['signed'] = {}
            if has_method(obj, 'get_version_fields'):
                fields = obj.get_version_fields()
            else:
                fields = {}
            if fields and list(fields.items()) != list(objFields.items()):
                prnt(key)
                prnt(f' return {objFields}')
                prnt()

def hash_upk_id(pubKey):
    from utils.locked import generate_id
    return 'upkSo' + generate_id(pubKey, length=14)    


_appInfo = None

def get_app_info(rerun=False):
    # prnt('-get_app_info')
    global _appInfo
    if _appInfo is None or rerun:
        import importlib
        from django.conf import settings
        from network.models import Plugin
        app_dict = {'apps':{}}
        plugins = Plugin.objects.exclude(Block_obj=None)
        if plugins:
            # prnt('plugins',plugins)
            for plug in plugins:
                app = plug.app_name
                app_dict['apps'][plug.app_name] = []
                for key, value in plug.model_prefixes.items():
                    if key not in app_dict['apps'][plug.app_name]:
                        app_dict['apps'][plug.app_name].append(key)
                    if plug.plugin_prefix and plug.plugin_prefix != '0':
                        text = f'{plug.plugin_prefix}{value}'
                    else:
                        text = f'{value}'
                    app_dict[key] = text
            _appInfo = app_dict
        else:
            from network.models import default_apps
            supported_apps = default_apps
            plugin_prefixes = {}
            for app in settings.INSTALLED_APPS:
                try:
                    if app in supported_apps or app == 'transactions':
                        models_module = importlib.import_module(f"{app}.models")
                        if hasattr(models_module, "model_prefixes"):
                            prefixes = getattr(models_module, "model_prefixes")
                            if isinstance(prefixes, dict):
                                app_dict['apps'][app] = []
                                for key, value in prefixes.items():
                                    if key not in app_dict['apps'][app]:
                                        app_dict['apps'][app].append(key)
                                    if app in plugin_prefixes and plugin_prefixes[app]:
                                        text = f'{plugin_prefixes[app]}{value}'
                                    else:
                                        text = f'{value}'
                                    app_dict[key] = text

                except ModuleNotFoundError:
                    continue
                except Exception:
                    continue
        if plugins:
            _appInfo = app_dict
        else:
            # prnt('app_dict2',app_dict)
            return app_dict
        
    # prnt('_appInfo',_appInfo)
    return _appInfo


def get_app_name(model_name=None, prefix=None, return_prefix=False, return_model_list=False, am_i_model=False):
    # prnt('-get_app_name',model_name,prefix,return_prefix)
    models = get_app_info()
    # prnt('models:',models)
    if model_name and not return_prefix and not am_i_model:
        for app_name in models['apps']:
            if model_name in models['apps'][app_name]:
                return app_name
    elif model_name and return_prefix:
        if model_name in models:
            return models[model_name]
    elif prefix:
        for m in models:
            if models[m] == prefix:
                return m
    elif return_model_list:
        return models
    elif am_i_model and model_name in models['apps']:
        return model_name
    return ''

def get_model(obj_type):
    # prnt('-get_model', obj_type)
    if not obj_type or not isinstance(obj_type, str):
        return None
    if is_id(obj_type):
        obj_type = get_pointer_type(obj_type)
    # prnt('obj_type',obj_type)
    app_name = get_app_name(obj_type)
    # prnt('app_name',app_name)
    if app_name and obj_type:
        from django.apps import apps
        return apps.get_model(app_name, obj_type)
    return None

def get_plugin(obj, name=False, id=False):
    try:
        if isinstance(obj, str):
            obj = get_model(obj)
        if name:
            return obj._meta.app_label
        from network.models import Plugin
        if id:
            plugin = Plugin.objects.filter(app_name=obj._meta.app_label).values('id').first()
            if plugin:
                return plugin['id']
        else:
            return Plugin.objects.filter(app_name=obj._meta.app_label).first()
    except Exception as e:
        prnt('get_plugin err',str(e))
    return None

def get_objType(obj):
    try:
        return obj._meta.object_name
    except Exception as e:
        prnt('get_objType err',str(e))
        return None

def dynamic_bulk_create(model_name=None, model=None, items=[], return_items=False, retrieve_missing=True):
    prntDebug('-dynamic_bulk_create', model_name)

    if not model:
        model = get_model(model_name)
    if not model:
        prnt('no model')
        return None
    if model._meta.object_name == 'Post':
        model_manager = 'all_objects'
    else:
        model_manager = 'objects'
    try:
        getattr(model, model_manager).bulk_create(items)
    except Exception as e:
        prnt('d create err 5689:',model_name,str(e))
        for i in items:
            compensate_save(i, model, return_err=False, retrieve_missing=retrieve_missing)
    if return_items:
        return items
    return None

def dynamic_bulk_update(model_name=None, model=None, update_data=None, items_field_update=None, items=[], compensate_save=True, return_items=False, retrieve_missing=True, **kwargs):
    if not update_data:
        update_data = {}
    if not items_field_update:
        items_field_update = []
    prntDebug('-dynamic_bulk_update',model_name, model, len(update_data), len(items),'items_field_update:',items_field_update)
    # update_data requires kwargs - performs lookup - will not return items
    # rest is interchangable
    # not receiving update_data or items_field_update will update entire model
    # must receive model_name or model
    
    if not model_name and not model:
        return None
    err = 'A'
    if not model:
        model = get_model(model_name)
    if not model:
        return None
    if not update_data and not items_field_update:
        items_field_update = [
            field.name for field in model._meta.get_fields()
            if field.concrete and not field.auto_created and field.name != 'id'
        ]
    if model._meta.object_name == 'Post':
        err = err + 'a'
        model_manager = 'all_objects'
    else:
        err = err + 'b'
        model_manager = 'objects'
    err = err + str(len(items))
    try:
        err = err + 'B'
        if update_data and kwargs:
            err = err + 'C'
            update_data['updated_on_node'] = now_utc()
            getattr(model, model_manager).filter(**kwargs).update(**update_data)
            # model.objects.filter(**kwargs).update(**update_data)
            items = 'N/A'
            err = err + 'fini1'
        elif items_field_update:
            if 'updated_on_node' not in items_field_update:
                err = err + 'D'
                items_field_update.append('updated_on_node')
                now = now_utc()
                for i in items:
                    i.updated_on_node = now
            err = err + 'E'
            if not items and kwargs:
                err = err + 'e'
                items = getattr(model, model_manager).filter(**kwargs)
            if items:
                err = err + 'F'
                try:
                    err = err + str(len(items))
                    err = err + 'f'
                    prnt('items_field_update',items_field_update)
                    getattr(model, model_manager).bulk_update(items, items_field_update)
                    err = err + 'fini2'
                except Exception as e:
                    err = err + 'G'
                    if compensate_save and compensate_save_handle(str(e), retrieve_missing=retrieve_missing):
                        err = err + 'I'
                        bulk_update_fields_no_foreignKey = [
                            field.name for field in model._meta.get_fields()
                            if field.concrete and not field.auto_created and field.name not in ['id', 'is_staff', 'password', 'groups', 'user_permissions'] and '_obj' not in field.name
                        ]
                        bulk_update_fields_only_foreignKey = [
                            field.name for field in model._meta.get_fields()
                            if field.concrete and not field.auto_created and field.name not in ['id', 'is_staff', 'password', 'groups', 'user_permissions'] and '_obj' in field.name
                        ]
                        # logError(str(e), code='947262', func='dynamic_bulk_update', extra={'bulk_update_fields_no_foreignKey':bulk_update_fields_no_foreignKey,'bulk_update_fields_only_foreignKey':bulk_update_fields_only_foreignKey})
                        from django.db import transaction
                        err = err + 'J'
                        with transaction.atomic():
                            err = err + 'K'
                            getattr(model, model_manager).bulk_update(items, bulk_update_fields_no_foreignKey)
                            err = err + 'L'
                            getattr(model, model_manager).bulk_update(items, bulk_update_fields_only_foreignKey)
                            err = err + 'finixxx'

        prntDebug('dynamic_bulk_update prog:',err)
        if return_items:
            return items
        return None
    except Exception as e:
        err = err + 'H'
        prntDebug('dynamic_bulk_update prog2:',err)
        from utils.locked import convert_to_dict
        if compensate_save_handle(str(e), context={'from':'dynamic_bulk_update2','err':str(err),'model':str(model),'dict':[convert_to_dict(q) for q in items[:20]]}):
            return dynamic_bulk_update(model=model, items_field_update=items_field_update, update_data=update_data, items=items, compensate_save=False, return_items=return_items, **kwargs)
        return None


def compensate_save(obj, model, return_err=False, retrieve_missing=True, context=None, *args, **kwargs):
    prntDebug('-compensate_save',obj)

    if context:
        from utils.locked import convert_to_dict
        logError('context', code='5736', func='compensate_save', extra={'model':str(model),'obj':str(convert_to_dict(obj))[:500],'context':context})
    try:
        super(model, obj).save(*args, **kwargs)
        if return_err:
            return True, None
        return True
    except Exception as e:
        if compensate_save_handle(str(e), create_obj=True, context=obj, retrieve_missing=retrieve_missing):
            if return_err:
                return True, None
            return True
        if return_err:
            return False, str(e)
        return False

def compensate_save_handle(err, create_obj=True, context=None, retrieve_missing=True):
    prnt('-compensate_save_handle',str(err),'context:',context)

    from utils.locked import convert_to_dict
    err = str(err)
    if 'violates foreign key constraint' in err:
        x = err.find("DETAIL:  Key (")+len("DETAIL:  Key (")
        z = err[x:].find('_obj')
        q = x+z
        model_name = err[x:q]
        y = err[q:].find("_id)=(")+len("_id)=(")
        v = err[q+y:].find(") is not present")
        iden = err[q+y:q+y+v]
        if not iden:
            prnt('iden not found in compensate save')
            return False
        if create_obj:
            obj = create_dynamic_model(iden, id=iden)
            obj.save()
            prnt('created obj 7643', obj)
            return True
    elif "bulk_update() can only be used with concrete fields" in err:
        prntDebug('compensate_save_handle skipped1, 4689')
        return True 

    elif all(word in err.lower() for word in ['duplicate', 'key', 'violates', 'unique', 'constraint']):
        prntDebug('compensate_save_handle skipped2, key exists, 8854')
        if isinstance(context, models.Model):
            xModel = get_dynamic_model(context._meta.object_name, id=context.id)
            if xModel and not is_locked(xModel):
                xModel, sigs, proceed_to_sync, updatedDB = sync_model(xModel, convert_to_dict(context), skip_fields=[], do_save=True, opBlock_data={}, force_sync=True, get_missing_blocks=False)
                if updatedDB:
                    return True
        elif isinstance(context, dict) and 'id' in context:
            xModel = get_dynamic_model(context['objType'], id=context['id'])
            if xModel and not is_locked(xModel):
                xModel, sigs, proceed_to_sync, updatedDB = sync_model(xModel, context, skip_fields=[], do_save=True, opBlock_data={}, force_sync=True, get_missing_blocks=False)
                if updatedDB:
                    return True
    elif all(word in err.lower() for word in ['key', 'already', 'exists']):
        prntDebug('compensate_save_handle skipped3, key exists, 9312')
        if isinstance(context, models.Model):
            xModel = get_dynamic_model(context._meta.object_name, id=context.id)
            if xModel and not is_locked(xModel):
                xModel, sigs, proceed_to_sync, updatedDB = sync_model(xModel, convert_to_dict(context), skip_fields=[], do_save=True, opBlock_data={}, force_sync=True, get_missing_blocks=False)
                if updatedDB:
                    return True
        elif isinstance(context, dict) and 'id' in context:
            xModel = get_dynamic_model(context['objType'], id=context['id'])
            if xModel and not is_locked(xModel):
                xModel, sigs, proceed_to_sync, updatedDB = sync_model(xModel, context, skip_fields=[], do_save=True, opBlock_data={}, force_sync=True, get_missing_blocks=False)
                if updatedDB:
                    return True
    else:
        if context:
            prntDebug('compensate_save_handle failed1, 77543')
        else:
            prntDebug('compensate_save_handle failed2, 4578')

    return False


def get_dynamic_model(model_name, list=False, order_by=None, exclude={}, values=[], **kwargs):
    # Post model uses special model_manager, only returns validated objs normally
    prntDebug(f'-get_dynamic_model:{model_name} exclude:{exclude}, list:{list}, order_by:{order_by}, values:{values}, **kwargs:{kwargs}')
    model = None
    if isinstance(model_name, str):
        model = get_model(model_name)
    elif isinstance(model_name, models.Model) or issubclass(model_name, models.Model):
        model = model_name
    # prnt('model',model)
    if not model:
        return [] if list else None
    creation_fields = ['created','created_dt']
    if order_by and order_by in creation_fields:
        for f in creation_fields:
            if has_field(model, f):
                order_by = f
    try:
        del kwargs['objType']
    except:
        pass
    if list:
        if list == True:
            try:
                if order_by:
                    return model.objects.filter(**kwargs).exclude(**exclude).order_by(order_by)
                else:
                    return model.objects.filter(**kwargs).exclude(**exclude)
            except Exception as e:
                prntDebug('get_dynamic_model err1', str(e))
                return []
        else:
            try:
                if order_by:
                    return model.objects.filter(**kwargs).exclude(**exclude).order_by(order_by)[list[0]:list[1]]
                else:
                    return model.objects.filter(**kwargs).exclude(**exclude)[list[0]:list[1]]
            except model.DoesNotExist:
                return []
            
    else:
        try:
            if order_by:
                if values:
                    return model.objects.filter(**kwargs).exclude(**exclude).values(*values).order_by(order_by).first()
                else:
                    return model.objects.filter(**kwargs).exclude(**exclude).order_by(order_by).first()
            else:
                if values:
                    return model.objects.filter(**kwargs).exclude(**exclude).values(*values).first()
                else:
                    return model.objects.filter(**kwargs).exclude(**exclude).first()
        except Exception as e:
            prnt('get_dynamic_model err2',str(e))
            return None

def create_dynamic_model(model_name, **kwargs):
    # prnt('-create_dynamic_model',model_name)
    model = get_model(model_name)
    try:
        del kwargs['objType']
    except:
        pass
    obj = model(**kwargs)
    return obj

def get_or_create_model(model_name, return_is_new=False, **kwargs):
    # prnt('-get_or_create_model')
    is_new = False
    obj = get_dynamic_model(model_name, **kwargs)
    if not obj:
        try:
            obj = create_dynamic_model(model_name, **kwargs)
            is_new = True
        except Exception as e:
            prnt('get_or_create_model err',str(e))
    elif obj:
        if has_field(obj, 'Validator_obj'):
            if not obj.Validator_obj or not obj.Validator_obj.is_valid:
                prnt('get_create_is_new',obj)
                is_new = True
    if return_is_new:
        return obj, is_new
    return obj

def get_model_and_update(model_name, dt=None, obj=None, new_model=True, **kwargs):
    # prnt('-get model and update', model_name)
    from posts.models import Update
    if not obj and not kwargs:
        return None, None, None
    if not obj:
        obj = get_dynamic_model(model_name, **kwargs)
        if obj and has_field(obj, 'Validator_obj') and obj.Validator_obj and obj.Validator_obj.is_valid:
            new_model = False
        if not obj:
            obj = create_dynamic_model(model_name, **kwargs)
    u = Update(pointerId=obj.id)
    update = u.create_next_version(obj=obj)
    return obj, update, new_model

def save_and_return(obj, update, log):
    prntn('--save and return, obj',obj, 'update:',update)
    func = log.data['func']
    created = string_to_dt(log.data['created'])
    def confer(obj):
        field_names = [field.name for field in obj._meta.fields]
        query_kwargs = {field: getattr(obj, field) for field in field_names}
        match = get_dynamic_model(obj._meta.object_name, list=False, **query_kwargs)
        return False if match else True
    
    new_obj = True
    if is_locked(obj):
        prnt('forbidden save - is_locked', obj)
        new_obj = False
    elif has_field(obj, 'Validator_obj'):
        if obj.Validator_obj == None:
            new_obj = True
        else:
            new_obj = False
    elif has_field(obj, 'Block_obj') and obj.Block_obj:
        new_obj = False
    elif has_field(obj, 'proposed_modification'):
        if obj.id != None:
            new_obj = False
        obj = obj.propose_modification()
    if new_obj:
        if func:
            obj.func = func
        obj.created = created
        if obj.id != None and has_method(obj, 'get_hash_to_id'):
            from utils.locked import hash_obj_id
            hashed_id = hash_obj_id(obj)
            if obj.id != hashed_id:

                logEvent(f'changed_id: old_id{obj.id}, new_id:{hashed_id}')
                obj.id = hashed_id
        if has_method(obj, 'update_data'):
            obj.update_data()
        else:
            obj.save()
        if obj.id not in log.data['shareData']:
            log.updateShare(obj)

    if update and has_field(obj, 'Block_obj'):
        if update.data != {}:
            has_data = True
        else:
            has_data = False
            for f in update._meta.fields:
                if '_obj' in str(f.name) or str(f.name) == 'data':
                    attr = getattr(update, f.name)
                    if not attr or attr == {}:
                        pass
                    else:
                        has_data = True
        if has_data:
            update.pointerId = obj.id 
            update.Region_obj = obj.Region_obj
            if not update.DateTime and has_field(obj, 'DateTime'):
                update.DateTime = obj.DateTime
            elif not update.DateTime and has_field(obj, 'created'):
                update.DateTime = obj.created
            if func:
                update.func = func
            update.created = created

            update, u_is_new = update.save_if_new()
            if u_is_new and not is_locked(update):
                log.updateShare(update)

    return obj, update, new_obj, log

def superDelete(obj, force_delete=False):
    prnt('-superdelete',obj)
    if not has_field(obj, 'Block_obj') or has_field(obj, 'Block_obj') and not obj.Block_obj or has_field(obj, 'Block_obj') and obj.Block_obj.validated == False or force_delete:
        from posts.models import Update, Post, Keyphrase
        try:
            updates = Update.objects.filter(pointerId=obj.id)
            for u in updates:
                u.delete()
        except:
            pass
        try:
            p = Post.all_objects.filter(pointerId=obj.id).first()
            p.delete()
        except:
            pass
        try:
            keys = Keyphrase.objects.filter(pointerId=obj.id)
            for k in keys:
                k.delete()
        except:
            pass
        try:
            from accounts.models import Notification
            notifications = Notification.objects.filter(pointerId=obj.id)
            for n in notifications:
                n.delete(force_delete=force_delete)
        except:
            pass
        try:
            model = get_model(obj._meta.object_name)
            super(model, obj).delete()
            prnt('deleted')
            return True
        except Exception as e:
            prnt('super delete fail',str(e))
    return False


def save_image(url, file_name, pointerId, r=None, region=None, max_bytes=(0.125 * 1024 * 1024)):
    prnt('-save_image', pointerId, url)
    import mimetypes
    from django.core.files.base import ContentFile
    from posts.models import ImageFile
    obj = ImageFile.objects.filter(pointerId=pointerId, Validator_obj__is_valid=True).order_by('-created').first()
    if obj:
        return obj
    if not r:
        import requests
        try:
            prnt('fetch img')
            r = requests.get(url, timeout=10)
        except Exception as e:
            prnt('save img err 222',str(e))
            return None
    content_type = r.headers.get("Content-Type")
    ext = mimetypes.guess_extension(content_type) or ".jpg"

    filename = f"{file_name}{pointerId}{ext}"
    image_bytes = r.content
    if len(image_bytes) > max_bytes:
        image_bytes = downscale_to_size(image_bytes, max_bytes=max_bytes)
        prnt('scaled:',len(image_bytes))

    try:
        obj = ImageFile(source_url=url, pointerId=pointerId, Region_obj=region, file_path=f"images/{filename}")
        obj.imageField.save(filename, ContentFile(image_bytes), save=True)
        return obj
    except Exception as e:
        prnt('fail save img', str(e))
        return None

def downscale_to_size(image_bytes, max_bytes=(0.25 * 1024 * 1024)):
    prnt('-downscale_to_size',len(image_bytes))
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(image_bytes))

    max_size = (1600, 1600) # width/height
    img.thumbnail(max_size) # shrink resolution

    # recompress until under byte limit
    quality = 90
    while True:
        buf = BytesIO()
        img.save(buf, format=img.format or "JPEG", quality=quality, optimize=True)
        data = buf.getvalue()

        if len(data) <= max_bytes or quality <= 30:
            return data

        quality -= 10


def fetch_obj_data(iden):
    prnt('-fetch_obj_data',iden)
    from utils.locked import convert_to_dict, sign_for_sending
    obj = get_dynamic_model(iden, id=iden)
    if obj:
        return convert_to_dict(obj)
    else:

        self_node_id = get_operator_obj("self_nodeId")
        keys = get_operator_obj('keyPair')
        signedRequest = json.dumps(sign_for_sending({'itemId' : iden, 'dt':dt_to_string(now_utc())}, keys=keys))
        data = {'senderId':self_node_id, 'request':signedRequest}

        from network.models import Node
        nodes = Node.objects.filter(activeNode=True).exclude(chain_array=[])

        for node in nodes:
            prnt('fetch node',node)
            if node.id != self_node_id:
                try:
                    success, response = connect_to_node(node, 'network/request_obj', data=data, timeout=(7,25), log_reponse_time=False)
                    if success and response.status_code == 200:
                        received_json = response.json()
                        if received_json['message'].lower() == 'success':
                            return received_json['data']
                except Exception as e:
                    prnt('fetch err 7',str(e))