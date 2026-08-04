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

from utils.locked import dt_to_string, load_key

from os.path import expanduser
homepath = expanduser("~")



import platform
import os
if platform.system() == 'Darwin':
    device_system = 'mac'
elif platform.system() == 'Windows':
    device_system = 'windows'
else:
    device_system = 'linux'




def check_super_commands():
    ...

check_super_commands() # dont run this here, should run at system startup, find the right way - gunicorn startup?

_e_brake_end_dt = None
_e_brake = 0
# 0 = run all
# 1 = run nothing
# 2 = resolve blocks
# 3 = resolve blocks/txs/posts, do not run scrapers

def e_brake(priority):
    global _e_brake
    global _e_brake_end_dt
    if _e_brake_end_dt and _e_brake_end_dt < now_utc():
        _e_brake_end_dt = None
        _e_brake = 0
    if _e_brake and priority >= _e_brake:
        prnt('STOP! E_BREAK',priority,'>=',_e_brake)
        return True
        # raise Exception('E_BREAK')
    return False


def _already_prefixed(value: bytes, max_byte_length: int) -> bool:
    if len(value) < 2:
        return False
    declared_length = int.from_bytes(value[:2], 'big')
    # total stored = 2 (prefix) + max_byte_length (padded data)
    return len(value) == max_byte_length + 2 and declared_length <= max_byte_length

class BinaryBase62Field(models.BinaryField):
    def __init__(self, max_byte_length, *args, **kwargs):
        self.max_byte_length = max_byte_length
        kwargs['max_length'] = max_byte_length + 2
        kwargs.setdefault('editable', True)
        super().__init__(*args, **kwargs)

    def value_from_object(self, obj):
        value = getattr(obj, self.attname)
        if value is None:
            return value
        if isinstance(value, str):
            return value  # already base62
        if isinstance(value, (bytes, memoryview)):
            raw = bytes(value)
            if len(raw) >= 2:
                length = int.from_bytes(raw[:2], 'big')
                return to_base62(raw[2:2 + length])
            return to_base62(raw)
        return value

    def value_to_string(self, obj):
        value = getattr(obj, self.attname)
        if value is None:
            return ''
        if isinstance(value, str):
            # convert to bytes for Django's b64encode session storage
            raw = from_base62(value)
            padded = raw.ljust(self.max_byte_length, b'\x00')
            prefix = len(raw).to_bytes(2, 'big')
            from base64 import b64encode
            return b64encode(prefix + padded).decode('ascii')
        return ''
        
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        raw = bytes(value)
        length = int.from_bytes(raw[:2], 'big')
        return to_base62(raw[2:2 + length])

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        raw = bytes(value)
        length = int.from_bytes(raw[:2], 'big')
        return to_base62(raw[2:2 + length])

    def get_prep_value(self, value):
        if value is None:
            return value
        if isinstance(value, memoryview):
            return bytes(value)
        if isinstance(value, bytes):
            if _already_prefixed(value, self.max_byte_length):
                return value
            actual_length = len(value)
            padded = value.ljust(self.max_byte_length, b'\x00')
            prefix = actual_length.to_bytes(2, 'big')
            return prefix + padded
        if isinstance(value, str):
            # detect standard base64 from Django session/fixture storage
            if len(value) % 4 == 0 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in value):
                try:
                    from base64 import b64decode
                    raw = b64decode(value)
                    if len(raw) == self.max_byte_length + 2:
                        return raw  # already prefixed, came from session storage
                except Exception:
                    pass
            # otherwise treat as base62
            try:
                raw = from_base62(value)
                actual_length = len(raw)
                padded = raw.ljust(self.max_byte_length, b'\x00')
                prefix = actual_length.to_bytes(2, 'big')
                return prefix + padded
            except Exception as e:
                prnt(f"ERROR in str branch: {e}, value={repr(value)}")
                raise
        return value
        
    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop('max_length', None)
        args = [self.max_byte_length] + list(args)
        return name, path, args, kwargs

class BinaryBase64urlField(models.BinaryField):
    def __init__(self, max_byte_length, *args, **kwargs):
        self.max_byte_length = max_byte_length
        kwargs['max_length'] = max_byte_length + 2
        kwargs.setdefault('editable', True)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        raw = bytes(value)
        length = int.from_bytes(raw[:2], 'big')
        data = raw[2:2 + length]
        from utils.locked import bytes_to_base64url
        return bytes_to_base64url(data)

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        raw = bytes(value)
        length = int.from_bytes(raw[:2], 'big')
        from utils.locked import bytes_to_base64url
        return bytes_to_base64url(raw[2:2 + length])

    def get_prep_value(self, value):
        if value is None:
            return value
        if isinstance(value, memoryview):
            return bytes(value)
        if isinstance(value, str):
            from utils.locked import base64url_to_bytes
            raw = base64url_to_bytes(value)
            actual_length = len(raw)
            padded = raw.ljust(self.max_byte_length, b'\x00')[:self.max_byte_length]
            prefix = actual_length.to_bytes(2, 'big')
            return prefix + padded
        if isinstance(value, bytes):
            if _already_prefixed(value, self.max_byte_length):
                return value
            actual_length = len(value)
            # pad RIGHT so actual data is always at the start
            padded = value.ljust(self.max_byte_length, b'\x00')[:self.max_byte_length]
            prefix = actual_length.to_bytes(2, 'big')
            return prefix + padded

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop('max_length', None)
        args = [self.max_byte_length] + list(args)
        return name, path, args, kwargs

class CompressedJSONField(models.JSONField):
    """
    A JSONField that compresses text values before saving
    and decompresses them when accessed.
    """

    def from_db_value(self, value, expression, connection):
        value = super().from_db_value(value, expression, connection)
        if value is None:
            return value
        return self._decompress(value)

    def to_python(self, value):
        value = super().to_python(value)
        if value is None:
            return value
        # Already a dict/list (i.e. came from DB), try to decompress
        if isinstance(value, (dict, list)):
            return self._decompress(value)
        return value

    def get_prep_value(self, value):
        if value is None:
            return value
        compressed = self._compress(value)
        return super().get_prep_value(compressed)

    def _compress(self, value):
        """Recursively compress string values in dicts/lists, or compress directly if string."""
        if isinstance(value, str):
            compressed = zlib.compress(value.encode("utf-8"), level=zlib.Z_BEST_COMPRESSION)
            return {"__compressed__": True, "data": base64.b64encode(compressed).decode("ascii")}
        elif isinstance(value, dict):
            return {k: self._compress(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._compress(item) for item in value]
        return value  # Leave non-string types (int, bool, None) as-is

    def _decompress(self, value):
        """Recursively decompress values that were compressed."""
        if isinstance(value, dict):
            if value.get("__compressed__") is True and "data" in value:
                compressed_bytes = base64.b64decode(value["data"])
                return zlib.decompress(compressed_bytes).decode("utf-8")
            return {k: self._decompress(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._decompress(item) for item in value]
        return value


ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

def to_base62(hash_bytes):
    num = int.from_bytes(hash_bytes, "big")
    if num == 0:
        return ALPHABET[0]
    result = []
    while num:
        result.append(ALPHABET[num % 62])
        num //= 62
    return ''.join(reversed(result))

def from_base62(s):
    num = 0
    for char in s:
        num = num * 62 + ALPHABET.index(char)
    length = max(1, (num.bit_length() + 7) // 8)
    return num.to_bytes(length, "big")

def to_bytes(value):
    if value is None:
        return None
    if isinstance(value, (bytes, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        if any(c in value for c in ('-', '_', '=')):
            import base64
            padding = 4 - len(value) % 4
            if padding != 4:
                value += '=' * padding
            return base64.urlsafe_b64decode(value)
        return from_base62(value)
    raise ValueError(f"Unsupported type: {type(value)}")

def compress_data(data):
    # prnt('-compressing...')
    return data # not compressing right now
    if isinstance(data, str):
        # prnt('opt1')
        data = data.encode('utf-8')  # Only encode if it's a string
    elif isinstance(data, dict) or isinstance(data, list):
        # prnt('opt2')
        data = json.dumps(data).encode('utf-8')

    compressed_data = gzip.compress(data)
    return base64.b64encode(compressed_data).decode('utf-8')
    # return compressed_data

def decompress_data(base64_data):
    # prnt('-decompressing...')
    try:
        compressed_data = base64.b64decode(base64_data)
        decompressed_bytes = gzip.decompress(compressed_data)
        json_data = decompressed_bytes.decode('utf-8')
        data = json.loads(json_data)
        return data
    except Exception as e:
        prntDebug('decompress_data error',str(e))
        try:
            return json.loads(base64_data)
        except:
            return base64_data

def is_debug():
    debugging = False
    try:
        operatorData = get_operatorData()
        if operatorData['myNodes'][operatorData['local_nodeId']]['meta']['debug'] == True:
            return True
        else:
            prnt('whats up debug:',operatorData['myNodes'][operatorData['local_nodeId']]['meta']['debug'])
            prnt('wdb2', operatorData['start_local_install'])
    except Exception as e:
        prnt('is_debug err1',str(e))
    try:
        if 'start_local_install' in operatorData and operatorData['start_local_install'] == True:
            return True
    except Exception as e:
        prnt('is_debug err2',str(e))
    return debugging    

def is_test_env():
    # prntn('---is_test_env')

    operatorData = get_operatorData(return_test=False)
    try:
        if 'isTesting' in operatorData and operatorData['myNodes'][operatorData['local_nodeId']]['settings']['isTesting']:
            return True
    except:
        pass
    import os
    current_dir = os.getcwd()
    
    while True:
        sfolder_path = os.path.join(current_dir, 'sonet')
        if os.path.isdir(sfolder_path):
            file_path = os.path.join(sfolder_path, 'settings/local.py')
            return os.path.isfile(file_path)
        
        parent_dir = os.path.dirname(current_dir)
        
        if current_dir == parent_dir:
            break
        
        current_dir = parent_dir
    
    return False

def timezonify(tz, dt):
    if tz.lower() in ['est', 'newyork', 'washington', 'dc']:
        tz = 'America/New_York'
    elif tz.lower() in ['toronto', 'ottawa']:
        tz = 'America/Toronto'
    else:
        tz = 'UTC'
    if isinstance(dt, str):
        from dateutil.parser import parse
        dt = parse(dt)
    if dt.tzinfo is None:
        local_dt = dt.replace(tzinfo=ZoneInfo(tz))
    else:
        local_dt = dt.astimezone(ZoneInfo(tz))
    return local_dt

_testing = None
_debugging = None

def testing():
    global _testing
    if _testing is None:
        _testing = is_test_env()
    return _testing

def debugging():
    global _debugging
    if _debugging is None:
        _debugging = is_debug()
    return _debugging


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


def list_all_scrapers(plugin='legis'):
    import sys
    import os
    from pathlib import Path
    current_directory = Path(__file__).parent.parent
    sibling_folder = current_directory / plugin / 'generators'
    sys.path.append(str(sibling_folder))
    all_files = []
    for root, dirs, files in os.walk(sibling_folder):
        for file in files:
            if file.endswith('.py'):
                all_files.append(os.path.join(root, file))
    return all_files


def create_share_object(func, region, special, dt=None, iden=None, job_dt=None, task=1):
    if not dt:
        dt = now_utc()
    prnt('-create_share_object', 'func:', func, special, region, dt, iden, job_dt)
    if e_brake(3):
        raise Exception('E_BRAKE')
    if job_dt:
        if job_dt < now_utc() - datetime.timedelta(hours=2):
            prnt('job is greater than two hours old', now_utc())
            return None
    from network.models import DataPacket
    from utils.locked import hash_obj_id
    dp = None
    if not iden:
        if not job_dt:
            job_dt = round_time(dt=dt, dir='down', amount='hour')
        job_iden = f'{func}-{region.id}-{task}-{dt_to_string(job_dt)}-{get_operator_obj("self_nodeId")}'
        prnt('job_iden',job_iden)
        iden = hash_obj_id(DataPacket(), verify=False, specific_data=job_iden, return_data=False, model=None, version=None)
        prnt('iden1',iden)
    if iden:
        dp = DataPacket.objects.filter(id=iden).first()
    if not dp:
        prnt('create dp',iden)
        dp = DataPacket(func=f'scrape_job:{func}')
        dp.id = iden
        dp.jobId = hash_obj_id('DataPacket', specific_data=f"{dt_to_string(job_dt)}{func}{region.id}")
        dp.created = job_dt
        dp.Node_obj = get_self_node()
        dp.task = task
        dp.data['func'] = func
        dp.data['task'] = task
        dp.data['created'] = dt_to_string(job_dt)
        dp.data['started'] = dt_to_string(now_utc())
        dp.data['region_name'] = region.Name
        dp.data['region_id'] = region.id
        dp.data['job_id'] = dp.jobId
        dp.data['shareData'] = []
        dp.Region_obj = region
    dp.data['special'] = special
    dp.save()
    prnt('dp id:',dp.id)
    prnt('jobId:',dp.jobId)
    try:
        if special == 'super':
            create_job(super_share, job_timeout=300, worker='low', clear_chrome_job=False, log=dp.id)
        else:
            create_job(send_for_validation, job_timeout=300, worker='low', clear_chrome_job=False, log=dp.id)
    except Exception as e:
        prnt('Error creating share object 457834', str(e)) 
    return dp

def finishScript(log, gov=None, special=None, func=None, log_event=True, send_off=True):
    from network.models import DataPacket
    if is_id(log):
        log = DataPacket.objects.filter(id=log).first()
    if not log or 'completed' in log.func:
        return None
    prnt('-finishScript', log.data['func'], gov, special)
    gov_id = None
    if gov and isinstance(gov, models.Model):
        gov_id = gov.id
    elif isinstance(gov, str):
        gov_prefix = get_model_prefix('Government')
        if gov.startswith(gov_prefix):
            gov = get_dynamic_model(gov_prefix, id=gov)
            if gov and not has_field(gov, 'proposed_modification') or gov and not gov.proposed_modification:
                gov_id = gov.id
    if 'shareData' in log.data:
        r = len(log.data['shareData'])
        if not gov_id:
            gov_prefix = get_model_prefix('Government')
            for i in log.data['shareData']:
                if isinstance(i, str):
                    if i.startswith(gov_prefix):
                        gov = get_dynamic_model(gov_prefix, id=i)
                        if gov and not has_field(gov, 'proposed_modification') or gov and not gov.proposed_modification:
                            gov_id = gov.id
                            break
                        else:
                            gov = None
                elif isinstance(i, models.Model):
                    if not has_field(i, 'proposed_modification') or not i.proposed_modification:
                        if i._meta.object_name == 'Government':
                            gov = i
                            gov_id = gov.id
                            break
    else:
        r = 'unknown'
    log.data['content_length'] = r
    do_save = False
    if gov_id:
        if 'gov_id' not in log.data or log.data['gov_id'] != gov_id:
            log.data['gov_id'] = gov_id
            do_save = True
    if gov:
        log.data['gov_level'] = gov.gov_level
        do_save = True
    if 'special' in log.data:
        special = log.data['special']
        do_save = True
    if 'finished' not in log.data:
        log.data['finished'] = dt_to_string(now_utc())
        do_save = True
    if do_save:
        log.save()
    if log_event and r:
        logEvent(f'finishScript: {log.data["region_name"]} {log.data["func"]} -item count: {r}')
    if special == 'testing':
        return return_test_result(log)
    elif special == 'super':
        items, completed = super_share(log, gov)
        return completed
    elif 'shareData' in log.data and log.data['shareData'] or 'content' in log.data and log.data['content']:
        if send_off:
            return send_for_validation(log, gov)
    else:
        log.delete()
    return None

def retrieve_browser_data(region, job_name, job_id, requesting_node_id, request_dt, app_name='legis'):
    job_started = now_utc()

    from network.models import Plugin
    plugin = Plugin.objects.filter(app_name=app_name).first()
    if plugin:
        import importlib
        importScript = f'{plugin.app_name}.utils'
        utils_funcs = importlib.import_module(importScript)
        get_scripts_func = getattr(utils_funcs, 'get_scraperScripts')


        scraperScripts = get_scripts_func(region=region)
        func = getattr(scraperScripts, 'data_request')
        fetched_data = func(job_name)
        if fetched_data:
            from network.models import DataPacket
            from utils.locked import sign_for_sending
            self_node_id = get_operator_obj('self_nodeId')
            func_name = f"data_fetch:{job_name}"
            dp = DataPacket(func=f'{func_name}_for:{requesting_node_id}')
            dp.jobId = job_id
            dp.Node_obj_id = self_node_id
            dp.Region_obj = region
            dp.data = fetched_data

            dp.save()
            dp.headers = {'Packet-Id':dp.id, 'Senderid':self_node_id, 'Requesting-Node':requesting_node_id, 'Job-Id':job_id, 'Task':func_name, 'Job-Dt':dt_to_string(request_dt), 'Dt':dt_to_string(now_utc()), 'Func':func_name, 'Region-Id':region.id if region else None}
            dp.save(update_fields=['headers'])

            # compressed_data = json.dumps(iden_list)
            data_to_send = {'type':'data_retrieval', 'packet_id':dp.id, 'job_started':dt_to_string(job_started), 'job_finished':dt_to_string(now_utc()), 'func':func_name, 'senderId':self_node_id, 'region_id':region.id, 'region_name':region.Name, 'content': fetched_data}
            sending_data = sign_for_sending(data_to_send)
            data_to_send = {}
            # compressed_data = None
            prnt('return from data retrieval job_id:',requesting_node_id)
            completed, response = connect_to_node(requesting_node_id, 'network/receive_gathered_data', sending_data, headers=dp.headers)

def request_browser_data(func, country, dt):
    job_dt = round_time(dt)
    self_node_id = get_operator_obj('self_nodeId')
    
    scraper_list, approved_models = get_scrape_duty(region=country, receivedDt=job_dt)

    assigned_nodes = []
    for i in scraper_list:
        if i['region_id'] == country.id and i['function_name'] == func:
            assigned_nodes = i['scraping_order']
            break
    
    assigned_nodes.append(self_node_id)

    from network.models import Node
    nodes = Node.objects.filter(region_data__country_code=country.AbbrName).exclude(id__in=assigned_nodes).exclude(activated_dt=None).exclude(Block_obj=None).filter(suspended_dt=None, expelled_dt=None).order_by('?')
    
    for node in nodes:
        prnt('node',node)
        content = sign_post_header(data={'country_code':country, 'address':url},  post='post', target_node=node)
        success, response = connect_to_node(node, 'utils/proxyme', data=None, self_node=None, content=content, headers={}, operatorData=None, timeout=(5,25), get=False, stream=False, node_is_string=False, log_reponse_time=False)
        prnt('success',success)
        # prnt('response:',type(response),str(response)[:1000])
        if success:
            return response
        


def open_browser(url=None, headless=True, chrome_testing=False):
    prnt("--opening browser", url)
    # ua = UserAgent()
    # user_agent = ua.random
    def chrome_for_testing():

        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options

        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        if headless:
            options.add_argument("--headless")

        if device_system == 'linux':
            chrome_binary_path = os.path.expanduser("~/chrome-for-testing/chrome-linux64/chrome")
            chromeDriver_path = os.path.expanduser("~/chrome-for-testing/chromedriver-linux64/chromedriver")
        elif device_system == 'mac':
            chrome_binary_path = "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
            chromeDriver_path = "/usr/local/bin/chromedriver"
            options.add_argument("--disable-breakpad")  # Disables crashpad crash reporter
            options.add_argument("--no-default-browser-check")
            options.add_argument("--no-first-run")
            options.add_argument("--disable-logging")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])  # Prevent logs
            # chrome_binary_path = "../chrome-for-testing/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
            # chromeDriver_path = "../chrome-for-testing/chromedriver-mac-arm64/chromedriver"
        # elif device_system == 'mac':
        #     chrome_binary_path = "../chrome-for-testing/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
        #     chromeDriver_path = "../chrome-for-testing/chromedriver-mac-arm64/chromedriver"

        # options.add_argument(f"user-agent={user_agent}")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36")
        options.binary_location = chrome_binary_path
        service = Service(chromeDriver_path)
        return webdriver.Chrome(service=service, options=options), service
    
    def normal_chrome(attempt=1):

        try:
            # Chrome options
            chrome_options = Options()
            chrome_options.binary_location = "/usr/bin/google-chrome"  # Explicit Chrome binary path
            chrome_options.add_argument('--no-sandbox')
            if headless:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36")
            chrome_options.add_argument('--remote-debugging-port=9222')

            caps = DesiredCapabilities().CHROME.copy()
            caps["pageLoadStrategy"] = "normal"

            service = webdriver.chrome.service.Service("/usr/local/bin/chromedriver")  # Explicit Chromedriver path
            driver = webdriver.Chrome(service=service, options=chrome_options)

            return driver, service
        except Exception as e:
            prnt('driver fail38572',str(e))

            version_err = '''Message: session not created: This version of ChromeDriver only supports Chrome version'''
            install_err = '''Unable to obtain driver for chrome'''
            if version_err in str(e):
                # Current browser version is 136.0.7103.92 with binary path /usr/bin/google-chrome'''
                x = str(e).find('Current browser version is ')+len('Current browser version is ')
                y = str(e)[x:].find(' ')
                required_version = str(e)[x:x+y]
                prnt('required_version',required_version)
                if attempt == 1:
                    update_chromeDriver(required_version)
                    return normal_chrome(attempt=2)
            elif install_err in str(e):
                if attempt == 1:
                    update_chromeDriver()
                    return normal_chrome(attempt=2)

    import subprocess
    import re
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    def get_chrome_version(fallback="134.0.0.0"):
        try:
            # macOS
            result = subprocess.run(
                ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                version = re.search(r"\d+\.\d+\.\d+\.\d+", result.stdout)
                if version:
                    return version.group()
        except FileNotFoundError:
            pass

        try:
            # Linux
            result = subprocess.run(
                ["google-chrome", "--version"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                version = re.search(r"\d+\.\d+\.\d+\.\d+", result.stdout)
                if version:
                    return version.group()
        except FileNotFoundError:
            pass

        return fallback

    def get_chrome_binary():
        # Common macOS Chrome locations
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        
        try:
            result = subprocess.run(
                ["mdfind", "kMDItemCFBundleIdentifier == 'com.google.Chrome'"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().splitlines():
                binary = os.path.join(line, "Contents/MacOS/Google Chrome")
                if os.path.exists(binary):
                    return binary
        except Exception:
            pass
        
        raise FileNotFoundError("Chrome binary not found on this system")

    def new_chrome():
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        import platform

            
        chrome_ver = get_chrome_version()
        prnt('chrome_version',chrome_ver)
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-extensions")
        options.add_argument(
            f"--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_ver} Safari/537.36"
        )

        if platform.system() == "Darwin":
            options.binary_location = get_chrome_binary()

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        return driver

    driver = new_chrome()

    if url:
        driver.get(url)
        prnt('url ready')

    return driver

def close_browser(driver, service=None):
    if driver:
        driver.quit()
    try:
        service.stop()
    except Exception:
        pass

def update_chromeDriver(required_version=None):
    prnt('-update_chromeDriver',required_version)
    if platform.system() == 'Darwin': 
        # import requests
        # r = requests.get('https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE')
        # if r.status_code == 200:
        #     stable_ver = r.content.decode('utf-8')
            # chrome_link = f'https://storage.googleapis.com/chrome-for-testing-public/{stable_ver}/mac-arm64/chrome-mac-arm64.zip'
        driver_link = f'https://storage.googleapis.com/chrome-for-testing-public/{required_version}/mac-arm64/chromedriver-mac-arm64.zip'

        group = subprocess.check_output("id -gn", shell=True).decode().strip()
        import getpass
        username = getpass.getuser()
        commands = [
            ['wget', '-O', '/tmp/chromedriver_mac64.zip', driver_link],
            ['unzip', '/tmp/chromedriver_mac64.zip', '-d', '/tmp'],
            ['sudo', '-S', 'mv', '/tmp/chromedriver', '/usr/local/bin/'],
            ['sudo', '-S', 'chown', f'{username}:{group}', '/usr/local/bin/chromedriver'],
            ['sudo', '-S', 'chmod', '+x', '/usr/local/bin/chromedriver'],
            ['rm', '/tmp/chromedriver_mac64.zip'],
        ]
    else:
        if not required_version:
            required_version = '131.0.6778.85'
        commands = [
            ['wget', '-O', '/tmp/chromedriver-linux64.zip', f'https://storage.googleapis.com/chrome-for-testing-public/{required_version}/linux64/chromedriver-linux64.zip'],
            ["sudo", "-S", "apt", "install", "zip"],
            # ["unzip", "/tmp/chromedriver-linux64.zip", "-y"],
            ["unzip", "-o", "/tmp/chromedriver-linux64.zip", "-d", "/tmp"],
            ["sudo", "-S", "mv", "/tmp/chromedriver-linux64/chromedriver", "/usr/local/bin/"],
            ["sudo", "-S", "chown", "root:root", "/usr/local/bin/chromedriver"],
            ["sudo", "-S", "chmod", "+x", "/usr/local/bin/chromedriver"],
            ["sudo", "-S", "rm", "/tmp/chromedriver-linux64.zip"],
        ]

    import subprocess
    systemPass = fetch_secure_item('sysPass')
    for cmd in commands:
        prnt('cmd',cmd)
        result = subprocess.run(cmd, input=systemPass, text=True, capture_output=True)
        prnt('result',result)

def proxy_request(url, country='CA'):
    prnt('-proxy_request',country,url)
    import requests
    self_node = get_self_node()
    if 'country_code' in self_node.region_data and self_node.region_data['country_code'] == country:
        prnt('self_run')
        r = requests.get(url)
        return r
    sources = [
        f"https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http&country={country}",
        f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1000&country={country}&ssl=all&anonymity=all",
        f"https://letushide.com/api/proxylist.txt?country={country}&type=http",

        # "https://pubproxy.com/api/proxy?limit=1000&country=CA&type=http",
        # "https://gimmeproxy.com/api/getProxy?country=CA&protocol=http",
        # "https://hide.mn/en/proxy-list/countries/canada/",
    ]

    x = 0
    for src in sources:
        x += 1
        try:
            prnt()
            prnt(f"Fetching from {src}")
            r = requests.get(src, timeout=10)
            r.raise_for_status()
            text = r.text.strip()
            try:
                js = r.json()
            except ValueError:
                js = None

            results = []
            if js:
                if "proxy" in js:
                    # single proxy
                    results.append(js["proxy"])
                if "data" in js and isinstance(js["data"], list):
                    for item in js["data"]:
                        ip = item.get("ip")
                        prt = item.get("port") or item.get("proxy_port")
                        if ip and prt:
                            results.append(f"{ip}:{prt}")
            else:
                for line in text.splitlines():
                    line = line.strip()
                    if line and ":" in line and len(line) < 30:
                        results.append(line)
            if results:
                # proxy_list = [line.strip() for line in txt.splitlines() if ":" in line]
                num = 0
                for proxy in results:
                    num += 1
                    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
                    prnt(f"Trying ({x}/{len(sources)}) {num}/{len(results)} ...")
                    ip1 = "https://httpbin.org/ip"
                    try:
                        r = requests.get(ip1, proxies=proxies, timeout=25)
                        prnt("Success:", r.text)

                        r = requests.get("http://ip-api.com/json", proxies=proxies, timeout=30)
                        country_code = r.json().get("countryCode")
                        print('country_code',country_code)

                        # country_code = requests.get("https://ipapi.co/country/", proxies=proxies, verify=False, timeout=60).text.strip()
                        # prnt('country:',country_code)
                        if country_code == country:
                            r = requests.get(url, proxies=proxies, timeout=240)
                            prnt("Success get")
                            return r
                        else:
                            time.sleep(3)

                    except requests.exceptions.Timeout:
                        prnt("Request timed out")
                    except Exception as e:
                        # prnt("Failed:", e)
                        pass
        except Exception as e:
            prnt("Failed fetch from", src, ":", str(e))

    # use network proxyme request
    from network.models import Node
    # would be more secure to select node from get_node_assignment - requires job and dt input - make sure each scraper uses a proxy through a different node by different users
    nodes = Node.objects.filter(region_data__country_code=country).exclude(activated_dt=None).exclude(Block_obj=None).filter(suspended_dt=None).order_by('-pos')
    
    
    for node in nodes:
        prnt('trying node',node)
        content = sign_post_header(data={'country_code':country, 'address':url},  post='post', target_node=node)
        success, response = connect_to_node(node, 'utils/proxyme', data=None, self_node=None, content=content, headers={}, operatorData=None, timeout=(5,25), get=False, stream=False, node_is_string=False, log_reponse_time=False)
        prnt('success',success)
        # prnt('response:',type(response),str(response)[:1000])
        if success:
            return response

    return None


def create_job(job_func, job_timeout=60, worker='low', clear_chrome_job=False, **kwargs):
    prnt('-create_job',worker,job_func)
    try:
        if isinstance(worker, str):
            queue = django_rq.get_queue(worker)
        else:
            queue = worker
        if not exists_in_worker(job_func.__name__, queue=queue, **kwargs):
            queue.enqueue(job_func, **kwargs, job_timeout=job_timeout, result_ttl=7200)
            
        if clear_chrome_job:
            from utils.cronjobs import clear_chrome
            queue.enqueue(clear_chrome, job_timeout=10)
    except Exception as e:
        prnt('create_job fail 459', str(e))
        

def remove_accents(input_str):
    import unicodedata
    normalized_str = unicodedata.normalize('NFD', input_str)
    filtered_str = ''.join(
        char for char in normalized_str 
        if unicodedata.category(char) != 'Mn'
    )
    return unicodedata.normalize('NFC', filtered_str)

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


_self_nodeId = None
_self_address = None
_self_local_address = None
_node_keys = None
_user_id = None

def get_operator_obj(obj, operatorData=None):
    # prnt('-get_operator_obj', obj)
    result = None
    if obj == 'keyPair':
        global _node_keys
        if not _node_keys:
            _node_keys = fetch_secure_item('node_keys')
            if _node_keys and 'keyId' not in _node_keys:
                from accounts.models import UserPubKey
                upk = UserPubKey.objects.filter(id=hash_upk_id(_node_keys['pubKey'])).first()
                if upk:
                    _node_keys['keyId'] = upk.id
            prnt('stored node_keys',_node_keys)
        if not _node_keys:
            raise ValueError(f"missing _node_keys:{_node_keys}")
        return _node_keys
    elif obj == 'userId':
        global _user_id
        if not _user_id:
            operatorData = get_operatorData(operatorData)
            _user_id = operatorData['user_id']
        return _user_id
    elif obj in ['local_nodeId', 'self_nodeId']:
        global _self_nodeId
        if not _self_nodeId:
            operatorData = get_operatorData(operatorData)
            if 'local_nodeId' in operatorData:
                _self_nodeId = operatorData['local_nodeId']
            elif is_test_env():
                from network.models import Node
                _self_nodeId = Node.objects.first().id
        return _self_nodeId
    elif obj == 'address':
        global _self_address
        if not _self_address:
            _self_address = fetch_secure_item('address')
        return _self_address
    elif obj == 'local_address':
        global _self_local_address
        if not _self_local_address:
            operatorData = get_operatorData(operatorData)
            _self_local_address = operatorData['myNodes'][operatorData['local_nodeId']]['settings']['localhost']
        return _self_local_address
    return result

def get_operatorData(val=None, return_test=True):
    # prnt('-get_operatorData')
    if val:
        return val
    result = fetch_secure_item('operatorData')
    return result if result else {}

def write_operatorData(data):
    try:
        current_data = get_operatorData()
        data = {**current_data, **data}
    except:
        pass
    store_secure_item("operatorData", data)


def encrypt(text):
    if not text:
        return text
    try:
        key = load_key()
        
        cipher_suite = Fernet(key)
        cipher_text = cipher_suite.encrypt(text.encode())
        return cipher_text
    except:
        return text

def decrypt(text):
    # prnt('-decrypt', text)
    if not text:
        return text
    try:
        key = load_key()
        cipher_suite = Fernet(key)
        decrypted_text = cipher_suite.decrypt(text).decode()
        return decrypted_text
    except Exception as e:
        prnt('decrypt err',str(e))
        return text


def fetch_secure_item(val_name):
    # prnt('-fetch_secure_item',val_name)
    try:
        with open(homepath + f"/Sonet/.data/operator_data/{val_name}.enc", 'rb') as file:
            encrypted_data = file.read()
            data_string = decrypt(encrypted_data)
    except Exception as e:
        prnt('fetch_secure_item err 1, carry_on',str(e))
        try:
            server_path = Path(homepath + '/Sonet/.data')
            server_path.mkdir(parents=True, exist_ok=True)
            data_string = json.dumps({}, indent=4)
            encrypted_data = encrypt(data_string)
            with open(homepath + f"/Sonet/.data/operator_data/{val_name}.enc", 'wb') as file:
                file.write(encrypted_data)
            import stat
            key_file = os.path.expanduser(f"~/Sonet/.data/operator_data/{val_name}.enc")
            os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)  # 600: Owner read & write
            with open(homepath + f"/Sonet/.data/operator_data/{val_name}.enc", 'rb') as file:
                encrypted_data = file.read()
                data_string = decrypt(encrypted_data)
        except Exception as e:
            prnt('fetch item fail 2',str(e))
            return None
    try:
        return json.loads(data_string)
    except:
        return data_string

def store_secure_item(val_name, data):
    prnt('-store_secure_item',val_name,data)
    data_string = json.dumps(data, indent=4)
    encrypted_data = encrypt(data_string)
    with open(homepath + f"/Sonet/.data/operator_data/{val_name}.enc", 'wb') as file:
        file.write(encrypted_data)


def script_test_error(testing, err, wait=False, log=None):
    if testing:
        prnt('script_test_error',err)
        if wait:
            time.sleep(wait)
    elif log:
        logEvent('scrapeAssignment: ' + log[0].Name + ' ' + log[1] + ' ' + err + ' ' + now_utc(), log_type='Tasks')

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
                'Bill':13, 'Committee':14, 'Meeting':15, 'Statement':16, 'Motion':17, 'Vote':18, 'Agenda':19, 'BillText':20, 'Update':21,'Spren':22,'Notification':23,'UserVote':24}
    
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
    prnt('-has_field',field_name,model,type(model))
    if is_model_or_instance(model):
        prnt('-has_field',[f.name for f in model._meta.get_fields()])
        if exclude_method:
            try:
                return any([f.name for f in model._meta.get_fields() if f.name == field_name])
            except Exception as e:
                prnt('has_field err 6892',str(e))
        return hasattr(model, field_name)
    elif isinstance(model, dict):
        prnt('is dict')
        if exclude_method:
            try:
                return any([f for f in model if f == field_name])
            except Exception as e:
                prnt('has_field err 6893',str(e))
        if model.get(field_name, None):
            return True
        else:
            return False
    else:
        prnt('else',type(model))

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
    prntDebug('obj_list',obj_list)
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
        elif isinstance(i, models.Model):
            obj_type = i._meta.object_name
            value = i.id
            model = i
        prntDebug('value',value,'model',model,'obj_type',obj_type,'obj_types',obj_types,'skipping_models',skipping_models)
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
                            prnt('field',field)
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
                prntDebug('skip',skip,'exclude',exclude)
                err += '2'
                if not skip and exclude:
                    err += '3'
                    if 'fields' in exclude:
                        if isinstance(exclude['fields'], dict):
                            for field_name, field_value in exclude['fields'].items():
                                prnt('field_name',field_name,'field_value',field_value)
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
                                if isinstance(field, dict):
                                    for field_name, field_value in field.items():
                                        if field_value.startswith('!'):
                                            field_value = field_value.replace('!','')
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
                prntDebug('err',err,'obj_type',obj_type,'value',value,'skip',skip)
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
            return app_dict
        
    # prnt('app_dict',app_dict)
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

def get_plugin(obj, name=False):
    try:
        if name:
            return obj._meta.app_label
        from network.models import Plugin
        return Plugin.objects.filter(app_name=name).first()
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
    prntDebug('dynamic_bulk_create', model_name)

    if not model:
        model = get_model(model_name)
    if not model:
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


def sync_model(xModel, jsonContent, skip_fields=[], do_save=True, opBlock_data={}, force_sync=False, get_missing_blocks=True, skip_verify=False):
    from utils.locked import verify_obj_to_data, convert_to_dict, get_node_assignment
    proceed_to_sync = False
    updatedDB = False
    sigs = []
    try:
        received_data = json.loads(jsonContent)
    except:
        received_data = jsonContent
    iden = 'unknown'
    try:
        if 'id' in received_data:
            iden = received_data['id']
    except:
        pass
    prnt('**syncing',iden, xModel)

    if 'created' in received_data:
        dt = received_data['created']
    else:
        dt = now_utc()
    if skip_verify:
        is_valid = True
    else:
        is_valid, users = verify_obj_to_data(xModel, received_data, return_user=True)
    if not is_valid:
        prnt('is_not_validA:',is_valid)
        prntDebug('xmodel',str(convert_to_dict(xModel))[:500],'\ndata',str(received_data)[:500])
        return xModel, [], is_valid, False
    try:
        if not force_sync:
            prnt('pq1')
            if is_locked(xModel):
                prnt('return sync is locked')
                return xModel, [], is_valid, False
            if has_field(xModel, 'lastUpdate') and xModel.lastUpdate and 'lastUpdate' in received_data:
                prnt('pq2')
                previously_updated = True
                if 'Validator_obj' in received_data and received_data['Validator_obj']:
                    if not xModel.Validator_obj or xModel.Validator_obj.id != received_data['Validator_obj']:
                        previously_updated = False
                elif 'Block_obj' in received_data and received_data['Block_obj']:
                    if not xModel.Block_obj or xModel.Block_obj.id != received_data['Block_obj']:
                        previously_updated = False
                elif received_data['signed'] != xModel.signed:
                    previously_updated = False
                if previously_updated and string_to_dt(received_data['lastUpdate']) <= string_to_dt(xModel.lastUpdate):
                    prnt('previously updated - skipping sync')
                    return xModel, [], is_valid, False
            elif not has_field(xModel, 'lastUpdate') and has_field(xModel, 'signed') and {k:v['pk'] for k,v in xModel.signed.items()} == {k:v['pk'] for k,v in received_data['signed'].items()}:
                if not has_field(xModel, 'Validator_obj') or xModel.Validator_obj and xModel.Validator_obj.id != received_data['Validator_obj']:
                    prnt('previously updated p2 - skipping sync')
                    return xModel, [], is_valid, False

    except Exception as e:
        prnt('fail130584',str(e))
        pass
    # userTypes = ['User', 'UserPubKey', 'Wallet', 'Transaction', 'UserVote', 'SavePost', 'Follow']
    if is_valid:  
        if xModel._meta.object_name == 'Spren' or xModel._meta.object_name == 'SprenItem':
            # get list of Nodes with ai_capable, xModel.publicKey should match node.User_obj.get_keys()
            pass
        elif xModel._meta.object_name in ['Sonet','Plugin','SuperSign']:
            if not users:
                target_keys = resolve_target_keys(received_data['signed'])
                from accounts.models import UserPubKey
                upks = UserPubKey.objects.filter(id__in=target_keys).only('User_obj')
                users = [upk.User_obj for upk in upks]

            prnt("['Sonet','Plugin','SuperSign']",'user',users)
            if all(user for user in users if user.assess_super_status(dt=dt)):
                proceed_to_sync = True
        elif xModel._meta.object_name in ['Node']:
            proceed_to_sync = True
            if 'activated_dt' in received_data and not value_is_none(received_data['activated_dt']):
                if 'node_type' not in received_data or value_is_none(received_data['node_type']):
                    proceed_to_sync = False
                if 'address' not in received_data or value_is_none(received_data['address']):
                    proceed_to_sync = False
            if proceed_to_sync and any(x in received_data['node_type'] for x in ['intelligence']) or proceed_to_sync and 'abilities' in received_data and received_data['abilities']:
                if not users:
                    target_keys = resolve_target_keys(received_data['signed'])
                    from accounts.models import UserPubKey
                    upks = UserPubKey.objects.filter(id__in=target_keys).only('User_obj')
                    users = [upk.User_obj for upk in upks]
                if not all(user for user in users if user.assess_super_status(dt=dt)):
                    proceed_to_sync = False
        elif xModel._meta.object_name in ['UserAction']:
            proceed_to_sync = True
        elif xModel._meta.app_label.lower() in ['transactions']:
            if xModel._meta.object_name == 'Wallet': # is user created
                proceed_to_sync = True
            elif xModel._meta.object_name == 'Transaction':
                proceed_to_sync = True # should check assignment elsewhere along with attached block
        elif xModel._meta.object_name != 'Validator' and xModel._meta.app_label.lower() not in ['posts', 'legis']: # should check for any plugin, dont hardcode 'legis' here
            # not task assigned object - excluding blocks which are checked elsewhere
            proceed_to_sync = True
        if not proceed_to_sync:
            prnt('x2 not yet good')
            if 'func' in received_data and received_data['func'].lower() == 'super':
                if 'CreatorNode_obj' in received_data:
                    from network.models import Node
                    node = Node.objects.filter(id=received_data['CreatorNode_obj']).first()
                    if node and node.User_obj.assess_super_status(dt=string_to_dt(received_data['created'])):
                        proceed_to_sync = True
                else:
                    sig_data = get_sigData(received_data)
                    if sig_data['pk'] in get_superuser_keys(dt=sig_data['dt']):
                        proceed_to_sync = True
    
            elif not proceed_to_sync and received_data['objType'] == 'Validator' and received_data['validatorType'] == 'Block':
                proceed_to_sync = True
            elif not proceed_to_sync:
                # verify which nodes were assigned to scrape and validate this data, should verify creatorNode as well as validatorNode are correct - currently only checks validatorNode
                if all(field in received_data for field in ['created', 'networkChain', 'func']):
                    prnt('opBlock_data',opBlock_data)
                    # should cross reference with scraper jobs - when should func have been run?
                    
                    creator_nodes, validator_nodes = get_node_assignment(dt=received_data['created'], chainId=received_data['networkChain'], func=received_data['func'], opBlock_data=opBlock_data, strings_only=True)
                    
                    if received_data['objType'] == 'Validator':
                        prnt('pp1',received_data['CreatorNode_obj'], received_data.get('validatorType', ''))
                        if any(isinstance(n, models.Model) for n in creator_nodes):
                            creator_nodes = [v.id for v in creator_nodes]
                        prnt('creator_nodes',creator_nodes)
                        if any(isinstance(n, models.Model) for n in validator_nodes):
                            validator_nodes = [v.id for v in validator_nodes]
                        prnt('validator_nodes',validator_nodes)
                        if received_data['CreatorNode_obj'] in validator_nodes or received_data['CreatorNode_obj'] in creator_nodes:
                            proceed_to_sync = True
                        else:
                            sig_data = get_sigData(received_data)
                            if sig_data['pk'] in get_superuser_keys(dt=sig_data['dt']):
                                proceed_to_sync = True      
                        
                    elif 'validatorNodeId' in received_data and received_data['validatorNodeId'] in validator_nodes:
                        
                        if not any(isinstance(n, models.Model) for n in creator_nodes):
                            from network.models import Node
                            creator_nodes = Node.objects.filter(id__in=creator_nodes).values('User_obj_id')
                        prnt('pp3',creator_nodes)
                        if not users:
                            target_keys = resolve_target_keys(received_data['signed'])
                            from accounts.models import UserPubKey
                            upks = UserPubKey.objects.filter(id__in=target_keys).only('User_obj')
                            users = [upk.User_obj for upk in upks]
                        if all(item in [c['User_obj_id'] for c in creator_nodes] for item in [user.id for user in users]):
                            proceed_to_sync = True
                    else:
                        sig_data = get_sigData(received_data)
                        if sig_data['pk'] in get_superuser_keys(dt=sig_data['dt']):
                            proceed_to_sync = True      

        prntDebug('proceed_to_sync:',proceed_to_sync)
        if proceed_to_sync:
            import copy
            xModel_copy = copy.deepcopy(xModel)
            xModel, sigs, updatedDB = set_model_attrs(xModel, received_data, None, dt, skip_fields=skip_fields, get_missing_blocks=get_missing_blocks)
            if not updatedDB:
                prnt('obj not updated')
                xModel = xModel_copy
            else:
                from utils.locked import get_signing_data, verify_data, bytes_to_base64url
                pk = None
                if xModel._meta.object_name == 'User':
                    sig_data = get_sigData(xModel.signed)
                    if sig_data['publicKey']:
                        pk = sig_data['publicKey'] # if user obj, upk does not yet exist, must pass publicKey here
                    else:
                        pk = sig_data['pk']
                if not verify_data(get_signing_data(xModel), pk, signature=sigs):
                    prnt('failed re verification',str(get_signing_data(xModel))[:1000])
                    updatedDB = False
                    proceed_to_sync = False
                    xModel = xModel_copy

                else:
                    prnt('-xModel sync, attempt save')
                    if has_field(xModel, 'validated'):
                        xModel.validated = None
                    if has_field(xModel, 'commitChain') and has_field(xModel, 'networkChain') and xModel.networkChain == xModel.id:
                        network_chain, xModel, commit_chain = find_or_create_chain_from_object(xModel)
                    if do_save or has_method(xModel, 'on_confirmation') and has_method(xModel, 'Block_obj') and xModel.Block_obj:
                        if has_method(xModel, 'save_if_new'):
                            xModel, is_new = xModel.save_if_new()
                        else:
                            if func_accepts_var(xModel.save, 'sig'):
                                xModel.save(sig=sigs)
                            else:
                                xModel.save()
                        save_sigs(sigs)
                        prnt('-sync_model saved',xModel)

                        if has_method(xModel, 'on_confirmation') and has_field(xModel, 'Block_obj') and xModel.Block_obj:
                            xModel = xModel.on_confirmation(xModel.Block_obj) 

                    else:
                        if has_field(xModel, 'updated_on_node'):
                            xModel.updated_on_node = now_utc()
                        prnt('do not save')
    prnt('-return sync:',xModel, proceed_to_sync, updatedDB, is_valid)
    return xModel, sigs, proceed_to_sync, updatedDB

def sync_and_share_object(obj, received_json, skip_verify=False):
    try:
        data = json.loads(received_json)
    except:
        data = received_json
    obj, sigs, valid_obj, updatedDB = sync_model(obj, data, skip_verify=skip_verify)
    if valid_obj and updatedDB:
        share_with_network(obj)
    return obj, valid_obj

def set_model_attrs(obj, data, user=None, dt=None, skip_user_check=False, skip_fields=[], debug=False, get_missing_blocks=True):
    import decimal
    from django.contrib.contenttypes.models import ContentType
    from utils.locked import sort_for_sign
    prnt('-set_model_attrs',obj,get_missing_blocks)
    
    updatedDB = False
    updated_fields = []
    run_on_block_confirmation = False
    block = None
    sigs = []
    fields = obj._meta.fields
    if debug:
        prnt('fields',fields)
        prnt('data',data)
    superFields = {'is_supported':['True',True], 'isVerified':'any', 'is_superuser':'any', 'is_staff':'any', 'is_admin':'any', 'fcm_capable':'any', 'ai_capable':'any', 'validated':'any', 'abilities':'any', 'keyType':['guardian','super'], 'node_level':['super'], 'node_type':['intelligence']}
    for f in fields:
        try:
            if f.name not in data:
                if debug:
                    prnt('skip',f.name)
            elif f.name not in skip_fields:
                if debug:
                    prnt('sync:',f.name, f.__class__.__name__, data[f.name])
                proceed = True
                if f.name in superFields:
                    prnt('field is super field', f.name, superFields[f.name], data[f.name])
                    if superFields[f.name] == 'any' or data[f.name] in superFields[f.name] or getattr(obj, f.name) in superFields[f.name]:
                        prnt('is in super field', superFields[f.name], data[f.name], getattr(obj, f.name))
                        proceed = False
                        from utils.locked import detect_security
                        from accounts.models import UserPubKey
                        for dt, sig_data in data['signed'].items():
                            if not proceed:
                                if 'publicKey' in sig_data:
                                    security = detect_security(sig_data['publicKey'], key_type='pubkey')
                                else:
                                    security = detect_security(sig_data['pk'], key_type='pubkey')
                                if security == 'ML_DSA_87':
                                    prnt('is in super field step 2')
                                    for dt, sig_data in data['signed'].items():
                                        upk = UserPubKey.objects.filter(id=sig_data['pk'], keyType='guardian').first()
                                        prnt('upk',upk)
                                        if upk:
                                            if 'lastUpdate' in data and upk.super_level('guardian', dt=string_to_dt(data['lastUpdate'])):
                                                proceed = True
                                            elif 'created' in data and upk.super_level('guardian', dt=string_to_dt(data['created'])):
                                                proceed = True
                                        else:
                                            from network.models import Sonet
                                            if not Sonet.objects.all().exists():
                                                proceed = True
                                

                if proceed:
                    if str(data[f.name]) in ['Val:N','None']:
                        if getattr(obj, f.name) != None:
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                        setattr(obj, f.name, None)
                    elif f.__class__.__name__ == 'BooleanField' and (str(data[f.name]).lower() == 'true' or str(data[f.name]).lower() == 'false'):
                        value = data[f.name]
                        if f.__class__.__name__ == 'BooleanField':
                            if str(data[f.name]).lower() == 'false':
                                value = False
                            elif str(data[f.name]).lower() == 'true':
                                value = True
                        if str(getattr(obj, f.name)) != value:
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                prnt('--UDP:',str(getattr(obj, f.name)), value)
                        setattr(obj, f.name, value)
                    elif str(f.name) == "signed":
                        if debug:
                            prnt('== signed',str(data[f.name])[:50])
                        from network.models import Signature
                        # from utils.locked import base64url_to_bytes
                        signed = {}
                        for dt, sig_data in data['signed'].items():
                            prnt('sig_data',sig_data)
                            if is_id(sig_data['pk']):
                                signed[dt] = {'pk':sig_data['pk']}
                            else:
                                signed[dt] = {'pk':hash_upk_id(sig_data['pk'])}
                            if 'req' in sig_data:
                                signed[dt]['req'] = sig_data['req']
                            if 'publicKey' in sig_data:
                                from accounts.models import UserPubKey
                                if not UserPubKey.objects.filter(id=signed[dt]['pk']).exists():
                                    prnt('add full publicKey')
                                    signed[dt]['publicKey'] = sig_data['publicKey']
                            if 'sig' in sig_data:
                                sig_obj = Signature.objects.filter(pointerId=data['id'], Upk_obj__id=signed[dt]['pk'], DateTime=string_to_dt(dt)).first()
                                prnt('sig_obj',sig_obj)
                                if not sig_obj:
                                    sig_obj = Signature(pointerId=data['id'], Upk_obj_id=signed[dt]['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                    updatedDB = True
                                    updated_fields.append('sig_obj')
                                    if debug:
                                        prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                                sigs.append(sig_obj)
                        if str(signed) != str(data[f.name]):
                            updatedDB = True
                            updated_fields.append(f.name)
                            # if debug:
                            #     prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                        setattr(obj, f.name, signed)

                    elif 'name' in str(f.name).lower() and isinstance(data[f.name], str):
                        if not is_id(data[f.name]) and not has_profanity(data[f.name], level=3):
                            setattr(obj, f.name, data[f.name])
                    elif str(f.name) in ['Block_obj','SenderBlock_obj','ReceiverBlock_obj']:
                        
                        if f.name in data and data[f.name] and 'networkChain' in data and not value_is_none(data[f.name]):
                            if not getattr(obj, f.name) or getattr(obj, f.name).id != data[f.name]:
                                from network.models import Block, Blockchain, Node, mandatoryChains
                                block = Block.objects.filter(id=data[f.name]).first()
                                prnt('block532:',block)
                                if not block:
                                    chain = Blockchain.objects.filter(id=data['networkChain']).values('genesisId').first()
                                    if chain:
                                        self_node = Node.objects.filter(id=get_operator_obj('self_nodeId')).values('chain_array').first()
                                        if self_node['chain_array'] and chain['genesisId'] in self_node['chain_array'] or get_pointer_type(chain['genesisId']) in mandatoryChains:
                                            # prnt('y3')
                                            if not block or block.validated == False:
                                                # prnt('get_missing_blocks',get_missing_blocks)
                                                if get_missing_blocks:
                                                    returned_objs = request_items(requested_items=[data[f.name]], return_updated_objs=True, return_updated_ids=False, return_missing=False, check_consensus=True, downstream_worker=False, get_missing_blocks=False, override_completed=True)
                                                    prnt('returned_objs',returned_objs)
                                                    for block in returned_objs:
                                                        if block.id == data[f.name]:
                                                            break
                                # if block and block.validated == False:
                                #     # prnt('y4')
                                #     pass
                                if block and block.validated:
                                    if data['id'] in block.data or data['id'] in block.extraData:
                                        prnt('set attr?')
                                        from utils.locked import check_commit_data
                                        if check_commit_data(data, block.data[data['id']]) or check_commit_data(data, block.extraData[data['id']]):
                                        #     ...
                                        # if block.data[data['id']] == get_commit_data(data, extra_data=None):
                                            prnt('set attr!')
                                            setattr(obj, f.name, block)
                                            updatedDB = True
                                            updated_fields.append(f.name)
                                            run_on_block_confirmation = True
                                        else:
                                            return obj, sigs, False
                    elif str(f.name) in ['activated_dt']:
                        if debug:
                            prnt('is activated_dt',data[f.name])
                        if f.name in data and data[f.name]:
                            if obj.suspended_dt and getattr(obj, f.name):
                                if obj.suspended_dt < string_to_dt(data[f.name]):
                                    obj.suspended_dt = None
                            setattr(obj, f.name, string_to_dt(data[f.name]))
                    elif str(f.name) in ['end_life_dt']:
                        if debug:
                            prnt('is end_life_dt',data[f.name])
                        if not obj.end_life_dt:
                            setattr(obj, f.name, string_to_dt(data[f.name]))
                    elif str(f.name) in ['networkChain','commitChain']:
                        if data[f.name] == 'Nodes':
                            pass
                        elif data[f.name] == 'Sonet':
                            from network.models import _EarthChain_genesisId
                            if get_plugin(obj, name=True) == 'network' or data['id'] == _EarthChain_genesisId:
                                setattr(obj, f.name, data[f.name])
                        else:
                            setattr(obj, f.name, data[f.name])
                    elif 'prevVersion' == str(f.name):
                        if debug:
                            prnt('sync prevVersion',data[f.name])
                        if value_is_none(value):
                            value = None
                        else:
                            value = str(data[f.name])
                        setattr(obj, f.name, value)
                        prnt('prevVersion',value)
                        if not value_is_none(value):
                            prnt('is not none')
                            prev_ver = get_model(obj._meta.object_name).objects.filter(id=value).first()
                            if not prev_ver:

                                returned_objs = request_items(requested_items=[value], return_updated_objs=True, return_updated_ids=False, return_missing=False, check_consensus=True, downstream_worker=False, get_missing_blocks=False, override_completed=True)
                                prnt('returned_objs',returned_objs)
                            elif prev_ver and has_field(prev_ver, 'validated') and not prev_ver.validated:
                                from utils.locked import validate_obj
                                validate_obj(obj=prev_ver, pointer=None, validators=[], save_obj=True, update_pointer=True, verify_validator=True, add_to_queue=True, opBlock_data={})

                    
                    elif '_obj' in str(f.name):
                        # prnt('y21')
                        id_field = str(f.name) + '_id'
                        if str(data[f.name]) == 'Val:N':
                            value = None
                        else:
                            value = str(data[f.name])
                        if debug:
                            prnt('is _obj',value)
                        if not getattr(obj, id_field) and data[f.name] or str(getattr(obj, id_field)) != value:
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                try:
                                    prnt('--UDP:',str(getattr(obj, id_field)), str(data[f.name]))
                                except Exception as e:
                                    prnt(str(e))
                        if value:
                            # foreignKey = get_dynamic_model(value, id=value)
                            foreignKey = get_model(value).objects.filter(id=value).exists()
                            if not foreignKey and get_pointer_type(value) != 'Update': # only request if field in signing_fields

                                returned_objs = request_items(requested_items=[value], return_updated_objs=True, return_updated_ids=False, return_missing=False, check_consensus=False, downstream_worker=False, get_missing_blocks=False, override_completed=True)
                                for i in returned_objs:
                                    if i.id == value:
                                        foreignKey = i
                                if not foreignKey:
                                    foreignKey = create_dynamic_model(value, id=value)
                                    foreignKey.save()
                            if foreignKey:
                                setattr(obj, id_field, value)
                        else:
                            setattr(obj, id_field, value)
                    

                    elif f.__class__.__name__ == 'ArrayField' or isinstance(data[f.name], list) or '_array' in f.name:
                        if debug:
                            prnt('is array or list',data[f.name])
                        if value_is_none(data[f.name]):
                            value = None
                        else:
                            value = list(data[f.name])
                        if str(sort_for_sign(getattr(obj, f.name))) != str(sort_for_sign(value)):
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                prnt('--UDP:',str(sort_for_sign(getattr(obj, f.name))), str(value))
                        setattr(obj, f.name, value)
                    elif f.__class__.__name__ == 'ImageField' or 'imageField' in f.name:
                        if debug:
                            prnt('is imageField')
                        if str(sort_for_sign(getattr(obj, f.name))) != str(sort_for_sign(data[f.name])):
                            updatedDB = True
                            updated_fields.append(f.name)
                            # if debug:
                            #     prnt('--UDP:',str(sort_for_sign(getattr(obj, f.name))), str(data[f.name]))
                        # setattr(obj, f.name, data[f.name])
                        from django.core.files.base import ContentFile
                        # prnt('data[f.name]',data[f.name])       
                        # prnt('data["file_path"]',data["file_path"].replace('images/',''))               
                        image_bytes = base64.b64decode(data[f.name])
                        # prnt('x1')
                        obj.imageField.save(data["file_path"].replace('images/',''), ContentFile(image_bytes), save=False)
                        # prnt('x2')

                    elif f.name == 'pointerKey':
                        # pointer = get_dynamic_model(data['pointerId'], id=data['pointerId'])
                        setattr(obj, f.name, ContentType.objects.get_for_model(get_model(data['pointerId'])))
                    elif f.__class__.__name__ == 'IntegerField' or isinstance(data[f.name], int):
                        if debug:
                            prnt('is int',data[f.name])
                        if str(getattr(obj, f.name)) != str(data[f.name]):
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                        setattr(obj, f.name, int(data[f.name]))
                    elif f.__class__.__name__ == 'DecimalField' or isinstance(data[f.name], decimal.Decimal):
                        if debug:
                            prnt('is decimal',data[f.name])
                        if str(getattr(obj, f.name)) != str(data[f.name]):
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                        setattr(obj, f.name, decimal.Decimal(data[f.name]))
                    elif str(data[f.name]) == "[]":
                        if debug:
                            prnt('== []',data[f.name])
                        if str(getattr(obj, f.name)) != str(data[f.name]):
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                        setattr(obj, f.name, "[]")
                    elif str(data[f.name]).startswith('[') and str(data[f.name]).endswith(']'):
                        if debug:
                            prnt('starts with []', json.dumps(data[f.name]))
                        if str(getattr(obj, f.name)) != str(data[f.name]):
                            updatedDB = True
                            updated_fields.append(f.name)
                            if debug:
                                prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                        setattr(obj, f.name, json.dumps(data[f.name]))
                    elif f.__class__.__name__ == 'DateTimeField':
                        if debug:
                            prnt('is DateTimeField', data[f.name])
                        prnt("string_to_dt(data[f.name])",data[f.name],'st2dt:',string_to_dt(data[f.name]))
                        try:
                            if not getattr(obj, f.name) and data[f.name] or str(dt_to_string(getattr(obj, f.name))) != str(data[f.name]):
                                updatedDB = True
                                updated_fields.append(f.name)
                        except:
                            updatedDB = True
                            updated_fields.append(f.name)
                        setattr(obj, f.name, string_to_dt(data[f.name]))
                    elif f.__class__.__name__ == 'CharField' or f.__class__.__name__ == 'TextField':
                        if debug:
                            prnt('is string',data[f.name])
                        if len(str(data[f.name])) < 10000000:
                            if str(data[f.name]) == 'Val:N':
                                value = None
                            else:
                                value = str(data[f.name])
                            if str(getattr(obj, f.name)) != value:
                                updatedDB = True
                                updated_fields.append(f.name)
                                if debug:
                                    prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                            setattr(obj, f.name, value)
                    else:
                        if debug:
                            prnt('sync esle',data[f.name])
                        if len(str(data[f.name])) < 10000000:
                            if str(data[f.name]) == 'Val:N':
                                value = None
                            else:
                                value = str(data[f.name])
                            fieldData = parse_input(value)
                            if str(sort_for_sign(getattr(obj, f.name))) != str(fieldData) and str(getattr(obj, f.name)) != str(data[f.name]):
                                updatedDB = True
                                updated_fields.append(f.name)
                                if debug:
                                    prnt('--UDP:',str(sort_for_sign((getattr(obj, f.name)))), str(data[f.name]), fieldData)
                            setattr(obj, f.name, fieldData)
                    

        except Exception as e:
            prnt('fsyncattr4937',f.name,str(e),str(data[f.name])[:100])
            pass

    if has_field(obj , 'Block_obj') and obj.Block_obj and obj.id in obj.Block_obj.data:
        from utils.locked import check_commit_data
        if not check_commit_data(obj, obj.Block_obj.data[obj.id]):
            obj.Block_obj = None
    prnt('updated_fields::',updated_fields)
    prnt('updatedDBx1',updatedDB)
    return obj, sigs, updatedDB

def super_sync(target, received_data, do_save=False, skip_fields=['latestVer'], if_empty_fields=[]):
    prntDebug('-super_sync',skip_fields)
    dt = None
    if isinstance(received_data, dict):
        if 'created' in received_data:
            dt = received_data['created']
    if not dt:
        dt = now_utc()

    target, sigs, updatedDB = set_model_attrs(target, received_data, dt=dt, skip_fields=skip_fields)

    if do_save:
        if func_accepts_var(target.save, 'sig'):
            from utils.locked import bytes_to_base64url
            target.save(sig=sigs)
        else:
            target.save()
        save_sigs(sigs)
    else:
        target.updated_on_node = now_utc()
    return target, sigs

def save_sigs(sigs):
    prnt('-save_sigs',sigs)
    sig = None
    pointerId = None
    sig_idens = []
    for sig in sigs:
        if not pointerId:
            pointerId = sig.pointerId
        if not sig.id:
            sig.save()
        sig_idens.append(sig.id)
    prnt('sig_idens',sig_idens)
    if sig:
        obj = sig.Pointer_obj
        prnt('obj id',obj.id)
        from network.models import Signature
        from utils.locked import verify_obj_to_data, verify_data, get_signing_data
        for s in Signature.objects.filter(pointerId=pointerId).exclude(id__in=sig_idens):
            remove = True
            for k, v in obj.signed.items():
                if remove == False and 'pk' in v and v['pk'] == s.Upk_obj.id:
                    if verify_data(get_signing_data(obj), s.Upk_obj.publicKey, signature=s.sig, key_type=None, skip_sort=False):
                        remove = False
            # if not verify_obj_to_data(obj, obj):
            if remove:
                prnt('delete sig:',s)
                s.delete()


def find_or_create_chain_from_object(obj, recheck_chain=False):
    prntDebug('-find_or_create_chain_from_object',obj)

    def get_commitChain(obj, network_chain, commit_chain, obj_is_model):     
        if obj_is_model and has_field(obj, 'commitChain') or not obj_is_model and 'commitChain' in obj:
            if obj_is_model and has_method(obj, 'get_chains'):
                network_chain, commit_chain = obj.get_chains()
            
            elif obj_is_model and has_field(obj, 'commitChain') and obj.commitChain or not obj_is_model and 'commitChain' in obj and obj['commitChain']:
                
                if obj_is_model and is_id(obj.commitChain):
                    commit_chain = Blockchain.objects.filter(Q(id=obj.commitChain)|Q(genesisId=obj.commitChain)).only('id','genesisName','genesisId').first()
                    if not commit_chain:
                        if get_pointer_type(networkChain) == 'Blockchain':
                            commit_chain = Blockchain(id=obj.commitChain)
                        else:
                            commit_chain = Blockchain(genesisId=obj.commitChain)
                        commit_chain.save()
                elif not obj_is_model and is_id(obj['commitChain']):
                    commit_chain = Blockchain.objects.filter(Q(id=obj['commitChain'])|Q(genesisId=obj['commitChain'])).only('id','genesisName','genesisId').first()
                    if not commit_chain:
                        if get_pointer_type(obj['commitChain']) == 'Blockchain':
                            commit_chain = Blockchain(id=obj['commitChain'])
                        else:
                            commit_chain = Blockchain(genesisId=obj['commitChain'])
                        commit_chain.save()
                else:
                    try:
                        if obj_is_model:
                            chainGenObj = getattr(obj, f"{obj.commitChain}_obj")
                        else:
                            chainGenObj = get_dynamic_model(obj['commitChain'], id=obj[f"{obj['commitChain']}_obj"])
                        if chainGenObj:
                            commit_chain = Blockchain.objects.filter(genesisId=chainGenObj.id).only('id','genesisName','genesisId').first()
                    except:
                        pass

        return network_chain, commit_chain
    
    if isinstance(obj, dict):
        obj_is_model = False
    else:
        obj_is_model = True
    from network.models import Blockchain, Sonet, _EarthChain_genesisId, selectableChains, mandatoryChains
    network_chain = None
    commit_chain = None
    ChainTypes = selectableChains + mandatoryChains
    if not recheck_chain and obj_is_model:
        if has_method(obj, 'get_chains'):
            network_chain, commit_chain = obj.get_chains()
            return network_chain, obj, commit_chain
        elif has_field(obj, 'networkChain') and is_id(obj.networkChain):
            network_chain = Blockchain.objects.filter(id=obj.networkChain).defer('queuedData').first()
            if network_chain:
                network_chain, commit_chain = get_commitChain(obj, network_chain, commit_chain, obj_is_model)
                return network_chain, obj, commit_chain
    if obj_is_model and has_field(obj, 'proposed_modification') and obj.proposed_modification or not obj_is_model and 'proposed_modification' in obj and obj['proposed_modification']:
        return None, obj, None # proposals are not committed to chain, commit after modification completed
    
    elif has_field(obj, 'networkChain') and (obj_is_model and obj.networkChain == 'Region' or not obj_is_model and obj['networkChain'] == 'Region'):
        prnt('p4')
        region = None
        from posts.models import Region
        if obj_is_model and has_field(obj, 'Region_obj') or not obj_is_model and 'Region_obj' in obj:
            if obj_is_model:
                region = obj.Region_obj
            else:
                region = Region.supported_objects.filter(id=obj['Region_obj']).first()
        elif obj_is_model and has_field(obj, 'pointerId') or not obj_is_model and 'pointerId' in obj:
            if obj_is_model:
                pointerId = obj.pointerId
            else:
                pointerId = obj['pointerId']
            regionId = get_dynamic_model(pointerId, values=['Region_obj__id'], id=pointerId)
            prnt('regionId',regionId)
            region = Region.supported_objects.filter(id=regionId['Region_obj__id']).first()
        elif obj_is_model and obj._meta.object_name == 'Region' or not obj_is_model and obj['objType'] == 'Region':
            if obj_is_model:
                region = obj
                if obj.id == _EarthChain_genesisId:
                    commit_chain = Blockchain.objects.filter(genesisId='Sonet').only('id','genesisName','genesisId').first()
            else:
                region = Region.supported_objects.filter(id=obj['id']).first()
                if obj['id'] == _EarthChain_genesisId:
                    commit_chain = Blockchain.objects.filter(genesisId='Sonet').only('id','genesisName','genesisId').first()
            
        if region:
            network_chain = Blockchain.objects.filter(genesisId=region.id).only('id','genesisName','genesisId').first()
            if not network_chain:
                network_chain = Blockchain(genesisId=region.id, genesisType='Region', genesisName=region.Name, created=region.created)
                network_chain.save()
            elif network_chain.genesisName != get_chainName(region):
                network_chain.genesisName = get_chainName(region)
                network_chain.save()
    else:
        from network.models import universalChains
        if has_field(obj, 'networkChain') and (obj_is_model and obj.networkChain in universalChains or not obj_is_model and obj['networkChain'] in universalChains):
            prnt('p5')
            if obj_is_model:
                for n in universalChains:
                    if n == obj.networkChain:
                        chainId = n
                        break
            else:
                for n in universalChains:
                    if n == obj['networkChain']:
                        chainId = n
                        break
            network_chain = Blockchain.objects.filter(Q(id=chainId)|Q(genesisId=chainId)).defer('queuedData').first()
            if not network_chain:
                sonet = Sonet.objects.only('id').first()
                if sonet:
                    prnt('new chain branched from Sonet chain',chainId)
                    network_chain = Blockchain(genesisId=chainId, genesisType=chainId, genesisName=chainId, created=sonet.created)
                    network_chain.save()

        elif has_field(obj, 'networkChain') and (obj_is_model and obj.networkChain and not has_method(obj, 'get_chains') or not obj_is_model and 'networkChain' in obj and obj['networkChain']):
            if obj_is_model:
                obj_id = obj.id
                obj_type = obj._meta.object_name
                networkChain = obj.networkChain
            else:
                obj_id = obj['id']
                obj_type = obj['objType']
                networkChain = obj['networkChain']
            if networkChain in [obj_type, obj_id, 'self']:
                network_chain = Blockchain.objects.filter(Q(id=obj_id)|Q(genesisId=obj_id)).only('id','genesisName','genesisId').first()
                if not network_chain:
                    created_time = get_timeData(obj)
                    name_field = any_field_contains(obj, 'Name')
                    if name_field:
                        if obj_is_model:
                            name = getattr(obj, name_field)
                        else:
                            name = obj[name_field]
                    else:
                        if obj_is_model:
                            name = str(obj)
                        else:
                            name = obj['id']
                    network_chain = Blockchain(genesisId=obj_id, genesisType=obj_type, genesisName=name, created=created_time)
                    network_chain.save()
            elif networkChain in universalChains:
                network_chain = Blockchain.objects.filter(genesisName=networkChain).only('id','genesisName','genesisId').first()
            elif networkChain == 'Plugin':
                if obj_is_model:
                    plugin = get_plugin(obj)
                else:
                    plugin = get_plugin(get_model(obj_type))
                if plugin:
                    network_chain = Blockchain.objects.filter(genesisId=plugin.id).only('id','genesisName','genesisId').first()
            elif is_id(networkChain):
                network_chain = Blockchain.objects.filter(Q(id=networkChain)|Q(genesisId=networkChain)).only('id','genesisName','genesisId').first()
                if not network_chain:
                    if get_pointer_type(networkChain) == 'Blockchain':
                        network_chain = Blockchain(id=networkChain)
                    else:
                        network_chain = Blockchain(genesisId=networkChain)
                    network_chain.save()
            else:
                try:
                    if obj_is_model:
                        chainGenObj = getattr(obj, f"{obj.networkChain}_obj")
                    else:
                        chainGenObj = get_dynamic_model(networkChain, id=obj[f"{networkChain}_obj"])
                    if chainGenObj:
                        network_chain = Blockchain.objects.filter(genesisId=chainGenObj.id).only('id','genesisName','genesisId').first()
                except Exception as e:
                    prnt('find chain err 1',str(e))

            if obj_is_model and has_field(obj, 'commitChain') and obj.commitChain or not obj_is_model and 'commitChain' in obj and obj['commitChain']:
                if obj_is_model and is_id(obj.commitChain):
                    commit_chain = Blockchain.objects.filter(Q(id=obj.commitChain)|Q(genesisId=obj.commitChain)).only('id','genesisName','genesisId').first()
                    if not commit_chain:
                        if get_pointer_type(networkChain) == 'Blockchain':
                            commit_chain = Blockchain(id=obj.commitChain)
                        else:
                            commit_chain = Blockchain(genesisId=obj.commitChain)
                        commit_chain.save()
                elif not obj_is_model and is_id(obj['commitChain']):
                    commit_chain = Blockchain.objects.filter(Q(id=obj['commitChain'])|Q(genesisId=obj['commitChain'])).only('id','genesisName','genesisId').first()
                    if not commit_chain:
                        if get_pointer_type(obj['commitChain']) == 'Blockchain':
                            commit_chain = Blockchain(id=obj['commitChain'])
                        else:
                            commit_chain = Blockchain(genesisId=obj['commitChain'])
                        commit_chain.save()
                else:
                    if obj_is_model and obj.commitChain in universalChains:
                        commit_chain = Blockchain.objects.filter(genesisName=obj.commitChain).only('id','genesisName','genesisId').first()
                    if not commit_chain:
                        try:
                            if obj_is_model:
                                chainGenObj = getattr(obj, f"{obj.commitChain}_obj")
                            else:
                                chainGenObj = get_dynamic_model(obj['commitChain'], id=obj[f"{obj['commitChain']}_obj"])
                            commit_chain = Blockchain.objects.filter(genesisId=chainGenObj.id).only('id','genesisName','genesisId').first()
                            if not commit_chain:
                                commit_chain = Blockchain(genesisId=chainGenObj.id)
                                commit_chain.save()
                        except Exception as e:
                            prnt('find chain err 2',str(e))
                    
            prntDebug('done find chainx', network_chain, obj, commit_chain)
            return network_chain, obj, commit_chain
    
    if not commit_chain:
        network_chain, commit_chain = get_commitChain(obj, network_chain, commit_chain, obj_is_model)

    prntDebug('done find chain', network_chain, obj, commit_chain)
    return network_chain, obj, commit_chain

def get_data(items_list, include_related=False, return_model=False, verify_data=True, result_as_dict=False, include_deletions=False, special_request={}):
    prntDebug('--get data sgtart',len(items_list),'result_as_dict',result_as_dict,'return_model',return_model)
    from network.models import Validator, EventLog, _OperationsChain_genesisId
    from utils.locked import verify_obj_to_data, convert_to_dict
    mb_size = 0
    modelObjs = []
    obj_types = {}
    iden_list = []
    not_found = []
    not_valid = []
    if result_as_dict:
        storedData = {}
    else:
        storedData = []
    if not items_list:
        return storedData, not_found, not_valid
    def add_to_list(objType, value):
        if objType and value and is_id(value):
            if objType in obj_types:
                if value not in obj_types[objType]:
                    obj_types[objType].append(value)
            else:
                obj_types[objType] = [value]
            iden_list.append(value)

    def add_to_return_list(obj, target_list_or_dict):
        if return_model:
            if isinstance(target_list_or_dict, dict):
                if obj._meta.object_name not in target_list_or_dict:
                    target_list_or_dict[obj._meta.object_name] = {}
                target_list_or_dict[obj._meta.object_name][obj.id] = obj
            else:
                target_list_or_dict.append(obj)
        else:
            if isinstance(target_list_or_dict, dict):
                if obj._meta.object_name not in target_list_or_dict:
                    target_list_or_dict[obj._meta.object_name] = {}
                target_list_or_dict[obj._meta.object_name][obj.id] = convert_to_dict(obj)
            else:
                target_list_or_dict.append(convert_to_dict(obj))
        return target_list_or_dict

    if isinstance(items_list, dict):
        for key, value in items_list.items():
            if key == 'All' or key == _OperationsChain_genesisId or key == 'New':
                # node block
                objType = 'Node'
                for i in value:
                    add_to_list(objType, i)
                break
            elif key != 'meta':
                objType = get_pointer_type(key)
                if objType:
                    if is_id(key):
                        add_to_list(objType, key)
                    elif isinstance(value, list):
                        for i in value:
                            if is_id(i):
                                add_to_list(objType, i)
                    elif isinstance(value, dict):
                        if 'id' in value:
                            add_to_list(objType, value['id'])
                        else:
                            add_to_list(objType, key)
                    elif isinstance(value, str) and is_id(value):
                        add_to_list(objType, value)
            
    elif isinstance(items_list, list):
        if isinstance(items_list[0], dict):
            for i in items_list:
                if 'objType' in i:
                    add_to_list(i['objType'], i['id'])
                else:
                    for key, value in i.items():
                        if key == 'All' or key == _OperationsChain_genesisId or key == 'New':
                            # node block
                            objType = 'Node'
                            for i in value:
                                add_to_list(objType, i)
                            break
                        elif key != 'meta':
                            objType = get_pointer_type(key)
                            if objType:
                                if is_id(key):
                                    add_to_list(objType, key)
                                elif isinstance(value, list):
                                    for i in value:
                                        add_to_list(objType, i)
                                elif isinstance(value, dict):
                                    if 'id' in value:
                                        add_to_list(objType, value['id'])
                                    else:
                                        add_to_list(objType, key)
                                elif isinstance(value, str):
                                    add_to_list(objType, value)
        elif isinstance(items_list[0], models.Model):
            for i in items_list:
                modelObjs.append(i)
                iden_list.append(i.id)
        elif isinstance(items_list[0], str):
            for i in items_list:
                if is_id(i):
                    add_to_list(get_pointer_type(i), i)
    prnt('include_related',include_related)
    if include_related:
        validators = Validator.objects.filter(data__has_any_keys=iden_list).exclude(id__in=iden_list)
        prnt('validators',validators)
        for obj in validators:
            prnt('obj',obj)
            if not verify_data or verify_obj_to_data(obj, obj):
                storedData = add_to_return_list(obj, storedData)
                mb_size += to_megabytes(obj)
            else:
                not_valid = add_to_return_list(obj, not_valid)
    for obj in modelObjs:
        if not verify_data or not has_field(obj, 'signed') or verify_obj_to_data(obj, obj):
            storedData = add_to_return_list(obj, storedData)
            mb_size += to_megabytes(obj)
        else:
            not_valid = add_to_return_list(obj, not_valid)

    for obj_type in obj_types:
        prnt(' searching obj_types[obj_type]',obj_type, len(obj_types[obj_type]))
        if special_request:
            prntDebug('special_request',special_request)
            model = get_model(obj_type)
            if 'exclude' in special_request and has_field(model, next(iter(special_request['exclude'].keys()))):
                objs = get_dynamic_model(model, list=True, exclude=special_request['exclude'], id__in=obj_types[obj_type])
            else:
                objs = get_dynamic_model(obj_type, list=True, id__in=obj_types[obj_type])
        else:
            objs = get_dynamic_model(obj_type, list=True, id__in=obj_types[obj_type])
        if objs:
            for obj in objs:
                if not verify_data or not has_field(obj, 'signed') or verify_obj_to_data(obj, obj):
                    storedData = add_to_return_list(obj, storedData)
                    mb_size += to_megabytes(obj)
                else:
                    not_valid = add_to_return_list(obj, not_valid)
                obj_types[obj._meta.object_name].remove(obj.id)
    if include_related:
        from posts.models import Update
        updates = Update.objects.filter(pointerId__in=iden_list).exclude(id__in=iden_list).distinct('pointerId').order_by('-pointerId', '-created')
        for obj in updates:
            if not verify_data or verify_obj_to_data(obj, obj):
                storedData = add_to_return_list(obj, storedData)
                mb_size += to_megabytes(obj)
            else:
                not_valid = add_to_return_list(obj, not_valid)
            try:
                obj_types[obj._meta.object_name].remove(obj.id)
            except:
                pass
        notifications = get_dynamic_model('Notification', list=True, pointerId__in=iden_list)
        for obj in notifications:
            if not verify_data or verify_obj_to_data(obj, obj):
                storedData = add_to_return_list(obj, storedData)
                mb_size += to_megabytes(obj)
            else:
                not_valid = add_to_return_list(obj, not_valid)
            try:
                obj_types[obj._meta.object_name].remove(obj.id)
            except:
                pass

    for obj_type, idList in obj_types.items():
        for i in idList:
            not_found.append(i)
    if include_deletions:
        delLogs = []
        if not_found:
            delLogs = EventLog.objects.filter(type='Deletion_Log', data__has_any_key=not_found)
            prnt('delLogs:',delLogs.count())
            not_found_list = not_found
            for log in delLogs:
                for i in not_found_list:
                    if i in log:
                        not_found.remove(i)
            if not return_model:
                return storedData, not_found, not_valid, [convert_to_dict(d) for d in delLogs]
        return storedData, not_found, not_valid, delLogs
    
    prnt('results: data:',len(storedData), 'not_found:',len(not_found),'not_valid:',len(not_valid),'mb_size', mb_size)
    return storedData, not_found, not_valid

def get_all_objects(items):
    prnt('-get_all_objects',len(items))
    found = []
    data = {}
    for i in items:
        if isinstance(i, dict) and 'id' in i:
            i = i['id']
        m = get_pointer_type(i)
        if m:
            if m not in data:
                data[m] = []
            data[m].append(i)
    for objType, id_list in data.items():
        objs = get_dynamic_model(objType, list=True, id__in=id_list)
        prnt('objType',objType,'found',len(objs), 'id_list_len',len(id_list), 'id_list',id_list)
        if objs:
            found = found + list(objs)
    prnt('returning',len(found))
    return found
    

def super_share(log=None, gov=None, func=None, val_type='super', job_id=None, adjust_created_time=True):

    # other nodes do not seem to verify all of this data on reception

    # super_share can handle a single scrape function or a singular item at a time, not items for multiple chains
    # from blockchain.models import get_scraperScripts, get_latest_dataPacket, get_self_node, Validator, sigData_to_hash, get_operatorData, get_user, logEvent, DataPacket, convert_to_dict
    prnt('-super_share', gov, 'func:', func,'log1:',log,'now_utc',now_utc())
    from network.models import DataPacket, Validator
    from posts.models import Region
    items = []
    approved_funcs = []
    job_time = None
    
    if is_id(log):
        log = DataPacket.objects.filter(id=log).first()
    if not log:
        return 0, False
    if log._meta.object_name == 'DataPacket' and 'process' not in log.func and 'scrape' not in log.func:
        prnt('job previously completed',log.id)
        return 0, False
    if isinstance(log, list):
        items = log
    if isinstance(log, models.Model):
        if log._meta.object_name == 'DataPacket' and 'shareData' in log.data:
            if log.data['shareData']:
                func = log.data['func']
                items = get_all_objects(log.data['shareData'])
                prnt('func:',func)
                if 'job_dt' in log.data:
                    job_time = string_to_dt(log.data['job_dt'])
                    prnt('job_dt1',dt_to_string(job_time))
                elif 'created' in log.data:
                    job_time = string_to_dt(log.data['created'])
                job_id = log.id
                # go.delete()
                # region = json.loads(log.data['region_dict'])
                if 'gov_level' in log.data:
                    gov_level = log.data['gov_level']
                elif 'gov_id'in log.data:
                    from legis.models import Government
                    gov = Government.objects.filter(id=log.data['gov_id']).first()
                    if gov:
                        gov_level = gov.gov_level
                region_name = log.data['region_name']
                region_id = log.data['region_id']
                region = Region.objects.filter(id=region_id).first()
                from legis.utils import get_scrape_duty
                scraper_list, approved_models = get_scrape_duty(gov=gov, receivedDt=job_time, region=region, gov_level=gov_level, func=func)
                prnt('approved_models',approved_models)
                model_types = list({i._meta.object_name for i in items})
                prnt('model_types',model_types)
                for key, value in approved_models.items():
                    value = value + ['Update','Notification']
                    result = all(item in value for item in model_types)
                    if result:
                        approved_funcs.append(key)
                prnt('approved_funcs',approved_funcs)
        else:
            if has_field(log, 'func'):
                func = log.func
            items = [log]
    if not job_time:
        job_time = round_time(dt=now_utc(), dir='down', amount='hour')
    prnt('log2:',log)
    operatorData = get_operatorData()
    self_node = get_self_node(operatorData=operatorData)
    prnt('self_node', self_node)
    prnt('items length:',len(items))
    is_super = False
    if self_node:
        is_super = self_node.User_obj.assess_super_status()
    else:
        user = get_user(obj=items[0])
        if user:
            is_super = user.assess_super_status()
    prnt('log3:',log)
    prnt('is_super',is_super)
    if is_super and len(items) > 0:
        dataPacket = None
        network_chain = None
        validator = None
        # approved_funcs = []
        if not isinstance(items, list):
            items = [items]
        
        prnt('log4:',log)
        prnt('func',func)
        prnt('approved_funcs',approved_funcs)
        if func in approved_funcs:
            prnt('is yes')
        else:
            prnt('is not')
        if func in ['super'] or func in approved_funcs:
            prnt('proceed to validate')
            # prnt('items',items)
            from utils.locked import sign_obj, convert_to_dict, validate_obj
            from posts.models import Post, Update, update_post
            processed_data = {'obj_ids':[],'hashes':{}}
            for i in items:
                prnt('i',i.id)
                # proceed = False
                # if has_field(i, 'CreatorNode_obj') and i.CreatorNode_obj == self_node:
                proceed = True

                if has_field(i, 'Region_obj') and not i.Region_obj:
                    i.Region_obj = log.Region_obj

                if has_method(i, 'required_for_validation'):
                    for c in i.required_for_validation():
                        if '.' in c:
                            attr = rgetattr(i, c)
                        else:
                            attr = getattr(i, c)
                        if not attr:
                            prnt('FAIL PROCeed',i.id,c,attr,'\n\n')
                            proceed = False
                            break
                if proceed:
                    prnt('proceed')
                    obj = None
                    if has_field(i, 'Validator_obj') and i.Validator_obj:
                        if has_field(i, 'signed') and i.signed:
                            processed_data['hashes'][i.id] = sigData_to_hash(i)
                    elif has_field(i, 'validated') and i.validated:
                        if has_field(i, 'signed') and i.signed:
                            processed_data['hashes'][i.id] = sigData_to_hash(i)
                    prnt('pro2')
                    prnt('self_node',self_node)
                    i.func = 'super'
                    i.CreatorNode_obj = self_node
                    i.validatorNodeId = self_node.id
                    do_sync = True
                    if has_field(i, 'proposed_modification') and i.proposed_modification:
                        prnt('handle proposed_modification')
                        modded_obj = i
                        prnt('modded_obj',modded_obj)
                        obj = get_or_create_model(modded_obj._meta.object_name, id=modded_obj.proposed_modification)
                        prnt('obj',obj)
                        if not obj.signed or obj.signed != modded_obj.signed:
                            if not has_field(obj, 'lastUpdate') or obj.lastUpdate and string_to_dt(obj.lastUpdate) < string_to_dt(modded_obj.lastUpdate):
                                prnt('super sync')
                                if not obj.created:
                                    obj.created = job_time
                                obj, sigs = super_sync(obj, convert_to_dict(modded_obj), skip_fields=['latestVer','id'])
                                prntn('done sync',convert_to_dict(obj))
                                obj.proposed_modification = None
                                obj.Validator_obj = None
                                obj.save()
                                save_sigs(sigs)
                                obj = sign_obj(obj, operatorData=operatorData)
                                super(get_model(modded_obj._meta.object_name), modded_obj).delete()
                                do_sync = False
                            else:
                                do_sync = False
                    
                    if do_sync and not is_locked(i):
                        if adjust_created_time or not i.created:
                            i.created = job_time
                        network_chain, obj, commit_chain = find_or_create_chain_from_object(obj)
                        obj = sign_obj(i, operatorData=operatorData)
                    if obj:
                        if not network_chain:
                            prnt('get blockchain')
                            chainId = 'All'
                            if has_field(obj, 'networkChain'):
                                # from utils.models import find_or_create_chain_from_object
                                network_chain, obj, commit_chain = find_or_create_chain_from_object(obj)
                                if network_chain:
                                    chainId = network_chain.id

                        if not dataPacket:
                            prnt('get datapacket')
                            dataPacket = get_latest_dataPacket(chainId)
                            prnt('dataPacket',dataPacket)

                        if not validator:
                            prnt('get validator')
                            validator = Validator(jobId=job_id, CreatorNode_obj=self_node, validatorType=val_type, func='super', is_valid=True)
                            if network_chain:
                                validator.networkChain = network_chain.genesisId
                            validator.save()
                        processed_data['obj_ids'].append(obj.id)

                        from utils.locked import get_signing_data
                        prnt('get_signing_data:',get_signing_data(obj))
                        obj_hash = sigData_to_hash(obj)
                        prnt('obj_hash',obj_hash)
                        validator.data[obj.id] = obj_hash
                        processed_data['hashes'][obj.id] = obj_hash
                        if obj and has_method(obj, 'boot'):
                            if not Post.all_objects.filter(pointerId=obj.id).exists():
                                obj.boot()
            prnt('log6:',log)
            prnt('super next')
            if validator:
                prnt('log6.1')
                validator = sign_obj(validator, operatorData=operatorData)
                prnt('log6.2')
                if dataPacket:
                    prnt('log6.3')
                    processed_data['obj_ids'].append(validator.id)
                    processed_data['hashes'][validator.id] = sigData_to_hash(validator)
                    dataPacket.add_item_to_share(processed_data['hashes'])
                    prnt('log6.4')
                if network_chain:
                    prnt('log6.5')
                    network_chain.add_item_to_queue(validator)
                    print('validate posts')
                prnt('log6.6')
                prnt("get_model_prefix('Update')",get_model_prefix('Update'),"get_model_prefix('Notification')",get_model_prefix('Notification'),"get_model_prefix('BillText')",get_model_prefix('BillText'))
                prefixes = [get_model_prefix('Update'),get_model_prefix('Notification')]
                btxt = get_model_prefix('BillText')
                if btxt:
                    prefixes.append(btxt)

                for i in items:
                    if not i.id:
                        prnt('xia',i)
                        prnt('xi',i.id)
                objs = [i for i in items if i.id and not i.id.startswith(get_model_prefix('Update')) and not i.id.startswith(get_model_prefix('Notification'))]
                for i in objs:
                    i.refresh_from_db()
                    if validate_obj(obj=i, pointer=i, validators=[validator], save_obj=True, update_pointer=True):
                        try:
                            if has_method(i, 'upon_validation'):
                                i.upon_validation()
                            if has_method(i, 'on_confirmation'):
                                i = i.on_confirmation()
                        except Exception as e:
                            prnt('***ERROR*** 9823',str(e))
                for i in objs:
                    prnt('c2d:',convert_to_dict(i))
                pointerIdens = [i for i in processed_data['obj_ids'] if not i.startswith(tuple(prefixes))]
                prnt('pointerIdens',pointerIdens)
                while pointerIdens:
                    posts = Post.all_objects.filter(pointerId__in=pointerIdens[:500]).exclude(validated=True)
                    to_queue = []
                    if testing():
                        for p in posts:
                            p.validated = True
                            p, updated_fields = update_post(p=p, save_p=True)
                            to_queue.append(p.pointerId)
                    else:
                        for p in posts:
                            validated = p.validate(validators=[validator])
                            if validated:
                                to_queue.append(p.pointerId)
                            else:
                                pointer = p.get_pointer()
                                if pointer and pointer.Validator_obj == validator:
                                    pointer.Validator_obj = None
                                    pointer.save()
                    if network_chain and to_queue:
                        network_chain.add_item_to_queue(to_queue)
                    if len(pointerIdens) >= 500:
                        pointerIdens = pointerIdens[500:]
                    else:
                        pointerIdens = []
                updateIdens = [u for u in processed_data['obj_ids'] if u.startswith(get_model_prefix('Update'))]
                prnt('updateIdens',updateIdens)
                updates = Update.objects.filter(validated=False, id__in=updateIdens)
                to_queue = []
                if testing():
                    for u in updates:
                        u.validated = True
                        super(Update, u).save()
                        u.sync_with_post()
                        to_queue.append(u)
                
                else:
                    for u in updates:
                        validated = u.validate(validators=[validator])
                        if validated:
                            to_queue.append(u)
                if network_chain and to_queue:
                    network_chain.add_item_to_queue(to_queue)
                from accounts.models import Notification
                notiIdens = [u for u in processed_data['obj_ids'] if u.startswith(get_model_prefix('Notification'))]
                prnt('notiIdens',notiIdens)
                notifications = Notification.objects.filter(validated=False, id__in=notiIdens)
                to_queue = []
                for n in notifications:
                    validated = n.validate(validators=[validator])
                    if validated:
                        to_queue.append(n)
                if network_chain and to_queue:
                    network_chain.add_item_to_queue(to_queue)
                chains = {}
                from network.models import script_created_modifiable_models
                for m in script_created_modifiable_models:
                    prefix = get_model_prefix(m)
                    if prefix:
                        mIdens = [u for u in processed_data['obj_ids'] if u.startswith(prefix)]
                        prnt('mIdens',mIdens)
                        objs = get_dynamic_model(m, list=True, id__in=mIdens)
                        for o in objs:
                            chain, o, secondChain = find_or_create_chain_from_object(o)
                            if chain:
                                if chain not in chains:
                                    chains[chain] = []
                                chains[chain].append(o)
                if chains:
                    for chain in chains:
                        chain.add_item_to_queue(chains[chain])

                prnt('log7:',log)
                if log and isinstance(log, models.Model) and log._meta.object_name == 'DataPacket':
                    try:
                        log.completed(completed='all')
                    except Exception as e:
                        prnt('del log fail',str(e))
                prnt('completed super share','items length:',len(items),'func:',func, 'updates:',updates.count(), 'posts:',posts.count())
                return items, True
            elif dataPacket:
                dataPacket.add_item_to_share(processed_data['hashes'])
            prnt('step3')
            for i in objs:
                i.refresh_from_db()
                prnt('c2d:',convert_to_dict(i))
    if log and isinstance(log, models.Model) and log._meta.object_name == 'DataPacket':
        try:
            log.completed(completed='all')
        except Exception as e:
            prnt(str(e))
    prnt('skipped super share', func)
    prnt('items length:',len(items))
    return items, False


def share_with_network(items, post=None, datapacket=None, share_node=False):
    prnt('-share with network',items)
    if not isinstance(items, list):
        items = [items]
    for item in items:
        if item._meta.object_name != 'DataPacket': 
            network_chain = 'All'
            if has_field(item, 'networkChain'):
                network_chain, item, commit_chain = find_or_create_chain_from_object(item)
                if network_chain:
                    network_chain.add_item_to_queue(item)
                
                
            if item._meta.object_name != 'Node' or share_node:
                prnt('get datatotsharfe')
                if not datapacket:
                    datapacket = get_latest_dataPacket(network_chain)
                if datapacket:
                    datapacket.add_item_to_share(item)
                    prnt('shared',item)
    prnt('done share w netwrok')

# not used
def get_operator_pubKey(operatorData=None):
    if not operatorData:
        # from blockchain.models import get_operatorData
        operatorData = get_operatorData()
    return operatorData['pubKey']

def get_superuser_keys(dt=None, data=None):
    from accounts.models import User, UserPubKey
    prntDebug('-get_superuser_keys',dt)
    from network.models import Block, Node
    super_node_upks = []
    if dt:
        upks = UserPubKey.objects.filter(Block_obj__validated=True, keyType='guardian').filter(Q(end_life_dt__gte=dt)|Q(end_life_dt=None)).only('id')
        if not upks:
            first_sonet_block = Block.objects.filter(Blockchain_obj__genesisType='Sonet', validated=True).values('id','added_to_node').first()
            prnt('first_sonet_block1',first_sonet_block)
            if not first_sonet_block or first_sonet_block['added_to_node'] > now_utc() - datetime.timedelta(hours=24):
                upks = UserPubKey.objects.filter(keyType='guardian').filter(Q(end_life_dt__gte=dt)|Q(end_life_dt=None))
                prnt('upks:',[upk.id for upk in upks])
    else:
        upks = UserPubKey.objects.filter(end_life_dt=None, Block_obj__validated=True, keyType='guardian').only('id')
        if not upks:
            first_sonet_block = Block.objects.filter(Blockchain_obj__genesisType='Sonet', validated=True).values('id','added_to_node').first()
            prnt('first_sonet_block2',first_sonet_block)
            if not first_sonet_block or first_sonet_block['added_to_node'] > now_utc() - datetime.timedelta(hours=24):
                upks = UserPubKey.objects.filter(end_life_dt=None, keyType='guardian').only('id')

    result = [upk.id for upk in upks] + [upk.id for upk in super_node_upks]
    return result


def check_missing_data(obj, retrieve_missing=True, log_missing=True, downstream_worker=False):
    prnt('-check_missing_data', str(obj)[:100])
    from network.models import Block
    from utils.locked import check_block_contents
    result = {}
    if not obj:
        return result
    if is_id(obj):
        # if id is block:
        # get block by id
        # else
        block = Block.objects.filter(data__has_key=obj, validated=True).first()
        if block and 'unsupported_chain' not in block.notes:
            found_idens, problem_idens = check_block_contents(block, retrieve_missing=retrieve_missing, log_missing=log_missing, downstream_worker=downstream_worker, input_data=[obj])
            result['block_id'] = block.id
            result['found_idens'] = found_idens
        else:
            return None
    elif isinstance(obj, models.Model):
        if obj._meta.object_name == 'Block':
            if 'unsupported_chain' not in block.notes:
                found_idens, problem_idens = check_block_contents(block, retrieve_missing=False, log_missing=log_missing, downstream_worker=downstream_worker, input_data=[])
                result['block_id'] = block.id
                result['found_idens'] = found_idens
        else:
            block = Block.objects.filter(data__has_key=obj.id, validated=True).first()
            if block and 'unsupported_chain' not in block.notes:
                found_idens, problem_idens = check_block_contents(block, retrieve_missing=retrieve_missing, log_missing=log_missing, downstream_worker=downstream_worker, input_data=[obj.id])
                result['block_id'] = block.id
                result['found_idens'] = found_idens
            else:
                return None
    elif isinstance(obj, list):
        blocks = Block.objects.filter(data__has_any_key=obj, validated=True)
        result['block_ids'] = []
        result['found_idens'] = []
        for block in blocks:
            if 'unsupported_chain' not in block.notes:
                found_idens, problem_idens = check_block_contents(block, retrieve_missing=retrieve_missing, log_missing=log_missing, downstream_worker=downstream_worker, input_data=obj)
                result['block_ids'].append(block.id)
                result['found_idens'] += found_idens

    return result


def initial_save(item, share=False, length=None):
    prnt('---initial save', item)
    from utils.locked import hash_obj_id
    now = now_utc()
    if has_field(item, 'latestVer'):
        item.modlVer = item.latestVer
    if has_field(item, 'created') and not item.created:
        item.created = round_time(dt=now, dir='down', amount='hour')
    if has_field(item, 'DateTime'):
        if item.DateTime:
            if not isinstance(item.DateTime, datetime.datetime):
                item.DateTime = string_to_dt(item.DateTime)
            if not is_timezone_aware(item.DateTime):
                item.DateTime = item.DateTime.replace(tzinfo=ZoneInfo("America/New_York")) # should get tz by region_obj
            item.DateTime = item.DateTime.astimezone(ZoneInfo("UTC"))

    if has_field(item, 'lastUpdate') and not item.lastUpdate:
        item.lastUpdate = now
    if has_field(item, 'Region_obj') and not item.Region_obj and has_field(item, 'Country_obj'):
        item.Region_obj = item.Country_obj
    set_id = 'pre'
    if item.id is None:
        item.id = hash_obj_id(item, length=length)
        prnt('newId:', item.id, item._meta.object_name)
        set_id = item.id
    if has_field(item, 'networkChain') and (not item.networkChain or not is_id(item.networkChain)):
        pointer = None
        if has_field(item, 'pointerId'):
            pointer = get_dynamic_model(item.pointerId, id=item.pointerId)
        if pointer:
            network_chain, pointer, commit_chain = find_or_create_chain_from_object(pointer)
            if network_chain:
                item.networkChain = network_chain.genesisId
        else:
            network_chain, item, commit_chain = find_or_create_chain_from_object(item)
            if network_chain:
                item.networkChain = network_chain.genesisId
            if commit_chain and has_field(item, 'commitChain'):
                item.commitChain = commit_chain.genesisId

    prnt('item._meta.object_name',get_model(item._meta.object_name),'item',item)

    saved = compensate_save(item, get_model(item._meta.object_name), return_err=False, retrieve_missing=False, context=None)

    if saved:
        if has_method(item, 'boot'):
            try:
                prnt('try create post', item)
                p = item.boot()
            except Exception as e:
                prnt('create post fail', str(e))
                p = False
        if share:
            share_with_network(item)
        prnt('done initial save', item)
    else:
        prnt('FAILED initial save', item)

    return item


def save_mutable_fields(obj, *args, **kwargs):
    prntDebug('--save_mutable_fields',obj)
    if not has_field(obj, 'Validator_obj') or obj.Validator_obj != None:

        if has_field(obj, 'Block_obj') and obj.Block_obj:
            from utils.locked import check_commit_data, get_commit_data
            if not check_commit_data(obj, obj.Block_obj.data[obj.id]):
                prnt('commit_data has CHANGED')
                # logError('commit_data has CHANGED', code='7532', func='save_mutable_fields', extra={'commit_data':get_commit_data(obj)})
                return False
        if has_method(obj, 'get_hash_to_id') and obj._meta.object_name != 'Update':
            from utils.locked import hash_obj_id
            if obj.id != hash_obj_id(obj):
                prnt('IMMUTABLE field has CHANGED')
                # logError('IMMUTABLE field has CHANGED', code='6432', func='save_mutable_fields', extra={'get_hash_to_id':obj.get_hash_to_id()})
                return False
        if has_field(obj, 'signed') and obj.signed:
            from utils.locked import verify_obj_to_data
            if not verify_obj_to_data(obj, obj):
                prnt('-Not Valid Save')
                # logError('-Not Valid Save', code='3579', func='save_mutable_fields')
                return False
    prntDebug('-saving...',obj)
    model = get_model(obj._meta.object_name)
    return compensate_save(obj, model, *args, **kwargs)


def get_most_common_hashes(lists):
    if not lists:
        return []

    # Count occurrences weighted by length past the hash
    results = {}
    for lst in lists:
        for idx, h in enumerate(lst):
            weight = len(lst) - idx  # only count blocks after this one
            results[h] = results.get(h, 0) + weight

    if not results:
        return []
    prnt('results:',results)
    max_weight = max(results.values())
    prnt('max_weight',max_weight)
    top_hashes = [h for h, w in results.items() if w == max_weight]
    return top_hashes

def find_most_occuring_paths(most_common_hash, lists):
    results = {}
    for lst in lists:
        get_next = False
        for candidate_hash in lst:
            if get_next:
                results[candidate_hash] = results.get(candidate_hash, 0) + 1
                break
            elif candidate_hash == most_common_hash:
                get_next = True

    if not results:
        return []

    MIN_QUORUM = max(2, len(lists) // 3)
    max_count = max(results.values())
    if max_count < MIN_QUORUM:
        return []
    return {h:c for h, c in results.items() if c == max_count}


def resolve_chain_fork(chainId, request_count=50, node_count=50, starting_hash=None):
    prnt('--resolve_chain_fork', chainId, 'starting_hash', starting_hash)
    from utils.locked import get_relevant_nodes_from_block

    self_node = get_self_node()
    operatorData = get_operatorData()
    node_data = get_relevant_nodes_from_block(blockchain=chainId, exclude_list=[self_node.id], strings_only=False)

    k = min(node_count * 2, len(node_data['relevant_nodes']))
    node_list = dict(
        random.sample(list(node_data['relevant_nodes'].items()), k)
    )

    anchored_paths = []
    for node_id, node in node_list.items():
        success, response = connect_to_node(node,'network/request_chain_path',data={'blockchainId': chainId,'count': request_count,'start': starting_hash},self_node=self_node,operatorData=operatorData)
        if success:
            data = response.json()
            if data.get('message') == 'Success':
                path = json.loads(data['result'])
                if starting_hash: # enforce anchoring
                    if starting_hash not in path:
                        continue

                anchored_paths.append(path)
                if len(anchored_paths) >= node_count:
                    break

    if not anchored_paths:
        prnt('no anchored_paths')
        return {}, []

    if starting_hash:
        most_common_hashes = [starting_hash]
        winning_path_hashes = find_most_occuring_paths(starting_hash, anchored_paths)
        hash_map = {starting_hash:winning_path_hashes}
    else:
        most_common_hashes = get_most_common_hashes(anchored_paths)
        hash_map = {}
        for common_hash in most_common_hashes:
            winning_path_hashes = find_most_occuring_paths(common_hash, anchored_paths)
            hash_map[common_hash] = winning_path_hashes
    prnt('returning hash_map:',hash_map)
    return hash_map, anchored_paths

def discover_chain_divergence(chainId, local_hash_list=None, request_count=100, node_count=50, node_list=None, peer_hash_lists=None):
    prnt('--discover_chain_divergence', chainId)
    from network.models import Block
    from utils.locked import get_relevant_nodes_from_block

    if not local_hash_list:
        blocks = Block.objects.filter(networkChain=chainId, validated=True).values('hash').order_by('-index')[:request_count]
        local_hash_list = [b['hash'] for b in reversed(blocks)]

    if not peer_hash_lists:
        self_node = get_self_node()
        operatorData = get_operatorData()
        if not node_list:
            node_data = get_relevant_nodes_from_block(blockchain=chainId, exclude_list=[self_node.id], strings_only=False)

            k = min(node_count * 2, len(node_data['relevant_nodes']))
            node_list = dict(
                random.sample(list(node_data['relevant_nodes'].items()), k)
            )
        
        peer_hash_lists = []
        for node in node_list:
            try:
                resp = connect_to_node(node, 'network/request_chain_path', data={'blockchainId': chainId, 'count': request_count, 'hash_history':local_hash_list}, self_node=self_node, operatorData=operatorData)
                success, response = resp
                if success:
                    received = response.json()
                    if received.get('message') == 'Success':
                        peer_list = json.loads(received['result'])
                        prnt('peer_list',peer_list)
                        peer_hash_lists.append(peer_list)
                        if len(peer_hash_lists) >= node_count:
                            break
            except Exception as e:
                prnt('Peer request failed:', node.id, str(e))
                continue

    if not peer_hash_lists:
        prnt('No peer responses received')
        return {}

    blocks = Block.objects.filter(networkChain=chainId, validated=True, hash__in=[h for h in [lst for lst in peer_hash_lists]]).values('hash').order_by('-index')[:request_count]
    local_hash_list = [b['hash'] for b in reversed(blocks)]
    all_hash_lists = peer_hash_lists + [local_hash_list]

    most_common_hashes = get_most_common_hashes(all_hash_lists)
    prnt('most_common_hashes',most_common_hashes)

    hash_map = {}
    for common_hash in most_common_hashes:
        winning_path_hashes = find_most_occuring_paths(common_hash, all_hash_lists)
        hash_map[common_hash] = winning_path_hashes
    prnt('returned hash_map:',hash_map)
    return hash_map





def register_new_user(userData, upkData_accnt, upkData_sign, walletData=None, nodeData=None, upkData_node=None, reward_walletData=None, extraData=None, return_err_code=None):
    prnt('-register_new_user')
    proceed_to_login = False
    err_code = return_err_code
    user = None
    upk = None
    sign_upk = None
    wallet = None
    node = None
    node_upk = None
    try:
        # if walletData['Name'] == 'Main':
        #     prnt('wallet is main')
        if True:
            err_code = 'A1'
            import ast
            from accounts.models import UserPubKey, User
            from transactions.models import Wallet
            from utils.locked import get_signing_data, base64url_to_bytes
            from network.models import Signature
            sig_data = get_sigData(userData)
            userPublicKey = sig_data['publicKey']
            userSignature = sig_data['sig']
            upk_accnt_Signature = get_sigData(upkData_accnt, first_key=True)['sig']
            upk_sign_Signature = get_sigData(upkData_sign, first_key=True)['sig']
            if walletData:
                walletSignature = get_sigData(walletData, first_key=True)['sig']
            
            prnt('userPublicKey',userPublicKey)
            validator_upk = UserPubKey()
            # user and upk must exist before attempts to sync
            err_code = 'B'
            prnt('begin verify of data')
            if not is_id(userData['username']) and validator_upk.verify(get_signing_data(userData), userSignature, userPublicKey):
                # prnt('L1')
                if validator_upk.verify(get_signing_data(upkData_accnt, print_data=True), upk_accnt_Signature, userPublicKey):
                    # prnt('L2')
                    if not upkData_sign or validator_upk.verify(get_signing_data(upkData_sign), upk_sign_Signature, userPublicKey):
                        # prnt('L3')
                        # prnt('walletData',walletData)
                        # prnt('walletSignature',walletSignature)
                        if not walletData or validator_upk.verify(get_signing_data(walletData), walletSignature, userPublicKey):
                            # prnt('L4')

                            user = User()
                            sig_objs = []
                            prnt('create user')
                            for key, value in userData.items():
                                if value != 'None':
                                    # prnt(key, value)
                                    if not value or value == 'Val:N':
                                        value = None
                                    elif str(value).lower() == 'false':
                                        value = False
                                    elif str(value).lower() == 'true':
                                        value = True
                                    if key == 'publicKey':
                                        setattr(user, key, base64url_to_bytes(value))
                                    elif key == 'signed':
                                        signed = {}
                                        for dt, sig_data in value.items():
                                            signed[dt] = {'pk':sig_data['pk']}
                                            if 'req' in sig_data:
                                                signed[dt]['req'] = sig_data['req']
                                            if 'sig' in sig_data:
                                                sig_obj = Signature.objects.filter(pointerId=user.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).exists()    
                                                prnt('sig_objA:',sig_obj,sig_data['pk'])
                                                if not sig_obj:
                                                    sig_obj = Signature(pointerId=user.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                    sig_objs.append(sig_obj)
                                        setattr(user, key, signed)
                                    else:
                                        setattr(user, key, value)
                            prnt('save user first time')
                            err_code = 'C'
                            user.save(is_new=True)
                            u = get_dynamic_model(User, id=user.id)
                            prnt('u',u)
                            u = get_dynamic_model(user.id, id=user.id)
                            prnt('u2',u)

                            prnt('create 111')
                            err_code = 'D'
                            upk = UserPubKey()
                            prnt('create accnt upk')
                            for key, value in upkData_accnt.items():
                                if value != 'None':
                                    # prnt(key,value)
                                    if value == 'Val:N':
                                        value = None
                                    elif str(value).lower() == 'false':
                                        value = False
                                    elif str(value).lower() == 'true':
                                        value = True
                                    if str(key) == 'User_obj':
                                        setattr(upk, 'User_obj_id', value)
                                    elif key == 'publicKey':
                                        setattr(upk, key, value)
                                    elif key == 'signed':
                                        signed = {}
                                        for dt, sig_data in value.items():
                                            prnt('sig_data',sig_data)
                                            signed[dt] = {'pk':sig_data['pk']}
                                            if 'req' in sig_data:
                                                signed[dt]['req'] = sig_data['req']
                                            if 'sig' in sig_data:
                                                sig_obj = Signature.objects.filter(pointerId=upk.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).exists()
                                                prnt('sig_objA:',sig_obj,sig_data['pk'])
                                                if not sig_obj:
                                                    sig_obj = Signature(pointerId=upk.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                    sig_objs.append(sig_obj)
                                                    # from utils.locked import convert_to_dict
                                                    # prnt('sig_obj',convert_to_dict(sig_obj))
                                        setattr(upk, key, signed)
                                    else:
                                        setattr(upk, key, value)
                            prnt('save upk')
                            upk.save(is_new=True)
                            upk.refresh_from_db()
                            # sig_obj.save()
                            prnt('create 222')
                            err_code = 'E'
                            if upkData_sign:
                                sign_upk = UserPubKey()
                                prnt('create upk signign')
                                for key, value in upkData_sign.items():
                                    if value != 'None':
                                        # prnt(key,value)
                                        if value == 'Val:N':
                                            value = None
                                        elif str(value).lower() == 'false':
                                            value = False
                                        elif str(value).lower() == 'true':
                                            value = True
                                        if str(key) == 'User_obj':
                                            setattr(sign_upk, 'User_obj_id', value)
                                        elif key == 'publicKey':
                                            setattr(sign_upk, key, value)
                                        elif key == 'signed':
                                            signed = {}
                                            for dt, sig_data in value.items():
                                                signed[dt] = {'pk':sig_data['pk']}
                                                if 'req' in sig_data:
                                                    signed[dt]['req'] = sig_data['req']
                                                if 'sig' in sig_data:
                                                    sig_obj = Signature.objects.filter(pointerId=sign_upk.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).exists()
                                                    prnt('sig_objA:',sig_obj,sig_data['pk'])
                                                    if not sig_obj:
                                                        sig_obj = Signature(pointerId=sign_upk.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                        sig_objs.append(sig_obj)
                                            setattr(sign_upk, key, signed)
                                        else:
                                            setattr(sign_upk, key, value)
                                prnt('save upk')
                                sign_upk.save(is_new=True)
                                u = get_dynamic_model(user.id, id=user.id)
                                prnt('u3',u)
                                prnt('save sig1111')
                                from utils.locked import convert_to_dict
                                for sig_obj in sig_objs:
                                    prnt('cd',convert_to_dict(sig_obj))
                                    sig_obj.save()
                            
                            prnt('create 333')
                            err_code = 'F'
                            if walletData:
                                wallet = Wallet()
                                prnt('create wallet')
                                for key, value in walletData.items():
                                    if value != 'None':
                                        # prnt(key,value)
                                        if value == 'Val:N':
                                            value = None
                                        elif str(value).lower() == 'false':
                                            value = False
                                        elif str(value).lower() == 'true':
                                            value = True
                                        if str(key) == 'User_obj':
                                            setattr(wallet, 'User_obj_id', value)
                                        elif key == 'signed':
                                            signed = {}
                                            for dt, sig_data in value.items():
                                                signed[dt] = {'pk':sig_data['pk']}
                                                if 'req' in sig_data:
                                                    signed[dt]['req'] = sig_data['req']
                                                if 'sig' in sig_data:
                                                    sig_obj = Signature.objects.filter(pointerId=wallet.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).first()
                                                    if not sig_obj:
                                                        sig_obj = Signature(pointerId=wallet.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                            setattr(wallet, key, signed)
                                        else:
                                            setattr(wallet, key, value)
                                prnt('save wallet')
                                wallet.save(sig=walletSignature)
                                # wallet.boot()
                                sig_obj.save()
                                prnt('create 444')
                                err_code = 'G'

            prntn('create user stage 12')
            err_code = 11
            if upk and upk.verify(get_signing_data(upkData_accnt), upk_accnt_Signature):
                err_code = 12
                prntn('create user stage 12a')
                if not upkData_sign or upk and upk.verify(get_signing_data(upkData_sign), upk_sign_Signature):
                    err_code = 13
                    prntn('create user stage 12b')
                    if upk.verify(get_signing_data(userData), userSignature):
                        err_code = 14
                        prntn('create user stage 12c')
                        if not walletData or upk.verify(get_signing_data(walletData), walletSignature):
                            err_code = 3
                            prntn('create user stage 12d')
                            try:
                                user = get_or_create_model(userData['objType'], id=userData['id'])
                                err_code = 4
                                user, good = sync_and_share_object(user, userData)
                                prnt('done user22',user)
                                err_code = 5
                                user.save()
                                prnt('user-good',good)
                                if good:
                                    # prnt('new user data', get_signing_data(user))
                                    prnt()
                                    err_code = 6
                                    upk = get_or_create_model(upkData_accnt['objType'], id=upkData_accnt['id'])
                                    err_code = 7
                                    upk, good = sync_and_share_object(upk, upkData_accnt)
                                    prnt('upk-good',good)
                                    err_code = 8
                                    if good:
                                        err_code = 81
                                        if walletData:
                                            wallet = get_or_create_model(walletData['objType'], id=walletData['id'])
                                            err_code = 82
                                            wallet, good = sync_and_share_object(wallet, walletData)
                                            prnt('wallet-good',good)
                                            err_code = 83
                                        if good:
                                            err_code = 84
                                            proceed_to_login = True
                            except Exception as e:
                                prnt('create user fail 233',str(e),'\n')
                                err_code = str(err_code) + '/' + str(e)

                            prntn('create user stage 3', user, wallet)
                            if proceed_to_login and user:
                                err_code = 9
                                new_user_valid = False
                                # new_wallet_valid = False
                                prnt('newU', user)
                                new_user_valid = upk.verify(get_signing_data(user), userSignature)
                                prnt('new_user_valid',new_user_valid)
                                err_code = 10
                                if new_user_valid:
                                    from network.models import Block, Node
                                    if not Block.objects.filter(validated=True).exists():
                                        err_code = 101
                                        
                                        proceed = True
                                        super_PublicKey = None
                                        if extraData:
                                            proceed = True
                                            for dataType, data in extraData.items():
                                                if proceed:
                                                    proceed = False
                                                    sig_data = get_sigData(data, first_key=True)
                                                    pk = sig_data['publicKey']
                                                    s = sig_data['sig']
                                                    if validator_upk.verify(get_signing_data(data), s, pk):
                                                        prnt('step2 super',dataType)
                                                        err_code = 131
                                                        new_upk = UserPubKey()
                                                        sig_obj = None
                                                        for key, value in data.items():
                                                            if value != 'None':
                                                                # prnt(key,value)
                                                                if value == 'Val:N':
                                                                    value = None
                                                                elif str(value).lower() == 'false':
                                                                    value = False
                                                                elif str(value).lower() == 'true':
                                                                    value = True
                                                                if str(key) == 'User_obj':
                                                                    setattr(new_upk, 'User_obj_id', value)
                                                                elif str(key) == 'nodeId':
                                                                    setattr(new_upk, 'nodeId', nodeData['id'])
                                                                elif key == 'publicKey':
                                                                    setattr(new_upk, key, value)
                                                                elif key == 'signed':
                                                                    signed = {}
                                                                    for dt, sig_data in value.items():
                                                                        signed[dt] = {'pk':sig_data['pk']}
                                                                        if 'req' in sig_data:
                                                                            signed[dt]['req'] = sig_data['req']
                                                                        if 'sig' in sig_data:
                                                                            sig_obj = Signature.objects.filter(pointerId=new_upk.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).first()
                                                                            if not sig_obj:
                                                                                sig_obj = Signature(pointerId=new_upk.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                                    setattr(new_upk, key, signed)
                                                                else:
                                                                    setattr(new_upk, key, value)
                                                        prnt('save node_upk')
                                                        # prnt(model_to_dict(upk))
                                                        new_upk.save(is_new=True)
                                                        sig_obj.save()
                                                        prnt('create 333a')
                                                        err_code = 132
                                                        new_upk, good = sync_and_share_object(new_upk, data)
                                                        prnt('super_upk-good',good)
                                                        err_code = 133
                                                        if good:
                                                            if dataType == 'upkData_super':
                                                                super_PublicKey = pk
                                                            err_code = 134
                                                            proceed = True
                                        try:
                                            prnt('nodeData',nodeData)
                                            if Node.objects.exists():
                                                prnt('Node.objects.exists()',Node.objects.exists())
                                                nodeData = None
                                        except Exception as e:
                                            prnt('falitrynode1', str(e))
                                            nodeData = None
                                        if proceed and nodeData and upkData_node:
                                            prnt('step2', upkData_node)
                                            err_code = 110
                                            proceed_to_login = False
                                            
                                            sig_data = get_sigData(upkData_node, first_key=True)
                                            nodeUpk_PublicKey = sig_data['publicKey']
                                            nodeUpk_Signature = sig_data['sig']
                                            sig_data = get_sigData(nodeData, first_key=True)
                                            node_PublicKey = sig_data['publicKey']
                                            node_Signature = sig_data['sig']
                                            sig_data = get_sigData(reward_walletData, first_key=True)
                                            reward_wallet_PublicKey = sig_data['publicKey']
                                            reward_wallet_Signature = sig_data['sig']
                                            if proceed and validator_upk.verify(get_signing_data(upkData_node), nodeUpk_Signature, nodeUpk_PublicKey):
                                                prnt('step2a')
                                                user.assess_super_status()
                                                prnt('user.is_superuser',user.is_superuser)
                                                err_code = 111
                                                proceed = False
                                                node_upk = UserPubKey()
                                                sig_obj = None
                                                for key, value in upkData_node.items():
                                                    if value != 'None':
                                                        # prnt(key,value)
                                                        if value == 'Val:N':
                                                            value = None
                                                        elif str(value).lower() == 'false':
                                                            value = False
                                                        elif str(value).lower() == 'true':
                                                            value = True
                                                        if str(key) == 'User_obj':
                                                            setattr(node_upk, 'User_obj_id', value)
                                                        elif str(key) == 'nodeId':
                                                            setattr(node_upk, 'nodeId', nodeData['id'])
                                                        elif key == 'publicKey':
                                                            setattr(node_upk, key, value)
                                                        elif key == 'signed':
                                                            signed = {}
                                                            for dt, sig_data in value.items():
                                                                signed[dt] = {'pk':sig_data['pk']}
                                                                if 'req' in sig_data:
                                                                    signed[dt]['req'] = sig_data['req']
                                                                if 'sig' in sig_data:
                                                                    sig_obj = Signature.objects.filter(pointerId=node_upk.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).first()
                                                                    if not sig_obj:
                                                                        sig_obj = Signature(pointerId=node_upk.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                            setattr(node_upk, key, signed)
                                                        else:
                                                            setattr(node_upk, key, value)
                                                prnt('save node_upk')
                                                node_upk.save(is_new=True)
                                                sig_obj.save()
                                                prnt('create 333b')
                                                err_code = 112
                                                node_upk, good = sync_and_share_object(node_upk, upkData_node)
                                                prnt('node_upk-good',good)
                                                err_code = 113
                                                if good:
                                                    err_code = 114
                                                    proceed = True
                                            prnt('step3',proceed, nodeData)
                                            prnt('super_PublicKey',super_PublicKey)
                                            if proceed and (validator_upk.verify(get_signing_data(nodeData), node_Signature, node_upk.publicKey) or validator_upk.verify(get_signing_data(nodeData), node_Signature, super_PublicKey)):
                                                prnt('step3a')
                                                proceed = False
                                                err_code = 115
                                                node = Node()
                                                sig_obj = None
                                                for key, value in nodeData.items():
                                                    if value != 'None':
                                                        # prnt(key,value)
                                                        if value == 'Val:N':
                                                            value = None
                                                        elif str(value).lower() == 'false':
                                                            value = False
                                                        elif str(value).lower() == 'true':
                                                            value = True
                                                        if str(key) == 'User_obj':
                                                            setattr(node, 'User_obj_id', value)
                                                        elif key == 'signed':
                                                            signed = {}
                                                            for dt, sig_data in value.items():
                                                                signed[dt] = {'pk':sig_data['pk']}
                                                                if 'req' in sig_data:
                                                                    signed[dt]['req'] = sig_data['req']
                                                                if 'sig' in sig_data:
                                                                    sig_obj = Signature.objects.filter(pointerId=node.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).first()
                                                                    if not sig_obj:
                                                                        sig_obj = Signature(pointerId=node.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                            setattr(node, key, signed)
                                                        else:
                                                            setattr(node, key, value)
                                                prnt('save node')
                                                node.pos = 1
                                                node.save(bypass_upk_block=True)
                                                node.boot()
                                                sig_obj.save()
                                                prnt('create 444')
                                                err_code = 116
                                                if user.nodeCreatorId == node.id:
                                                # user.save()
                                                    err_code = 117
                                                    node, good = sync_and_share_object(node, nodeData)
                                                    prnt('node-good',good)
                                                    err_code = 118
                                                    if good:
                                                        err_code = 119
                                                        proceed = True
                                            if proceed and validator_upk.verify(get_signing_data(reward_walletData), reward_wallet_Signature, userPublicKey):
                                                prnt('step4a')
                                                proceed = False
                                                err_code = 120
                                                reward_wallet = Wallet()
                                                sig_obj = None
                                                prnt('create reward wallet')
                                                for key, value in reward_walletData.items():
                                                    if value != 'None':
                                                        # prnt(key,value)
                                                        if value == 'Val:N':
                                                            value = None
                                                        elif str(value).lower() == 'false':
                                                            value = False
                                                        elif str(value).lower() == 'true':
                                                            value = True
                                                        if str(key) == 'User_obj':
                                                            setattr(reward_wallet, 'User_obj_id', value)
                                                        elif key == 'signed':
                                                            signed = {}
                                                            for dt, sig_data in value.items():
                                                                signed[dt] = {'pk':sig_data['pk']}
                                                                if 'req' in sig_data:
                                                                    signed[dt]['req'] = sig_data['req']
                                                                if 'sig' in sig_data:
                                                                    sig_obj = Signature.objects.filter(pointerId=reward_wallet.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).first()
                                                                    if not sig_obj:
                                                                        sig_obj = Signature(pointerId=reward_wallet.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                            setattr(reward_wallet, key, signed)
                                                        else:
                                                            setattr(reward_wallet, key, value)
                                                prnt('save reward wallet')
                                                err_code = 121
                                                # prnt(model_to_dict(upk))
                                                reward_wallet.save(sig=reward_wallet_Signature)
                                                # reward_wallet.boot()
                                                # from utils.models import get_dynamic_model, convert_to_dict
                                                # from utils.locked import convert_to_dict
                                                # prnt('c2d',convert_to_dict(reward_wallet))
                                                w = get_dynamic_model(reward_wallet.id, id=reward_wallet.id)
                                                prnt('w',w)
                                                sig_obj.save()
                                                err_code = 122
                                                reward_wallet, good = sync_and_share_object(reward_wallet, reward_walletData)
                                                prnt('reward_wallet-good',good)
                                                err_code = 123
                                                if good:
                                                    err_code = 124
                                                    proceed_to_login = True
                                            
                                    else:
                                        prnt('else1')
                                        if not node:
                                            node = get_self_node()
                                        
                                        if proceed_to_login and int(user.pattern) > 0 and int(user.pattern) <= 12 and user.nodeCreatorId == node.id:
                                            proceed_to_login = True
                                            user.save()
                                        else:
                                            err_code = 140
                                            proceed_to_login = False

                                if proceed_to_login and not new_user_valid:
                                    err_code = 141
                                    proceed_to_login = False
    except Exception as e:
        err_code = str(err_code) + f'err:{e}'
    prnt('err_code',err_code)
    if return_err_code:
        return proceed_to_login, {'user':user, 'upk':upk, 'upk_sign':sign_upk, 'wallet':wallet, 'node':node}, err_code
    return proceed_to_login, {'user':user, 'upk':upk, 'upk_sign':sign_upk, 'wallet':wallet, 'node':node}

def register_node_on_cloudflare(tunnel_name, DOMAIN=None):
    prnt('-register_new_node',tunnel_name)
    from os.path import expanduser
    
    cert_path = expanduser("~/.cloudflared/cert.pem")
    if os.path.exists(cert_path):
        self_node = get_self_node()
        if 'cloudflare' in self_node.abilities and self_node.abilities['cloudflare']:
            if self_node.User_obj.assess_super_status():
                import subprocess
                import shutil
                import yaml
                from pathlib import Path
                import zipfile

                zip_path = Path.home() / "Sonet" / ".data" / "cloudflare_bundles" / tunnel_name / "bundle.zip"
                if zip_path.exists():
                    prnt(f"✅ Bundle already exists: {zip_path}")
                    return zip_path
            
                if not DOMAIN:
                    from network.models import Sonet
                    sonet = Sonet.objects.first()
                    DOMAIN = sonet.Domain

                project_dir = Path.home() / "Sonet"
                bundle_dir = project_dir / ".data" / "cloudflare_bundles" / tunnel_name
                # hostname = f"{tunnel_name}.node.{DOMAIN}"
                hostname = f"{tunnel_name}.{DOMAIN}"
                bundle_dir.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(["cloudflared", "tunnel", "create", tunnel_name], check=True)
                except Exception as e:
                    prnt('create tunnel err 3245', str(e))
                try:
                    subprocess.run(["cloudflared", "tunnel", "route", "dns", tunnel_name, hostname], check=True)
                except Exception as e:
                    prnt('create dns err 359', str(e))

                # hostname_orange = f"{tunnel_name}.{DOMAIN}"
                # hostname_grey = f"{tunnel_name}_grey.{DOMAIN}"

                # try:
                #     subprocess.run(["cloudflared", "tunnel", "route", "dns", tunnel_name, hostname_orange], check=True)
                # except Exception as e:
                #     prnt('create orange-cloud dns err', str(e))

                # 2️⃣ Create grey-cloud DNS by adding second DNS record
                # We can reuse cloudflared cert auth to write DNS-only record:
                # Note: cloudflared itself doesn't have a direct flag for grey-cloud, so this usually requires
                # editing the DNS record after creation. A simple way is to create a CNAME to the tunnel and
                # mark DNS-only (grey-cloud) in the Cloudflare dashboard or automate with cert.pem access.
                # For illustration, we just create the hostname here; you'll need to toggle proxy status:
                # try:
                #     subprocess.run(["cloudflared", "tunnel", "route", "dns", tunnel_name, hostname_grey], check=True)
                #     prnt(f"⚠️ Created grey-cloud hostname {hostname_grey}, make sure proxy is set to DNS-only")
                # except Exception as e:
                #     prnt('create grey-cloud dns err', str(e))

                    
                def get_tunnel_json_path(tunnel_name):
                    result = subprocess.run(
                        ["cloudflared", "tunnel", "list", "--output", "json"],
                        check=True, capture_output=True, text=True
                    )
                    tunnels = json.loads(result.stdout)
                    for tunnel in tunnels:
                        if tunnel["name"] == tunnel_name:
                            uuid = tunnel["id"]
                            return Path.home() / ".cloudflared" / f"{uuid}.json"
                    raise Exception(f"Tunnel '{tunnel_name}' not found")

                src_path = get_tunnel_json_path(tunnel_name)
                prnt("✅ Found credentials at:", src_path)

                try:
                    dst_json = bundle_dir / f"{tunnel_name}.json"
                    shutil.copy(src_path, dst_json)
                except Exception as e:
                    prnt('move json config err 493',str(e))

                config = {
                    "tunnel": tunnel_name,
                    "credentials-file": f"~/Sonet/.data/cloudflare_registration/{tunnel_name}.json",
                    "origincert": f"~/Sonet/.data/cloudflare_registration/{tunnel_name}.json", # needed for mac?, not linux
                    "ingress": [
                        {
                            "hostname": hostname,
                            "service": f"http://localhost:9909",
                        },
                        {
                            "hostname": DOMAIN,
                            "service": f"http://localhost:9909"
                        },
                        {"service": "http_status:404"}
                    ]
                }
                config_path = bundle_dir / "config.yml"
                with open(config_path, "w") as f:
                    yaml.dump(config, f)
                
                folder = Path.home() / "Sonet" / ".data" / "cloudflare_bundles" / tunnel_name
                yaml_file = next(folder.glob("*.yml"), None)
                json_file = next(folder.glob(f"*.json"), None)

                if not yaml_file or not json_file:
                    raise FileNotFoundError("Missing config.yml or credentials.json in folder")

                with zipfile.ZipFile(zip_path, "w") as zipf:
                    zipf.write(yaml_file, arcname=yaml_file.name)
                    zipf.write(json_file, arcname=json_file.name)

                prnt(f"✅ Bundle created: {zip_path}")
                return zip_path
    prnt(f"Bundle skipped")
    
    from network.models import Node
    return {n.id:n.return_address() for n in Node.objects.filter(abilities__has_key='cloudflare', suspended_dt=None, expelled_dt=None).exclude(Block_obj=None).exclude(activated_dt=None).only('id','address','onion') if n.abilities['cloudflare']}






def remove_tags(text):
    try:
        TAG_RE = re.compile(r'<[^>]+>')
        text = TAG_RE.sub('', text).replace('"', "'").replace('\n', '').strip()
        text = ''.join(text.splitlines())
        text = unidecode(text)
        return text
    except:
        return None
    
def get_token_count(string: str) -> int:
    import tiktoken
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(string))
    print('-get_token_count',num_tokens)
    return num_tokens

def makeText(data):
    prntn('-makeText',len(data))
    def remove_tags(text):
        try:
            TAG_RE = re.compile(r'<[^>]+>')
            text = TAG_RE.sub('', text).replace('"', "'").replace('\n', '').strip()
            text = ''.join(text.splitlines())
            text = unidecode(text)
            return text
        except:
            return None
    def textualize(statement, text):
        if statement.PersonName:
            person_name = statement.PersonName
        else:
            person_name = ''
            if statement.Person_obj:
                name = statement.Person_obj.get_name()
                if name and not any(char.isdigit() for char in name):
                    person_name = name
                
        text = text + '[post_id:ppxpp%sqqxqq]%s:\n%s\n\n' %(statement.id, person_name, statement.Content)
        return text
    text = ""
    
    from legis.models import Statement
    for i in data:
        if is_id(i):
            s = Statement.objects.filter(id=i).first()
            if s and len(s.Content) > 100:
                text = textualize(s, text)
        elif isinstance(i, models.Model) and i._meta.object_name == 'Post':
            if i.Statement_obj and len(i.Statement_obj.Content) > 100:
                text = textualize(i.Statement_obj, text)
        elif isinstance(i, models.Model) and i._meta.object_name == 'Statement':
            if len(i.Content) > 100:
                text = textualize(i, text)
    text = remove_tags(text)
    # prnt('text', len(text),text)
    num_tokens = get_token_count(text)
    prnt('-----num_tokens',num_tokens)
    return num_tokens, text

def run_prompt(prompt, tkns_plus=0, prompt_type='ollama'):
    prnt('-run_prompt')
    max_tkns = 7000 + tkns_plus
    url = 'http://10.0.0.217:1234/v1/'
    model = "qwen/qwen3-4b-2507"

    prnt(str(prompt)[:500])
    prnt('len:',len(prompt))
    # prnt(f"{str(prompt)[:10000]}...")
    tkns = get_token_count(prompt)
    # prnt('tkns',tkns)
    while tkns > max_tkns and len(prompt) > 1000:
        prompt = prompt[:-700]
        tkns = get_token_count(prompt)
    prnt('tkns2',tkns)


    if prompt_type == 'openai':
        import time, openai

        openai.api_key = "lm-studio"
        openai.base_url = url

        start = time.time()
        resp = openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.time() - start
        tokens = resp.usage.total_tokens

        result = resp.choices[0].message.content
        # print(resp)
        # print()
        prnt()
        prnt(f"Response time: {elapsed:.2f}s, Tokens/sec: {tokens/elapsed:.2f}, Total tokens: {tokens}")
        prnt(result)
        prnt()

        return result
    elif prompt_type == 'ollama':
        import requests, json, time
        start = time.time()
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "qwen2.5:3b",
            # "model": "qwen3:4b",
            "prompt": prompt,
            "stream": False,
            "options": {
            "temperature": 0.2,
            "seed": 42,
            "top_p": 1.0
            }
        }

        r = requests.post(url, json=payload)
        end = time.time()
        r_json = r.json()
        prnt('response:',r_json["response"])

        prnt(f"Time: {end - start:.2f}s")        
        prnt(f"Prompt tokens: {r_json.get('prompt_eval_count')}")
        prnt(f"Generated tokens: {r_json.get('eval_count')}")
        prnt(f"Tokens/sec: {r_json.get('eval_count') / (end - start):.2f}")

        return r_json["response"]
    elif prompt_type == 'ollama_stream':
        import requests, json, time

        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "qwen2.5:3b",
            "prompt": prompt,
            "stream": True,
            "options": {
            "temperature": 0.2,
            "seed": 42,
            "top_p": 1.0
            }
        }

        full_text = []
        start = time.time()

        with requests.post(url, json=payload, stream=True) as r:
            for line in r.iter_lines():
                if not line:
                    continue

                data = json.loads(line.decode("utf-8"))
                if "response" in data:
                    chunk = data["response"]
                    # stream_prnt(chunk, end="")
                    full_text.append(chunk)
                if data.get("done"):
                    stats = data

        end = time.time()
        final_text = "".join(full_text)

        prnt(f"Time: {end - start:.2f}s")
        prnt(f"Prompt tokens: {stats.get('prompt_eval_count')}")
        prnt(f"Generated tokens: {stats.get('eval_count')}")
        prnt(f"Tokens/sec: {stats.get('eval_count') / (end - start):.2f}")
        return final_text








def logEvent(details, code=None, region=None, func=None, extra=None, log_type='LogBook', dt='week'):
    # from utils.models import timezonify
    from network.models import EventLog
    now = now_utc()
    if dt and dt == 'week':
        start_time = round_time(dt=now, dir='down', amount='week')
    elif dt and isinstance(dt, datetime.datetime):
        start_time = dt
    else:
        start_time = now
    log = EventLog.objects.filter(type=log_type, created__gte=start_time).first()
    if not log:
        log = EventLog(type=log_type, created=start_time)
    event = {'~':str(details)}
    if func:
        event['func'] = func
    if code:
        event['code'] = code
    if region:
        if isinstance(region, models.Model):
            region = region.Name
        elif not isinstance(region, str):
            region = str(region)
        event['reg'] = region
    if extra:
        if not isinstance(extra, str):
            extra = str(extra)
        event['extra'] = extra
    log.data[dt_to_string(now)] = event
    # log.data[timezonify('est', now).isoformat()] = event
    log.save()

def logTask(task, code=None, region=None, extra=None):
    # prnt('logError', err, code, func, region, extra)
    from network.models import EventLog
    now = now_utc()
    start_of_week = round_time(dt=now, dir='down', amount='week')
    log = EventLog.objects.filter(type='Tasks', created__gte=start_of_week).first()
    if not log:
        log = EventLog(type='Tasks', created=start_of_week)
    event = {'task':str(task)}
    if code:
        event['code'] = code
    if region:
        if isinstance(region, models.Model):
            region = region.Name
        elif not isinstance(region, str):
            region = str(region)
        event['reg'] = region
    if extra:
        if not isinstance(extra, str):
            extra = str(extra)
        event['extra'] = extra
    log.data[dt_to_string(now)] = event
    # log.data[timezonify('est', now).isoformat()] = event
    log.save()

def logError(err, code=None, func=None, region=None, extra=None):
    # prnt('logError', err, code, func, region, extra)
    from network.models import EventLog
    now = now_utc()
    start_of_week = round_time(dt=now, dir='down', amount='week')
    log = EventLog.objects.filter(type='Errors', created__gte=start_of_week).first()
    if not log:
        log = EventLog(type='Errors', created=start_of_week)
    event = {'err':str(err)}
    if func:
        event['func'] = func
    if code:
        event['code'] = code
    if region:
        if isinstance(region, models.Model):
            region = region.Name
        elif not isinstance(region, str):
            region = str(region)
        event['reg'] = region
    if extra:
        if not isinstance(extra, str):
            extra = str(extra)
        event['extra'] = extra
    log.data[dt_to_string(now)] = event
    # log.data[timezonify('est', now).isoformat()] = event
    log.save()

def logRequest(items, return_log=False, dt='week'):
    from network.models import EventLog
    # logEvent(f'request_items:{items}')
    now = now_utc()
    start_of_week = round_time(dt=now, dir='down', amount=dt)
    log = EventLog.objects.filter(type='RequestedItems', created__gte=start_of_week).first()
    if not log:
        log = EventLog(type='RequestedItems', created=start_of_week)
    log.data[dt_to_string(now)] = items
    log.save()
    if return_log:
        return log

def logMissing(iden, reg=None, context={}):
    from network.models import EventLog
    self_node = get_self_node()
    now = now_utc()
    start_of_month = round_time(dt=now, dir='down', amount='month')
    if reg and is_id(reg):
        from posts.models import Region
        reg = Region.objects.filter(id=reg).first()
    elif reg and not isinstance(reg, models.Model) or reg and reg._meta.object_name != 'Region':
        reg = None

    log = EventLog.objects.filter(type='missing_items', Node_obj=self_node, Region_obj=reg, created__gte=start_of_month).first()
    if not log:
        log = EventLog(type='missing_items', Node_obj=self_node, Region_obj=reg, created=start_of_month)

    if isinstance(iden, list):
        for i in iden:
            if i not in log.data:
                log.data[i] = context
    elif isinstance(iden, str):
        if iden not in log.data:
            log.data[iden] = context

    log.save()

def logBroadcast(return_log=True):
    from network.models import EventLog
    now = now_utc()
    start_of_week = round_time(dt=now, dir='down', amount='week')
    log = EventLog.objects.filter(type='Broadcast History', created__gte=start_of_week).first()
    if not log:
        log = EventLog(type='Broadcast History', created=start_of_week)
    return log
    
def toBroadcast(obj, remove_item=False, extra={}):
    from network.models import EventLog
    if not is_id(obj):
        if isinstance(obj, models.Model):
            obj = obj.id
    now = now_utc()
    if remove_item:
        log = EventLog.objects.filter(type='toBroadcast', data__icontains=obj).first()
        if log:
            if obj in log.data:
                del log.data[obj]
            if not log.data:
                log.delete()
            else:
                log.save()
    else:
        start_of_week = round_time(dt=now, dir='down', amount='week')
        log = EventLog.objects.filter(type='toBroadcast', created__gte=start_of_week).first()
        if not log:
            log = EventLog(type='toBroadcast', created=start_of_week)
        if obj not in log.data:
            extra['dt'] = dt_to_string(now)
            log.data[obj] = extra
        log.save()


def request_items(requested_items=[], nodes=None, supported_chain_list=None, request_validators=False, return_updated_count=False, return_updated_objs=False, return_updated_ids=False, return_missing=False, check_consensus=True, downstream_worker=True, get_missing_blocks=True, override_completed=True, recent_request_time=60):
    prntDebug('--request_items', str(requested_items)[:500], now_utc(), len(requested_items), 'nodes',nodes)
    from network.models import Node, Blockchain, DataPacket, EventLog
    from utils.locked import hash_obj_id, sign_for_sending
    if e_brake(2):
        return 
    if not requested_items or all(value_is_none(i) for i in requested_items):
        return None
    now = now_utc()
    if recent_request_time:
        log = EventLog.objects.filter(type='RequestedItems', updated_on_node__gt=now - datetime.timedelta(minutes=recent_request_time)).first()
        if log and log.data:
            requested_items_copy = requested_items.copy()
            for key, value in log.data.items():
                if any(i for i in requested_items_copy if i in value) and string_to_dt(key) > now - datetime.timedelta(minutes=recent_request_time):
                    for i in requested_items_copy:
                        if i in value:
                            prnt(f"{i} recently requested", key)
                            requested_items_copy.remove(i)
                if not requested_items_copy:
                    break
            requested_items = requested_items_copy.copy()
            if not requested_items or all(value_is_none(i) for i in requested_items):
                return None

    operatorData = get_operatorData()
    if not nodes:
        prnt("H")
        if supported_chain_list:
            prnt('a')
            if not isinstance(supported_chain_list, list):
                supported_chain_list = [supported_chain_list]
            if any(get_pointer_type(i) == 'Blockchain' for i in supported_chain_list):
                chains = []
                for i in Blockchain.objects.filter(id__in=supported_chain_list):
                    chains.append(i.genesisId)
                    if i.genesisType not in chains:
                        chains.append(i.genesisType)
                prnt('chains',chains)
                supported_chain_list += chains
            prnt('supported_chain_list',supported_chain_list)
            nodes = Node.objects.filter(chain_array__overlap=supported_chain_list, activeNode=True)
        else:
            prnt('b')
            # maybe get supported chains from requested_items list
            nodes = Node.objects.filter(activeNode=True).exclude(chain_array=[])
            if not nodes:
                prnt('c')
                nodes = Node.objects.exclude(activated_dt=None).exclude(chain_array=[])
    elif isinstance(nodes, list) and isinstance(nodes[0], str):
        prnt("I")
        nodes = Node.objects.filter(id__in=nodes, activeNode=True, expelled_dt=None)
    elif isinstance(nodes, list):
        prnt("L")
    elif isinstance(nodes, str) and is_id(nodes):
        prnt("J")
        nodes = Node.objects.filter(id=nodes, activeNode=True, expelled_dt=None)
    elif isinstance(nodes, models.Model):
        prnt("K")
        nodes = [nodes]
    prnt('0')
    from django.db.models.query import QuerySet
    if isinstance(nodes, QuerySet):
        nodes = list(nodes)

    def fetch_data(data, nodes, output=None, target_node=None, starting_index=0):
        prnt('\nfetch_data',now_utc(),'nodes',nodes,'target_node:',target_node, 'data',str(data)[:500])

        if target_node: 
            nodes.remove(target_node)
            nodes.insert(0, target_node)
        nonlocal return_updated_count
        nonlocal return_updated_objs
        nonlocal return_updated_ids
        nonlocal self_node
        returned_update = False
        received_json = {'none':0}
        for node in nodes:
            prnt('fetch node',node)
            if node != self_node and node != self_node.id:
                try:
                    success, response = connect_to_node(node, 'network/request_data', data=data, operatorData=operatorData, timeout=(7,25), stream=True, log_reponse_time=False)
                    if success and response.status_code == 200:
                        received_json = response.json()
                        if received_json['message'].lower() == 'success':
                            prnt("received_json['type']",received_json['type'])
                            if 'returning_idens' in received_json:
                                returned_idens = received_json['returning_idens']
                            else:
                                returned_idens = None
                            if 'not_found' in received_json:
                                not_found_idens = received_json['not_found']
                            else:
                                not_found_idens = []
                            if received_json['type'] == 'Blockchain':
                                blockchain_dict = json.loads(received_json['blockchain_obj'])
                                update_response = process_received_data(received_json['content'], return_updated_count=return_updated_count, return_updated_objs=return_updated_objs, return_updated_ids=return_updated_ids, downstream_worker=downstream_worker, check_consensus=check_consensus, get_missing_blocks=get_missing_blocks, override_completed=override_completed, force_sync=True)
                            elif received_json['type'] == 'Block':
                                block_dict = json.loads(received_json['block_obj'])
                                content = [block_dict]
                                if 'transaction_obj' in received_json and received_json['transaction_obj']:
                                    content.append(json.loads(received_json['transaction_obj']))
                                index = block_dict['index']
                                update_response = process_received_data(received_json['content'], return_updated_count=return_updated_count, return_updated_objs=return_updated_objs, return_updated_ids=return_updated_ids, downstream_worker=downstream_worker, check_consensus=check_consensus, get_missing_blocks=get_missing_blocks, override_completed=override_completed, force_sync=True)
                            elif received_json['type'] == 'Blocks':
                                received_json['senderId'] = node.id
                                received_json = sign_for_sending(received_json, operatorData=operatorData)
                                iden = hash_obj_id('DataPacket', specific_data=str(received_json)+dt_to_string(now_utc()))
                                dp = DataPacket.objects.filter(id=iden).first()
                                if not dp:
                                    dp = DataPacket(id=iden, func='process_received_blocks', created = now_utc(), data=received_json)
                                    dp.save()
                                update_response = process_received_blocks(dp, get_missing_blocks=get_missing_blocks, resend_missing_blocks=False, return_result=True, force_check=True, rebroadcast=False)
                            
                            else:
                                try:
                                    index = int(received_json['index'])
                                except:
                                    index = 'NA'
                                update_response = process_received_data(received_json['content'], return_updated_count=return_updated_count, return_updated_objs=return_updated_objs, return_updated_ids=return_updated_ids, downstream_worker=downstream_worker, check_consensus=check_consensus, get_missing_blocks=get_missing_blocks, override_completed=override_completed, force_sync=True)
                                if index != 'NA' and index != starting_index:
                                    time.sleep(2)
                                    json_data = json.loads(data['request'])
                                    if returned_idens:
                                        obj_types = {}
                                        for obj_type in json_data['items']:
                                            again_idens = [i for i in json_data['items'][obj_type] if i not in returned_idens]
                                            if not_found_idens:
                                                not_found_idens = [i for i in not_found_idens if i not in returned_idens]
                                            if again_idens:
                                                obj_types[obj_type] = again_idens
                                        json_data['items'] = obj_types
                                        json_data['exclude'] = returned_idens
                                    else:
                                        json_data['index'] = index
                                    json_data['dt'] = dt_to_string(now_utc())
                                    signedRequest = json.dumps(sign_for_sending(json_data))
                                    data['request'] = signedRequest
                                    returned_update = fetch_data(data, nodes, output=output, target_node=node, starting_index=index)
                            prnt('ending festch and process')
                            if isinstance(update_response, int) and isinstance(returned_update, int):
                                r = update_response + returned_update
                            elif isinstance(update_response, list) and isinstance(returned_update, list):
                                r = update_response + returned_update
                            else:
                                r = update_response or returned_update
                            if return_missing:
                                return {'found': r, 'not_found':not_found_idens}
                            else:
                                return r
                        else:
                            prnt('fetch data success = False')
                            prnt('received_json 853',received_json)
                    else:
                        prnt('fetch data not successful')
                except Exception as e:
                    prnt('fetch data err 9745',str(e))
    
    self_node = get_self_node(operatorData=operatorData)
    if isinstance(requested_items, list):
        requested_items = data_sort_priority(requested_items)
    elif isinstance(requested_items, dict):
        requested_items = sorted(requested_items, key=data_sort_priority)
    else:
        requested_items = data_sort_priority([requested_items])
    prnt('3, ',requested_items)
    keys = get_operator_obj('keyPair', operatorData=operatorData)
    # logRequest(requested_items, return_log=False, dt='day')
    from network.views import max_obj_send_count
    if len(requested_items) <= max_obj_send_count:
        prnt('request items path 0')
        obj_types = {}
        for i in requested_items:
            obj_type = get_pointer_type(i)
            if obj_type in obj_types:
                obj_types[obj_type].append(i)
            else:
                obj_types[obj_type] = [i]
        prnt('obj_types',obj_types)
        if request_validators:
            request_type = 'Validators_only'
        elif len(obj_types) == 1:
            request_type = next(iter(obj_types), 'multi')
            if request_type in obj_types:
                obj_types = obj_types[request_type]
        else:
            request_type = 'multi'
        prnt('request_type',request_type)
        signedRequest = json.dumps(sign_for_sending({'type':request_type,'items' : obj_types, 'index' : 0,'dt':dt_to_string(now_utc())}, keys=keys))
        # data = {'userData':userData, 'upkData':upkData, 'nodeData':selfNode, 'request':signedRequest}
        data = {'senderId':self_node.id, 'request':signedRequest}
        prnt('data',data)
        result = fetch_data(data, nodes)
        return result
    else:
        prnt('request items path 1')
        if return_updated_count:
            result = 0
        elif return_updated_objs or return_updated_ids:
            result = []
        else:
            result = False
        for obj_type, iden_list in seperate_by_type(requested_items).items():
            if request_validators:
                request_type = 'Validators_only'
            else:
                request_type = obj_type
            if len(iden_list) <= max_obj_send_count:
                prnt('request items path 12')
                signedRequest = json.dumps(sign_for_sending({'type':request_type,'items' : iden_list, 'index' : 0,'dt':dt_to_string(now_utc())}, keys=keys))
                data = {'senderId':self_node.id, 'request':signedRequest}
                resp = fetch_data(data, nodes)
                if resp:
                    if isinstance(resp, int) or isinstance(resp, list):
                        if not result:
                            result = resp
                        else:
                            result = result + resp
                    else:
                        result = True
                time.sleep(1)
            else:
                prnt('request items path 13')
                def process_in_chunks(request_type, items, chunk_size):
                    result = False
                    for i in range(0, len(items), chunk_size):
                        chunk = items[i:i + chunk_size]
                        signedRequest = json.dumps(sign_for_sending({'type':request_type,'items' : chunk, 'index' : 0,'dt':dt_to_string(now_utc())}, keys=keys))
                        data = {'senderId':self_node.id, 'request':signedRequest}
                        resp = fetch_data(data, nodes)
                        if resp:
                            if isinstance(resp, int) or isinstance(resp, list):
                                if not result:
                                    result = resp
                                else:
                                    result = result + resp
                            else:
                                result = True
                        time.sleep(1)
                    return result

                resp = process_in_chunks(request_type, iden_list, max_obj_send_count)
                if resp:
                    if isinstance(resp, int) or isinstance(resp, list):
                        if not result:
                            result = resp
                        else:
                            result = result + resp
                    else:
                        result = True
        return result

def tasker(dt, test=False):
    try:
        est = pytz.timezone('US/Eastern')
        est_time = dt.astimezone(est)
        formatted_time = est_time.strftime("%I:%M:%S %p")
        prnt('\n--tasker',formatted_time,'est')
    except:
        prnt('\n--tasker',dt)
    dt = round_time(dt, amount='10mins', dir='down')
    prnt('dt_utc',dt)

    if e_brake(1):
        return
    # runs every 10 minutes
    from network.models import DataPacket, Block, Blockchain, Node, NodeRecord, Validator, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, selectableChains, block_time_delay
    from utils.locked import check_validation_consensus
    # prnt('blcSomuAHD5878nUb8xYUlmV')
    # for v in Validator.objects.all():
    #     prnt('val::',v.id)
    #     prnt('jobId',v.jobId)
    #     prnt('is_valid',v.is_valid)
    #     prnt('data',v.data)
    #     prnt('created',v.created)
    #     prnt()
    for n in NodeRecord.objects.filter(is_valid=True):
        prnt('rec::',n.id)
        prnt('pointerId',n.pointerId)
        prnt('pointerType',n.pointerType)
        prnt('is_valid',n.is_valid)
        prnt('networkChain',n.networkChain)
        prnt('data',n.data)
        prnt()

    for b in Block.objects.all():
        prnt('blocks::',b)
        prnt('networkChain',b.networkChain)
        prnt('index',b.index)
        prnt('Blockchain_obj.genesisName',b.Blockchain_obj.genesisName)
        prnt('DateTime',b.DateTime)
        prnt('validated',b.validated)
        prnt()
    chains = Blockchain.objects.all()
    prnt('Blockchain::',chains)
    for c in chains:
        prnt('c',c,c.genesisId,c.id,c.chain_length, c.queuedData)
    b = Block.objects.filter(id='blcSo3iF62djr89CvBywJpaa',validated=True).first()
    if b:
        b.is_not_valid()
    result = {'dt':dt_to_string(dt),'now_utc':dt_to_string(now_utc())}
    # skip if start time is excessively delayed
    difference = now_utc() - dt
    diff_mins = difference.total_seconds() / 60
    if diff_mins < 10 or test:
        result = result | {'dps':[],'unvalidated_blocks':[],'new_block_candidate':[],'restore failed scrapers':[],'scrape assignment':[],'unvalidated_txs':[]}
        self_node_id = get_operator_obj('self_nodeId')
        low_queue = django_rq.get_queue('low')

        if dt.minute >= 30 and dt.minute < 40:
        # if dt.minute in _opBlock_creation_times:
            compute_node_trust()
            prnt("now_utc()-datetime.timedelta(minutes=block_time_delay('operations'))",now_utc()-datetime.timedelta(minutes=block_time_delay('operations')))
            opChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId, last_block_datetime__lte=now_utc()-datetime.timedelta(minutes=block_time_delay('operations'))).defer('queuedData').first()
            if opChain:
                block_assigned = opChain.new_block_candidate(self_node=self_node_id, dt=dt)
                prnt('block_assigned',block_assigned)
                if block_assigned:
                    result['new_block_candidate'].append(opChain.genesisName)
                    result['new_block_candidate'].append(block_assigned.id)
        elif dt.minute >= 40:
        # elif dt.minute >= 40 or dt.minute >= 10 and dt.minute <= 20:
            for block in Block.objects.filter(networkChain=_OperationsChain_genesisId, validated__isnull=True).exclude(id__in=result['new_block_candidate']).values('id'):
                result['unvalidated_blocks'].append(block['id'])
                result['new_block_candidate'].append(block['id'])
                if dt.minute >= 50:
                # if dt.minute >= 50 or dt.minute == 20:
                    check_validation_consensus(block['id'], block_id=block['id'], downstream_worker=False)
                elif not exists_in_worker('check_validation_consensus', queue_name='high', block_id=block['id']):
                    django_rq.get_queue('high').enqueue(check_validation_consensus, block=block['id'], block_id=block['id'], only_if_unkown=True, job_timeout=420, result_ttl=7200)
        else:
            for block in Block.objects.filter(networkChain=_OperationsChain_genesisId, validated__isnull=True).defer('data','extraData',"notes").order_by('index'):
                django_rq.get_queue('high').enqueue(block.is_not_valid, mark_strike=False, note='tasker1', job_timeout=300, result_ttl=7200)
            if dt.minute >= 20 and dt.minute < 30:
                operationsPacket = DataPacket.objects.filter(Node_obj__id=self_node_id, func='share', networkChain=_OperationsChain_genesisId).defer('data').first() # broadcast nodeReviews and/or node updates
                if not operationsPacket:
                    operationsPacket = DataPacket(Node_obj_id=self_node_id, networkChain=_OperationsChain_genesisId, func='share', chainName=_OperationsChain_genesisId)
                    operationsPacket.save()
                if operationsPacket:
                    django_rq.get_queue('chat').enqueue(operationsPacket.broadcast_dp, job_timeout=60, result_ttl=7200)

        for block in Block.objects.filter(validated__isnull=True).exclude(networkChain=_OperationsChain_genesisId).exclude(id__in=result['new_block_candidate']).filter(Q(data__meta__isnull=True) | ~Q(data__meta__has_key='is_reward')).exclude(Blockchain_obj=None).values('id').order_by('created','index'): # exclude .data['meta']['is_reward']
            result['unvalidated_blocks'].append(block['id'])
            prnt('check_validation_consensus',block)
            if not exists_in_worker('check_validation_consensus', queue_name=['main','high'], block_id=block['id']):
                django_rq.get_queue('main').enqueue(check_validation_consensus, block=block['id'], block_id=block['id'], only_if_unkown=True, job_timeout=300, result_ttl=7200)
        if e_brake(2):
            return
        from transactions.models import Transaction
        for tx in Transaction.objects.exclude(enacted=True).exclude(ReceiverBlock_obj=None).filter(enact_dt__lt=now_utc()).filter(validated=True).order_by('enact_dt'):
            if not exists_in_worker('enact_transaction', id=tx.id):
                prnt('enact_transaction tx',tx)
                # result['unvalidated_txs'].append(tx.id)
                django_rq.get_queue('main').enqueue(tx.enact_transaction, id=tx.id, job_timeout=60, result_ttl=7200)
        for tx in Transaction.objects.filter(validated=True, ReceiverBlock_obj=None).order_by('ReceiverWallet_obj__id','created').distinct('ReceiverWallet_obj__id'):
            if not exists_in_worker('send_for_block_creation', id=tx.id):
                prnt('send_for_block_creation tx',tx)
                result['unvalidated_txs'].append(tx.id)
                django_rq.get_queue('main').enqueue(tx.send_for_block_creation, id=tx.id, downstream_worker=False, job_timeout=60, result_ttl=7200)
        for tx in Transaction.objects.filter(validated__isnull=True).order_by('created'):
            if not exists_in_worker('send_for_block_creation', id=tx.id):
                prnt('send_for_block_creation tx',tx)
                result['unvalidated_txs'].append(tx.id)
                django_rq.get_queue('main').enqueue(tx.send_for_block_creation, id=tx.id, downstream_worker=False, job_timeout=60, result_ttl=7200)

        self_node = Node.objects.filter(id=self_node_id).values('chain_array','region_array','plugin_array').first()
        prnt('self_node',self_node)

        dataPackets = DataPacket.objects.filter(Node_obj__id=self_node_id, func='share').filter(Q(networkChain__in=self_node['chain_array']+['All'])|Q(Region_obj__id__in=self_node['chain_array'])).exclude(networkChain=_OperationsChain_genesisId).exclude(data={}).defer('data','notes')
        for dp in dataPackets:
            if not exists_in_worker('broadcast_dp', queue_name=['chat'], iden=dp.id):
                django_rq.get_queue('chat').enqueue(dp.broadcast_dp, iden=dp.id, job_timeout=300, result_ttl=7200)

        processes = DataPacket.objects.filter(func__icontains='process', created__lte=now_utc() - datetime.timedelta(minutes=9.5), created__gt=now_utc() - datetime.timedelta(minutes=125)).exclude(func__icontains='completed').defer('data').order_by('created')
        if processes:
            for log in processes:
                prnt('processes log',log)
                if log.created < now_utc() - datetime.timedelta(minutes=65):
                    log.completed('passed_65_minutes')
                elif not log.data:
                    log.delete()
                elif log.updated_on_node < now_utc() - datetime.timedelta(minutes=10):
                    func = log.func
                    if ':' in func:
                        func = func[:func.find(':')]
                    if not exists_in_worker(func, id=log.id):
                        prnt('Continuing RunA:', func)
                        if 'block' in func:
                            queue = django_rq.get_queue('main')
                        else:
                            queue = django_rq.get_queue('low')

                        try:
                            f = globals().get(func)
                            queue.enqueue(f, log.id, job_timeout=300, result_ttl=7200)
                        except Exception as e:
                            prnt('err 0903 ok',str(e))
                            try:
                                import utils.locked as locked_functions
                                f = getattr(locked_functions, func)  
                                queue.enqueue(f, log.id, job_timeout=300, result_ttl=7200)
                            except Exception as e:
                                prnt('err 58351', str(e))

        # return
        # every 60 mins create block if data
        prnt("self_node['chain_array']",self_node['chain_array'])
        prnt("self_node['region_array']",self_node['region_array'])
        prnt("self_node['plugin_array']",self_node['plugin_array'])
        if dt.minute in _block_creation_times or test==True:
            block_assigned = False
            from network.models import Sonet, universalChains, _SonetChain_genesisName
            universalChains.remove(_OperationsChain_genesisId)
            universalChains.remove(_SonetChain_genesisName)
            s = Sonet.objects.values('id').first()
            universalChains.append(s['id'])
            prnt('universalChains',universalChains)
            chains = Blockchain.objects.filter(genesisId__in=universalChains, last_block_datetime__lte=dt - datetime.timedelta(minutes=block_time_delay()-10)).exclude(queuedData={}).defer('queuedData')
            for chain in chains:
                prnt('chain1',chain)
                block_assigned = chain.new_block_candidate(self_node=self_node_id, dt=dt)
                prntDebug('block_assigned0',block_assigned)
                if block_assigned:
                    result['new_block_candidate'].append(chain.genesisName)
                    result['new_block_candidate'].append(block_assigned.id)
            try:
                p_array = self_node['plugin_array'] if self_node['plugin_array'] else []
                r_array = self_node['region_array'] if self_node['region_array'] else []
                supported = list(p_array) + list(r_array)
                prnt('supported',supported)
                chains = Blockchain.objects.filter(genesisId__in=supported, genesisType__in=selectableChains, last_block_datetime__lte=dt - datetime.timedelta(minutes=block_time_delay()-10)).exclude(queuedData={}).defer('queuedData').order_by('?')
                for c in chains:
                    prnt('chain2',c)
                    block_assigned = c.new_block_candidate(self_node=self_node_id, dt=dt)
                    prntDebug('block_assigned::',block_assigned)
                    if block_assigned:
                        result['new_block_candidate'].append(c.genesisName)
                        result['new_block_candidate'].append(block_assigned.id)
            except Exception as e:
                prnt('tasker err 3',str(e))
        if e_brake(3):
            return
        
        if dt.minute < 10 and test==False:
            create_job(run_script_duty, job_timeout=300, worker='high', receivedDt=dt, result=result)

    return result






def compute_job_success(log_dt_start, log_dt_end):
    """
    Returns:
        { node_id: job_success_alignment }
    """
    from django.db.models import Count, Q, F, Case, When, BooleanField, Subquery, OuterRef
    from network.models import NodeReview

    reviews = NodeReview.objects.filter(
        lastUpdate__gte=log_dt_start,
        lastUpdate__lt=log_dt_end,
    )

    # --------------------------------
    # Network consensus per target node
    # --------------------------------
    consensus = (
        reviews
        .values("TargetNode_obj")
        .annotate(
            success_votes=Count("id", filter=Q(job_success__gte=0.5)),
            failure_votes=Count("id", filter=Q(job_success__lt=0.5)),
        )
        .annotate(
            consensus=Case(
                When(success_votes__gte=F("failure_votes"), then=True),
                default=False,
                output_field=BooleanField(),
            )
        )
    )

    consensus_subquery = consensus.filter(
        TargetNode_obj=OuterRef("TargetNode_obj")
    ).values("consensus")[:1]

    reviews = reviews.annotate(
        consensus=Subquery(consensus_subquery)
    )

    # --------------------------------
    # Alignment per reviewing node
    # --------------------------------
    alignment = (
        reviews
        .values("CreatorNode_obj")
        .annotate(
            total=Count("id"),
            aligned=Count(
                "id",
                filter=Q(
                    Q(job_success__gte=0.5, consensus=True) |
                    Q(job_success__lt=0.5, consensus=False)
                )
            )
        )
    )

    results = {}

    for row in alignment:
        node_id = row["CreatorNode_obj"]
        total = row["total"]
        aligned = row["aligned"]

        results[node_id] = aligned / total if total else 0.5

    return results

def compute_block_success(log_dt_start, log_dt_end):
    """
    Returns:
        { node_id: block_success }
    """
    from django.db.models import Count, Q
    from network.models import Block

    blocks = (
        Block.objects.filter(
            DateTime__gte=log_dt_start,
            DateTime__lt=log_dt_end,
        )
        .values("CreatorNode_obj")
        .annotate(
            completed=Count("id", filter=Q(validated=True)),
            failed=Count("id", filter=Q(validated=False)),
        )
    )

    results = {}

    for row in blocks:
        node_id = row["CreatorNode_obj"]
        completed = row["completed"]
        failed = row["failed"]
        total = completed + failed

        results[node_id] = completed / total if total else 0

    return results

def compute_consensus_alignment(log_dt_start, log_dt_end):
    """
    Returns:
        { node_id: consensus_alignment }
    """
    from django.db.models import Count, Q, F, Case, When, BooleanField, Subquery, OuterRef
    from network.models import Validator

    # All validators in window
    validators = Validator.objects.filter(
        created__gte=log_dt_start,
        created__lt=log_dt_end,
        validatorType="Block",
    )

    # -----------------------------
    # Consensus per job
    # -----------------------------
    job_consensus = (
        validators
        .values("jobId")
        .annotate(
            true_votes=Count("id", filter=Q(is_valid=True)),
            false_votes=Count("id", filter=Q(is_valid=False)),
        )
        .annotate(
            consensus=Case(
                When(true_votes__gte=F("false_votes"), then=True),
                default=False,
                output_field=BooleanField(),
            )
        )
    )

    # Attach consensus to each validator
    consensus_subquery = job_consensus.filter(
        jobId=OuterRef("jobId")
    ).values("consensus")[:1]

    validators = validators.annotate(
        consensus=Subquery(consensus_subquery)
    )

    # -----------------------------
    # Alignment grouped by node
    # -----------------------------
    node_alignment = (
        validators
        .values("CreatorNode_obj")
        .annotate(
            total_votes=Count("id"),
            aligned_votes=Count(
                "id",
                filter=Q(is_valid=F("consensus"))
            ),
        )
    )

    # -----------------------------
    # Final scores
    # -----------------------------
    results = {}

    for row in node_alignment:
        node_id = row["CreatorNode_obj"]
        total = row["total_votes"]
        aligned = row["aligned_votes"]

        results[node_id] = aligned / total if total else 0

    return results

def compute_node_trust():
    """
    Compute trust and influence scores for all nodes using all NodeReviews received.
    Weights each review by:
      - review metrics
      - recency
      - interaction count
      - reviewer influence_score (derived from trust_score in review)
    """

    # should also track when a node goes dark, lower trust score if happens often

    from django.db import transaction
    from network.models import Node, NodeReview
    import time
    import math
    from collections import defaultdict
    self_node_id = get_operator_obj('local_nodeId')
    log_dt_end = round_time(now_utc(), dir='down', amount='hour')
    log_dt_start = log_dt_end - datetime.timedelta(hours=1)

    block_successes = compute_block_success(log_dt_start, log_dt_end)
    alignments = compute_consensus_alignment(log_dt_start, log_dt_end)
    job_successes = compute_job_success(log_dt_start, log_dt_end)

    nodes = {n.id: n for n in Node.objects.exclude(activated_dt=None)}

    reviews = NodeReview.objects.filter(TargetNode_obj__id__in=nodes, CreatorNode_obj__id__in=nodes, lastUpdate__gte=now_utc() - datetime.timedelta(minutes=120)).only('TargetNode_obj__id','CreatorNode_obj__id','response_success','job_success','trust_score','interactions','lastUpdate')
    updated_reviews = []

    review_map = {}
    peer_reviews = defaultdict(list)
    for r in reviews:
        peer_reviews[r.TargetNode_obj.id].append({
        "response_success": r.response_success,
        "job_success": job_successes.get(r.CreatorNode_obj.id, 0.5),
        "block_success": block_successes.get(r.TargetNode_obj.id, 0.5),
        "consensus_alignment": alignments.get(r.TargetNode_obj.id, 0.5),
        "trust_score": r.trust_score,
        "interactions": r.interactions,
        "timestamp": int(r.lastUpdate.timestamp())
            })
        if r.CreatorNode_obj.id == self_node_id:
            review_map[r.TargetNode_obj.id] = r
    reviews = []
    block_successes.clear()
    alignments.clear()
    job_successes.clear()

    METRIC_WEIGHTS = {
        "response_success": 0.15,
        "job_success": 0.35,
        "block_success": 0.25,
        "consensus_alignment": 0.25,
    }
    REVIEW_HALF_LIFE_HOURS = 48
    MIN_INTERACTIONS = 10

    def recency_weight(timestamp):
        age_hours = (time.time() - timestamp) / 3600
        return math.exp(-age_hours / REVIEW_HALF_LIFE_HOURS)

    def interaction_weight(interactions):
        return min(1.0, interactions / 50)

    def metric_score(r):
        return sum(r[k] * w for k, w in METRIC_WEIGHTS.items())

    for node_id, node in nodes.items():
        reviews_for_node = peer_reviews.get(node_id, [])
        total_weighted_score = 0
        total_weight = 0

        for r in reviews_for_node:
            if r['interactions'] < MIN_INTERACTIONS:
                continue

            # Reviewer influence = sqrt(reviewer trust_score from the review)
            reviewer_trust = r.get("trust_score", 0.5)
            reviewer_influence = math.sqrt(max(reviewer_trust, 0))

            w = recency_weight(r['timestamp']) * interaction_weight(r['interactions']) * reviewer_influence
            total_weighted_score += metric_score(r) * w
            total_weight += w

        observed_trust = total_weighted_score / total_weight if total_weight > 0 else 0.5

        TRUST_FLOOR = 0.05
        TRUST_CEILING = 0.99

        previous_trust = node.trust_score or 0.5

        if observed_trust < previous_trust:
            lr = 0.25   # lose trust faster
        else:
            lr = 0.10   # gain trust slower

        updated_trust = (
            (1 - lr) * previous_trust
            + lr * observed_trust
        )

        # clamp
        updated_trust = max(TRUST_FLOOR, min(TRUST_CEILING, updated_trust))

        node.trust_score = updated_trust
        node.influence_score = math.sqrt(updated_trust)
        node.score_dt = now_utc()

        review = review_map.get(node_id, None)
        if review:
            review.trust_score = updated_trust
            review.interactions = 0
            updated_reviews.append(review)


    NodeReview.objects.bulk_update(updated_reviews, ['trust_score','interactions'])
    # Save all nodes at once
    with transaction.atomic():
        for node in nodes.values():
            node.save()
    

def run_script_duty(receivedDt=None, result=None):
    # runs every hour
    prnt('\n---run_script_duty',receivedDt)
    from network.models import Plugin, Tidy
    import importlib
    import hashlib
    self_node = get_self_node()

    if not receivedDt:
        receivedDt = now_utc()
    if receivedDt.minute < 10 and receivedDt.hour in [9, 11, 20]:
        # also check for User objs without valid UPK and vice versa, maybe less often
        queue = django_rq.get_queue('low')
        queue.enqueue(Tidy()._add_all_jobs, dt=receivedDt, job_timeout=60, result_ttl=7200)
                    
    result = {}
    if receivedDt.minute < 10:

        def shuffle_list(seed_input, lst):
            seed_hash = hashlib.sha256(seed_input.encode('utf-8')).hexdigest()
            seed_int = int(seed_hash, 16)
            rng = random.Random(seed_int)
            rng.shuffle(lst)
            return lst

        # check plugin support for self_node
        # shuffle plugins list
        plugins = Plugin.objects.filter(app_name='legis')
        for plugin in plugins:
            importScript = f'{plugin.app_name}.utils'
            utils_funcs = importlib.import_module(importScript)
            run_assigned_duties = getattr(utils_funcs, 'run_assigned_duties')
            try:
                r = run_assigned_duties(receivedDt)
                result[plugin.app_name] = r
            except Exception as e:
                prnt('run_assigned_duties err',plugin.app_name,str(e))
                result[plugin.app_name] = str(e)


    if result:
        return result


def process_received_data(received_data, block_dict=None, downstream_worker=True, return_updated_count=False, return_updated_objs=False, return_updated_ids=False, check_consensus=True, skip_log_check=False, get_missing_blocks=True, override_completed=False, force_sync=False):
    prnt('---process_received_data now_utc:', now_utc(),'get_missing_blocks',get_missing_blocks,'check_consensus',check_consensus)
    from accounts.models import User, Notification, UserPubKey
    from transactions.models import Transaction
    from posts.models import scoreMe, Update, Post
    from utils.locked import verify_data, check_commit_data, get_signing_data, convert_to_dict, sign_obj, validate_obj, get_relevant_nodes_from_block, get_node_assignment, get_commit_data, check_block_contents, check_validation_consensus
    from network.models import Plugin, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay, share_to_all, script_created_modifiable_models
    
    result = process_received_dp(received_data, 'process_received_data', skip_log_check=skip_log_check, override_completed=override_completed)
    prnt('reslut:',str(result)[:1000])
    if result and 'dp' in result:
        log = result['dp']
        received_data = result['data']
    elif result and 'data' in result:
        received_data = result['data']
        log = None
    else:
        received_data = []
        log = None

    if not force_sync and log and isinstance(log, models.Model):
        if log.func and 'process' not in log.func and not override_completed:
            return []

    synced_idens = []
    updated_objs = []
    updated_count = 0
    databaseUpdated = False
    if 'opBlock' in received_data and received_data['opBlock']:
        if 'opBlock_hash' in received_data:
            block_exists = Block.objects.filter(hash=received_data['opBlock_hash'], validated=True).exists()
        else:
            block_exists = Block.objects.filter(id=received_data['opBlock'], validated=True).exists()
        prnt('block_exists??1',block_exists)
        if not block_exists:
            if 'senderId' in received_data and received_data['senderId']:
                nodes = [received_data['senderId']]
            else:
                nodes = None
            request_items(requested_items=[received_data['opBlock']], get_missing_blocks=get_missing_blocks, nodes=nodes, downstream_worker=False)
            
    try:
        if isinstance(received_data, dict) and 'content' in received_data:
            content = received_data['content']
            if isinstance(content, dict) and 'content' in content: 
                content = content['content']
        else:
            content = received_data
        content = decompress_data(content)
        if isinstance(content, str):
            content = json.loads(content)
        elif isinstance(content, list):
            content = content
        prnt('next3')
        if not content:
            prnt('no data')
            if log:
                log.completed(note='no_data')
            return []
        objs = {}
        for i in content:
            try:
                objs[i['objType']].append(i['id'])
            except:
                objs[i['objType']] = [i['id']]
        self_node = get_self_node()
        if self_node and self_node.node_type == 'relay':
            prcs = share_to_all+['blc','val','chn']
            content = [i for i in content if isinstance(i,dict) and get_model_prefix(i['objType']) in prcs]
        prnt('stage2- data Len:',len(content))
        opBlock_dict = {'index':{}}
        userVotes = []
        validators = []
        received_invalids = []
        storedModels, not_found, not_valid = get_data(content, return_model=True, include_related=False, result_as_dict=True, verify_data=False)
        prnt('existing_objs-',len(storedModels))

        sorted_data = sorted(content, key=data_sort_priority) # data must be added in order due to dependancies
        prntDebug('--received_data len:',len(sorted_data))
        # get_model_prefix

        def save_to_db(bulk_update_items):
            prntDebug('save_to_db',len(bulk_update_items))
            nonlocal return_updated_objs
            nonlocal return_updated_ids
            nonlocal return_updated_count
            nonlocal updated_objs
            nonlocal updated_count
            nonlocal synced_idens
            created_items = []
            bulk_create_objs = [bulk_update_items[key]['obj'] for key in bulk_update_items if bulk_update_items[key]['is_new']]
            prnt('bulk_create_objs',bulk_create_objs)
            if bulk_create_objs:
                created_items = dynamic_bulk_create(current_model_type, items=bulk_create_objs, return_items=True, retrieve_missing=get_missing_blocks)
                prnt('created_items',[i.id for i in created_items])
                synced_idens += [i.id for i in created_items]
                if return_updated_objs:
                    updated_objs = updated_objs + created_items
                elif return_updated_ids:
                    updated_objs = updated_objs + [i.id for i in created_items]
                elif return_updated_count:
                    updated_count += len(created_items)
            prnt('bulk_update_items',bulk_update_items.keys())
            bulk_update_objs = [bulk_update_items[key]['obj'] for key in bulk_update_items if not bulk_update_items[key]['is_new'] and bulk_update_items[key]['updatedDB']]
            prnt('bulk_update_objs',bulk_update_objs)
            if bulk_update_objs:
                updated_items = dynamic_bulk_update(current_model_type, items=bulk_update_objs, return_items=True, retrieve_missing=get_missing_blocks)
                synced_idens += [i.id for i in updated_items]
                if return_updated_objs:
                    updated_objs = updated_objs + updated_items
                elif return_updated_ids:
                    updated_objs = updated_objs + [i.id for i in updated_items]
                elif return_updated_count:
                    updated_count += len(updated_items)
                if updated_items:
                    updated_items.clear()
            prnt('bulk_update_items',bulk_update_items)
            for key, value in bulk_update_items.items():
                prnt('item',value)
                save_sigs(value['sigs'])
            prnt('created_items',created_items)
            for obj in created_items:
                prnt('obj',obj)
                if bulk_update_items[obj.id]['is_new'] or bulk_update_items[obj.id]['updatedDB']:
                    if has_method(obj, 'boot'):
                        if not has_field(obj, 'proposed_modification') or not obj.proposed_modification:
                            prntDebug('booting obj', obj.id)
                            obj.boot()
            prnt('to_chain_items')
            to_chain_items = created_items + [i for i in bulk_update_items]
            if created_items:
                created_items.clear()
            bulk_update_items.clear()
            to_queue = {}
            for i in to_chain_items:
                if has_field(i, 'networkChain') and i.networkChain:
                    if i.networkChain not in to_queue:
                        to_queue[i.networkChain] = []
                    to_queue[i.networkChain].append(i)
            to_chain_items.clear()
            prnt('to_queue',to_queue)
            for chainId, objs in to_queue.items():
                blockchain = Blockchain.objects.filter(id=chainId).first()
                prnt('blockchain',blockchain)
                if blockchain:
                    blockchain.add_item_to_queue(objs)
            to_queue.clear()
            

        current_model_type = None
        bulk_update_items = {}
        for i in sorted_data:
            prntDebugn('ixi:',str(i)[:2000])
            if not current_model_type:
                current_model_type = i['objType']
            if current_model_type != i['objType'] or len(bulk_update_items) >= 1000:
                prnt('bulk_update_items p1', len(bulk_update_items))
                if bulk_update_items:
                    save_to_db(bulk_update_items)
                current_model_type = i['objType']
                bulk_update_items = {}
            valid_obj = False
            bad_commit = False
            val_err = '-'
            updatedDB = False
            if block_dict: # not doing anything currently
                hash = sigData_to_hash(i)
                receivedHash = [data['hash'] for iden, data in block_dict['data'].items() if iden == i['id'] and 'hash' in data][0]
                if receivedHash == hash:
                    hashMatch = True
                else:
                    hashMatch = False
            try:
                prnt('try')
                # check self_node that plugin and region are supported before sync for each item 

                userModels = ['User', 'Node', 'Transaction', 'UserPubKey']
                if i['objType'] in storedModels and i['id'] in storedModels[i['objType']] and storedModels[i['objType']][i['id']].signed:
                    val_err += 'a'
                    obj = storedModels[i['objType']][i['id']]
                    del storedModels[i['objType']][i['id']]
                    is_new = False
                else:
                    val_err += 'b'
                    obj, is_new = get_or_create_model(i['objType'], return_is_new=True, id=i['id'])
                
                if bad_commit:
                    prnt('bad_commit',bad_commit)
                elif i['objType'] == 'Sonet':
                    from network.models import Sonet
                    if not Sonet.objects.all().exists():
                        if verify_data(get_signing_data(i), i['signed']):
                            sonet, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                            new_sonet_valid = verify_data(get_signing_data(sonet), i['signed'])
                            prnt('new_sonet_valid',new_sonet_valid)
                            if new_sonet_valid:
                                from utils.locked import bytes_to_base64url
                                sonet.save(sig=bytes_to_base64url(sigs[-1].sig))
                                sonet.boot()
                                obj = sonet
                                save_sigs(sigs)
                    else:
                        val_err += '3'
                        obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                        val_err += f"_{valid_obj}_{updatedDB}_"
                elif i['objType'] in userModels:
                    val_err += 'A'
                    if obj._meta.object_name == 'User':
                        prnt('obj is user')
                        val_err += 'B'
                        if is_new:
                            val_err += '1'
                            prntDebug('is new')
                            if verify_data(get_signing_data(i), i['signed']):
                                val_err += '2'
                                prnt('create user')
                                user, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                new_user_valid = verify_data(get_signing_data(user), i['signed'])
                                prnt('new_user_valid',new_user_valid)
                                if new_user_valid:
                                    user.save(bypass_verify=True)
                                    obj = user
                                    save_sigs(sigs)
                                    new = False
                        else:
                            val_err += 'C'
                            # check on UserVerification_obj here - isVerified is no longer used
                            if has_field(obj, 'isVerified') and obj.isVerified == False and i['isVerified'] == 'True' or has_field(obj, 'isVerified') and obj.isVerified == True and i['isVerified'] == 'False':
                                val_err += '1'
                                is_verified = obj.assess_verification()
                                obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                                if not is_verified:
                                    obj.isVerified = False
                                    # obj.save()
                            else:
                                val_err += '2'
                                obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                        val_err += 'D'
                        # check if username already taken
                        must_rename = False
                        u = User.objects.filter(username=i['username']).exclude(id=i['id']).first()
                        if u and u.lastpdate > string_to_dt(i['lastUpdate']):
                            u.alerts['must_rename'] = True
                            # u.save() # shuold broadcast?
                            bulk_update_items[u.id] = {'is_new':False,'updatedDB':True,'obj':u}

                        elif u:
                            must_rename = True
                        if must_rename:
                            obj.alerts['must_rename'] = True
                            # obj.save()
                    elif obj._meta.object_name == 'Transaction':
                        val_err += 'E'
                        # if 'ReceiverBlock_obj' in i and value_is_none(i['ReceiverBlock_obj']):
                        # receiverBlock = Block.objects.filter(Transaction_obj=self.Transaction_obj, Blockchain_obj__genesisId=self.Transaction_obj.ReceiverWallet_obj.id).exclude(id=self.Transaction_obj.senderBlockId).first()
                        # if receiverBlock:
                        #     obj.ReceiverBlock_obj = Block.objects.filter(id=i['receiverBlockId']).first()
                        if 'senderBlockId' in i and not value_is_none(i['senderBlockId']):
                            obj.SenderBlock_obj = Block.objects.filter(id=i['senderBlockId']).first()
                        val_err += '1'
                        obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                    elif obj._meta.object_name == 'Node':
                        val_err += 'F'
                        is_active = True
                        if obj.expelled_dt or i['expelled_dt']:
                            # handle disavowed claims appropriately
                            val_err += '1'
                            pass
                        if obj.suspended_dt and i['suspended_dt'] == 'None':
                            val_err += '2'
                            is_active = obj.assess_activity()
                        if is_active:
                            val_err += '3'
                            if verify_data(get_signing_data(i), i['signed']):
                                from utils.locked import bytes_to_base64url
                                val_err += '5'
                                if is_new:
                                    val_err += '6'
                                    prnt('create node')
                                    node, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                    new_node_valid = verify_data(node, i['signed'], sigs)
                                    prnt('new_node_valid',new_node_valid)
                                    if new_node_valid:
                                        val_err += '7'
                                        node.save(bypass_lock=True, bypass_upk_block=True)
                                        obj = node
                                        save_sigs(sigs)
                                        is_new = False
                                else:
                                    val_err += '8'
                                    node, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                    node_is_valid = verify_data(get_signing_data(node), i['signed'])
                                    prnt('node_is_valid',node_is_valid, 'updatedDB',updatedDB)
                                    if node_is_valid:
                                        val_err += '9'
                                        node.save(bypass_lock=True, bypass_upk_block=True)
                                        save_sigs(sigs)
                                        obj = node
                    
                    elif obj._meta.object_name == 'UserPubKey':
                        val_err += 'G'
                        prnt('obj is upk')
                        if is_new or not obj.Block_obj:
                            val_err += '1'
                            prntDebug('is new')

                            # sig_data = get_sigData(target_data, first_key=False)
                            # target_dt = sig_data['dt']

                            if verify_data(get_signing_data(i), i['signed'], upk_bypass=True):
                                val_err += '2'
                                valid_obj = True
                                prntDebug('creta upk')
                                if not User.objects.filter(id=i['User_obj']).exists():
                                    user = User(id=i['User_obj'], modlVer=1)
                                    user.save(bypass_verify=True)
                                # double check:
                                # make sure not injecting unauthorized super keys
                                # nodeId must correlate with keyType = 'node', upk.user must match node.user
                                # new upks are signed by older upk from same user, if no prev upk, must be created at same time as user
                                obj, sigs, updatedDB = set_model_attrs(obj, i, get_missing_blocks=get_missing_blocks)
                                obj.save(bypass_verify=True)
                                save_sigs(sigs)
                                new_upk_valid = verify_data(get_signing_data(obj), i['signed'])
                                prnt('new_upk_valid?',new_upk_valid)
                                is_new = False
                        else:
                            val_err += '3'
                            obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)

                elif not force_sync and is_locked(obj) and not has_field(obj, 'is_modifiable'):
                    valid_obj = True
                    val_err += 'X'
                else:
                    val_err += 'H'
                    try:
                        if 'func' in i and 'created' in i:
                            pos = f"{i['func']}_{i['created']}"
                        else:
                            pos = f"{i['created']}"
                        if pos not in opBlock_dict:
                            val_err += '1' # was causing issues with getting maintainers/intelligence/all
                        opBlock_dict['index'][i['id']] = pos
                        if has_field(obj, 'proposed_modification'):
                            val_err += '4'
                            obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                            if has_field(obj, 'Update_obj'):
                                obj.Update_obj = None
                            if has_field(obj, 'Validator_obj'):
                                obj.Validator_obj = None
                            if has_field(obj, 'Block_obj'):
                                obj.Block_obj = None
                            val_err += f"_{valid_obj}_{updatedDB}_"
                            mod_obj = get_dynamic_model(obj._meta.object_name, proposed_modification=obj.id)
                            if mod_obj and mod_obj.created <= string_to_dt(obj.lastUpdate):
                                prnt('delete1',mod_obj.id)
                                modded_chain = Blockchain.objects.filter(genesisId=mod_obj.id).first()
                                if modded_chain:
                                    super(get_model(modded_chain._meta.object_name), modded_chain).delete()
                                post = Post.objects.filter(pointerId=mod_obj.id).first()
                                if post:
                                    post.validated = False
                                    post.delete()
                                super(get_model(mod_obj._meta.object_name), mod_obj).delete()
                            Post.objects.filter(pointerId=obj.id, validated=True).update(validated=False, blockId=None)
                        else:
                            val_err += '3'
                            obj, sigs, valid_obj, updatedDB = sync_model(obj, i, do_save=False, force_sync=force_sync, get_missing_blocks=get_missing_blocks)
                            if has_field(obj, 'Update_obj'):
                                obj.Update_obj = None
                            if has_field(obj, 'Validator_obj'):
                                obj.Validator_obj = None
                            if has_field(obj, 'Block_obj'):
                                obj.Block_obj = None
                            val_err += f"_{valid_obj}_{updatedDB}_"

                        if valid_obj and obj._meta.object_name == 'UserVote':
                            userVotes.append(obj)

                    except Exception as e:
                        prntDebug('---fail5937564, val_err:',val_err,str(e),str(i)[:1000])
                        logError(e, code='482764', func='processed_received_data', extra=str(i)[:1000])
                if valid_obj and obj._meta.object_name == 'Validator':
                    val_err += 'I'
                    if obj not in validators:
                        if obj.validatorType != 'Block' or is_new:
                            val_err += 'a'
                            validators.append(obj)
                        elif obj.validatorType == 'Block':
                            val_err += 'b'
                            val_block = Block.objects.filter(id__in=obj.data).first()
                            if val_block and val_block.validated == None or val_block and override_completed or not val_block:
                                val_err += 'c'
                                validators.append(obj) # check_block_consensus()
                            elif val_block and val_block.validated:
                                val_err += 'd'
                                if 'unsupported_chain' in val_block.notes or 'problem_idens' in val_block.notes or 'found_idens' not in val_block.notes:
                                    validators.append(obj) # check_block_contents()
                                    val_err += 'e'
                if not valid_obj:
                    received_invalids.append({i['id']:val_err,'updatedDB':updatedDB})
                elif updatedDB:
                    if obj._meta.object_name == 'Region': # ParentRegion_obj must be saved before bulk update
                        obj.save()
                    else:
                        bulk_update_items[obj.id] = {'is_new':is_new,'updatedDB':updatedDB,'obj':obj, 'sigs':sigs}
                    synced_idens.append(obj.id)
                    
                elif has_field(obj, 'Validator_obj') and not obj.Validator_obj:
                    synced_idens.append(obj.id)
                elif override_completed:
                    synced_idens.append(obj.id)
                if not databaseUpdated and valid_obj and updatedDB:
                    databaseUpdated = True
                prnt('process data progress:',val_err,'len(bulk_update_items)',len(bulk_update_items))
            except Exception as e:
                prntDebug('-process data fail593, err:',val_err,str(e),str(i)[:1000])
                logError(e, code='09863', func='processed_received_data', extra={'err':str(e),'i':str(i)[:1000]})

        if received_invalids:
            # logError('received_invalids', code='4684', func='processed_received_data', extra={'received_invalids_count':len(received_invalids),'received_invalids':received_invalids[:500]})
            pass

        if bulk_update_items:
            prnt('bulk_update_items p2', len(bulk_update_items))
            save_to_db(bulk_update_items)
            
        prnt('stage3-',databaseUpdated)
        func = 'process_received_data'
        v_list = {key:None for key in synced_idens}
        validated_obj_idens = []
        prnt('validators:',len(validators))
        if validators:
            prnt('validators...')
            now = now_utc()
            chain_list = {}
            validIds = []
            
            prnt('vals step1a',validators)
            from network.models import Validator
            for validator in validators:
                if validator.validatorType != 'Block' and validator.is_valid:
                    for key, value in validator.data.items():
                        if key in synced_idens:
                            validIds.append(key)
                            v_list[key] = validator
                    if validator.networkChain not in chain_list:
                        blockchain = Blockchain.objects.filter(id=validator.networkChain).first()
                        if blockchain:
                            chain_list[validator.networkChain] = blockchain
                    if validator.networkChain in chain_list:
                        chain_list[validator.networkChain].add_item_to_queue(validator)                
            
            validated_idens = [i for i in validIds if not i.startswith(get_model_prefix('Update')) and not i.startswith(get_model_prefix('Notification'))]
            prnt('vals step2a',len(validated_idens))

            if validated_idens:
                q = 13
                for model_name, id_list in seperate_by_type(validated_idens).items():
                    prnt('model_name',model_name)
                    q = 131
                    to_queue = {}
                    objIdens = id_list
                    while objIdens:
                        q = 132
                        objs = list(get_dynamic_model(model_name, list=True, id__in=objIdens[:500]))
                        del objIdens[:500]
                        bulk_update = []
                        for obj in objs:
                            prnt('obj',obj)
                            try:
                                if obj.id not in v_list:
                                    prnt('obj not with validator list', obj.id)
                                else:
                                    if has_field(obj, 'Validator_obj'):
                                        if obj.Validator_obj and obj.Validator_obj.is_valid:
                                            prnt('previously validated', obj.id)
                                            validated_obj_idens.append(obj.id)
                                            # objs.remove(obj)
                                        else:
                                            prnt('else',obj.id)
                                            pos = None
                                            # if has_field(obj, 'func'):
                                            #     pos = f"{obj.func}_{dt_to_string(obj.created)}"
                                            # if pos and pos in opBlock_dict:
                                            #     # pos = opBlock_dict['index'][obj.id]
                                            #     target_opBlock = opBlock_dict[pos]
                                            # elif has_field(obj, 'created') and has_field(obj, 'blockchainId') and obj.blockchainId:
                                            #     opBlock_data = get_relevant_nodes_from_block(dt=string_to_dt(obj.created), blockchain=obj.blockchainId)
                                            #     opBlock_dict[pos] = {'node_ids':[n for n in opBlock_data['relevant_nodes']],'number_of_peers':opBlock_data['opData']['number_of_peers'],'relevant_nodes':opBlock_data['relevant_nodes']}
                                            #     opBlock_dict['index'][obj.id] = pos
                                            #     target_opBlock = opBlock_dict[pos]
                                            # else:
                                            target_opBlock = {}
                                            obj = validate_obj(obj=obj, pointer=obj, opBlock_data=target_opBlock, save_obj=False, update_pointer=False)
                                            if obj and obj.Validator_obj:
                                                obj.updated_on_node = now
                                                validated_obj_idens.append(obj.id)
                                                if has_field(obj, 'networkChain') and obj.networkChain:
                                                    if obj.networkChain not in to_queue:
                                                        to_queue[obj.networkChain] = []
                                                    to_queue[obj.networkChain].append(obj)
                                                
                                                if has_method(obj, 'upon_validation'):
                                                    obj.upon_validation()
                                                if has_method(obj, 'on_confirmation'):
                                                    i = obj.on_confirmation()
                                                    if i:
                                                        obj = i
                                                bulk_update.append(obj)
                            except Exception as e:
                                prnt('***ERROR*** 9898',str(e))
                        dynamic_bulk_update(model_name, items_field_update=['Validator_obj','updated_on_node'], items=bulk_update) 
                        q = 133
                        objs.clear()
                    if to_queue:
                        ...
                        # for chainId, objs in to_queue.items():
                        #     if chainId not in chain_list:
                        #         blockchain = Blockchain.objects.filter(id=chainId).first()
                        #         if blockchain:
                        #             chain_list[chainId] = blockchain
                        #     if chainId in chain_list:
                        #         chain_list[chainId].add_item_to_queue(objs)
                    to_queue.clear()
        if synced_idens:
            pointerIdens = [i for i in validated_obj_idens if not i.startswith(get_model_prefix('Update')) and not i.startswith(get_model_prefix('Notification')) and not i.startswith(get_model_prefix('BillText'))]
            prnt('vals step2.5a',len(pointerIdens))
            from posts.models import update_post
            while pointerIdens:
                q = 121
                prnt('pointerIdens[:1000]',len(pointerIdens[:500]),pointerIdens[:500])
                bulk_update = []
                fields = []
                posts = Post.all_objects.filter(pointerId__in=pointerIdens[:500]).exclude(validated=True)
                del pointerIdens[:500]
                prnt('posts len',posts.count())
                for p in posts:
                    try:
                        # if p.pointerId in opBlock_dict['index']: # was causing issues with getting maintainers/intelligence/all
                        #     pos = opBlock_dict['index'][p.pointerId]
                        #     target_opBlock = opBlock_dict[pos]
                        # else:
                        target_opBlock = {}
                        if validate_obj(obj=p, pointer=None, opBlock_data=target_opBlock, save_obj=False, update_pointer=False, verify_validator=False):
                            p.validated = True
                            p.updated_on_node = now
                            p, updated_fields = update_post(p=p, save_p=False)
                            bulk_update.append(p)
                            if updated_fields:
                                fields += [f for f in updated_fields if f not in fields]
                    except Exception as e:
                        prnt('***ERROR*** 7888',str(e))
                posts = None
                q = 122
                prnt('process data bulk_update posts',bulk_update)
                if bulk_update:
                    dynamic_bulk_update(model=Post, items_field_update=['validated','updated_on_node']+fields, items=bulk_update)
                q = 123
            q = 124
            updateIdens = [u for u in synced_idens if u.startswith(get_model_prefix('Update'))]
            prnt('vals step3a',len(updateIdens))
            if updateIdens:
                q = 14
                prnt('updateIdens',updateIdens)
                while updateIdens:
                    bulk_update = []
                    to_queue = {}
                    updates = Update.objects.filter(id__in=updateIdens[:500]).exclude(validated=True).order_by('id')
                    del updateIdens[:500]
                    for u in updates:
                        prnt('u',u)
                        try:
                            if u.id not in v_list:
                                prnt('obj not with validator list', u.id)
                            else:
                                if not is_locked(u, skip=['Validator_obj']):
                                    # if u.id in opBlock_dict['index']: # was causing issues with getting maintainers/intelligence/all
                                    #     pos = opBlock_dict['index'][u.id]
                                    #     target_opBlock = opBlock_dict[pos]
                                    # else:
                                    target_opBlock = {}
                                    u = validate_obj(obj=u, pointer=None, opBlock_data=target_opBlock, save_obj=False, verify_validator=False, update_pointer=False)
                                    if u and u.Validator_obj:
                                        u.validated = True
                                        u.updated_on_node = now
                                        validated_idens.append(u.id)
                                        if has_method(u, 'upon_validation'):
                                            u.upon_validation()
                                        if has_method(u, 'on_confirmation'):
                                            i = u.on_confirmation()
                                            if i:
                                                u = i
                                        bulk_update.append(u)
                                        if has_field(u, 'networkChain') and u.networkChain:
                                            if u.networkChain not in to_queue:
                                                to_queue[u.networkChain] = []
                                            to_queue[u.networkChain].append(u)
                                else:
                                    prnt('locked', convert_to_dict(u))
                        except Exception as e:
                            prnt('***ERROR*** 6787',str(e))
                    updates = None
                    q = 141
                    if bulk_update:
                        items = dynamic_bulk_update(model=Update, items_field_update=['validated', 'Validator_obj','updated_on_node'], items=bulk_update, return_items=True)
                        
                    if to_queue:
                        ...
                        # for chainId, objs in to_queue.items():
                        #     if chainId not in chain_list:
                        #         blockchain = Blockchain.objects.filter(id=chainId).first()
                        #         if blockchain:
                        #             chain_list[chainId] = blockchain
                        #     if chainId in chain_list:
                        #         chain_list[chainId].add_item_to_queue(objs)
                    to_queue.clear()

            q = 142
            from accounts.models import Notification
            notiIdens = [u for u in synced_idens if u.startswith(get_model_prefix('Notification'))]
            prnt('vals step3.5a',len(notiIdens))
            if notiIdens:
                q = 15
                prnt('notiIdens',notiIdens)
                bulk_update = []
                to_queue = {}
                notifications = Notification.objects.filter(id__in=notiIdens).exclude(validated=True)
                for n in notifications:
                    try:
                        # if not is_locked(n):
                        # if has_field(n, 'func'):
                        #     pos = f"{n.func}_{dt_to_string(n.created)}" # was causing issues with getting maintainers/intelligence/all
                        # if pos and pos in opBlock_dict:
                        #     # target_opBlock = opBlock_data[n.created]
                        #     # pos = opBlock_dict['index'][n.id]
                        #     target_opBlock = opBlock_dict[pos]
                        # elif has_field(n, 'created'):
                        #     opBlock_data = get_relevant_nodes_from_block(dt=string_to_dt(n.created), genesisId=_OperationsChain_genesisId)
                        #     opBlock_dict[pos] = {'node_ids':[n for n in opBlock_data['relevant_nodes']],'number_of_peers':opBlock_data['opData']['number_of_peers'],'relevant_nodes':opBlock_data['relevant_nodes']}
                        #     opBlock_dict['index'][n.id] = pos
                        #     target_opBlock = opBlock_dict[pos]
                        # else:
                        target_opBlock = {}
                        n = validate_obj(obj=n, pointer=None, opBlock_data=target_opBlock, save_obj=False, update_pointer=False)
                        if n and n.Validator_obj:
                            n.validated = True
                            n.updated_on_node = now
                            if has_method(n, 'upon_validation'):
                                n.upon_validation()
                            if has_method(n, 'on_confirmation'):
                                i = n.on_confirmation()
                                if i:
                                    n = i
                            bulk_update.append(n)
                            if has_field(n, 'networkChain') and n.networkChain:
                                if n.networkChain not in to_queue:
                                    to_queue[n.networkChain] = []
                                to_queue[n.networkChain].append(n)
                    except Exception as e:
                        prnt('***ERROR*** 8965',str(e))
                notifications = None
                prnt('bulk_update',bulk_update)
                if bulk_update:
                    dynamic_bulk_update(model=Notification, items_field_update=['validated', 'Validator_obj','updated_on_node'], items=bulk_update)
                    if to_queue:
                        ...
                        # for chainId, objs in to_queue.items():
                        #     if chainId not in chain_list:
                        #         blockchain = Blockchain.objects.filter(id=chainId).first()
                        #         if blockchain:
                        #             chain_list[chainId] = blockchain
                        #     if chainId in chain_list:
                        #         chain_list[chainId].add_item_to_queue(objs)
                    to_queue.clear()

            transIdens = [i for i in synced_idens if i.startswith(get_model_prefix('Transaction'))]
            prnt('vals step4a',len(transIdens))
            transactions = Transaction.objects.filter(id__in=transIdens).exclude(validated=True)
            for t in transactions:
                t.assess_validation()
            transactions = None

            chains = {}
            prnt('vals step6a')
            for m in script_created_modifiable_models:
                mIdens = [u for u in synced_idens if u.startswith(get_model_prefix(m))]
                if mIdens:
                    objs = get_dynamic_model(m, list=True, id__in=mIdens)
                    for o in objs:
                        chain, o, secondChain = find_or_create_chain_from_object(o)
                        if chain:
                            if chain not in chains:
                                chains[chain] = []
                            chains[chain].append(o)
                    objs = None
            prnt('vals step7a')
            if chains:
                for chain in chains:
                    chain.add_item_to_queue(chains[chain])
            val_block = None
            node_data = None
            for v in validators:
                prntDebug('v2',v)
                if v.validatorType == 'Block' and check_consensus:
                    # for key in v.data:
                    try:
                        if not val_block or v.jobId.startswith(get_model_prefix('Block')) and val_block.id != v.jobId:
                            val_block = Block.objects.filter(id=v.jobId).first()
                        prnt('val_block',val_block)
                        if val_block:
                            if v.id not in val_block.validations:
                                val_block.validations[v.id] = get_commit_data(v)
                                val_block.save()
                            if not val_block.validated and len(val_block.validations) >= val_block.get_required_validator_count() or not val_block.validated and val_block.networkChain == _OperationsChain_genesisId:
                                prev_block = Block.objects.filter(networkChain=val_block.networkChain, hash=val_block.prv_hash, validated=True).first()
                                if not prev_block:
                                    latest_block = val_block.Blockchain_obj.get_last_block(is_validated=True, do_not_return_self=True)
                                    if latest_block:
                                        start = latest_block.index + 1
                                    else:
                                        start = val_block.prv_hash
                                if not downstream_worker or testing():
                                    if not prev_block and val_block.index > 1:
                                        retrieve_missing_blocks(blockchain=val_block.Blockchain_obj, starting_point=start, items_to_get=2, downstream_worker=downstream_worker)
                                    check_validation_consensus(val_block, block_id=val_block.id, downstream_worker=downstream_worker, get_missing_blocks=get_missing_blocks)
                                else:
                                    queue = django_rq.get_queue('high')
                                    if not prev_block and val_block.index > 1:
                                        if not exists_in_worker('retrieve_missing_blocks', blockchain=val_block.Blockchain_obj, starting_point=start):
                                            queue.enqueue(retrieve_missing_blocks, blockchain=val_block.Blockchain_obj, starting_point=start, items_to_get=2, job_timeout=300, result_ttl=7200)
                                    if not exists_in_worker('check_validation_consensus', block_id=val_block.id):
                                        queue.enqueue(check_validation_consensus, val_block, block_id=val_block.id, broadcast_if_unknown=False, get_missing_blocks=get_missing_blocks, job_timeout=420, result_ttl=7200)
                            elif val_block.validated and not v.Block_obj:
                                if v.id in val_block.extraData and check_commit_data(v, val_block.extraData[v.id]) or v.id in val_block.data and check_commit_data(v, val_block.data[v.id]):
                                    prnt('adding val_block to val:',v.id,val_block)
                                    Validator.objects.filter(id=v.id).update(Block_obj=val_block)

                            if val_block.validated:
                                if 'unsupported_chain' in val_block.notes or 'problem_idens' in val_block.notes or 'found_idens' not in val_block.notes:
                                    try:
                                        if not node_data:
                                            operatorData = get_operatorData()
                                            node_data = operatorData['myNodes'][operatorData['local_nodeId']] # use operator_data instead of self_node to allow sync by node software while node is deactivated
                                            operatorData.clear()
                                        if 'chainData' in node_data['meta'] and 'supported' in node_data['meta']['chainData'] and node_data['meta']['chainData']['supported'] != '':
                                            if val_block.Blockchain_obj.genesisId in node_data['meta']['chainData']['supported'] or val_block.Blockchain_obj.genesisType in node_data['meta']['chainData']['supported']:
                                                if val_block.Blockchain_obj.genesisId != _OperationsChain_genesisId:
                                                    retrieve_missing=False
                                                    operatorData = get_operatorData()
                                                    node_data = operatorData['myNodes'][operatorData['local_nodeId']]
                                                    if 'do_sync_block_content' in node_data['meta']:
                                                        retrieve_missing = True
                                                    check_block_contents(val_block, retrieve_missing=retrieve_missing, update_items=True, log_missing=True, downstream_worker=downstream_worker)
                                    except Exception as e:
                                        prnt('err 5617', str(e))
                    except Exception as e:
                        prnt('***ERROR*** 4433',str(e))

            validators.clear()
        if userVotes: # not used
            prnt('userVotes...')
            postIds = []
            for v in userVotes:
                if v.postId not in postIds:
                    postIds.append(v.postId)
            posts = Post.objects.filter(id__in=postIds)
            for p in posts:
                scoreMe(p)
        if log:
            log.completed()
    except Exception as e:
        prnt('fail process data 9374',str(e))
        if log:
            log.completed(str(e))
    prnt('done process received data databaseUpdated',databaseUpdated)
    if return_updated_objs or return_updated_ids:
        return updated_objs
    elif return_updated_count:
        return updated_count
    return databaseUpdated            
            
def process_data_packet(received_json):
    prnt('--process_data_packet')
    from network.models import DataPacket, Block, Blockchain, Node, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay, get_node_assignment

    if e_brake(2):
        return 
    result = process_received_dp(received_json, 'process_data_packet')
    prnt('reslut:',str(result)[:1000])
    if result and 'dp' in result:
        dp = result['dp']
        received_json = result['data']
        if 'senderId' in received_json:
            node = Node.objects.filter(id=received_json['senderId']).first()
        elif 'headers' in received_json and 'Senderid' in received_json['headers']:
            node = Node.objects.filter(id=received_json['headers']['Senderid']).first()
        else:
            node = None
        if node:
            node.accessed()
        
    elif result and 'data' in result:
        received_json = result['data']
        dp = None
    else:
        received_json = []
        dp = None

    if dp and isinstance(dp, models.Model):
        if 'completed' in dp.func:
            prnt('previously completed')
            return 'previously completed'

    if 'opBlock_id' in received_json:
        prnt('opBlock_id1')
        opBlock = Block.objects.filter(id=received_json['opBlock_id']).first()
        prnt('opBlock_id2',opBlock)
        if not opBlock:
            prnt('opBlock_id3')
            create_job(retrieve_missing_blocks, job_timeout=200, worker='high', genesisId=_OperationsChain_genesisId, target_node=received_json['senderId'], starting_point=received_json['opBlock_id'])
        elif not opBlock.validated or opBlock.hash != received_json['opBlock_hash'] and opBlock.validated:
            prnt('opBlock_id4')
            create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=received_json['senderId'])
        elif 'opBlock_not_latest' in received_json:
            prnt('opBlock_id5')
            pass
        elif opBlock and opBlock.index != opBlock.Blockchain_obj.chain_length:
            prnt('opBlock_id6')
            sent_dt = string_to_dt(received_json['dt'])
            latest_opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=sent_dt, validated=True).order_by('-index', 'created').first()
            prnt('opBlock_id7 latest_opBlock',latest_opBlock)
            if latest_opBlock and latest_opBlock != opBlock:
                prnt('opBlock_id8')
                create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=latest_opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=received_json['senderId'])
    else:
        prnt('opBlock not included')
    
    updated = False
    prnt('next1')
    if 'type' in received_json and received_json['type'] == 'DataPacket':
        sender_node = Node.objects.filter(id=received_json['senderId']).first()
        if sender_node == get_self_node():
            if dp:
                dp.completed()
        else:
            if dp:
                updated = process_received_data(dp, return_updated_count=True, skip_log_check=True)
            else:
                updated = process_received_data(received_json, return_updated_count=True, skip_log_check=True)
        prnt('done process datapacket, updated:',updated)

def rebroadcast_dp(dp_id, override_completed=False):
    prnt('-rebroadcast_dp',dp_id)
    if e_brake(2):
        return 
    
    from network.models import Node, DataPacket, universalChains
    dp = DataPacket.objects.filter(id=dp_id).first()

    if ('completed' in dp.func or 'chunked' in dp.func) and not override_completed:
        prnt('dp.func',dp.func)
        return

    queue = django_rq.get_queue("main")
    if not exists_in_worker('process_data_packet', queue=queue, id=dp_id):
        prnt('add to main worker')
        queue.enqueue(process_data_packet, dp_id, job_timeout=240, result_ttl=3600)

    if dp.rebroadcast_dt and dp.rebroadcast_dt > now_utc() - datetime.timedelta(hours=2):
        prnt('already broadcast')
        return

    if dp.headers['Senderid'] != get_operator_obj('self_nodeId'):
        if 'chainId' not in dp.headers or dp.headers['chainId'] != get_operator_obj('self_nodeId'):
            result = process_received_dp(dp, 'process_data_packet', override_completed=True)
            prnt('reslut:',str(result)[:1000])
            if result and 'dp' in result:
                received_json = result['data']
            elif result and 'data' in result:
                received_json = result['data']
            else:
                received_json = []
            if received_json:


                from utils.locked import get_broadcast_list
                if 'Seedid' in dp.headers and dp.headers['Seedid'] != get_operator_obj('self_nodeId'):
                    prnt('dp.headers',dp.headers)
                    include_relays = False
                    if 'chainId' in dp.headers and dp.headers['chainId'] in universalChains:
                        include_relays = True
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], all_nodes=True, dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Chainid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays)
                    downstream_broadcast(broadcast_list, 'network/receive_data_packet', received_json, headers=dp.headers, skip_self=True)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()

                else: # shouldnt ever be used
                    prnt('rebroadcast_dp_Packet-Id',dp.headers['Packet-Id'])
                    # broadcast_list = get_broadcast_list(packet_id, dt=now, region_id=self.chainId, seed_nodes=[self_node_id])
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Chainid'], seed_nodes=[dp.headers['Senderid']])
                    downstream_broadcast(broadcast_list, 'network/receive_data_packet', received_json, headers=dp.headers, exclude=[dp.headers['Senderid']], skip_self=True)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()

def rebroadcast_block(dp_id):
    prnt('-rebroadcast_block',dp_id)
    if e_brake(2):
        return 
    
    from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, universalChains
    dp = DataPacket.objects.filter(id=dp_id).first()

    if 'completed' in dp.func or 'chunked' in dp.func:
        prnt('dp.func',dp.func)
        return
        
    def process_blocks(dp):
        prnt('-process_blocks',dp.headers['Index'])
        if dp.headers.get("Genesisid") == _OperationsChain_genesisId:
            queue = django_rq.get_queue('high')
            worker = 'high'
        else:
            queue = django_rq.get_queue('main')
            worker = 'main'
        if not exists_in_worker('process_received_blocks', queue=queue, id=dp.id):
            prnt(f'add worker job {worker}')
            queue.enqueue(process_received_blocks, dp.id, job_timeout=500, result_ttl=3600)
            
    if dp.rebroadcast_dt and dp.rebroadcast_dt > now_utc() - datetime.timedelta(hours=2):
        prnt('already broadcast')
        process_blocks(dp)
        return
    
    if 'Rebroadcast' in dp.headers and str(dp.headers['Rebroadcast']) == 'True':
        broadcast_list = {}
        from utils.locked import get_broadcast_list, get_relevant_nodes_from_block, get_node_assignment
        prnt("dp.headers",dp.headers)
        prnt('Rebroadcast...')

        result = process_received_dp(dp, 'process_blocks', override_completed=True)
        if result and 'dp' in result:
            prnt('dp in result')
            received_json = dp.data
        elif result and 'data' in result:
            prnt('data in result')
            received_json = result['data']
            # dp = None
        else:
            prnt('no dp or data in result')
            received_json = []
            # dp = None
        if received_json:
            prnt('received_json')
            if dp.headers['Genesisid'] == _OperationsChain_genesisId:
                # check if already received latest opBlock, if so, consult get_node_assignment and keep lowest on list. rebroadcast lowest block on current packet_id
                current_blocks = Block.objects.filter(networkChain=dp.headers['Blockchainid'], index=int(dp.headers['Index'])).exclude(validated=False).defer('data','extraData','notes')
                prnt('current_blocksxxx',current_blocks)
                if current_blocks:
                    prnt('block.CreatorNode_obj.id,',[block.CreatorNode_obj.id for block in current_blocks])
                
                if string_to_dt(dp.headers['Blockdt']) > now_utc():
                    is_good = False
                    prev_block = Block.objects.filter(networkChain=dp.headers['Blockchainid'], hash=dp.headers['Prevhash'], validated=True).values('id').first()
                    latest_block = Block.objects.filter(networkChain=dp.headers['Blockchainid'], validated=True).values('id').order_by('-index').first()
                    prnt('prev_block x',prev_block)
                    if prev_block and latest_block:
                        if prev_block['id'] == latest_block['id']:
                            is_good = True
                    if not is_good:
                        if 'hash_history' in received_json:
                            prnt("received_json['hash_history']",len(received_json['hash_history']))
                            hash_list = received_json['hash_history'].copy()

                            prnt('hash_list len:',len(hash_list))
                            local_hash_history = [i['hash'] for i in Block.objects.filter(Blockchain_obj=dp.headers['Blockchainid'], hash__in=hash_list).exclude(validated=False).values('hash')]
                            prnt('local_hash_history len:',len(local_hash_history))
                            missing_hashes = [i for i in hash_list if i not in local_hash_history]
                            prnt('missing_hashes hashes',missing_hashes)
                            if missing_hashes:
                                if not retrieve_missing_blocks(genesisId=dp.headers['Genesisid'], target_node=dp.headers['Packet-Creator'], starting_point=missing_hashes[0], items_to_get=len(missing_hashes)):
                                    prnt('failed to retrieve prior blocks 9434',missing_hashes)
                                    note = 'missing_prior_blocks1'
                                    for block in current_blocks:
                                        block.is_not_valid(note=note, mark_strike=False)
                                        creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                                        if get_operator_obj('self_nodeId') in validator_list:
                                            from utils.locked import validate_block
                                            is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
                                    if dp:
                                        dp.completed(note)
                                    return False


                prnt("dp.headers['Seedid']",dp.headers['Seedid'])
                if current_blocks and 'Seedid' in dp.headers and any(block.CreatorNode_obj.id != dp.headers['Seedid'] for block in current_blocks):
                    prnt('pz1')
                    new_block = None
                    for block in current_blocks:
                        block_dt = block.DateTime
                        opBlock_data = get_relevant_nodes_from_block(dt=(block.DateTime-datetime.timedelta(minutes=20)), genesisId=block.Blockchain_obj.genesisId, include_relays=True)
                        creator_nodes, validator_nodes = get_node_assignment(block, opBlock_data=opBlock_data, full_creator_list=True)
                        prnt('creator_nodes',creator_nodes)
                        new_index = 1
                        current_index = 0
                        try:
                            new_index = creator_nodes.index(dp.headers['Seedid'])
                            current_index = creator_nodes.index(block.CreatorNode_obj.id)
                        except Exception as e:
                            prnt('err xa',str(e))
                            if block.CreatorNode_obj.id in creator_nodes and dp.headers['Seedid'] not in creator_nodes:
                                new_index = 1
                                current_index = 0
                            elif dp.headers['Seedid'] in creator_nodes and block.CreatorNode_obj.id not in creator_nodes:
                                new_index = 0
                                current_index = 1
                            elif dp.headers['Seedid'] not in creator_nodes and block.CreatorNode_obj.id not in creator_nodes:
                                node = Node.objects.filter(id=dp.headers['Seedid'], expelled_dt=None).first()
                                if node and node.activated_dt < block.CreatorNode_obj.activated_dt:
                                    new_index = 0
                                    current_index = 1
                                else:
                                    new_index = 1
                                    current_index = 0
                            prnt('current_index',current_index)
                            prnt('new_index',new_index)
                        if new_index < current_index:
                            prnt('replace current block')
                            # keep new block, delete current
                            block.delete()
                            if not new_block:
                                if 'block_list' in received_json:
                                    block_list = decompress_data(received_json['block_list'])
                                    try:
                                        block_list = json.loads(block_list)
                                    except:
                                        pass
                                    for b in block_list:
                                        try:
                                            block_dict = json.loads(b['block_dict'])
                                        except:
                                            block_dict = b['block_dict']
                                        if block_dict['id'] in dp.headers['Blockid']:
                                            blockchain = Blockchain.objects.filter(genesisId=dp.headers['Genesisid']).first()
                                            new_block = blockchain.create_block(block_dict=block_dict)
                            
                            broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], include_relays=True, peer_count=10, loop=False, all_nodes=True)
                            received_data = received_json.copy()
                            headers = dp.headers
                            # del received_data['headers']
                        elif current_index < new_index:
                            prnt('keep current block')
                            # keep current block
                            competing_dp = DataPacket.objects.filter(Node_obj__id=block.CreatorNode_obj.id, func__contains=f"received_blocks:{block.id}").first()
                            result = process_received_dp(competing_dp, 'process_blocks', override_completed=True, skip_log_check=True)
                            if result and 'dp' in result:
                                prnt('rebroadcast')
                                log = result['dp']
                                received_data = log.data.copy()
                                headers = dp.headers
                                broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], include_relays=True, peer_count=10, loop=False, all_nodes=True)
                                # del received_data['headers']
                            else:
                                prnt('no dp')
                                if dp:
                                    dp.completed('received_blocks_non_winner2')
                                return False
                            received_json = {}
                        
                    if not block or now_utc() < (string_to_dt(block_dt) - datetime.timedelta(minutes=10)):
                        prnt('wait to process block')
                        received_json = {} # do not begin validations until 10 minutes from block.DateTime
                    else:
                        process_blocks(dp)
                    if dp.headers['Seedid'] != get_operator_obj('self_nodeId'):
                        downstream_broadcast(broadcast_list, 'network/receive_blocks', received_data, headers=headers, skip_self=True)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()
                elif 'Seedid' in dp.headers:
                    prnt('pz2')
                    received_data = received_json.copy()
                    headers = dp.headers
                    include_relays = False
                    if 'Genesisid' in headers and headers['Genesisid'] in universalChains:
                        include_relays = True
                    if 'Validators-Only' in dp.headers and dp.headers['Validators-Only'] == 'True':
                        prnt('validators only')
                        broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], loop=True, all_nodes=False, dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays)
                    else:
                        prnt('not validators only')
                        broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays, peer_count=10, loop=False, all_nodes=True)
                    # del received_data['headers']
                    
                    prnt('now_utc() < (block.DateTime + datetime.timedelta(minutes=1))')
                    prnt(now_utc())
                    if current_blocks:
                        prnt((current_blocks[0].DateTime + datetime.timedelta(minutes=1)))
                    if current_blocks and now_utc() < (current_blocks[0].DateTime - datetime.timedelta(minutes=10)):
                        prnt('pz3')
                        received_json = {} # do not begin validations until 10 minutes from block.DateTime
                    else:
                        process_blocks(dp)
                    downstream_broadcast(broadcast_list, 'network/receive_blocks', received_data, headers=headers)
                    dp.rebroadcast_dt = now_utc()
                    dp.save()
                    prnt('blockblocks,',current_blocks)
            elif 'Seedid' in dp.headers and dp.headers['Seedid'] != get_operator_obj('self_nodeId'):
                process_blocks(dp)
                include_relays = False
                if 'Genesisid' in dp.headers and dp.headers['Genesisid'] in universalChains:
                    include_relays = True
                prnt('dp.headers',dp.headers)
                if 'Validators-Only' in dp.headers and dp.headers['Validators-Only'] == 'True':
                    prnt('validators only')
                    opBlock_data = get_relevant_nodes_from_block(dt=string_to_dt(dp.headers['Dt']), blockchain=dp.headers['Blockchainid'], strings_only=True, first_block_override=True)

                    creator_nodes, validator_list = get_node_assignment(func=dp.headers['Packet-Id'],dt=string_to_dt(dp.headers['Dt']), chainId=dp.headers['Blockchainid'], opBlock_data=opBlock_data)
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], relevant_nodes=validator_list, loop=True, all_nodes=False, dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays, opBlock_data=opBlock_data)
                else:
                    prnt('not validators only')
                    broadcast_list = get_broadcast_list(dp.headers['Packet-Id'], dt=string_to_dt(dp.headers['Dt']), region_id=dp.headers['Blockchainid'], seed_nodes=[dp.headers['Seedid']], include_relays=include_relays)
                downstream_broadcast(broadcast_list, 'network/receive_blocks', received_json, headers=dp.headers, skip_self=True)
                dp.rebroadcast_dt = now_utc()
                dp.save()
            else:
                prnt('else1')
                process_blocks(dp)
    else:
        prnt('else2')
        process_blocks(dp)




def process_received_blocks(received_json, get_missing_blocks=True, resend_missing_blocks=True, return_result=False, force_check=False, rebroadcast=True, downstream_worker=True, override_completed=False):
    prntn('--process_received_blocks now_utc:',now_utc())
    from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay, universalChains
    from utils.locked import get_broadcast_list, check_validation_consensus, get_relevant_nodes_from_block, get_node_assignment, hash_obj_id, get_signing_data
    prnt()
    if e_brake(2):
        return 
    
    result = process_received_dp(received_json, 'process_blocks', override_completed=override_completed)
    if result and 'dp' in result:
        prnt('x1')
        log = result['dp']
        received_json = result['data']
        if 'senderId' in received_json:
            node = Node.objects.filter(id=received_json['senderId']).first()
        elif 'headers' in received_json and 'Senderid' in received_json['headers']:
            node = Node.objects.filter(id=received_json['headers']['Senderid']).first()
        else:
            node = None
        if node:
            node.accessed()
    elif result and 'data' in result:
        prnt('x2')
        received_json = result['data']
        log = None
    else:
        prnt('x3')
        received_json = []
        log = None
    completed = False
    prntn('received_json snippet:',str(received_json)[:4000])
    if not received_json or 'genesisId' not in received_json:
        if log:
            log.completed('no_data')
        return completed

    if 'headers'in received_json and 'Packet-Creator' in received_json['headers']:
        if received_json['headers']['Packet-Creator'] == get_operator_obj('self_nodeId') and Node.objects.filter(activeNode=True).count() > 1:
            if log:
                log.completed('self_seeded')
            return completed
    packet_creator = None
    if 'headers'in received_json and 'Packet-Creator' in received_json['headers']:
        packet_creator = received_json['headers']['Packet-Creator']
    sender_node = received_json['senderId']
    if 'opBlock' in received_json and received_json['opBlock']:
        if 'opBlock_hash' in received_json:
            opBlock = Block.objects.filter(hash=received_json['opBlock_hash']).first()
        else:
            opBlock = Block.objects.filter(id=received_json['opBlock']).first()
        prnt('opBlock??',opBlock)
        if not opBlock:
            retrieve_missing_blocks(genesisId=_OperationsChain_genesisId, target_node=packet_creator if packet_creator else sender_node, starting_point=received_json['opBlock'])
            opBlock = Block.objects.filter(id=received_json['opBlock']).first()
            if not opBlock:
                if log:
                    log.completed('missing_opBlock')
                return completed
        elif not opBlock.validated and opBlock.hash == received_json['opBlock_hash']:
            block_is_valid, consensus_found, validations = check_validation_consensus(opBlock, block_id=opBlock.id, backcheck=force_check, get_missing_blocks=True)
            if not block_is_valid and consensus_found and resend_missing_blocks:
                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=packet_creator if packet_creator else sender_node)
        elif not opBlock.validated or opBlock.hash != received_json['opBlock_hash'] and opBlock.validated:
            if resend_missing_blocks:
                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=packet_creator if packet_creator else sender_node)
        elif 'opBlock_not_latest' in received_json:
            pass
        elif opBlock and opBlock.index != opBlock.Blockchain_obj.chain_length:
            sent_dt = string_to_dt(received_json['dt'])
            latest_opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=sent_dt, validated=True).order_by('-index', 'created').first()
            if latest_opBlock and latest_opBlock != opBlock and resend_missing_blocks:
                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=latest_opBlock.Blockchain_obj, starting_index=opBlock.index, send_to=packet_creator if packet_creator else sender_node)
    else:
        prnt('opBlock not included')

    if 'headers' in received_json and 'Genesisid' in received_json['headers']:
        blockchain = Blockchain.objects.filter(genesisId=received_json['headers']['Genesisid']).defer('queuedData').first()
        prntDebug('blockchain',blockchain)
    elif 'blockchainId' in received_json:
        blockchain = Blockchain.objects.filter(id=received_json['blockchainId']).defer('queuedData').first()
        prntDebug('blockchain',blockchain)

    if 'force_check' in received_json:
        force_check = received_json['force_check']
    blocks = {}
    if 'block_list' in received_json:
        block_list = decompress_data(received_json['block_list'])
        try:
            block_list = json.loads(block_list)
        except:
            pass
        for b in block_list:
            try:
                block_dict = json.loads(b['block_dict'])
            except:
                block_dict = b['block_dict']
            blocks[block_dict['index']] = b
    elif 'block_dict' in received_json:
        blocks[received_json['block_dict']['index']] = received_json
    prnt('number of blocks',len(blocks))

    from utils.locked import calculate_reward, verify_obj_to_data, convert_to_dict
    from accounts.models import UserPubKey
    from network.models import Validator, _OperationsChain_genesisId
    import operator
    for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
        try:
            new_block_dict = json.loads(b['block_dict'])
        except:
            new_block_dict = b['block_dict']
        prnt('process:',new_block_dict['index'],new_block_dict['id'])

    try:
        prnt('process block into database')
        added_blocks = []
        received_hashes = []
        full_nodeData = None
        for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
            try:
                new_block_dict = json.loads(b['block_dict'])
            except:
                new_block_dict = b['block_dict']
            if verify_obj_to_data(Block(), new_block_dict):
                prntDebugn('new_block',new_block_dict['id'])
                block_transaction = b['block_transaction']
                prntDebug('block_transaction',block_transaction)
                try:
                    block_transaction = json.loads(block_transaction)
                except:
                    pass
                if new_block_dict['networkChain'] == _OperationsChain_genesisId:
                    specific_data = {'objType':'Block','networkChain':new_block_dict['networkChain'],'DateTime':new_block_dict['DateTime'],'CreatorNode_obj':new_block_dict['CreatorNode_obj']}
                else:
                    specific_data = {'objType':'Block','networkChain':new_block_dict['networkChain'],'DateTime':new_block_dict['DateTime']}
                if True:
                    if 'opBlockId' in new_block_dict and not value_is_none(new_block_dict['opBlockId']):
                        opBlock = Block.objects.filter(id=new_block_dict['opBlockId']).exists()
                        if not opBlock:
                            updated_objs = request_items([new_block_dict['opBlockId']], return_updated_objs=True, downstream_worker=False, get_missing_blocks=get_missing_blocks, override_completed=get_missing_blocks)
                    transaction_signature_verified = False
                    if not block_transaction:
                        prntDebug('no reward')
                        proceed_to_check_consensus = True
                        transaction = None
                    else:
                        prntDebug('process reward')
                        proceed_to_check_consensus = False
                        if block_transaction['token_value'] == calculate_reward(block_transaction['created']):
                            sig_data = get_sigData(block_transaction, first_key=True)
                            pkey = sig_data['pk']
                            if is_id(pkey):
                                iden = pkey
                            else:
                                iden = hash_upk_id(pkey)
                            upk = UserPubKey.objects.filter(id=iden, keyType='node').only('publicKey','end_life_dt').first()
                            if upk:
                                transaction_signature_verified = upk.verify(get_signing_data(block_transaction), sig_data['sig'], publicKey=block_transaction['signed'])
                            prntDebug('transaction_signature_verified',transaction_signature_verified)
                            if transaction_signature_verified:
                                transaction = get_or_create_model('Transaction', id=block_transaction['id'])
                                transaction, sigs, proceed_to_check_consensus, transaction_updatedDB = sync_model(transaction, block_transaction, get_missing_blocks=get_missing_blocks)
                                
                    prnt('proceed_to_check_consensus',proceed_to_check_consensus)
                    if proceed_to_check_consensus:
                        block = Block.objects.filter(hash=new_block_dict['hash']).defer('data','extraData').first()
                        if not block or block.signed != new_block_dict['signed']:
                            block = blockchain.create_block(block_dict=b, dummy_block=block)
                        prnt('transactionx',transaction)
                        if block and block.signed:
                            prnt('block.Transaction_obj',block.Transaction_obj)
                            if transaction and transaction_signature_verified and transaction == block.Transaction_obj:
                                prnt('py1')
                                if block.id == transaction.senderBlockId:
                                    prnt('py2a')
                                    if transaction.SenderBlock_obj != block:
                                        prnt('py2b')
                                        transaction.SenderBlock_obj = block
                                        transaction.save()
                                elif transaction.ReceiverBlock_obj != block:
                                    prnt('py3')
                                    transaction.ReceiverBlock_obj = block
                                    transaction.save()
                            prnt('py4')
                            received_hashes.append(block.hash)
                            added_blocks.append(b)
                            if b['validations']:
                                if isinstance(b['validations'], str):
                                    vals_dict = json.loads(b['validations'])
                                else:
                                    vals_dict = b['validations']
                                val_ids = [v['id'] for v in vals_dict if v['objType'] == 'Validator' and v['jobId'] == new_block_dict['id']]
                                prnt('CHECK VALIDATIONS HERE3',val_ids)
                                current_vals = Validator.objects.filter(id__in=val_ids).exclude(signed={}).values('id')
                                prnt('current_vals G',len(current_vals),len(val_ids))
                                if len(current_vals) < len(val_ids):
                                    process_received_data([v for v in vals_dict if v['id'] in val_ids+[i['id'] for i in current_vals]], check_consensus=False, get_missing_blocks=get_missing_blocks)
                
        if 'hash_history' in received_json:
            prnt("received_json['hash_history']",len(received_json['hash_history']))
            hash_list = received_json['hash_history'].copy()

            prnt('hash_list len:',len(hash_list))
            local_hash_history = [i['hash'] for i in Block.objects.filter(Blockchain_obj=blockchain, hash__in=hash_list).exclude(validated=False).values('hash')]
            prnt('local_hash_history len:',len(local_hash_history))
            missing_hashes = [i for i in hash_list if i not in local_hash_history and i not in received_hashes]
            prnt('missing_hashes hashes',missing_hashes)
            if missing_hashes:
                if not retrieve_missing_blocks(genesisId=blockchain.genesisId, target_node=packet_creator if packet_creator else sender_node, starting_point=missing_hashes[0], items_to_get=len(missing_hashes), downstream_worker=downstream_worker):
                    prnt('failed to retrieve prior blocks 9432',missing_hashes)
                    note = 'missing_prior_blocks2'
                    block.is_not_valid(note=note, mark_strike=False)
                    creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                    if get_operator_obj('self_nodeId') in validator_list:
                        from utils.locked import validate_block
                        is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
                    if log:
                        log.completed(note)
                    return False
                
        prnt('check block validity')
        block_num = 0
        for b in added_blocks:
            prnt('b:',b)
            block_num += 1
            if block_num < len(added_blocks) or downstream_worker == False:
                downstream_worker = False
            else:
                downstream_worker = True
            completed = False
            try:
                new_block_dict = json.loads(b['block_dict'])
            except:
                new_block_dict = b['block_dict']
            block_transaction = b['block_transaction']
            prntDebug('block_transaction',block_transaction)
            try:
                block_transaction = json.loads(block_transaction)
            except:
                pass
            block = Block.objects.filter(id=new_block_dict['id']).defer('data','extraData').first()
            if block and block.validated != None and 'block_is_valid' in b and b['block_is_valid'] != block.validated: # block.validation result does not match received block.validation
                prnt('block recheck: received.is_valid:',block.id,b['block_is_valid'],'block.validated:',block.validated)
                if b['validations']:
                    vals = [v['id'] for v in b['validations'] if v['objType'] == 'Validator' and v['jobId'] == block.id]
                    prnt('CHECK VALIDATIONS HERE3',vals)
                    current_vals = Validator.objects.filter(id__in=vals).exclude(signed={}).count()
                    prnt('current_vals B',current_vals,len(vals))
                    if current_vals < len(vals):
                        process_received_data(vals, check_consensus=False, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)
                    block_is_valid, consensus_found, validations = check_validation_consensus(block, block_id=block.id, backcheck=True, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)
            elif block and block.validated != None and not force_check:
                prnt('block already processed and validated',block.id)
                if b['validations']:
                    if isinstance(b['validations'], str):
                        vals_dict = json.loads(b['validations'])
                    else:
                        vals_dict = b['validations']
                    val_ids = [v['id'] for v in vals_dict if v['objType'] == 'Validator' and v['jobId'] == new_block_dict['id']]
                    prnt('CHECK VALIDATIONS HERE',val_ids)
                    current_vals = Validator.objects.filter(id__in=val_ids).exclude(signed={}).values('id')
                    prnt('current_vals C',len(current_vals),len(val_ids))
                    if len(current_vals) < len(val_ids):
                        process_received_data([v for v in vals_dict if v['id'] in val_ids+[i['id'] for i in current_vals]], check_consensus=True, get_missing_blocks=get_missing_blocks)

            else:
                prnt('block not validated or force check:',new_block_dict['id'],block,force_check) # force_check if datapacket is send_missing_block or self_node ran block retrieval
                
                signature_verified = False
                if b['validations']:
                    if isinstance(b['validations'], str):
                        vals_dict = json.loads(b['validations'])
                    else:
                        vals_dict = b['validations']
                    val_ids = [v['id'] for v in vals_dict if v['objType'] == 'Validator' and v['jobId'] == new_block_dict['id']]
                    prnt('CHECK VALIDATIONS HERE2',val_ids)
                    current_vals = Validator.objects.filter(id__in=val_ids).exclude(signed={}).values('id')
                    prnt('current_vals C',len(current_vals),len(val_ids))
                    if len(current_vals) < len(val_ids):
                        process_received_data([v for v in vals_dict if v['id'] in val_ids+[i['id'] for i in current_vals]], check_consensus=False, get_missing_blocks=get_missing_blocks)
                        signature_verified = True
                        
                def handle_competitions(competing_blocks):
                    winning_block, validations = resolve_block_differences(block, competing_blocks=competing_blocks)
                    prnt('winning_blockxxw',convert_to_dict(winning_block))
                    prnt('blockxxw',convert_to_dict(block))
                    if winning_block and not winning_block.validated:
                        block_is_valid, consensus_found, validations = check_validation_consensus(winning_block, block_id=winning_block.id, backcheck=force_check, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)

                    if winning_block and winning_block.hash == block.hash:
                        prnt('pd continue')
                        return True
                    else:
                        prnt('pd1')
                        if winning_block and resend_missing_blocks:
                            prnt('pd3')
                            create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, missing_blocks=[winning_block], send_to=packet_creator if packet_creator else sender_node)
                        if winning_block and winning_block.hash != block.hash and block.validated != False :
                            note = f'lost_competition1_{winning_block.id}'
                            block.is_not_valid(note=note, mark_strike=False)
                            prntDebug(f'invalidatey1:',block.id)
                            creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                            if get_operator_obj('self_nodeId') in validator_list:
                                from utils.locked import validate_block
                                is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
                        return False
                
                if block:
                    prnt('new_block_dict',new_block_dict)
                    prev_block = Block.objects.filter(networkChain=new_block_dict['networkChain'], hash=new_block_dict['prv_hash'], validated=True).defer('data','extraData').first()
                    latest_block = blockchain.get_last_block(is_validated=True, do_not_return_self=True)
                    prnt('prev_block x',prev_block)
                    if prev_block and prev_block.index+1 == int(new_block_dict['index']) or int(new_block_dict['index']) == 1 and new_block_dict['prv_hash'] == '0000000': # if block has expected index or is first on chain
                        competing_blocks = Block.objects.filter(networkChain=new_block_dict['networkChain'], prv_hash=new_block_dict['prv_hash']).exclude(validated=False).exclude(hash=new_block_dict['hash']).defer('data','extraData')
                        
                        if competing_blocks:
                            block_is_winner = handle_competitions(competing_blocks)
                            if not block_is_winner:
                                prnt('ret 3')
                                if log:
                                    log.completed('received_blocks_non_winner')
                                return False
                                
                        elif latest_block and prev_block:
                            if prev_block.hash == latest_block.hash or prev_block.hash == latest_block.prv_hash:
                                signature_verified = True
                        elif int(new_block_dict['index']) == 1 and not latest_block and not prev_block:
                            signature_verified = True

                    else:
                        prnt('Block index not as expected')
                        if not prev_block:
                            block_is_winner = block.validated
                            if not block_is_winner:
                                competing_blocks = Block.objects.filter(networkChain=new_block_dict['networkChain'], prv_hash=new_block_dict['prv_hash']).exclude(hash=new_block_dict['hash']).defer('data','extraData')      
                                if competing_blocks:
                                    block_is_winner = handle_competitions(competing_blocks)
                            if not block_is_winner:
                                # missing blocks
                                prnt(f'prev_block not found11-- blockchain.chain_length:{blockchain.chain_length}, new_block_index:{new_block_dict["index"]}, get_missing_blocks:{get_missing_blocks}')
                                prnt('latest_block',latest_block, 'index',latest_block.index if latest_block else 0)
                                if not latest_block:
                                    if get_missing_blocks:
                                        if downstream_worker:
                                            create_job(retrieve_missing_blocks, job_timeout=200, worker='high', blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=blockchain.chain_length)
                                        else:
                                            retrieve_missing_blocks(blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=blockchain.chain_length, downstream_worker=downstream_worker)
                                elif latest_block.index < int(new_block_dict['index']) - 1:
                                    if get_missing_blocks:
                                        if downstream_worker:
                                            create_job(retrieve_missing_blocks, job_timeout=200, worker='high', blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=latest_block.index)
                                        else:
                                            retrieve_missing_blocks(blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=latest_block.index, downstream_worker=downstream_worker)
                                elif latest_block.index >= int(new_block_dict['index']) and resend_missing_blocks:
                                    create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=blockchain, starting_index=int(new_block_dict['index']), send_to=packet_creator if packet_creator else sender_node)
                                elif resend_missing_blocks:
                                    create_job(send_missing_blocks, job_timeout=60, worker='main', blockchain=blockchain, starting_index=int(new_block_dict['index'])-1, send_to=packet_creator if packet_creator else sender_node)
                                if log:
                                    log.completed('received_blocks_missing_prev_block')
                                return False
                        
                        elif prev_block and prev_block.index < int(new_block_dict['index']) - 1:
                            # missing blocks
                            if get_missing_blocks:
                                if downstream_worker:
                                    create_job(retrieve_missing_blocks, job_timeout=200, worker='high', blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=prev_block.hash)
                                else:
                                    retrieve_missing_blocks(blockchain=blockchain, target_node=packet_creator if packet_creator else sender_node, starting_point=prev_block.hash, downstream_worker=downstream_worker)
                            if log:
                                log.completed('received_blocks_retrieve_missing')
                            return False
                        
                        elif prev_block and prev_block.index >= int(new_block_dict['index']):
                            # sender node is missing blocks
                            if resend_missing_blocks:
                                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, starting_index=int(new_block_dict['index']), send_to=packet_creator if packet_creator else sender_node)
                            if log:
                                log.completed('received_blocks_send_missing')
                            return False
                        
                        elif prev_block and prev_block.index == int(new_block_dict['index']):
                            # block index discrepancy
                            prntDebug('sort out competeing blocks')
                            winning_block, validations = resolve_block_differences(block)
                            if not winning_block:
                                if log:
                                    log.completed('competing_block_p2')
                                return False 
                            if winning_block.hash != block.hash:
                                if resend_missing_blocks:
                                    block = winning_block
                                    create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, starting_index=int(new_block_dict['index']), send_to=packet_creator if packet_creator else sender_node)
                            else:
                                # if block:
                                signature_verified = True
                                prntDebug('signature_verified22',signature_verified)
                        else:
                            prnt('not signature_verified')    
                    
                    prnt('signature_verified',signature_verified)
                    if signature_verified:
                        block_is_valid, consensus_found, validations = check_validation_consensus(block, block_id=block.id, backcheck=force_check, get_missing_blocks=get_missing_blocks, downstream_worker=downstream_worker)
                        prntDebug('-a-a-block_is_valid',block_is_valid,'consensus_found',consensus_found,'block.id',block.id)
                        if not block_is_valid and consensus_found:
                            if resend_missing_blocks:
                                prntDebug('send_missing_blocks path 1')
                                if not send_missing_blocks(blockchain=blockchain, starting_index=block.index-1, send_to=packet_creator if packet_creator else sender_node):
                                    send_missing_blocks(blockchain=blockchain, genesisId=None, missing_blocks=[block], starting_index=block.index, send_to=packet_creator if packet_creator else sender_node, force_check=True)
                            if log:
                                log.completed('invalid')
                            return False
                        else:
                            if block_is_valid and consensus_found and block_num == len(blocks): # if last item in received list
                                next_block = Block.objects.filter(networkChain=blockchain.id, prv_hash=block.hash, validated=True).first()
                                prntDebug('next_block',next_block)  
                                if next_block:
                                    next_block_is_valid, next_block_consensus_found, validations = check_validation_consensus(next_block, block_id=next_block.id, backcheck=True, get_missing_blocks=get_missing_blocks)
                                    prntDebug('-a-a-next_block_is_valid-222',next_block_is_valid,'next_block_consensus_found',next_block_consensus_found)
                            if block_is_valid and consensus_found:
                                completed = True
                    if block_num == len(added_blocks) and get_missing_blocks:
                        if 'future_block_count' in b and b['future_block_count']:
                            if (block.index + 1) not in blocks:
                                future_blocks = Block.objects.filter(networkChain=blockchain.id, index__gt=block.index, validated=True).count()
                                # next_block = Block.objects.filter(blockchainId=blockchain.id, prv_hash=block.hash).exclude(validated=False).exists()
                                # if not next_block:
                                if future_blocks < b['future_block_count']:
                                    if downstream_worker:
                                        create_job(retrieve_missing_blocks, job_timeout=300, worker='main', blockchain=block.Blockchain_obj, starting_point=block.index + 1)
                                    else:
                                        retrieve_missing_blocks(blockchain=block.Blockchain_obj, starting_point=block.index + 1, downstream_worker=downstream_worker)
                                
    except Exception as e:
        prnt('process block fail1', str(e))
        if log:
            log.completed(fail=str(e))
        return False
    if log:
        log.completed()
    return completed


def resolve_block_differences(starting_block, competing_blocks=None, validated_blocks=True, allow_divergence_discovery=True):
    prnt('\n--resolve_block_differences', starting_block)
    from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay
    from utils.locked import get_broadcast_list, check_validation_consensus, get_relevant_nodes_from_block, get_node_assignment

    if e_brake(2):
        return 
    common_hashes_map = {}
    discover_divergence = False
    if not competing_blocks:
        qs = Block.objects.filter(networkChain=starting_block.networkChain, index=starting_block.index).exclude(id=starting_block.id)
        if validated_blocks:
            qs = qs.filter(validated=True)
        else:
            qs = qs.exclude(validated=False)
        competing_blocks = list(qs.defer('data', 'extraData').order_by('DateTime', 'created'))

    unique_hashes = {b.hash for b in competing_blocks}
    if not unique_hashes or unique_hashes == {starting_block.hash}:
        return starting_block, []
    prnt('competing_blocks',competing_blocks)

    validation_cache = {}

    def get_validation_state(block):
        prnt('-get_validation_state')
        if block.id not in validation_cache:
            is_valid, consensus_found, validations = check_validation_consensus(block, block_id=block.id, do_mark_valid=False, create_val=False, handle_discrepancies=False)
            prnt('get_validation_state', is_valid, consensus_found)
            validation_cache[block.id] = {'is_valid': is_valid, 'consensus_found': consensus_found, 'validations': [v for v in validations if v.is_valid]}
        return validation_cache[block.id]

    def invalidate_losers(winning_block, competing_blocks):
        if winning_block:
            for block in competing_blocks:
                if block.id != winning_block.id:
                    note = f'lost_resolve_bd_{winning_block.id}'
                    block.is_not_valid(note=note, mark_strike=False)
                    prntDebug(f'invalidatex2:',block.id)
                    creator_nodes, validator_list, broadcast_list = block.get_assigned_nodes(fetch_broadcast_list=False)
                    if get_operator_obj('self_nodeId') in validator_list:
                        from utils.locked import validate_block
                        is_valid, validator, is_new_validation = validate_block(block, creator_nodes=creator_nodes, fail_reason=note)
    # Precedence:
    # 1. Heuristic chain agreement
    # 2. Validator consensus
    # 3. Deterministic tie-breaks
    # 4. Timestamp
    major_candidate = None
    candidate, candidate_state = None, {}
    competing_blocks = [starting_block] + [b for b in competing_blocks]

    for block in competing_blocks:
        prnt('resolve block',block)
        if 'won_competition' in block.notes:
            if string_to_dt(block.notes['won_competition']) > now_utc() - datetime.timedelta(minutes=7):
                prnt('resolve_bd1')
                return block, get_validation_state(block)

        if candidate and block.hash == candidate.hash:
            prnt('resolve_bd2',block.id)
            continue

        state = get_validation_state(block)

        if block.DateTime > now_utc() and starting_block.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            creators, _ = get_node_assignment(block, full_creator_list=True)
            try:
                if creators.index(block.CreatorNode_obj.id) < creators.index(candidate.CreatorNode_obj.id):
                    candidate, candidate_state = block, state
                    continue
            except Exception:
                pass
            
        if not state['is_valid']:
            if state['consensus_found'] and block.validated:
                prntDebug(f'invalidatex3:',block.id)
                block.is_not_valid(note='bd_diff2', mark_strike=False)
            prnt('resolve_bd3',block.id)
            continue

        if not common_hashes_map:
            common_hashes_map, fetched_hashes = resolve_chain_fork(starting_block.networkChain, starting_hash=starting_block.prv_hash)

        if common_hashes_map:
            if block.prv_hash in common_hashes_map and block.hash in common_hashes_map[block.prv_hash]:
                if candidate and candidate.prv_hash in common_hashes_map and candidate.hash in common_hashes_map[candidate.prv_hash]:
                    prnt('resolve_bd4',block.id)
                    if common_hashes_map[block.prv_hash][block.hash] > common_hashes_map[candidate.prv_hash][candidate.hash]:
                        candidate, candidate_state = block, state
                        major_candidate = block
                        continue
                else:
                    prnt('resolve_bd5',block.id)
                    candidate, candidate_state = block, state
                    major_candidate = block
                    continue
            elif block == competing_blocks[-1]:
                if not candidate or candidate.prv_hash not in common_hashes_map or candidate.hash not in common_hashes_map[candidate.prv_hash]:
                    prnt('resolve_bd6',block.id)
                    discover_divergence = True
        
        if not major_candidate:
            if state['consensus_found'] and candidate is None or state['consensus_found'] and candidate and not candidate_state['consensus_found']:
                prnt('resolve_bd7',block.id)
                candidate, candidate_state = block, state
                continue

            if candidate and len(state['validations']) > len(candidate_state['validations']):
                prnt('resolve_bd8',block.id)
                candidate, candidate_state = block, state
                continue

            if candidate and len(state['validations']) < len(candidate_state['validations']):
                prnt('resolve_bd9',block.id)
                continue

            if candidate and string_to_dt(block.DateTime) < string_to_dt(candidate.DateTime):
                prnt('resolve_bd11',block.id)
                candidate, candidate_state = block, state
                continue

    if allow_divergence_discovery and discover_divergence:
        prnt('resolve_bd12',block.id)
        hash_map = discover_chain_divergence(starting_block.networkChain)
        fetch_blocks = []
        check_consensus = []
        for hash in hash_map:
            path_block = Block.objects.filter(networkChain=starting_block.networkChain, hash=hash).values('id','validated').first()
            if not path_block:
                fetch_blocks.append(hash)
            elif not path_block['validated']:
                check_consensus.append(path_block['id'])
        if starting_block.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            queue = django_rq.get_queue('high')
        else:
            queue = django_rq.get_queue('main')
        if fetch_blocks:
            prnt('resolve_bd13',block.id)
            if not exists_in_worker('retrieve_missing_blocks', queue_name=['main','high'], blockchain=starting_block.networkChain, starting_point=fetch_blocks, items_to_get=len(fetch_blocks)):
                queue.enqueue(retrieve_missing_blocks, blockchain=starting_block.networkChain, starting_point=fetch_blocks, items_to_get=len(fetch_blocks), job_timeout=300, result_ttl=7200)
        if check_consensus:
            prnt('resolve_bd14',block.id)
            for block in check_consensus:
                if not exists_in_worker('check_validation_consensus', queue_name=['main','high'], block_id=block.id):
                    queue.enqueue(check_validation_consensus, block, block_id=block.id, job_timeout=420, result_ttl=7200)
        if not fetch_blocks and not check_consensus:
            for block in competing_blocks:
                if state['consensus_found'] and candidate is None or state['consensus_found'] and candidate and not candidate_state['consensus_found']:
                    prnt('resolve_bd72',block.id)
                    candidate, candidate_state = block, state
                    continue

                if candidate and len(state['validations']) > len(candidate_state['validations']):
                    prnt('resolve_bd82',block.id)
                    candidate, candidate_state = block, state
                    continue

                if candidate and string_to_dt(block.DateTime) < string_to_dt(candidate.DateTime):
                    prnt('resolve_bd112',block.id)
                    candidate, candidate_state = block, state
                    continue
            if candidate:
                invalidate_losers(candidate, competing_blocks)
                prnt('resolve_bd152 Final',candidate.id)
                return candidate, candidate_state['validations']
        prnt('resolve_bd15',block.id)
        return None, {}

    winning_block = candidate
    if not winning_block:
        prnt('resolve_bd16',block.id)
        return None, {}

    winning_state = get_validation_state(winning_block)
    for block in [starting_block] + competing_blocks:
        if block.id == winning_block.id:
            prnt('resolve_bd17',block.id)
            continue

        if winning_state['consensus_found'] and block.validated is not False:
            block.is_not_valid(mark_strike=False, note=f'resolved_differences:{winning_block.id}')
        elif block.validated is True:
            block.notes['removed_validation'] = f'{dt_to_string(now_utc())}-{winning_block.id}'
            block.validated = None
            block.save(update_fields=['validated', 'notes'])

    winning_block.notes['won_competition'] = dt_to_string(now_utc())
    winning_block.save()

    invalidate_losers(winning_block, competing_blocks)
    prnt('resolve_bd Final', winning_block)
    prnt()
    return winning_block, winning_state['validations']

def retrieve_missing_blocks(blockchain=None, genesisId=None, target_node=None, starting_point=0, items_to_get=3, retrieve_following=True, downstream_worker=True):
    prntDebugn('--retrieve_missing_blocks- chainid:', blockchain,'starting_point:',starting_point)
    if e_brake(2):
        return 
    from network.models import Node, DataPacket, Block, Blockchain, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, block_time_delay
    from utils.locked import get_broadcast_list, check_validation_consensus, get_relevant_nodes_from_block, get_node_assignment, sign_for_sending, hash_obj_id
    if items_to_get < 3:
        items_to_get = 3
    if not blockchain and genesisId:
        blockchain = Blockchain.objects.filter(genesisId=genesisId).first()
    opBlock_data = get_relevant_nodes_from_block(genesisId=blockchain.genesisId)
    if target_node and not target_node in opBlock_data['relevant_nodes']:
        n = Node.objects.filter(id=target_node).defer('chain_array','Block_obj','User_obj','abilities','region_data').first()
        if n and n.activated_dt:
            opBlock_data['relevant_nodes'][target_node] = n.return_address()
        else:
            target_node = random.choice([n for n in opBlock_data['relevant_nodes']])
    elif not target_node:
        target_node = random.choice([n for n in opBlock_data['relevant_nodes']])

    value = opBlock_data['relevant_nodes'][target_node]
    opBlock_data['relevant_nodes'].pop(target_node)
    relevant_nodes = {target_node: value, **opBlock_data['relevant_nodes']}

    operatorData = get_operatorData()
    self_node = get_self_node(operatorData=operatorData)

    if not starting_point:
        starting_point = blockchain.chain_length
    elif is_id(starting_point):
        start_block = Block.objects.filter(networkChain=blockchain.id, id=starting_point, validated=True).first()
        if start_block:
            starting_point = start_block.index
    elif not isinstance(starting_point, int):
        start_block = Block.objects.filter(networkChain=blockchain.id, hash=starting_point, validated=True).first()
        if start_block:
            starting_point = start_block.index
    if isinstance(starting_point, int):
        prev_blocks = Block.objects.filter(networkChain=blockchain.id, index__lte=starting_point, index__gt=starting_point-50, validated=True).order_by('index').values('hash')
        hash_history = []
        if prev_blocks:
            hash_history = [b['hash'] for b in prev_blocks]
    else:
        hash_history = [b['hash'] for b in reversed(Block.objects.filter(networkChain=blockchain.id, validated=True).order_by('-index').values('hash')[:50])]
    prnt('starting_pointxxz',starting_point)
    signedRequest = json.dumps(sign_for_sending({'type':'Block', 'blockchainId' : blockchain.id, 'genesisId':blockchain.genesisId, 'include_content' : False, 'force_check':True, 'include_validators':True, 'item_count': items_to_get, 'hash_history':hash_history, 'index':starting_point}))
    prntn('signedRequest',signedRequest)
    sendingData = {'request':signedRequest, 'senderId':get_operator_obj('self_nodeId')}

    
    successes = 0
    for nodeId, addr in relevant_nodes.items():
        if nodeId != self_node.id:
            received_data = None
            content = sign_post_header(data=sendingData, operatorData=operatorData, self_node=self_node.id, post='post', target_node=nodeId)
            success, response = connect_to_node(addr, 'network/request_data', self_node=self_node, content=content, operatorData=operatorData)

            prnt('connect success',success)
            if success and response.status_code == 200:
                response_json = response.json()
                prntn('response_json666',str(response_json)[:3000])    
                if response_json['message'] == 'Success' and 'block_obj' in response_json:
                    block_list = json.dumps([{'block_dict' : response_json['block_obj'], 'block_transaction':response_json['transaction_obj'], 'block_data' : [], 'validations' : response_json['content']}])
                    received_data = {'type' : 'Blocks', 'blockchainId' : blockchain.id, 'genesisId':blockchain.genesisId, 'block_list' : block_list, 'force_check':True, 'end_of_chain' : response_json['end_of_chain']}
                elif response_json['message'] == 'Success' and 'block_list' in response_json:
                    received_data = response_json

                if received_data:
                    received_data['senderId'] = nodeId
                    received_data = sign_for_sending(received_data, operatorData=operatorData)
                    if not isinstance(starting_point, int):
                        try:
                            block_json = json.loads(response_json['block_obj'])
                            starting_point = block_json['index']
                        except Exception as e:
                            prnt('err0828', str(e))
                            block_list = json.loads(response_json['block_list'])
                            block_json = block_list[0]['block_dict']
                            starting_point = block_json['index']

                    iden = hash_obj_id('DataPacket', specific_data=str(received_data)+dt_to_string(now_utc()))
                    dp = DataPacket.objects.filter(id=iden).first()
                    if not dp:
                        dp = DataPacket(id=iden, func='process_received_blocks', created = now_utc(), data=received_data)
                        dp.save()

                    def wrong_blocks_returned(dp):
                        prnt('wrong_blocks_returned1?')
                        result = process_received_dp(dp, 'process_blocks', override_completed=True)
                        if result and 'dp' in result:
                            log = result['dp']
                            received_json = log.data
                        elif result and 'data' in result:
                            received_json = result['data']
                        else:
                            received_json = []
                        blocks = {}
                        if 'block_list' in received_json:
                            block_list = decompress_data(received_json['block_list'])
                            try:
                                block_list = json.loads(block_list)
                            except:
                                pass
                            for b in block_list:
                                try:
                                    block_dict = json.loads(b['block_dict'])
                                except:
                                    block_dict = b['block_dict']
                                blocks[block_dict['index']] = b
                        else:
                            blocks[received_json['block_dict']['index']] = received_json
                        import operator
                        for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
                            try:
                                new_block_dict = json.loads(b['block_dict'])
                            except:
                                new_block_dict = b['block_dict']
                            block = Block.objects.filter(id=new_block_dict['id']).first()
                            if block and block.validated == False:
                                create_job(send_missing_blocks, job_timeout=60, worker='high', blockchain=blockchain, starting_index=int(block.index), send_to=nodeId, force_check=True)
                                prnt('true')
                                return True
                        prnt('false')
                        return False

                    if process_received_blocks(dp, get_missing_blocks=False, resend_missing_blocks=False, return_result=True, force_check=True, rebroadcast=False, downstream_worker=downstream_worker):
                        if not wrong_blocks_returned(dp):
                            successes += 1
                            try:
                                prnt("str(response_json['end_of_chain'])",str(response_json['end_of_chain']))
                            except Exception as e:
                                prnt('err9621',str(e))
                            if retrieve_following and str(response_json['end_of_chain']) == 'False':
                                create_job(retrieve_missing_blocks, job_timeout=300, worker='high', blockchain=blockchain, starting_point=int(starting_point)+successes)
                    else:
                        wrong_blocks_returned(dp)
                    prnt('retreived_blocks successes',successes)
                    break

                else:
                    prnt('pass node, retrieve_missing_blocks 23595', response_json)
    return successes

def send_missing_blocks(blockchain=None, genesisId=None, missing_blocks=None, starting_index=1, send_to='', force_check=True):
    prntn('-send_missing_blocks',starting_index,'send_to:',send_to,'missing_blocks',missing_blocks,'blockchain',blockchain,'genesisId',genesisId)
    if e_brake(2):
        return 
    from network.models import Block, Blockchain, DataPacket, Validator, _OperationsChain_genesisId
    from utils.locked import verify_obj_to_data, sort_for_sign, hash_obj_id, convert_to_dict, get_relevant_nodes_from_block, get_node_assignment, sign_for_sending
    if not blockchain and genesisId:
        blockchain = Blockchain.objects.filter(genesisId=genesisId).defer('queuedData').first()
    operatorData = get_operatorData()
    self_node_id = get_operator_obj('self_nodeId')
    success = False
    if send_to and send_to != self_node_id:
        hash_history = []
        opBlock = None
        json_data = {'type' : 'Block', 'senderId':self_node_id, 'broadcast_list': [], 'blockchainId' : blockchain.id, 'genesisId':blockchain.genesisId, 'block_list' : [], 'force_check':force_check}
        sending_blocks = []
        if not missing_blocks:
            if isinstance(starting_index, int):
                missing_blocks = Block.objects.filter(networkChain=blockchain.id, index__gte=starting_index-1, validated=True).defer("data").order_by('index')[:3]
            elif is_id(starting_index):
                block = Block.objects.filter(id=starting_index).first()
                if not block:
                    prnt(f'block not found at: {starting_index}')
                    return False
                missing_blocks = Block.objects.filter(networkChain=blockchain.id, index__gte=block.index-1, validated=True).defer("data").order_by('index')[:3]

        for return_block in missing_blocks:
            if verify_obj_to_data(return_block, return_block):
                if not hash_history:
                    hash_history = [i['hash'] for i in reversed(Block.objects.filter(networkChain=blockchain.id, index__lte=return_block.index, validated=True).exclude(id__in=[i.hash for i in missing_blocks]).values("hash").order_by('-index')[:50])]

                if return_block.index == starting_index or return_block.id == starting_index:
                    opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=return_block.DateTime, validated=True).order_by('-index', 'created').first() 

                validations = Validator.objects.filter(validatorType='Block', networkChain=return_block.networkChain, data__has_key=return_block.id)
                validator_list = [sort_for_sign(convert_to_dict(v)) for v in validations if verify_obj_to_data(v, v)]
                prnt('validator_list',validator_list)
                future_block_count = Block.objects.filter(networkChain=blockchain.id, index__gt=return_block.index, validated=True).count()
                sending_blocks.append({'block_dict' : sort_for_sign(convert_to_dict(return_block, exclude=['notes','validators'])), 'block_transaction':return_block.get_transaction_data(), 'block_data' : [], 'validations' : validator_list, 'future_block_count':future_block_count, 'block_is_valid':return_block.validated, 'opBlock':return_block.opBlockId})
        
        if sending_blocks:

            sending_blocks = json.dumps(sending_blocks)
            packet_id = hash_obj_id('DataPacket', specific_data=str(sending_blocks)+send_to)
            prnt('packet_id',packet_id)
            dp = DataPacket.objects.filter(id=packet_id).values('id','updated_on_node').first()
            if dp and dp['updated_on_node'] > now_utc() - datetime.timedelta(minutes=20):
                prnt('recently sent')
                return True
            elif not dp:
                dp = DataPacket(id=packet_id, Node_obj_id=self_node_id, func='completed_sendmissingblocks', networkChain=blockchain.id)
                dp.save()
            if len(sending_blocks) > 1:
                sending_blocks = compress_data(sending_blocks)
            json_data['block_list'] = sending_blocks
            json_data['hash_history'] = hash_history
            if not opBlock:
                opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).order_by('-index', 'created').first() 
            if opBlock:
                json_data['opBlock_id'] = opBlock.id
                json_data['opBlock_hash'] = opBlock.hash
                if opBlock.index != opBlock.Blockchain_obj.chain_length:
                    json_data['opBlock_not_latest'] = True
            json_data = sign_for_sending(json_data, operatorData=operatorData)
            headers = {'packet-id':packet_id, 'packet-origin-dt':dt_to_string(now_utc()), 'senderId':self_node_id, 'func':'sendmissingblocks', 'packet-creator':get_operator_obj('self_nodeId'), 'dt':dt_to_string(now_utc()), 'blockchainId' : return_block.networkChain, 'Genesisid':return_block.Blockchain_obj.genesisId, 'blockId':return_block.id, 'index':str(return_block.index)}
            success, response = connect_to_node(get_node(id=send_to), 'network/receive_blocks', json_data, headers=headers, operatorData=operatorData)
            if success:
                dp = DataPacket.objects.filter(id=packet_id).values('id','notes').first()
                if 'history' not in dp['notes']:
                    dp['notes']['history'] = []
                dp['notes']['history'].append({'sendMissing':dt_to_string(now_utc()), 'send_to':send_to})
                DataPacket.objects.filter(id=dp['id']).update(updated_on_node=now_utc(), notes=dp['notes'])
    return success

def retrieve_transaction(tx=None, block_type='all', target_node=None):
    prntDebugn('--retrieve_transaction- tx:', tx,'target_node:',target_node)
    if e_brake(2):
        return 
    if not tx:
        return
    elif isinstance(tx, models.Model):
        tx = tx.id
    from network.models import DataPacket, Node, Block
    from transactions.models import Transaction
    from utils.locked import get_relevant_nodes_from_block, get_node_assignment, sign_for_sending, hash_obj_id
    opBlock_data = get_relevant_nodes_from_block()
    if target_node and not target_node in opBlock_data['relevant_nodes']:
        n = Node.objects.filter(id=target_node).defer('chain_array','Block_obj','User_obj','abilities','region_data').first()
        if n and n.activated_dt:
            opBlock_data['relevant_nodes'][target_node] = n.return_address()
        else:
            target_node = random.choice([n for n in opBlock_data['relevant_nodes']])
    elif not target_node:
        target_node = random.choice([n for n in opBlock_data['relevant_nodes']])

    value = opBlock_data['relevant_nodes'][target_node]
    opBlock_data['relevant_nodes'].pop(target_node)
    relevant_nodes = {target_node: value, **opBlock_data['relevant_nodes']}

    operatorData = get_operatorData()
    self_node = get_self_node(operatorData=operatorData)


    signedRequest = json.dumps(sign_for_sending({'type':'Transaction', 'iden':tx, 'block_type':block_type}))
    prntn('signedRequest',signedRequest)
    sendingData = {'request':signedRequest, 'senderId':get_operator_obj('self_nodeId')}

    
    successes = 0
    for nodeId, addr in relevant_nodes.items():
        if nodeId != self_node.id:
            received_data = None
            content = sign_post_header(data=sendingData, operatorData=operatorData, self_node=self_node.id, post='post', target_node=nodeId)
            success, response = connect_to_node(addr, 'network/request_data', self_node=self_node, content=content, operatorData=operatorData)

            prnt('connect success',success)
            if success and response.status_code == 200:
                response_json = response.json()
                prntn('response_json666777',str(response_json)[:3000])    
                if response_json['message'] == 'Success' and 'block_list' in response_json:
                    received_data = response_json

                if received_data:
                    received_data['senderId'] = nodeId
                    iden = hash_obj_id('DataPacket', specific_data=str(received_data)+dt_to_string(now_utc()))
                    dp = DataPacket.objects.filter(id=iden).first()
                    if not dp:
                        dp = DataPacket(id=iden, func='process_received_blocks', created = now_utc(), data=received_data)
                        dp.save()

                    def wrong_blocks_returned(dp):
                        prnt('wrong_blocks_returned2?')
                        result = process_received_dp(dp, 'process_blocks', override_completed=True)
                        if result and 'dp' in result:
                            log = result['dp']
                            received_json = log.data
                        elif result and 'data' in result:
                            received_json = result['data']
                        else:
                            received_json = []
                        blocks = {}
                        if 'block_list' in received_json:
                            block_list = decompress_data(received_json['block_list'])
                            try:
                                block_list = json.loads(block_list)
                            except:
                                pass
                            for b in block_list:
                                try:
                                    block_dict = json.loads(b['block_dict'])
                                except:
                                    block_dict = b['block_dict']
                                blocks[block_dict['index']] = b
                        else:
                            blocks[received_json['block_dict']['index']] = received_json
                        import operator
                        for index, b in sorted(blocks.items(), key=operator.itemgetter(0)):
                            try:
                                new_block_dict = json.loads(b['block_dict'])
                            except:
                                new_block_dict = b['block_dict']
                            block = Block.objects.filter(id=new_block_dict['id']).first()
                            if block and block.validated == False:
                                prnt('true')
                                return True
                        prnt('false')
                        return False

                    if process_received_blocks(dp, get_missing_blocks=True, resend_missing_blocks=False, return_result=True, force_check=True, rebroadcast=False):
                        if not wrong_blocks_returned(dp):
                            successes += 1
                    else:
                        wrong_blocks_returned(dp)
                    prnt('retreived_tx_blocks successes',successes)
                    break

                else:
                    prnt('pass node, retrieve_missing_blocks 5921', response_json)
    return successes



def send_for_validation(log=None, gov=None, force_send=False):
    prnt('--send_for_validation() now_utc:',now_utc(), gov, log)
    from network.models import DataPacket, intelligence_funcs
    from utils.locked import get_node_assignment, convert_to_dict, sign_for_sending, hash_obj_id, get_relevant_nodes_from_block, sign_obj
    job_time = None
    job_started = None
    job_finished = None
    job_id = None
    completed = False
    obj_list = []
    func = None
    iden_list = []
    items = []
    approved_funcs = []
    model_types = []
    exceptions = ['Update', 'Notification']
    scraper_list, approved_models = [], []
    gov_level = None
    region = None
    chainId = None
    q = 0
    if is_id(log):
        log = DataPacket.objects.filter(id=log).first()
    if not log:
        prnt('no log')
        return False
    if not force_send and 'process' not in log.func and 'scrape' not in log.func:
        prnt('job completed')
        return None
    if isinstance(log, list):
        q = 1
        items = log
    elif isinstance(log, models.Model):
        if log._meta.object_name == 'DataPacket':
            func = log.data['func']
            if 'shareData' in log.data and log.data['shareData']:
                items = sorted(log.data['shareData'], key=data_sort_priority)
                items = get_all_objects(items)
                prnt('func1:',func)
            elif 'content' in log.data and log.data['content']:
                try:
                    data = json.loads(log.data['content'])
                except:
                    data = log.data['content']
                prnt('rdat:',str(data)[:2000])
                items = sorted(data, key=data_sort_priority)
                items = get_all_objects(items)
                prnt('func2:',func,len(data))
            if items:
                if 'job_dt' in log.data:
                    job_time = string_to_dt(log.data['job_dt'])
                    prnt('job_dt1',dt_to_string(job_time))
                elif log.headers and 'Job-Dt' in log.headers:
                    job_time = string_to_dt(log.headers['Job-Dt'])
                    prnt('job_dt1',dt_to_string(job_time))
                elif 'created' in log.data:
                    job_time = string_to_dt(log.data['created'])
                    prnt('job_dt2',dt_to_string(job_time))
                if 'finished' in log.data:
                    job_finished = dt_to_string(log.data['finished'])
                if 'started' in log.data:
                    job_started = dt_to_string(log.data['started'])
                if 'job_id' in log.data:
                    job_id = log.data['job_id']
                elif log.headers and 'Job-Id' in log.headers:
                    job_id = log.headers['Job-Id']
                else:
                    job_id = hash_obj_id('DataPacket', specific_data=f"{job_time}{func}{log.data['region_id']}")
                if 'gov_level' in log.data:
                    gov_level = log.data['gov_level']
                elif any(i for i in items if i._meta.object_name == 'Government'):
                    for i in items:
                        if i._meta.object_name =='Government':
                            gov = i
                            gov_level = gov.gov_level # gov_level not really needed
                            break
                region_name = log.data['region_name']
                region_id = log.data['region_id']
                from posts.models import Region
                region = Region.objects.filter(id=region_id).first()
                
                q = 2
                if 'created' in log.data:
                    job_time = string_to_dt(log.data['created'])
                
                func = log.data['func']

        else:
            q = 3
            items = [log]
    try:
        start_len = len(items)
    except:
        start_len = 'x'
    if not job_time:
        job_time = round_time(dt=now_utc(), dir='down', amount='hour')
    if 'posts_for_validating' in log.func:
        # already sent
        log = None
        pass
    else:
        creator_nodes, validator_nodes = get_node_assignment(dt=job_time, func=func, chainId=region.id, strings_only=False, nodeType='maintainer')
        prnt('validator_nodes',str(validator_nodes))
        if validator_nodes:
            validator_node = validator_nodes[0]
        try:
            self_node_id = get_operator_obj('self_nodeId')
            prnt('self_node', self_node_id)
            keys = get_operator_obj('keyPair')
            processed_data = {'obj_ids':[],'hashes':{}}
            for i in items:
                prnt('i',i.id)
                proceed = True
                if i.modlVer < i.latestVer:
                    i.modlVer = i.latestVer
                if has_field(i, 'Region_obj') and not i.Region_obj:
                    i.Region_obj = region
                if has_field(i, 'Country_obj') and not i.Country_obj:
                    i.Country_obj = region
                if has_field(i, 'Government_obj') and not i.Government_obj:
                    i.Government_obj = gov
                # if has_field(i, 'networkChain') and not i.networkChain:
                #     if not chainId:
                #         from blockchain.models import Blockchain
                #         chainId = Blockchain.objects.filter(genesisId=region.id).values('id').first()['id']
                #     i.networkChain = chainId

                if has_method(i, 'required_for_validation'):
                    for c in i.required_for_validation():
                        try:
                            if '.' in c:
                                attr = rgetattr(i, c)
                            else:
                                attr = getattr(i, c)
                            if not attr:
                                proceed = False
                                break
                        except Exception as e:
                            prnt('err 4478',str(e))
                            proceed = False
                            break
                if proceed:
                    processed_data['obj_ids'].append(i.id)
                    if True == False:
                        ...
                    elif not is_locked(i):
                        i.func = func
                        i.CreatorNode_obj_id = self_node_id
                        i.validatorNodeId = validator_node
                        if not has_field(i, 'is_modifiable') or has_field(i, 'proposed_modification') and i.proposed_modification:
                            i.created = job_time
                        obj, err = sign_obj(i, keys=keys, return_error=True)
                        if obj.signed and not err:
                            obj_list.append(convert_to_dict(obj))
                            iden_list.append(obj.id)
            items = []
            if 'process' not in log.func:
                log.func = log.func.replace('scrape_','process_')
                log.save(update_fields=['func'])

            prntDebug('sending for validation...')
            content_length = len(obj_list)
            prntDebug('len(data)',content_length)
            packet_id = log.id
            compressed_data = json.dumps(obj_list)
            obj_list = []

            if not log.headers:
                log.headers = {'Packet-Id':packet_id, 'Senderid':self_node_id, 'Job-Id':job_id, 'Task':str(log.task), 'Job-Dt':dt_to_string(job_time), 'Dt':dt_to_string(now_utc()), 'Func':func, 'Region-Id':region.id if region else None}
                log.save(update_fields=['headers'])

            data_to_send = {'type':'for_validation', 'packet_id':packet_id, 'job_started':job_started, 'job_finished':job_finished, 'func':func, 'senderId':self_node_id, 'region_id':region.id, 'gov_level':gov_level, 'scrapers':[s for s in creator_nodes], 'validator':validator_node, 'region_name':region.Name, 'content_length':content_length, 'content': compressed_data}
            sending_data = sign_for_sending(data_to_send)
            data_to_send = {}
            compressed_data = None
            prnt('creator_nodes:',creator_nodes)
            prnt('validator_node:',validator_node)
            if len(creator_nodes) == 1:
                # do not mark log completed, must validate same dp
                log.func = f'process_gathered_data_job:{func}'
                log.data = sending_data
                log.notes['post_processed'] = True
                log.save(update_fields=['notes','data','func'])
                iden = log.id
                log = None
                completed = True
                from utils.locked import process_gathered_data
                queue = django_rq.get_queue('low')
                queue.enqueue(process_gathered_data, iden, job_timeout=600, result_ttl=3600)
                prnt('added to low worker')
            else:
                if log:
                    log.refresh_from_db(fields=['func'])
                    log.data = sending_data
                    log.save(update_fields=['data'])
                for node_id in creator_nodes:
                    if node_id != self_node_id:
                        prnt('send for validation job_id:',job_id)
                        completed, response = connect_to_node(node_id, 'network/receive_gathered_data', sending_data, headers=log.headers)
                sending_data = None
                if validator_node != self_node_id:
                    compressed_data = json.dumps(iden_list)
                    data_to_send = {'type':'job_completed', 'packet_id':packet_id, 'job_started':job_started, 'job_finished':job_finished, 'func':func, 'senderId':self_node_id, 'region_id':region.id, 'gov_level':gov_level, 'scrapers':[s for s in creator_nodes], 'validator':validator_node, 'region_name':region.Name, 'content_length':content_length, 'content': compressed_data}
                    sending_data = sign_for_sending(data_to_send)
                    completed, response = connect_to_node(validator_node, 'network/receive_event', sending_data, headers=log.headers)
            if log:
                log.notes['post_processed'] = True
                log.save(update_fields=['notes'])
                
        except Exception as e:
            prnt('fail987542', str(e))
            logError('failed to send for validation', code='98274',func='send_for_validation',extra={'err':str(e),"log":log.id if log else'none'})
    prnt('finish up...')
    if log:
        if completed or len(items) == 0 or log.created < now_utc() - datetime.timedelta(hours=24):
            try:
                log.completed()
            except Exception as e:
                prnt('fail086421',str(e))
    return completed



def assess_received_header(header, return_is_self=False, if_self_active=False, allow_inactive=False):
    prnt('--assess_received_header',header)
    from network.models import DataPacket, Block, _OperationsChain_genesisId
    dt = string_to_dt(header.get('Signed-Dt'))
    now = now_utc()
    err = 'A'
    try:
        if dt > (now - datetime.timedelta(minutes=10)) and dt < (now + datetime.timedelta(seconds=10)):
            err += 'B'
            senderId = header.get('senderid')
            targetId = header.get('Targetid')
            node_setup = header.get('nodesetup', allow_inactive)
            prnt('senderId',senderId,'targetId',targetId)
            if not targetId or targetId == get_operator_obj('self_nodeId'):
                err += 'a'
                sender_node = get_node(id=senderId)
                # prnt('sender_node',sender_node)
                if sender_node or str(node_setup) == 'True':
                    err += 'b'
                    sign_data = f"{senderId}-{targetId}-{header.get('Signed-Dt')}"
                    prnt('sign_data',sign_data,'sig', header.get('Dt-Sig'))
                    if sender_node and not sender_node.expelled_dt and sender_node.User_obj.verify_sig(sign_data, header.get('Dt-Sig'), simple_verify=True, keyType='node', nodeId=senderId, dt=dt):
                        err += 'C'
                        prnt('-good')
                        # if if_self_active and not get_self_node().activated_dt:
                        #     return False
                        if return_is_self:
                            if sender_node.id == get_operator_obj('self_nodeId'):
                                return True
                            else:
                                return False
                        return True
                    elif node_setup and str(node_setup) == 'True':
                        err += 'D'
                        if senderId == get_operator_obj('self_nodeId'):
                            # should check something has been signed here
                            return True
                        else:
                            initial_block = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).values('added_to_node').first()
                            if not initial_block or initial_block['added_to_node'] > now_utc() - datetime.timedelta(hours=24):
                                prnt('pass for initial setup2')
                                return True
                        return True
                    else:
                        err += 'E'
                        prnt('failed sig')
                if is_debug():
                    prntDebug('sender_node',sender_node, 'opBlock_count',Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).count())
        else:
            err += 'F'
            prnt('failed dt',dt, now)
    except Exception as e:
        prnt('fail864',str(e), )
    prnt('failed assess header', err)
    return False

def sign_post_header(data={}, headers=None, operatorData=None, self_node=None, target_node=None, post='post', address_type=None):
    prnt('-sign_post_header',target_node)
    if post:
        if not headers:
            headers = {}
        if not self_node:
            self_node = get_operator_obj('self_nodeId')
        elif isinstance(self_node, models.Model):
            self_node = self_node.id
        now = dt_to_string(now_utc())
        if isinstance(data, dict):
            data = json.dumps(data)
        from utils.locked import simpleSign
        keyPair = get_operator_obj('keyPair', operatorData=operatorData)
        headers['senderid'] = self_node
        headers['targetid'] = None
        if target_node:
            if isinstance(target_node, str):
                headers['targetid'] = target_node
            else:
                headers['targetid'] = target_node.id
        headers['signed-dt'] = now
        sign_data = f"{headers['senderid']}-{headers['targetid']}-{now}"
        prnt('sign_data',sign_data)
        sig = simpleSign(keyPair['privKey'], sign_data) # content gets hashed in sign_for_sending and verified in process_received_dp
        # if post == 'stream':
        #     content_length = len(data.encode('utf-8'))
        #     headers = {'Content-Type': 'application/json','Transfer-Encoding': 'chunked'}
        #     headers['Content-Length'] = str(content_length)
        #     headers['senderId'] = self_node.id
        #     headers['dt'] = now
        #     headers['dtsig'] = sig
        #     # prnt('header to send',headers)
        # else:
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'
        headers['dt-sig'] = sig
        headers['upk'] = keyPair['keyId']
        headers['address_type'] = address_type
    return {'body':data, 'headers':headers}


# MAX_SIZE = 5 * 1024 * 1024  # 5 MB
# MAX_SIZE = 1024 * 1024  # 1 MB (better for Tor)
MAX_SIZE = 256 * 1024  # 256 KB (1/4 MB)


def send_post(url, data_str, headers=None, timeout=(10, 60)):
    import requests, math, uuid, socket

    socket.setdefaulttimeout(20)

    session = requests.Session()
    if '.onion' in url:
        proxies = {
            "http": "socks5h://127.0.0.1:19050",
            "https": "socks5h://127.0.0.1:19050"
        }
        session.proxies = proxies

    if headers is None:
        headers = {}
    headers["User-Agent"] = "Mozilla/5.0 (NodeClient)"
    session.headers.update(headers)


    body_bytes = (data_str or '').encode("utf-8")
    total_size = len(body_bytes)
    prnt('total_size',total_size)
    prnt(to_megabytes(data_str),'MB')

    # Single part
    if total_size <= MAX_SIZE:
        session.headers["X-Last-Part"] = "true"
        try:
            return session.post(url, data=body_bytes, timeout=timeout, allow_redirects=False)
        except Exception as e:
            prnt('send post fail 1',str(e))
            return False

    upload_id = str(uuid.uuid4())
    total_parts = math.ceil(total_size / MAX_SIZE)
    last_received_chunk = 0
    start_time = now_utc()
    for part_number, start in enumerate(range(0, total_size, MAX_SIZE), start=1):

        prnt('part_number',part_number,'/',total_parts)
        if last_received_chunk >= part_number:
            prnt('already received - last_received_chunk',last_received_chunk)
        else:
            chunk = body_bytes[start:start + MAX_SIZE]


            part_headers = {
                "X-Upload-ID": upload_id,
                "X-Part-Number": str(part_number),
                "X-Last-Part": "true" if part_number == total_parts else "false",
            }

            for attempt in range(3):
                chunk_start = now_utc()
                resp = None
                if attempt:
                    prnt('attempt',attempt+1)
                try:
                    resp = session.post(
                        url,
                        data=chunk,
                        headers=part_headers,
                        timeout=(10, 90),
                        allow_redirects=False
                    )

                    end_chunk = now_utc()
                    print('attempt timeA:',end_chunk - chunk_start)
                    if resp.status_code == 200:
                        break
                except requests.exceptions.RequestException:
                    prnt('fail connect')
                    # if attempt == 2:
                    #     prnt('attempt == 2')
                            # raise
                    end_chunk = now_utc()
                    print('attempt timeB:',end_chunk - chunk_start)
            if not resp or resp.status_code != 200:
                return resp

            try:
                r_json = resp.json()
                if r_json.get("status") == "completed":
                    return resp
                last_received_chunk = int(r_json.get("last_chunk"))
                prnt('new last_received_chunk:',last_received_chunk)
            except Exception:
                pass


    end_time = now_utc()
    print('total time:',end_time - start_time)
    return resp

def send_post_nonTor(url, data_str, headers=None, timeout=(5, 30)):
    prnt('-send_post',url)
    import requests

    proxies = {
        "http": f"socks5h://127.0.0.1:19050",
        "https": f"socks5h://127.0.0.1:19050"
    }

    if headers is None:
        headers = {}
    headers["User-Agent"] = "Mozilla/5.0 (NodeClient)"
    if not data_str:
        data_str = ''
    body_bytes = data_str.encode('utf-8')
    total_size = len(body_bytes)
    prnt('total_size',total_size)
    if total_size < MAX_SIZE:
        headers['X-Last-Part'] = 'true'
        prnt('send in 1')
        return requests.post(url, data=body_bytes, headers=headers, timeout=timeout, proxies=proxies)

    import math
    import uuid
    # Multi-part upload
    upload_id = str(uuid.uuid4())
    responses = []
    total_parts = math.ceil(total_size / MAX_SIZE)
    for part_number, start in enumerate(range(0, total_size, MAX_SIZE), start=1):
        is_last = (part_number == total_parts)
        prnt('part_number',part_number,'start',start)
        chunk = body_bytes[start:start + MAX_SIZE]
        part_headers = headers.copy()
        part_headers['Content-Length'] = str(len(chunk))
        part_headers['X-Upload-ID'] = upload_id
        part_headers['X-Part-Number'] = str(part_number)
        part_headers['X-Last-Part'] = 'false'
        if part_number == total_parts:
            part_headers['X-Last-Part'] = 'true'

        resp = requests.post(url, data=chunk, headers=part_headers, timeout=(10, 120), proxies=proxies)
        if resp.status_code != 200:
            prnt('break! no contact')
            break
        else:
            r_json = resp.json()
            if 'status' in r_json and r_json['status'] == 'completed':
                prnt('break! job completed')
                break
        responses.append(resp)

    prnt('responses',responses)
    return resp
        
def connect_to_node(node, url, data=None, self_node=None, content={}, headers={}, operatorData=None, timeout=(10,15), get=False, stream=False, node_is_string=False, log_reponse_time=True, attempts=2, address_type='address'):
    prnt('---connect to node---', node, url, now_utc(),timeout,address_type)
    # prnt('data',str(data)[:1000])
    # prnt('content',str(content)[:1000])
    from network.models import Node
    import requests
    response = None
    try:
        start_time = None
        def get_node(ip, address_type):
            node = None
            if address_type == 'address':
                node = Node.objects.filter(address=ip, activeNode=True).only('id','suspended_dt','address','onion','node_name').first()
            elif address_type == 'onion':
                node = Node.objects.filter(onion=ip, activeNode=True).only('id','suspended_dt','address','onion','node_name').first()
            return node
        if node_is_string:
            ip = node
            node = get_node(ip, address_type)
        elif isinstance(node, dict):
            ip = node[address_type]
            node = get_node(ip, address_type)
        elif is_id(node):
            node = Node.objects.filter(id=node).only('id','suspended_dt','address','onion','node_name').first()
            addrs = node.return_address()
            ip = addrs[address_type]
        elif isinstance(node, str):
            ip = node
            node = get_node(ip, address_type)
        elif isinstance(node, models.Model):
            addrs = node.return_address()
            ip = addrs[address_type]
        if node_is_string or node and (not node.suspended_dt or retry_suspended(node.suspended_dt)) or ip:
            if url.startswith('/'):
                url = url[1:]
            if is_id(ip):
                target_node_id = None
                self_address = get_operator_obj(address_type, operatorData=operatorData)
                if self_address and ip == self_address:
                    ip = get_operator_obj('local_address', operatorData=operatorData)
            elif isinstance(node, models.Model):
                target_node_id = node.id
            else:
                target_node_id = ip
            if target_node_id:
                self_nodeId = get_operator_obj('self_nodeId', operatorData=operatorData)
                if self_nodeId == target_node_id:
                    ip = get_operator_obj('local_address', operatorData=operatorData)
            prnt('ip',ip)
            start_time = time.time()
            if '127.0.0.1' in ip or '.onion' in ip:
                http = 'http'
            else:
                http = 'https'
            if get:
                prnt('sending get from server...',ip,now_utc())
                response = requests.get(http + '://' + ip + '/' + url, timeout=timeout)
            else: 
                if not content:
                    post_type = 'get' if get else 'stream' if stream else 'post'
                    content = sign_post_header(data=data, headers=headers, operatorData=operatorData, self_node=self_node, target_node=node, post=post_type, address_type=address_type)
                prnt("content['headers']",content['headers'])
                response = send_post(f"{http}://{ip}/{url}", content['body'], headers=content['headers'], timeout=timeout)
                
            elapsed_time = time.time() - start_time
            prnt('post connection', f"{int(elapsed_time // 60):02}:{int(elapsed_time % 60):02}",response) 
            if isinstance(response, list):
                if node and response:
                    node.accessed(address_type=address_type, self_node=self_node)
                    return True, response
                return False, response
            else:
                prnt('response.elapsed.total_seconds()',response.elapsed.total_seconds() if response else None)
                if response and response.status_code == 200:
                    prnt('success connection')
                    try:
                        r_json = response.json()
                        if 'message' in r_json and r_json['message'].lower() == 'success' and 'nodeId' in r_json:
                            if 'status' in r_json:
                                prnt(f"--job status-- *{r_json['status']}*")
                            if node and node.id != r_json['nodeId']: # sometimes with cloudflare node will attempt connection to another node, but it actually connects to itself, returning a false positive
                                prnt('**FALSE CONNECTION**',str(r_json)[:500])
                                if address_type == 'address':
                                    return connect_to_node(node, url, data=data, self_node=self_node, content=content, headers=headers, operatorData=operatorData, timeout=timeout, address_type='onion', get=get, stream=stream, node_is_string=node_is_string, log_reponse_time=log_reponse_time, attempts=attempts-1)
                                else:
                                    return False, response
                            elif node and node.id != self_nodeId:
                                prnt('-POSITIVE CONNECTION-',str(r_json)[:500])
                            else:
                                prnt('UNKNOWN CONNECTION 1',str(r_json)[:500])
                        elif 'message' in r_json and r_json['message'].lower() == 'success':
                            prnt('UNKNOWN CONNECTION 2',str(r_json)[:500])
                        else:
                            prnt('FAILED CONNECTION',str(r_json)[:500])
                    except Exception as e:
                        prnt('connect err 6721',str(e))
                    # prnt('response.json()',response.json())
                    if node and log_reponse_time:
                        node.accessed(response_time=response.elapsed.total_seconds(), address_type=address_type, self_node=self_node)
                    elif node:
                        node.accessed(address_type=address_type, self_node=self_node)
                    return True, response
                if attempts > 1:
                    prnt('attempts',attempts)
                    if address_type == 'address':
                        address_type = 'onion'
                        timeout = (timeout[0]*2,timeout[1]*2)
                    return connect_to_node(node, url, data=data, self_node=self_node, content=content, headers=headers, operatorData=operatorData, timeout=timeout, address_type=address_type, get=get, stream=stream, node_is_string=node_is_string, log_reponse_time=log_reponse_time, attempts=attempts-1)
                else:
                    if response:
                        prnt('-connect fail',str(response.content)[:650])
                    if node:
                        node.add_failure(note=url, self_node=self_node)
                    return False, response
        else:
            return False, None
    except Exception as e:
        if start_time:
            elapsed_time = time.time() - start_time
            prnt('connect to node fail 111',str(e), f"{int(elapsed_time // 60):02}:{int(elapsed_time % 60):02}") 
        else:
            prnt('connect to node fail 222',str(e))
        return False, response
    

def downstream_broadcast(broadcast_list, url, sendingData, headers={}, operatorData=None, self_node=None, target_node_id=None, skip_self=False, timeout=(50,60), stream=False, exclude=[]):
    prnt('--downstream_broadcast now_utc:', now_utc(), url, broadcast_list, 'exclude:',exclude)
    prnt('data',str(sendingData)[:1000])
    from django.db.models import Model
    from network.models import Node
    import requests
    import json
    if not isinstance(sendingData, dict):
        sendingData = json.loads(sendingData)
    if not self_node:
        self_node = get_self_node(operatorData=operatorData)
    total_successes = 0
    if not target_node_id:
        target_node_id = self_node.id
    prnt('target_node_id',target_node_id)
    attemped_nodes = []
    def func(peer_nodes, content={}):
        prntDebug('func', peer_nodes, str(content)[:500])
        successes = 0
        if peer_nodes and not isinstance(peer_nodes[0], Model):
            if isinstance(peer_nodes[0],dict):
                peer_nodes = Node.objects.filter(address__in=[i['address'] for i in peer_nodes]).defer('chain_array','Block_obj','User_obj','abilities','region_data')
            elif is_id(str(peer_nodes[0])):
                peer_nodes = Node.objects.filter(id__in=peer_nodes).defer('chain_array','Block_obj','User_obj','abilities','region_data')
            elif '.onion' in str(peer_nodes[0]):
                peer_nodes = Node.objects.filter(onion__in=peer_nodes).defer('chain_array','Block_obj','User_obj','abilities','region_data')
            else:
                peer_nodes = Node.objects.filter(address__in=peer_nodes).defer('chain_array','Block_obj','User_obj','abilities','region_data')
        for node in peer_nodes:
            prntDebug('node',node)
            content = sign_post_header(data=sendingData, headers=headers, operatorData=operatorData, self_node=self_node.id, target_node=node, post='stream' if stream else 'post')
            if node.id not in exclude and node._meta.object_name == 'Node':
                if node not in attemped_nodes and (not node.suspended_dt or retry_suspended(node.suspended_dt)):
                    prnt('f1')
                    attemped_nodes.append(node)
                    if skip_self and node == self_node:
                        success = True
                    else:
                        success, response = connect_to_node(node, url, self_node=self_node, content=content, operatorData=operatorData, timeout=timeout, stream=stream)
                    prnt('success',success)
                    if success:
                        successes += 1
                    elif node.id != target_node_id:
                        try:
                            s = func(broadcast_list[node.id], content=content)
                            successes += s
                        except Exception as e:
                            prnt('connect err 988',str(e))
                elif node not in attemped_nodes and node.id in broadcast_list:
                    prnt('f2')
                    attemped_nodes.append(node)
                    try:
                        s = func(broadcast_list[node.id], content=content)
                        successes += s
                    except Exception as e:
                        prnt('connect err 977',str(e))
                elif node == self_node:
                    successes += 1
        return successes
    
    if isinstance(target_node_id, list):
        prntDebug('db1')
        for target_id in target_node_id:
            prntDebug('db1.1',target_id)
            if target_id in broadcast_list:
                prntDebug('db1.2')
                peers = broadcast_list[target_id]
                s = func(peers, content={})
                total_successes += s

    elif target_node_id in broadcast_list:
        prntDebug('db2')
        peers = broadcast_list[target_node_id]
        s = func(peers, content={})
        total_successes += s
    return total_successes

def rebroadcast(packet_id):
    from network.models import DataPacket
    dp = DataPacket.objects.filter(id=packet_id)
    if dp:
        successes = downstream_broadcast(lst, 'network/receive_blocks', sending_data,  skip_self=True)
        
    ...


def retry_suspended(past_dt: datetime.datetime) -> bool:
    # retry node every 4:00-4:20 hours
    now = datetime.datetime.now(datetime.timezone.utc)

    if past_dt.tzinfo is None:
        past_dt = past_dt.replace(tzinfo=datetime.timezone.utc)

    if past_dt > now:
        return False

    past_hour = past_dt.replace(minute=0, second=0, microsecond=0)
    now_hour = now.replace(minute=0, second=0, microsecond=0)

    delta_hours = (now_hour - past_hour).total_seconds() / 3600

    if delta_hours % 4 != 0: # 4 hours
        return False

    return 0 <= now.minute <= 20

# not used
def node_ai_capable():
    # when declaring self_node ai_capable, an already established ai_capable node
    # should test the response, should be a simple prompt that it's own ai can verify
    # should also return response in a reasonable time. if good, validate, share validation
    pass




def return_test_result(log):
    from posts.models import Post
    prnt('\nreturn_test_result')
    isTest = testing()
    # shareData = log.data['shareData']
    # prnt('shareData:',shareData)
    # get_data(log.data['shareData'])
    storedModels, not_found, not_valid = get_data(log.data['shareData'], return_model=True, include_related=False, verify_data=False)
    mb = 0
    if storedModels:
        for i in storedModels:
            if i:
                mb += to_megabytes(i)
                skip = False
                post = None
                if isTest:
                    prnt('\n',i._meta.object_name)
                    try:
                        if i._meta.object_name == 'Update':
                            post = Post.objects.filter(pointerId=i.pointerId).first()
                            if not post:
                                if has_method(i.Pointer_obj, 'create_post'):
                                    post = i.Pointer_obj.create_post()
                                    # post = Post.objects.filter(pointerId=i.pointerId).first()
                                if not post:
                                    skip = True
                            if not skip and post.Update_obj != i:
                                i.sync_with_post(post=post)
                                # if post.Update_obj:
                                #     post.Update_obj.delete()
                                # post.Update_obj = i
                                # post.DateTime = i.DateTime
                                # post.save()
                        else:
                            # prnt('else')
                            if has_method(i, 'create_post'):
                                # prnt('p1')
                                post = Post.all_objects.filter(pointerId=i.id).first()
                                if not post:
                                    post = i.create_post()
                                prnt('post:',post)
                                if post:
                                    # if post:
                                    post.validated = True
                                    post.save()
                                    if has_method(i, 'upon_validation'):
                                        i.upon_validation()
                                # prnt('p2')
                    except Exception as e:
                        prnt('FAIL-return:',str(e))
                        time.sleep(5)
        # log.delete()
    prnt('mb:', mb)
    return f'shareData: {len(storedModels)}, not_found:{len(not_found)}, not_valid:{len(not_valid)}\nMBs: {mb}'



skipwords = [
    "shouldn't", 'needn', 'before', 'we', 'are', 'after', 'because', 'haven', 'and', 'itself', 'all', 'o', 'but', 'any', 'again', 'aren', 'she', "you'll", 
    'himself', 'didn', 'under', 'wasn', 's', 'yours', 'very', "aren't", "won't", 'don', 'how', 'him', "mustn't", 'more', 't', 'off', 'ours', "it's", 'into', 
    'same', 'myself', 'at', "wouldn't", 'they', 'only', 'so', 'down', 'yourselves', 'both', 'each', 'who', 'themselves', 'yourself', 'as', 'up', 'not', 'above', 
    'this', 'will', 'was', 'here', 'does', 'for', 'such', 'there', 'should', 'by', 'mustn', 're', 'is', "isn't", "she's", "weren't", 'y', 'he', 'between', 
    'where', 'on', 'am', 'other', 'now', 'too', "haven't", 'some', 'd', 'being', 'then', 'hasn', "hadn't", 'in', 'having', 'i', 'which', "mightn't", 'were', 
    'wouldn', 'our', 'to', 'until', 'with', 'most', 'if', 'those', 'their', 'nor', 'of', 'doesn', "wasn't", 'do', 'that', 'once', 'than', 'ain', 'isn', 'its', 
    'these', 'had', 'your', 'can', 'you', 'shouldn', "you're", 'doing', 'it', 'while', 'the', 'll', 'or', 'hadn', "doesn't", 'his', 've', 'about', 'through', 'own', 
    'mightn', 'further', 'hers', "didn't", 'm', "that'll", "hasn't", "you'd", 'me', 'have', 'what', 'did', 'over', 'whom', "you've", 'has', 'why', "needn't", 
    'couldn', 'below', "don't", 'an', 'no', 'ourselves', 'out', 'won', 'her', 'be', 'from', "shan't", 'been', 'herself', "should've", 'just', 'ma', 'when', 'shan', 
    "couldn't", 'few', 'during', 'against', 'a', 'them', 'weren', 'theirs', 'my', 'statement',
    'SENATORS’ STATEMENTS','Orders of the Day', 'Question Period', 'Petitions', "Members' Statements", 'ORDERS OF THE DAY', 'SENATORS’ STATEMENTS', 'ROUTINE PROCEEDINGS', 
    'Oral questions', 'QUESTION PERIOD','QUESTION PERIOD', 'Government bills', 'Oral Questions', 'Adjournment Proceedings', 'Adjournment','adjourned',
    'Oral questions', 'Statements by Members', 'Government bills','ORDERS OF THE DAY', 'QUESTION PERIOD', 'ROUTINE PROCEEDINGS','Opposition motions',  
    'act', 'acts', 'statutes', 'legislature', 'schedule', 'tax','taxes','taxation','taxable','taxation','taxapyer','taxed','taxing','income','incomes',
    'bill amends the', 'enactment grants', 'enactment grants the', 'Opposition motions','declaration','minute','remark','remarks','minutes','yields',
    'this enactment grants', 'enactment amends the','this enactment amends','Royal Assent','unanimous','consent','motion','move','issues',
    'this acts amends', 'act amends the', 'act amends', 'amends','amendment','political', 'without objection', 'objection ordered',
    'enactment', 'enactment amends', 'provisions', 'intermediary', 'Introduction of Visitors', 'gentlemen', 'gentleman','gentlewoman','congress','yeas nays',
    'intermediaries', 'regulation', 'regulations', 'regulations to', 'Members’ Statements','gentlelady','one minute','recognized','time expired','two minutes','yield',
    'also amends', 'consequential amendments', 'amendments to', 'amendments', 'Business of the Senate','seconds','state','met',
    'amends', 'makes consequential amendments', 'enactment provides', 'Visitor in the Gallery','monday','tuesday','wednesday','thursday','friday','saturday','sunday',
    'provides', 'canada', 'council', 'councils', 'government','hon', 'Points of order','clerk','tempore','appoint',
    'senators','agreed','committee','senate','report','reports','presented', 'Report stage',
    'canadians','sector','legislation','bill','province','canadian','member', 'Visitors in the Gallery',
    'minister','ministers','madam','speaker','house','senator','statements','Third reading and adoption',
    'question','mr','mrs','ms','colleague','conservative','conservatives','liberal','called','thereupon','president',
    'liberals','ndp','mp','mps','chair','members','canada bill','proceedings','parliament',
    'canada bill','canada enacts','department','is amended','canada act','amended',
    'district','electoral','the province','province of','amend','amended','canadian bill',
    'parliamentary','commons','legislative','federal','provincial','sencanada','repealed',
    'ca','exemption','pursuant','provinces','repeal','commencement','day','laws','canada obligations',
    'ontario','ontario enacts','ontario regulation','schedule ontario','ontario act','enacted','policies','issued','agreements','documents','code','may',
    'amends the','agreement','exempt','law','federal provincial','provision','month','canadian charter',
    'amending','consultations','is repealed','comply','parliamentarians','municiapl','the parliament',
    'act canada','an assault','parliamentarians act','parliament of','of parliament',
    'canada implementation','insertion','canada official','provincial legislation','section',
    'to canada','of parliamentarians','to amend','act canadian','parliament report','proceeding',
    'canada council','municipal act','statutes of','amend the','province will','province law',
    'canadian council', 'implement', 'stage',
    'order','debate','opposition','leader','party','honourable','questions','vote','policy','secratary',
    'honour','representative','governments','bills','please','thank','municipalities','colleagues',
    'national','committees','official','third','second','parliamentarian','assent','politicians','Second reading',
    'representatives','parliaments','oh','None','none','points of order','The Senate',"Private Members' Bills",
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
    ]



def run_database_maintenance():
    # from django.db import connection
    # with connection.cursor() as cursor:
    #     cursor.execute("VACUUM FULL;")
    #     cursor.execute("REINDEX DATABASE so_data;")

    # run 
    cmd = ['psql', '-U', 'sozed (or whatever admin user)', '-d', 'so_data', '-c', '"VACUUM FULL;"']
    # psql -U sozed (or whatever admin user) -d so_data -c "REINDEX DATABASE so_data;"
    # result = subprocess.run(cmd, input=systemPass, text=True)
    pass


# not used
def reindex_model(model):
    # table_name = model._meta.db_table
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(f"SELECT indexname FROM pg_indexes WHERE tablename = '{model._meta.db_table}';")
        indexes = cursor.fetchall()

    for index in indexes:
        index_name = index[0]
        prnt(f"Found index: {index_name}")
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT 1 FROM pg_class WHERE relname = '{index_name}';")
                result = cursor.fetchone()

            if result:
                prnt(f"Reindexing index: {index_name}")
                with connection.cursor() as cursor:
                    cursor.execute(f"REINDEX INDEX {index_name};")
                prnt(f"Successfully reindexed {index_name}")
            else:
                prnt(f"Index {index_name} does not exist in pg_class, skipping.")
        except Exception as e:
            prnt(f"Error during reindexing {index_name}: {e}")




def get_object_size_in_mb(data, do_serial=False):
    # Serialize the object to JSON
    if do_serial:
        from django.core.serializers import serialize
        serialized_data = serialize('json', [data])  # Wrap the object in a list
    else:
        serialized_data = data
    # Calculate the size in bytes
    size_in_bytes = len(serialized_data.encode('utf-8'))
    # Convert to megabytes
    size_in_mb = size_in_bytes / (1024 * 1024)
    return size_in_mb

