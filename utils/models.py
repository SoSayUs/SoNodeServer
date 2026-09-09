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
from utils.utils import (
    prnt, save_sigs, now_utc, seperate_by_type, logError, get_node, is_debug, declare_var,
    round_time, get_operator_obj, get_self_node, is_id, get_model_prefix, get_dynamic_model, has_field,
    logEvent, fetch_secure_item, exists_in_worker, to_megabytes, 
    string_to_dt, get_pointer_type, get_app_name, prntDebug, is_locked, resolve_target_keys, value_is_none,
    get_sigData, has_method, find_or_create_chain_from_object, func_accepts_var, get_superuser_keys,
    hash_upk_id, has_profanity, get_model, parse_input, get_operatorData, get_user, get_latest_dataPacket, sigData_to_hash, testing,
    create_dynamic_model, get_all_objects, rgetattr, get_or_create_model, prntn,
)




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


_e_brake_end_dt = None
_e_brake = 0
# 0 = run all!
# 1 = run nothing
# 2 = resolve blocks
# 3 = resolve blocks/txs/posts, stop all scrapers
# 4 = finish active scrapers, do not call from tasker

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

from base64 import b64encode, b64decode

class BinaryBase62Field_old(models.BinaryField):
    def __init__(self, max_byte_length, *args, max_prefix_length=8, **kwargs):
        self.max_byte_length = max_byte_length
        self.max_prefix_length = max_prefix_length
        kwargs['max_length'] = 1 + max_prefix_length + 2 + max_byte_length
        kwargs.setdefault('editable', True)
        super().__init__(*args, **kwargs)

    def _split(self, value):
        """'usr$ok30...' -> ('usr', 'ok30...'); no '$' -> ('', value)"""
        if '$' in value:
            prefix, id_part = value.split('$', 1)
            return prefix, id_part
        return '', value

    def _pack(self, prefix, raw_id):
        if len(prefix) > self.max_prefix_length:
            raise ValueError(f"prefix {prefix!r} exceeds max_prefix_length={self.max_prefix_length}")
        prefix_bytes = prefix.encode('ascii')
        padded_id = raw_id.ljust(self.max_byte_length, b'\x00')
        return (
            len(prefix_bytes).to_bytes(1, 'big')
            + prefix_bytes
            + len(raw_id).to_bytes(2, 'big')
            + padded_id
        )

    def _unpack(self, raw):
        plen = raw[0]
        prefix = raw[1:1 + plen].decode('ascii')
        rest = raw[1 + plen:]
        idlen = int.from_bytes(rest[:2], 'big')
        raw_id = rest[2:2 + idlen]
        return prefix, raw_id

    def _to_display(self, prefix, raw_id):
        b62 = to_base62(raw_id)
        return f'{prefix}${b62}' if prefix else b62

    def value_from_object(self, obj):
        value = getattr(obj, self.attname)
        if value is None:
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, (bytes, memoryview)):
            prefix, raw_id = self._unpack(bytes(value))
            return self._to_display(prefix, raw_id)
        return value

    def value_to_string(self, obj):
        value = getattr(obj, self.attname)
        if value is None:
            return ''
        if isinstance(value, str):
            prefix, id_part = self._split(value)
            raw_id = from_base62(id_part)
            packed = self._pack(prefix, raw_id)
            return b64encode(packed).decode('ascii')
        return ''

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        prefix, raw_id = self._unpack(bytes(value))
        return self._to_display(prefix, raw_id)

    def to_python(self, value):
        if value is None or isinstance(value, str):
            return value
        prefix, raw_id = self._unpack(bytes(value))
        return self._to_display(prefix, raw_id)

    def get_prep_value(self, value):
        if value is None:
            return value
        if isinstance(value, memoryview):
            return bytes(value)
        if isinstance(value, bytes):
            if _already_prefixed(value, self.max_byte_length):
                return value
            return self._pack('', value)
        if isinstance(value, str):
            if len(value) % 4 == 0 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in value):
                try:
                    raw = b64decode(value)
                    if len(raw) == self.max_length:
                        return raw  # already packed, came from session storage
                except Exception:
                    pass
            prefix, id_part = self._split(value)
            try:
                raw_id = from_base62(id_part)
                return self._pack(prefix, raw_id)
            except Exception as e:
                prnt(f"ERROR in str branch: {e}, value={repr(value)}")
                raise
        return value

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs.pop('max_length', None)
        kwargs['max_prefix_length'] = self.max_prefix_length
        args = [self.max_byte_length] + list(args)
        return name, path, args, kwargs

    def get_internal_type(self):
        return 'CharField'

    def db_type(self, connection):
        return 'bytea'

    def get_db_prep_value(self, value, connection, prepared=False):
        value = self.get_prep_value(value)
        return value

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

    def get_internal_type(self):
        return 'CharField'

    def db_type(self, connection):
        return 'bytea'

    def get_db_prep_value(self, value, connection, prepared=False):
        value = self.get_prep_value(value)
        return value

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
    
    def get_internal_type(self):
        return 'CharField'

    def db_type(self, connection):
        return 'bytea'
        
    def get_db_prep_value(self, value, connection, prepared=False):
        value = self.get_prep_value(value)
        return value

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

def _already_prefixed(value: bytes, max_byte_length: int) -> bool:
    if len(value) < 2:
        return False
    declared_length = int.from_bytes(value[:2], 'big')
    # total stored = 2 (prefix) + max_byte_length (padded data)
    return len(value) == max_byte_length + 2 and declared_length <= max_byte_length

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
        idx = ALPHABET.find(char)
        if idx == -1:
            raise ValueError(f"invalid base62 character {char!r} in {s!r}")
        num = num * 62 + idx
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

def create_share_object(func, region, special, dt=None, iden=None, job_dt=None, task=1, plugin=None):
    if not dt:
        dt = now_utc()
    prnt('--create_share_object', 'func:', func, special, region, dt, iden, job_dt)
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
        dp.data['plugin_id'] = plugin
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
    prnt('--finishScript', log.data['func'], gov, special)
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
    prnt('gov_id',gov_id)
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
        

def data_sort_priority(entry, version=None):
    # prnt('-data_sort_priority',entry)
    # sort received data in order for adding to database
    # needs to be reworked to handle by plugin, not hardcoded like this
    type_order = {'UserPubKey': 0, 'User': 1, 'Validator': 2, 'Node':3, 'NodeReview': 4, 'Sonet':4, 'Wallet':5, 'Tx':6, 'Block':7, 'Region':8,
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

def sync_model(xModel, jsonContent, skip_fields=[], do_save=True, opBlock_data={}, force_sync=False, get_missing_blocks=True, skip_verify=False):
    from utils.locked import verify_obj_to_data, convert_to_dict, get_node_assignment
    from utils.utils import get_plugin
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
            if is_locked(xModel) and not has_field(xModel, 'lastUpdate'):
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
    # userTypes = ['User', 'UserPubKey', 'Wallet', 'Tx', 'UserVote', 'SavePost', 'Follow']
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
            elif xModel._meta.object_name == 'Tx':
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
                    
                    creator_nodes, validator_nodes = get_node_assignment(dt=received_data['created'], chainId=received_data['networkChain'], func=received_data['func'], plugin_id=get_plugin(xModel, id=True), opBlock_data=opBlock_data, strings_only=True)
                    
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
    prnt('-set_model_attrs',obj,get_missing_blocks,debug)
    
    updatedDB = False
    updated_fields = []
    run_on_block_confirmation = False
    block = None
    sigs = []
    fields = obj._meta.fields
    if debug:
        prnt('fields',fields)
        prnt('data',data)
    superFields = {'is_supported':['True',True], 'isVerified':'any', 'is_superuser':'any', 'is_staff':'any', 'is_admin':'any', 'fcm_capable':'any', 'ai_capable':'any', 'validated':'any', 'abilities':['cloudflare'], 'keyType':['guardian','super'], 'node_level':['super'], 'node_type':['intelligence']}
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
                    if superFields[f.name] == 'any' or data[f.name] in superFields[f.name] or getattr(obj, f.name) in superFields[f.name] or isinstance(data[f.name], dict) and any(item in superFields[f.name] for item in data[f.name].keys()):
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
                    elif f.name in ['created','lastUpdate']:
                        if getattr(obj, f.name) != data[f.name]:
                            dt = string_to_dt(data[f.name])
                            if dt < now_utc():
                                updatedDB = True
                                updated_fields.append(f.name)
                                if debug:
                                    prnt('--UDP:',str(getattr(obj, f.name)), str(data[f.name]))
                                setattr(obj, f.name, dt)
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
                        prnt('f HERE:',f.name, data[f.name])
                        prnt("is_id(data[f.name])",is_id(data[f.name]))
                        if not is_id(data[f.name]) and not has_profanity(data[f.name], level=3):
                            prnt('name field:', str(getattr(obj, f.name)), data[f.name], type(data[f.name]))
                            if str(getattr(obj, f.name)) != str(data[f.name]):
                                prnt('should update')
                                updatedDB = True
                                updated_fields.append(f.name)
                                prnt('updated_fields',updated_fields)
                            else:
                                prnt('matches')
                            setattr(obj, f.name, data[f.name])
                            prnt('done set f.name')
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
                            value = string_to_dt(data[f.name])
                            if obj.suspended_dt and getattr(obj, f.name):
                                if obj.suspended_dt < value:
                                    obj.suspended_dt = None
                            if str(getattr(obj, f.name)) != value:
                                updatedDB = True
                                updated_fields.append(f.name)
                            setattr(obj, f.name, value)
                    elif str(f.name) in ['end_life_dt']:
                        if debug:
                            prnt('is end_life_dt',data[f.name])
                        if not obj.end_life_dt:
                            updatedDB = True
                            updated_fields.append(f.name)
                            setattr(obj, f.name, string_to_dt(data[f.name]))
                    elif str(f.name) in ['networkChain','commitChain']:
                        if str(getattr(obj, f.name)) != data[f.name]:
                            from utils.utils import get_plugin
                            if data[f.name] == 'Nodes' and get_plugin(obj, name=True) != 'network':
                                pass
                            elif data[f.name] == 'Sonet':
                                from network.models import _EarthChain_genesisId
                                if get_plugin(obj, name=True) == 'network' or data['id'] == _EarthChain_genesisId:
                                    updatedDB = True
                                    updated_fields.append(f.name)
                                    setattr(obj, f.name, data[f.name])
                            else:
                                updatedDB = True
                                updated_fields.append(f.name)
                                setattr(obj, f.name, data[f.name])
                    elif 'prevVersion' == str(f.name):
                        if debug:
                            prnt('sync prevVersion',data[f.name])
                        if value_is_none(value):
                            value = None
                        else:
                            value = str(data[f.name])
                        if str(getattr(obj, f.name)) != value:
                            updatedDB = True
                            updated_fields.append(f.name)
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
                        from django.core.files.base import ContentFile
                        image_bytes = base64.b64decode(data[f.name])
                        obj.imageField.save(data["file_path"].replace('images/',''), ContentFile(image_bytes), save=False)

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
                                setattr(obj, f.name, string_to_dt(data[f.name]))
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
            prnt('fsyncattr err',f.name,str(e),str(data[f.name])[:100])
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

def super_share(log=None, gov=None, func=None, val_type='super', job_id=None, adjust_created_time=True):

    # other nodes do not seem to verify all of this data on reception

    # super_share can handle a single scrape function or a singular item at a time, not items for multiple chains
    # from blockchain.models import get_scraperScripts, get_latest_dataPacket, get_self_node, Validator, sigData_to_hash, get_operatorData, get_user, logEvent, DataPacket, convert_to_dict
    prnt('-super_share', gov, 'func:', func,'log1:',log,'now_utc',now_utc())
    from network.models import DataPacket, Validator
    from posts.models import Region
    items = []
    objs = []
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
                    # if has_field(i, 'Validator_obj') and i.Validator_obj:
                    if has_field(i, 'signed') and i.signed:
                        # prnt('hashes1',i.id)
                        processed_data['hashes'][i.id] = sigData_to_hash(i)
                    # elif has_field(i, 'validated') and i.validated:
                    #     if has_field(i, 'signed') and i.signed:
                    #         prnt('hashes2',i.id)
                    #         processed_data['hashes'][i.id] = sigData_to_hash(i)
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
                            dataPacket = get_latest_dataPacket(obj)
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
                    if has_field(i, 'Validator_obj') and validate_obj(obj=i, pointer=i, validators=[validator], save_obj=True, update_pointer=True):
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
                    datapacket = get_latest_dataPacket(item)
                if datapacket:
                    datapacket.add_item_to_share(item)
                    prnt('shared',item)
    prnt('done share w netwrok')



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
                                            if reward_walletData:
                                                sig_data = get_sigData(reward_walletData, first_key=True)
                                                reward_wallet_PublicKey = sig_data['publicKey']
                                                reward_wallet_Signature = sig_data['sig']
                                            if proceed and reward_walletData and validator_upk.verify(get_signing_data(reward_walletData), reward_wallet_Signature, userPublicKey):
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
                                                sig_obj.save(reward_wallet)
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

def run_prompt2(prompt, tkns_plus=0, prompt_type='ollama'):
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

def run_prompt(
        prompt: str,
        model_path: str = '',
        n_ctx: int = 9000,
        n_gpu_layers: int = -1,
        max_tokens: int = 1000,
        seed: int = 42,
        temperature: float = 0.7,
        top_p: float = 1.0,
        top_k: int = 40,
        repeat_penalty: float = 1.0,
        strict_determinism: bool = False,
        return_stats: bool = False,
        tkns_plus=0,
        prompt_type='ollama'
    ):
    """
    Run a single query against the given GGUF model, with reproducible
    output across runs.
 
    Reproducibility comes from two things:
      1. seed fixes llama.cpp's RNG, so the same prompt + same seed +
         same temperature/top_p/top_k always samples the same token
         sequence.
      2. top_p/top_k/repeat_penalty are held fixed (not left at whatever
         llama.cpp's defaults happen to be) so nothing besides seed and
         temperature can shift the output between runs.
 
    temperature=0.7 by default -- lower it toward 0 for more focused/
    deterministic-feeling output, raise it for more variation. As long as
    seed and the other sampling params stay the same, re-running with the
    same temperature reproduces the same output.
 
    strict_determinism=False (default) leaves thread count at
    llama-cpp-python's default (multi-threaded, fastest). In principle,
    floating-point reduction order can vary slightly with thread count,
    which can occasionally flip a borderline token. If you need
    byte-identical output guaranteed across machines/runs (not just on
    the same machine), set strict_determinism=True, which pins
    n_threads=1 and n_threads_batch=1 -- slower, but removes that last
    variable.
 
    return_stats=False (default): returns just the response text (str).
    return_stats=True: returns a dict instead --
        {
            "text": str,
            "runtime_seconds": float,       # wall-clock for generation only
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int,
            "tokens_per_second": float,     # completion_tokens / runtime_seconds
        }
    Note: runtime_seconds times the create_chat_completion() call itself
    (prompt processing + generation), not model load -- call query_llama()
    a second time on an already-loaded model if you want to exclude the
    one-time load cost from your timing (this function currently reloads
    the model each call; see note below if you're doing repeated timed
    queries).
 
    Must be called from within the venv created by run_setup() (i.e. run
    this script with the venv's python, or install llama-cpp-python into
    your current interpreter). n_gpu_layers=-1 offloads all layers to
    Metal GPU.
 
    Note: results are reproducible for a fixed model file, library
    version, n_ctx, and n_gpu_layers. Changing any of those (e.g. a
    different quant, or upgrading llama-cpp-python) can shift output,
    since they affect the underlying numerics.
    """
    import time
 
    from llama_cpp import Llama
    prnt('-run_prompt')
    prnt(str(prompt)[:500])
    prnt('len:',len(prompt))
    tkns = get_token_count(prompt)
    n_ctx = n_ctx + tkns_plus
    while tkns > n_ctx and len(prompt) > 1000:
        prompt = prompt[:-700]
        tkns = get_token_count(prompt)


    if not model_path:
        model_dir = "~/Sonet/.data/models"
        model_path_dir = Path(model_dir).expanduser()
        model_url = "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-1M-GGUF/resolve/main/qwen2.5-7b-instruct-1m-q5_k_m.gguf"
        model_filename = model_url.split("/")[-1]
        model_path = model_path_dir / model_filename

    llama_kwargs = dict(
        model_path=model_path,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        seed=seed,
        verbose=False,
    )
    if strict_determinism:
        llama_kwargs.update(n_threads=1, n_threads_batch=1)
 
    llm = Llama(**llama_kwargs)
 
    start = time.perf_counter()
    output = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        seed=seed,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=repeat_penalty,
    )
    elapsed = time.perf_counter() - start
 
    text = output["choices"][0]["message"]["content"]
 
    prnt("runtime_seconds", elapsed)
    prnt("prompt_tokens", usage.get("prompt_tokens", 0))
    prnt("completion_tokens", completion_tokens)
    prnt("tokens_per_second", completion_tokens / elapsed if elapsed > 0 else 0.0)

    if not return_stats:
        return text
 
    usage = output.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    return {
        "text": text,
        "runtime_seconds": elapsed,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": completion_tokens,
        "total_tokens": usage.get("total_tokens", 0),
        "tokens_per_second": completion_tokens / elapsed if elapsed > 0 else 0.0,
    }
 


def request_items(requested_items=[], nodes=None, supported_chain_list=None, request_validators=False, return_updated_count=False, return_updated_objs=False, return_updated_ids=False, return_missing=False, check_consensus=True, downstream_worker=True, get_missing_blocks=True, override_completed=True, recent_request_time=60):
    prntDebug('--request_items', str(requested_items)[:500], now_utc(), len(requested_items), 'nodes',nodes)
    from network.models import Node, Blockchain, DataPacket, EventLog
    from network.utils import process_received_data
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
                                from network.utils import process_received_blocks
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
    check_super_commands()

    if e_brake(1):
        return
    # runs every 10 minutes
    from network.models import DataPacket, Block, Blockchain, Node, Validator, _OperationsChain_genesisId, _block_creation_times, mandatoryChains, selectableChains, block_time_delay
    from utils.locked import check_validation_consensus
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
        from transactions.models import Tx
        for tx in Tx.objects.exclude(enacted=True).exclude(ReceiverBlock_obj=None).filter(enact_dt__lt=now_utc()).filter(validated=True).order_by('enact_dt'):
            if not exists_in_worker('enact_transaction', id=tx.id):
                prnt('enact_transaction tx',tx)
                # result['unvalidated_txs'].append(tx.id)
                django_rq.get_queue('main').enqueue(tx.enact_transaction, id=tx.id, job_timeout=60, result_ttl=7200)
        for tx in Tx.objects.filter(validated=True).exclude(ReceiverBlock_obj__validated=True).order_by('ReceiverWallet_obj__id','created').distinct('ReceiverWallet_obj__id'):
            if not exists_in_worker('send_for_block_creation', id=tx.id):
                prnt('send_for_block_creation1 tx',tx)
                result['unvalidated_txs'].append(tx.id)
                django_rq.get_queue('main').enqueue(tx.send_for_block_creation, id=tx.id, downstream_worker=False, job_timeout=60, result_ttl=7200)
        for tx in Tx.objects.filter(validated__isnull=True).order_by('created'):
            if not exists_in_worker('send_for_block_creation', id=tx.id):
                prnt('send_for_block_creation2 tx',tx)
                result['unvalidated_txs'].append(tx.id)
                django_rq.get_queue('main').enqueue(tx.send_for_block_creation, id=tx.id, downstream_worker=False, job_timeout=60, result_ttl=7200)

        self_node = Node.objects.filter(id=self_node_id).values('chain_array','region_array','plugin_array').first()
        prnt('self_node',self_node)
        prnt("self_node['chain_array']+['All']",self_node['chain_array']+['All'])
        dataPackets = DataPacket.objects.filter(Node_obj__id=self_node_id, func='share').filter(Q(networkChain__in=self_node['plugin_array']+self_node['region_array']+['All'])|Q(Region_obj__id__in=self_node['region_array'])).exclude(networkChain=_OperationsChain_genesisId).exclude(data={}).defer('data','notes')
        for dp in dataPackets:
            if not exists_in_worker('broadcast_dp', queue_name=['chat'], iden=dp.id):
                django_rq.get_queue('chat').enqueue(dp.broadcast_dp, iden=dp.id, job_timeout=300, result_ttl=7200)

        processes = DataPacket.objects.filter(func__icontains='process', updated_on_node__lte=now_utc() - datetime.timedelta(minutes=9.5), created__gt=now_utc() - datetime.timedelta(minutes=50)).exclude(func__icontains='completed').defer('data').order_by('created')
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
                                import network.utils as share_funcs
                                f = getattr(share_funcs, func)  
                                queue.enqueue(f, log.id, job_timeout=300, result_ttl=7200)
                            except Exception as e:
                                prnt('err 58351', str(e))

        # return
        # every 60 mins create block if data
        prnt("self_node['chain_array']",self_node['chain_array'])
        prnt("self_node['region_array']",self_node['region_array'])
        prnt("self_node['plugin_array']",self_node['plugin_array'])
        if dt.minute in [t-20 for t in _block_creation_times]:
            node_count = Node.objects.filter(activeNode=True).count()
            if node_count and (node_count < 3 and random.randrange(node_count) == 0 or random.randrange(node_count/3) == 0):
                from network.models import CommitData 
                commit = CommitData()
                commit, reveal = CommitData.create_salt_pair()
                # broadcast commit
        elif dt.minute in [t-10 for t in _block_creation_times]:
            from network.models import RevealData 
            reveal = RevealData.objects.filter(Node_obj__id=self_node_id, created=dt-datetime.timdelta(minutes=10)).first()
            if reveal:
                # broadcast
                ...
        elif dt.minute in _block_creation_times or test==True:
            block_assigned = False
            from network.models import Sonet, universalChains, _SonetChain_genesisName, _EarthChain_genesisId, reward_models
            universalChains.remove(_OperationsChain_genesisId)
            universalChains.remove(_SonetChain_genesisName)
            s = Sonet.objects.values('id').first()
            universalChains.append(s['id'])
            universalChains.append(_EarthChain_genesisId)
            prnt('universalChains',universalChains)
            chains = Blockchain.objects.filter(genesisId__in=universalChains, last_block_datetime__lte=dt - datetime.timedelta(minutes=block_time_delay()-10)).exclude(queuedData={}).defer('queuedData')
            for chain in chains:
                prnt('chain1',chain)
                block_assigned = chain.new_block_candidate(self_node=self_node_id, dt=dt)
                prntDebug('block_assigned1::',block_assigned)
                if block_assigned:
                    result['new_block_candidate'].append(chain.genesisName)
                    result['new_block_candidate'].append(block_assigned.id)
            try:
                p_array = self_node['plugin_array'] if self_node['plugin_array'] else []
                r_array = self_node['region_array'] if self_node['region_array'] else []
                supported = list(p_array) + list(r_array)
                chains = Blockchain.objects.filter(genesisId__in=supported, last_block_datetime__lte=dt - datetime.timedelta(minutes=block_time_delay()-10)).exclude(queuedData={}).defer('queuedData').order_by('?')
                for c in chains:
                    prnt('chain2',c)
                    block_assigned = c.new_block_candidate(self_node=self_node_id, dt=dt)
                    prntDebug('block_assigned2::',block_assigned)
                    if block_assigned:
                        result['new_block_candidate'].append(c.genesisName)
                        result['new_block_candidate'].append(block_assigned.id)

                chains = Blockchain.objects.exclude(rewardsData={}).exclude(queuedData={}).filter(last_block_datetime__lte=dt - datetime.timedelta(minutes=block_time_delay()-10)).defer('queuedData').order_by('?')
                for c in chains:
                    prnt('chain3',c)
                    block_assigned = c.new_block_candidate(self_node=self_node_id, dt=dt)
                    prntDebug('block_assigned3::',block_assigned)
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
        plugins = Plugin.objects.filter(id__in=self_node.plugin_array, app_name='legis')
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

def send_for_validation(log=None, gov=None, force_send=False):
    prnt('--send_for_validation() now_utc:',now_utc(), gov, log)
    from network.models import DataPacket, intelligence_funcs
    from utils.locked import get_node_assignment, convert_to_dict, sign_for_sending, hash_obj_id, get_relevant_nodes, sign_obj
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
    plugin_id = None
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
            plugin_id = log.data['plugin_id']
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
            if 'gov_level' in log.data:
                gov_level = log.data['gov_level']
            elif items and any(i for i in items if i._meta.object_name == 'Government'):
                for i in items:
                    if i._meta.object_name =='Government':
                        gov = i
                        gov_level = gov.gov_level # gov_level not really needed
                        break
            prnt('gov_level',gov_level)
            if items:
        
                q = 2
                if 'created' in log.data:
                    job_time = string_to_dt(log.data['created'])
                
                func = log.data['func']
            region_name = log.data['region_name']
            region_id = log.data['region_id']
            from posts.models import Region
            region = Region.objects.filter(id=region_id).first()

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
        if not log.data.get('plugin_id', None):
            if items:
                from utils.utils import get_plugin
                log.data['plugin_id'] = get_plugin(items[0], id=True)
            else:
                log.data['plugin_id'] = None
        creator_nodes, validator_nodes = get_node_assignment(dt=job_time, func=func, chainId=region.id, plugin_id=log.data['plugin_id'], strings_only=False, nodeType='maintainer')
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

            data_to_send = {'type':'for_validation', 'packet_id':packet_id, 'job_started':job_started, 'job_finished':job_finished, 'func':func, 'plugin_id':plugin_id, 'senderId':self_node_id, 'region_id':region.id, 'gov_level':gov_level, 'scrapers':[s for s in creator_nodes], 'validator':validator_node, 'region_name':region.Name, 'content_length':content_length, 'content': compressed_data}
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
                    data_to_send = {'type':'job_completed', 'packet_id':packet_id, 'job_started':job_started, 'job_finished':job_finished, 'func':func, 'plugin_id':plugin_id, 'senderId':self_node_id, 'region_id':region.id, 'gov_level':gov_level, 'scrapers':[s for s in creator_nodes], 'validator':validator_node, 'region_name':region.Name, 'content_length':content_length, 'content': compressed_data}
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



def compute_creator_reveal_violations(log_dt_start, log_dt_end):
    """
    Returns:
        { node_id: violation_count }
    Only counts a violation if a majority of reviewers who reported on this
    target this window agree one occurred.
    """
    from django.db.models import Count, Q
    from network.models import NodeReview

    reviews = NodeReview.objects.filter(
        lastUpdate__gte=log_dt_start,
        lastUpdate__lt=log_dt_end,
    )

    consensus = (
        reviews
        .values("TargetNode_obj")
        .annotate(
            flagged=Count("id", filter=Q(creator_reveal_violations__gt=0)),
            clear=Count("id", filter=Q(creator_reveal_violations=0)),
        )
    )

    results = {}
    for row in consensus:
        node_id, flagged, clear = row["TargetNode_obj"], row["flagged"], row["clear"]
        if flagged > clear:
            max_violations = (
                reviews.filter(TargetNode_obj=node_id, creator_reveal_violations__gt=0)
                .order_by('-creator_reveal_violations')
                .values_list('creator_reveal_violations', flat=True)
                .first()
            )
            results[node_id] = max_violations or 1

    return results
    
def compute_reveal_success(log_dt_start, log_dt_end):
    """
    Returns:
        { node_id: reveal_success }
    Ground truth per target: average of the (cubic-penalized) reveal_success
    each reviewer locally observed and broadcast about this target. No
    reviewer-credibility step — this is a directly observable fact per
    reviewer, not an opinion to be checked against consensus.
    """
    from django.db.models import Avg
    from network.models import NodeReview

    reviews = NodeReview.objects.filter(
        lastUpdate__gte=log_dt_start,
        lastUpdate__lt=log_dt_end,
    )

    scores = (
        reviews
        .values("TargetNode_obj")
        .annotate(avg_reveal_success=Avg("reveal_success"))
    )

    return {row["TargetNode_obj"]: row["avg_reveal_success"] or 0.5 for row in scores}

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

        # results[node_id] = completed / total if total else 0
        results[node_id] = completed / total if total else 0.5

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

        # results[node_id] = aligned / total if total else 0
        results[node_id] = aligned / total if total else 0.5

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

    # block_successes = compute_block_success(log_dt_start, log_dt_end)
    # alignments = compute_consensus_alignment(log_dt_start, log_dt_end)
    # job_successes = compute_job_success(log_dt_start, log_dt_end)
    block_successes = compute_block_success(log_dt_start, log_dt_end)
    alignments = compute_consensus_alignment(log_dt_start, log_dt_end)
    job_successes = compute_job_success(log_dt_start, log_dt_end)
    reveal_successes = compute_reveal_success(log_dt_start, log_dt_end)
    creator_violations = compute_creator_reveal_violations(log_dt_start, log_dt_end)

    # block_successes = compute_block_success(log_dt_start, log_dt_end)
    # alignments = compute_consensus_alignment(log_dt_start, log_dt_end)
    # job_successes = compute_job_success(log_dt_start, log_dt_end)
    # reveal_successes = compute_reveal_success(log_dt_start, log_dt_end)


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
        "reveal_success": reveal_successes.get(r.TargetNode_obj.id, 0.5),
        "trust_score": r.trust_score,
        "interactions": r.interactions,
        "timestamp": int(r.lastUpdate.timestamp())
            })

        # peer_reviews[r.TargetNode_obj.id].append({
        # "response_success": r.response_success,
        # "job_success": job_successes.get(r.CreatorNode_obj.id, 0.5),
        # "block_success": block_successes.get(r.TargetNode_obj.id, 0.5),
        # "consensus_alignment": alignments.get(r.TargetNode_obj.id, 0.5),
        # "trust_score": r.trust_score,
        # "interactions": r.interactions,
        # "timestamp": int(r.lastUpdate.timestamp())
        #     })
        if r.CreatorNode_obj.id == self_node_id:
            review_map[r.TargetNode_obj.id] = r

    reviews = []
    block_successes.clear()
    alignments.clear()
    job_successes.clear()
    reveal_successes.clear()

    METRIC_WEIGHTS = {
        "response_success": 0.10,
        "job_success": 0.30,
        "block_success": 0.25,
        "consensus_alignment": 0.20,
        "reveal_success": 0.15,
    }

    # reviews = []
    # block_successes.clear()
    # alignments.clear()
    # job_successes.clear()

    # METRIC_WEIGHTS = {
    #     "response_success": 0.15,
    #     "job_success": 0.35,
    #     "block_success": 0.25,
    #     "consensus_alignment": 0.25,
    # }
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

        # updated_trust = (
        #     (1 - lr) * previous_trust
        #     + lr * observed_trust
        # )
        updated_trust = (
            (1 - lr) * previous_trust
            + lr * observed_trust
        )

        # Assigned-creator reveal violation: direct haircut, bypasses the
        # weighted blend entirely so it can't be absorbed by otherwise-good
        # metrics. Compounds per violation this window so repeat offenders
        # get hit progressively harder, not just linearly.
        violations = creator_violations.get(node_id, 0)
        if violations:
            penalty = 1 - (0.6 ** violations)   # 1 viol -> -40%, 2 -> -64%, 3 -> -78%
            updated_trust *= (1 - penalty)

        # clamp
        updated_trust = max(TRUST_FLOOR, min(TRUST_CEILING, updated_trust))

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

def sign_post_header(data=None, headers=None, operatorData=None, self_node=None, target_node=None, post='post', address_type=None):
    prnt('-sign_post_header',target_node)
    data = declare_var(data, {})
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
    prnt('total_size',total_size,to_megabytes(data_str),'MB')

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
        
def connect_to_node(node, url, data=None, self_node=None, content=None, headers=None, operatorData=None, timeout=None, get=False, stream=False, node_is_string=False, log_reponse_time=True, attempts=2, address_type='address'):
    prnt('---connect to node---', node, url, now_utc(),timeout,address_type)
    content = declare_var(content, {})
    headers = declare_var(headers, {})
    timeout = declare_var(timeout, (10,15))
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
                # prnt('response.elapsed.total_seconds()',response.elapsed.total_seconds() if response else None)
                if response and response.status_code == 200:
                    # prnt('success connection')
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
    
def downstream_broadcast(broadcast_list, url, sendingData, headers=None, operatorData=None, self_node=None, target_node_id=None, skip_self=False, timeout=None, stream=False, exclude=None):
    prnt('--downstream_broadcast now_utc:', now_utc(), url, broadcast_list, 'exclude:',exclude)
    prnt('data',str(sendingData)[:1000])
    headers = declare_var(headers, {})
    exclude = declare_var(exclude, [])
    timeout = declare_var(timeout, (50,60))
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

