from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db.models import Q

from utils.models import (
    BinaryBase62Field, BinaryBase64urlField,
    prnt, prntn, e_brake, get_operatorData, get_operator_obj, now_utc,
    prntDev, prntDebug,
    string_to_dt, is_test_env, testing, 
    get_timeData, is_id, 
    chunk_list, chunk_dict, get_chain_id,
    get_dynamic_model, get_model, exists_in_worker, initial_save, downstream_broadcast, get_node_list, get_model_prefix,
    deactivate, convert_to_datetime, dynamic_bulk_update, get_app_name, get_pointer_type, retrieve_transaction, logBroadcast, get_app_info,
    has_method, has_field, value_is_none, round_time, get_self_node, find_or_create_chain_from_object, get_data, sigData_to_hash, is_locked
)
from utils.locked import hash_obj_id, verify_obj_to_data, sort_for_sign, validate_obj, dt_to_string, sign_obj, get_relevant_nodes_from_block, get_node_assignment, check_block_contents, get_commit_data, get_signing_data, sign_for_sending, convert_to_dict, check_validation_consensus, verify_data

import datetime
from dateutil.parser import parse
import hashlib
import json
import time
import random
import requests
import django_rq


_number_of_peers = 2 # used for downstream_broadcast
failure_range = 1.1 # minimum number of hours since last access for node to receive suspended_dt
recent_failure_count = 7 # minimum number of fails for node to receive suspended_dt
fails_to_strike = 10 # x failures == 1 strike
recent_failure_range = 3 # how many days between strikes for node if x failures
too_many_strike_count = 10 # deactivate node after x strikes
striking_days = 30 # too_many_strike count within this number of days before being deactivated
max_commit_window = 11 # number of days for an obj to be committed to a block
max_validation_window = 7 # number of days for an obj to be validated
_number_of_scrapers = 2
_user_peer_count = 12
_block_creator_count = 1
_block_validator_count = 15
_block_creation_times = [50, 20] # change here and block_time_delay
# _opBlock_creation_times = [30, 0]


def get_required_validator_count(dt=None, obj=None, func=None, genesisId=None, node_ids=None, include_initializers=False, opBlock_data={}):
    # prnt('-default get_required_validator_count')
    if obj and obj._meta.object_name == 'Block':
        return obj.get_required_validator_count(node_ids=node_ids)
    if obj and obj._meta.object_name == 'User':
        return 7
    elif node_ids == None:
        if obj and has_field(obj, 'networkChain'):
            if has_field(obj, 'created'):
                dt = obj.created
            if obj.networkChain:
                chain = Blockchain.objects.filter(id=obj.networkChain).first()
            else:
                chain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
            if chain:
                node_ids = get_relevant_nodes_from_block(dt=dt, genesisId=chain.genesisId, node_ids_only=True)
        if node_ids == None:
            if obj:
                if has_field(obj, 'created'):
                    dt = obj.created
            if not dt:
                dt = now_utc()
            node_ids = get_relevant_nodes_from_block(dt=dt, node_ids_only=True)
    if func:
        # for scraping functions
        if include_initializers:
            return 3, 1 # scrapers, validators
        return 1 
    elif obj:
        if isinstance(obj, models.Model):
            prnt('obj',obj)
            if obj._meta.object_name == 'Transaction' and obj.SenderBlock_obj:
                prnt('sender')
                return obj.SenderBlock_obj.get_required_validator_count(node_ids=node_ids, opBlock_data=opBlock_data)
            elif obj._meta.object_name == 'Transaction' and obj.ReceiverBlock_obj:
                prnt('receiver')
                return obj.ReceiverBlock_obj.get_required_validator_count(node_ids=node_ids, opBlock_data=opBlock_data)
            elif obj._meta.object_name == 'Transaction' and obj.senderBlockId:
                prnt('sender by senderBlockId')
                temp_block = Block(id='obj.senderBlockId', DateTime=obj.created, Blockchain_obj_id=get_chain_id(obj.senderChainGenId))
                return temp_block.get_required_validator_count(node_ids=node_ids, opBlock_data=opBlock_data)
        # else account for userTransaction initialization, before block is created
        if not dt:
            if has_field(obj, 'DateTime'):
                dt = obj.DateTime
            elif has_field(obj, 'created'):
                dt = obj.created
            
    else:
        # I don't know what this balognia is below - likely important at one time
        if not dt:
            ...
        if dt > Sonet.objects.first().created: # adjust here, covers userTransaction objs, not sure if anything else.
            vals = 10
            creator_options = 4
        else:
            vals = 10
            creator_options = 4
        
        if include_initializers: # handles userTransaction blocks, allows for multiple creators if first one is unavailable
            if (creator_options + vals) > len(node_ids):
                vals = int(vals/2)
                run = True
                while run and (creator_options + vals) > len(node_ids):
                    creator_options = int(creator_options/2)
                    vals = int(vals/2)
                    if vals <= 1 and creator_options <= 1:
                        run = False
                        vals = 1
                        creator_options = 1
            return creator_options, vals
        else:
            if len(node_ids) <= 1:
                return 1
            elif len(node_ids) <= 5:
                return len(node_ids) - 1 # minus creator, all remaining
            elif vals > len(node_ids):
                return ((len(node_ids)-1)*0.75) # minus creator, 75% of remaining
            else:
                return vals
        
def block_time_delay(obj=None, get_default=False): # minimum time (mins) before next block on chain    
    def node_count():
        # prnt('node_count')
        num = Node.objects.filter(Block_obj__validated=True).exclude(activated_dt=None).count()
        if not num:
            opDelay = 60
        elif num <= 2:
            opDelay = (60*1)
        elif num <= 5:
            opDelay = (60*1)
        elif num <= 20:
            opDelay = (60*2)
        elif num <= 50:
            opDelay = (60*3)
        elif num <= 100:
            opDelay = (60*4)
        elif num <= 200:
            opDelay = (60*5)
        else:
            opDelay = (60*6)
        return opDelay
    if get_default:
        other = 60
        wallet = 30 # used for block validation timeout, not block creation
        opDelay = node_count()
    else:
        
        try:
            blockData = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).values('opData','extraData').order_by('-index').first()
            # wallet = 30 # 30 minutes between transactions
            if blockData['extraData']:
                other = blockData['extraData']['opData']['block_time_delay']
                opDelay = blockData['extraData']['opData']['opBlock_time_delay']
                wallet = blockData['extraData']['opData']['wallet_time_delay']
            else:
                other = blockData['opData']['block_time_delay']
                opDelay = blockData['opData']['opBlock_time_delay']
                wallet = blockData['opData']['wallet_time_delay']
        except:
            opDelay = node_count()
            other = 60

    if not obj:
        return other
    if isinstance(obj, str):
        if obj.lower() in ['operations','nodes','node']:
            return opDelay
        elif obj.lower() == 'wallet':
            return wallet
        else:
            return other
    else:
        if has_field(obj, 'networkChain') and obj.networkChain == get_chain_id(_OperationsChain_genesisId) or has_field(obj, 'genesisType') and obj.genesisType == _OperationsChain_genesisId:
            return opDelay
        elif has_field(obj, 'genesisType') and obj.genesisType.lower() == 'wallet':
            return wallet
        else:
            return other

def get_default_opData():
    max_pos_node = Node.objects.filter(Block_obj__validated=True).order_by('-pos').values('pos').first()
    if max_pos_node:
        max_pos = max_pos_node['pos']
    else:
        max_pos = 1
    return {'number_of_peers':_number_of_peers,'block_creator_count':_block_creator_count,'block_creation_times':_block_creation_times,'block_time_delay':block_time_delay(get_default=True),'opBlock_time_delay':block_time_delay('operations', get_default=True),'walletBlock_time_delay':block_time_delay('wallet',get_default=True),'block_validator_count':_block_validator_count,'max_pos':max_pos}

_OperationsChain_genesisId = 'Nodes'
_KeyChain_genesisId = 'Keys'
_AccountChain_genesisId = 'Accounts'
_SonetChain_genesisName = 'Sonet'
_EarthChain_genesisId = 'regSoshCP31gSfl6p3mLw8dZ'

mainChains = [_OperationsChain_genesisId, _KeyChain_genesisId, _AccountChain_genesisId, _SonetChain_genesisName, _EarthChain_genesisId]
default_apps = ['accounts', 'network', 'posts']
if is_test_env():
    default_apps.append('transactions')
    default_apps.append('legis')

universalChains = [_KeyChain_genesisId, _OperationsChain_genesisId, _SonetChain_genesisName, _AccountChain_genesisId]
mandatoryChains = [_KeyChain_genesisId, _OperationsChain_genesisId, _SonetChain_genesisName, _AccountChain_genesisId] # careful usage in get_broadcast_list, get_relevant_nodes_from_block
specialChains = ['New']
selectableChains = ['Region','Plugin']
user_created_modifiable_models = ['UserFollow','UserSavePost','DataPacket','Node','NodeReview']
script_created_modifiable_models = ['Region','District','Party']
unshared_models = ['Post','UserAction','UserNotification','Wallet','Blockchain','EventLog','Keyphrase','KeyphraseTrend']
share_to_all = ['oh','nod','nrev','reg','usr','upk','uver','udat'] # this sends to relays as well, relay shouldnt need reg, uver and udat. can remove those under process_received_data, may cause relay to request those items in other locations
intelligence_funcs = ['summarize_meetings', 'summarize_bills']
node_types = ['server','maintainer','server/maintainer','relay','intelligence']
reward_models = ['1govSo'] # only Government chain - requires Region_obj on model - hardcoded to gov

model_prefixes = {'Sonet':'oh','Plugin':'plg','Signature':'sig','DataPacket':'dpk','Node':'nod','NodeReview':'nrev','NodeRecord':'nrec','Block':'blc','Validator':'val','Blockchain':'chn','EventLog':'log',}



def default_token_info():
    return {'name': 'Token', 'plural': 'Tokens', 'pronunciation': 'toe-ken'}

def default_repo_info():
    return {'source':'github.com', 'repo':'SoSayUs', 'branch':'main'}

class Sonet(models.Model):
    networkChain = models.CharField(max_length=50, default="Sonet", blank=True)
    # commitChain = 'Sonet'
    # to create new chain set commitChain, then link to genesis obj of existing chain
    # ie: commitChain = 'Region', Region_obj = models.ForeignKey('posts.Region', blank=True, null=True, on_delete=models.PROTECT)
    # then set networkChain to self._meta.object_name
    # if adding obj to existing chain, omit commitChain, set networkChain to match linked field of existing genesis obj
    # ie: networkChain = 'Region', Region_obj = models.ForeignKey('posts.Region', blank=True, null=True, on_delete=models.PROTECT)
    # if networkChain not set, obj will be broadcast via All
    is_modifiable = True
    # is_modifiable required to change fields on objs containing valid Block_obj
    # is_modifiable models can be committed to new block if commit data has changed
    # fields not committed to block can change without requiring new block if hash not committed as well
    # hash_to_id fields cannot be changed at all
    # ModifiableModel required for script created models to include proposed_modification field (posts.models)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    # if obj is to be committed to chain, include field Block_obj. ideally blockchainId as well
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    Title = models.CharField(max_length=200, default="x")
    Subtitle = models.CharField(max_length=200, default=None, blank=True, null=True)
    LogoLink = models.CharField(max_length=200, default="img/default_logo.png")
    Domain = models.CharField(max_length=200, default="")
    token_info = models.JSONField(default=default_token_info, blank=True, null=True)
    info = models.JSONField(default=None, blank=True, null=True)
    repo = models.JSONField(default=default_repo_info, blank=True, null=True)
    # anonymous_users = models.BooleanField(default=True)
    # private_content = models.BooleanField(default=False)
    # approved_nodes_only = models.BooleanField(default=False)
    node_requirements = models.JSONField(default=None, blank=True, null=True)
    signed = models.JSONField(default=dict)

    def __str__(self):
        return 'Sonet:%s' %(self.Title)
    
    class Meta:
        ordering = ['created']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Sonet', 'networkChain': 'Sonet', 'modlVer': 1, 'id': None, 'created': None, 'lastUpdate': None, 'Block_obj': None, 'Title': 'x', 'Subtitle': None, 'LogoLink': 'img/default_logo.png', 'Domain': '', 'token_info': {'name': 'Token', 'plural': 'Tokens', 'pronunciation': 'toe-ken'}, 'info': None, 'repo': {'source': 'github.com', 'repo': 'SoSayUs', 'branch': 'main'}, 'node_requirements': None, 'signed': {}}
        
    def delete(self):
        if not self.Block_obj:
            exists = Sonet.objects.exclude(id=self.id).exists()
            if exists:
                super(Sonet, self).delete()
        return 0, {}

    def initialize(self):
        self.modlVer = self.latestVer
        if self.id is None:
            self.id = hash_obj_id(self)
        return self
    
    def boot(self):
        prnt('-boot sonet')
        from accounts.models import User
        sonetChain = Blockchain.objects.filter(genesisId=self.id).first()
        if not sonetChain:
            sonetChain = Blockchain(genesisId=self.id, genesisType='Sonet', genesisName='Sonet', created=self.created)
            sonetChain.save()
        sonetChain.add_item_to_queue(self)
        for i in User.objects.filter(Block_obj=None):
            sonetChain.add_item_to_queue(i)
        for i in Node.objects.filter(Block_obj=None):
            sonetChain.add_item_to_queue(i)
        nodeChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
        if not nodeChain:
            nodeChain = Blockchain(genesisId=_OperationsChain_genesisId, genesisType=_OperationsChain_genesisId, genesisName=_OperationsChain_genesisId, created=self.created)
            nodeChain.save()
        prnt('nodeChain',nodeChain)
    
    def committed_data_matches(self):
        from utils.models import is_obj_commit_valid
        return is_obj_commit_valid(self)
    
    def save(self, sig=None, *args, **kwargs):
        prntDebug('-saving sonet...')
        from utils.models import share_with_network, get_sigData, is_id, hash_upk_id
        from accounts.models import User, UserPubKey
        sig_data = get_sigData(self.signed, first_key=True)
        pkey = sig_data['pk']
        if is_id(pkey):
            iden = pkey
        else:
            iden = hash_upk_id(pkey)
        prnt('iden',iden)
        dt = string_to_dt(self.lastUpdate)
        if Block.objects.filter(Blockchain_obj__genesisType='User', validated=True).exists():
            upks = UserPubKey.objects.filter(keyType='guardian', id=iden, created__lte=self.lastUpdate, Block_obj__validated=True).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=dt)).only('publicKey') # self.lastUpdate should be less than upk.end_life_dt
        else:
            upks = UserPubKey.objects.filter(keyType='guardian', id=iden, created__lte=self.lastUpdate).filter(Q(end_life_dt=None)|Q(end_life_dt__gt=dt)).only('publicKey') # self.lastUpdate should be less than upk.end_life_dt
        for upk in upks:
            prnt('upk',upk)
            if verify_data(get_signing_data(self), upk.publicKey, signature=sig):
                super(Sonet, self).save(*args, **kwargs)
                self.boot()
                share_with_network(self)
                break

class Plugin(models.Model):
    commitChain = models.CharField(max_length=50, default="Sonet", blank=True)
    networkChain = models.CharField(max_length=50, default="Plugin", blank=True)
    is_modifiable = True
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, on_delete=models.SET_NULL)
    Title = models.CharField(max_length=200, default="x")
    AbbrTitle = models.CharField(max_length=200, default=None, blank=True, null=True)
    Subtitle = models.CharField(max_length=200, default=None, blank=True, null=True)
    Description = models.TextField(default=None, blank=True, null=True)
    menu_index = models.JSONField(default=None, blank=True, null=True)
    data = models.JSONField(default=None, blank=True, null=True)
    app_name = models.CharField(max_length=200, default="x")
    plugin_prefix = models.CharField(max_length=200, default=None, blank=True, null=True)
    model_prefixes = models.JSONField(default=None, blank=True, null=True)
    user_facing = models.BooleanField(default=False)
    signed = models.JSONField(default=dict)

    def __str__(self):
        return 'Plugin:%s' %(self.Title)
    
    class Meta:
        ordering = ['created']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Plugin', 'commitChain': 'Sonet', 'networkChain': 'Plugin', 'modlVer': 1, 'id': None, 'created': None, 'lastUpdate': None, 'Block_obj': None, 'User_obj': None, 'Title': 'x', 'AbbrTitle': None, 'Subtitle': None, 'Description': None, 'menu_index': None, 'data': None, 'app_name': 'x', 'plugin_prefix': None, 'model_prefixes': None, 'user_facing': False, 'signed': {}}
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['id','created','User_obj','Title','model_prefixes','app_name','assign_plugin_prefix'] # should create a new block if any of these are changed
        
    def assign_plugin_prefix(self, addition=0, check_data=None):
        prnt('-assign_plugin_prefix',self.id)

        if check_data:
            prnt('check_data',check_data)
            if 'plugin_prefix' not in check_data:
                return False
            if self.Block_obj and self.Block_obj.validated:
                plugin_prefix = str(self.Block_obj.data[self.id]['plugin_prefix'])
                if self.plugin_prefix != plugin_prefix:
                    self.plugin_prefix = plugin_prefix
                    self.save()
                return True
            if 'app_name' in check_data['app_name'] and check_data['app_name'] in default_apps:
                if self.created < Sonet.objects.first().created + datetime.timedelta(minutes=10): 
                    if str(check_data['plugin_prefix']) == '0':
                        return True
                return False
            check_num = str(check_data['plugin_prefix'])
            if check_num == '0':
                latest_plugin = None
            else:
                latest_plugin = Plugin.objects.exclude(Block_obj=None).exclude(id=self.id).filter(plugin_prefix=check_num).first()
            if latest_plugin:
                return False
            return True # only checks that plugin_prefix not already used
        if self.app_name in default_apps:
            if self.created < Sonet.objects.first().created + datetime.timedelta(minutes=10): 
                return {'plugin_prefix':'0'}
        if self.Block_obj and self.Block_obj.validated:
            plugin_prefix = str(self.Block_obj.data[self.id]['plugin_prefix'])
            if self.plugin_prefix != plugin_prefix:
                self.plugin_prefix = plugin_prefix
                self.save()
            return {'plugin_prefix':str(self.plugin_prefix)}
        latest_plugin = Plugin.objects.exclude(Block_obj=None).order_by('-plugin_prefix').values('plugin_prefix').first()
        if latest_plugin:
            return {'plugin_prefix':str(int(latest_plugin['plugin_prefix']) + addition)}
        else:
            return {'plugin_prefix':'1'}

    def block_conditions(self):
        if self.commitChain == Blockchain.objects.filter(genesisType='Sonet').first().genesisId:
            if self.networkChain == self.id:
                return True
        return False
    
    def on_confirmation(self, block):
        self.plugin_prefix = block.data[self.id]['plugin_prefix']
        return self
        # return self, ['plugin_prefix']
    
    def initialize(self):
        self.modlVer = self.latestVer
        if self.id is None:
            self.id = hash_obj_id(self)
            self.created = now_utc()
            self.commitChain = Blockchain.objects.filter(genesisType='Sonet').first().genesisId
            self.networkChain = self.id

            if not self.model_prefixes:
                import importlib
                from django.conf import settings
                import string
                app_dict = {}
                for app in settings.INSTALLED_APPS:
                    try:
                        if app == self.app_name:
                            models_module = importlib.import_module(f"{app}.models")
                            if hasattr(models_module, "model_prefixes"):
                                prefixes = getattr(models_module, "model_prefixes")
                                if isinstance(prefixes, dict):
                                    for key, value in prefixes.items():
                                        if len(value) >= 2 and all(c in string.ascii_letters for c in value):
                                            app_dict[key] = str(value)[:5].lower() # model prefixes must be 2-5 chars. a-z
                            break
                    except ModuleNotFoundError:
                        continue
                    except Exception:
                            continue
                self.model_prefixes = app_dict
                
        # user must set User_obj, Title, app_name, app_dir, model_prefixes
        # optionally set Subtitle, Description, data
        return self

        
    def delete(self):
        # if not is_locked(self):
            # delete
        ...
    
    def committed_data_matches(self):
        from utils.models import is_obj_commit_valid
        return is_obj_commit_valid(self)
    
    def pre_save(self, *args, **kwargs):
        if self.committed_data_matches():
            return 'valid'
        else:
            from utils.locked import verify_obj_to_data
            if verify_obj_to_data(self, self):
                committed_fields = self.commit_data()
                mutable_fields = ['model_prefixes','Title','AbbrTitle','Subtitle','Description','user_facing']
                block_fields = self.Block_obj.data[self.id]
                prnt("block_fields",block_fields)
                valid_save = True
                new_block = False
                for f in self.get_version_fields():
                    attr = getattr(self, f)
                    if isinstance(attr, datetime.datetime):
                        attr = dt_to_string(attr)
                    elif f.endswith('_obj') and attr:
                        attr = attr.id
                    elif f in block_fields:
                        if value_is_none(block_fields[f]) and value_is_none(attr):
                            continue
                        elif attr == block_fields[f]:
                            continue
                        else:
                            prnt('field has changed1', f, attr)
                            new_block = True
                            if f not in mutable_fields:
                                valid_save = False
                                return 'invalid'
                            elif f == 'model_prefixes':
                                # only add, not remove items - check against block
                                if not all(key for key, value in block_fields[f].items() if key in attr and attr[key] == value):
                                    prnt('break2', block_fields[f])
                                    valid_save = False
                                    return 'invalid'    
                if valid_save:
                    if new_block:
                        return 'new_block'
                    else:
                        return 'valid'
        return 'invalid'
    
    def save(self, *args, **kwargs):
        prntDebug('-saving plugin...')
        pre_save_result = self.pre_save()
        if pre_save_result == 'valid':
            super(Plugin, self).save(*args, **kwargs)
        elif pre_save_result == 'new_block':
            self.Block_obj = None
            super(Plugin, self).save(*args, **kwargs)
            blockchain = Blockchain.objects.filter(genesisId=self.id).first()
            blockchain.add_item_to_queue(self)
            from utils.models import get_latest_dataPacket
            dp = get_latest_dataPacket(chain=blockchain.id)
            dp.add_item_to_share(self)
        else:
            prnt('invalid plugin save')
        
    def boot(self):
        pluginChain = Blockchain.objects.filter(genesisId=self.id).first()
        if not pluginChain:
            pluginChain = Blockchain(genesisName=self.app_name, genesisType=self._meta.object_name, genesisId=self.id, created=self.created)
            pluginChain.save()
        if not self.Block_obj:
            pluginChain.add_item_to_queue(self)

        chain = Blockchain.objects.filter(genesisId=self.id).first()
        if not chain:
            chain = Blockchain(genesisName=self.app_name, genesisType=self._meta.object_name, genesisId=self.id, created=self.created)
            chain.save()
        if not self.Block_obj:
            chain.add_item_to_queue(self)

class Signature(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    pointerId = BinaryBase62Field(max_byte_length=30, db_index=True)
    pointerKey = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="signatures", null=True, blank=True, default=None)
    Pointer_obj = GenericForeignKey('pointerKey', 'pointerId')
    Upk_obj = models.ForeignKey('accounts.UserPubKey', blank=True, null=True, on_delete=models.PROTECT)
    sig = BinaryBase64urlField(max_byte_length=4627, null=True, blank=True)
    DateTime = models.DateTimeField()

    def __str__(self):
        return 'Signature:%s:%s-%s' %(self.pointerId, self.Upk_obj_id, self.id)
    
    class Meta:
        ordering = ['-DateTime']

    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['pointerId', 'sig']

    def save(self, share=False, *args, **kwargs):
        prntDebug('-sig save...',self)
        if self.id is None:
            if self.pointerId and not self.pointerKey:
                pointer = get_dynamic_model(self.pointerId, id=self.pointerId)
                prnt('pointer1',pointer)
                self.pointerKey = ContentType.objects.get_for_model(pointer)
            elif self.pointerKey:
                pointer = self.Pointer_obj
                prnt('pointer2',pointer)
                self.pointerId = pointer.id
            self = initial_save(self)
        else:
            super(Signature, self).save(*args, **kwargs)

class DataPacket(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    queued_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    Node_obj = models.ForeignKey('network.Node', blank=True, null=True, on_delete=models.CASCADE)
    rebroadcast_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    headers = models.JSONField(default=dict, blank=True, null=True)
    networkChain = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    chainName = models.CharField(max_length=50, default="", blank=True, null=True)
    func = models.CharField(max_length=90, default=None, blank=True, null=True)
    jobId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    task = models.IntegerField(default=1)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    data = models.JSONField(default=dict, blank=True, null=True)
    notes = models.JSONField(default=dict, blank=True, null=True)
    signed = models.JSONField(default=dict)
    

    def __str__(self):
        return f'DATAPACKET:{self.id} chain:{self.networkChain}'
    
    class Meta:
        ordering = ["-updated_on_node","-created"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'DataPacket', 'modlVer': 1, 'id': None, 'created': None, 'queued_dt': None, 'Node_obj': None, 'rebroadcast_dt': None, 'headers': {}, 'networkChain': None, 'chainName': '', 'func': None, 'jobId': None, 'task': 1, 'Region_obj': None, 'data': {}, 'notes': {}, 'signed': {}}
        
    def completed(self, fail=None, note=None, completed='process'):
        if fail:
            self.func = self.func.replace('process','failed').replace('scrape','failed')
            self.func = self.func + f"-f:{fail.replace('process','prcs').replace(' ','_')}"
        elif completed == 'process':
            self.func = self.func.replace('process','completed').replace(' ','_').replace('failed','completed')
        elif completed == 'scrape':
            self.func = self.func.replace('scrape','completed').replace(' ','_')

        else:
            self.func = self.func.replace('process','completed').replace('scrape','completed').replace(' ','_')
        if note:
            self.func = self.func + f"-n:{note.replace(' ','_')}"
        prntDebug('dp completed, func',self.func)
        self.save(update_fields=['func'])  

    def broadcast_dp(self, iden=None, broadcast_list=None, packet_id=None, target_node=None):
        self.refresh_from_db()
        prnt('\n--broadcast_dp', self, len(self.data.keys()), 'self.networkChain',self.networkChain)
        if e_brake(2):
            return 
        # prnt('self.data:',str(self.data)[:1000])
        if not self.data and self.networkChain != _OperationsChain_genesisId:
            if self.queued_dt:
                self.queued_dt = None
                self.save()
            return None
        else:
            self_node_id = get_operator_obj('self_nodeId')
            if self.networkChain == _OperationsChain_genesisId:
                prnt('is op chain')
                from utils.locked import sign_obj
                self_node = get_self_node()
                try:
                    r = requests.get("http://ip-api.com/json", timeout=15)
                    if not self_node.region_data:
                        self_node.region_data = {}
                    self_node.region_data['country_code'] = r.json().get("countryCode")
                    self_node = sign_obj(self_node, do_save=False)
                    self_node.save(bypass_lock=True)
                    self.data[self_node.id] = sigData_to_hash(self_node)
                except Exception as e:
                    prnt('err 42311', str(e))

                try:
                    reviews = NodeReview.objects.filter(CreatorNode_obj__id=self_node_id)
                    prnt('reviews', reviews.count())
                    if reviews:
                        items = []
                        for r in reviews:
                            prnt('r', r)
                            log_dt_end = round_time(now_utc(), dir='down', amount='hour')
                            log_dt_start = log_dt_end - datetime.timedelta(hours=1)

                            completed_jobs = EventLog.objects.filter(Node_obj=r.TargetNode_obj, func__contains='completed_job:', created__gte=log_dt_start, created__lt=log_dt_end).count()
                            incomplete_jobs = EventLog.objects.filter(Node_obj=r.TargetNode_obj, func__contains='assigned_job:', created__gte=log_dt_start, created__lt=log_dt_end).count()
                            total = completed_jobs + incomplete_jobs
                            r.job_success = completed_jobs / total if total else 0.5

                            def get_consensus(validators, total_validators):
                                from collections import defaultdict

                                # --- group all validators by job ---
                                job_votes = defaultdict(list)

                                for v in total_validators:
                                    job_votes[v['jobId']].append(v['is_valid'])

                                # --- determine consensus result per job ---
                                job_consensus = {}

                                for job_id, votes in job_votes.items():
                                    true_votes = sum(votes)
                                    false_votes = len(votes) - true_votes

                                    # majority vote
                                    job_consensus[job_id] = true_votes >= false_votes


                                # --- compare this node's validators to consensus ---
                                aligned = 0
                                checked = 0

                                for v in validators:
                                    job_id = v['jobId']

                                    if job_id in job_consensus:
                                        checked += 1
                                        if v['is_valid'] == job_consensus[job_id]:
                                            aligned += 1

                                consensus_alignment = aligned / checked if checked else 0
                                return consensus_alignment

                            successes = 0
                            if r.response_times:
                                for dt, data in r.response_times.items():
                                    if string_to_dt(dt) >= log_dt_start:
                                        successes += 1
                                r.response_times = {}
                            r.response_success = 0.5
                            if r.interactions and r.interactions >= successes:
                                r.response_success = (successes/r.interactions)

                            if r.failures:
                                failures = 0
                                for dt, data in r.failures.items():
                                    if string_to_dt(dt) >= log_dt_start:
                                        failures += 1

                            r.lastUpdate = now_utc()

                            r = sign_obj(r, do_save=False)
                            v = verify_obj_to_data(r, r)
                            prnt('v', v)
                            self.data[r.id] = sigData_to_hash(r)
                            items.append(r)
                            prnt('nR:',get_signing_data(r))

                        dynamic_bulk_update(model=NodeReview, items=items)
                        reviews = []
                    
                except Exception as e:
                    prnt('err 42312', str(e))
                try:
                    # not in use
                    # include most recent instances of FCMDevice

                    # from fcm_django.models import FCMDevice
                    from accounts.models import CustomFCM
                    fcm_devices = CustomFCM.objects.filter(date_created__gte=now_utc() - datetime.timedelta(minutes=9.8))
                    for a in fcm_devices:
                        a = sign_obj(a)
                        self.data[a.id] = sigData_to_hash(a)
                except:
                    pass
                if len(self.data.keys()) == 0:
                    return None
                self.queued_dt = None
                self.save()

            now = now_utc()
            now_str = dt_to_string(now)
            dp = None
            if not packet_id:
                packet_id = hash_obj_id('DataPacket', specific_data=f"{self_node_id}-{dt_to_string(now)}")
                if packet_id != self.id and not DataPacket.objects.filter(id=packet_id).exists():
                    dp = DataPacket(id=packet_id, func='broadcast_dp', data={})
            prnt('packet_id',packet_id)
            if dp and not dp.data:
                dp.data = {}

            if self.headers and 'Packet-Id' in self.headers and self.headers['Packet-Id'] == packet_id:
                prnt('p1')
                headers = self.headers
            else:
                prnt('p2')
                headers = {'Packet-Id':packet_id, 'Packet-Origin-Dt':dt_to_string(now), 'Packet-Creator':self_node_id, 'Seedid':self_node_id, 'Senderid':self_node_id, 'Dt':now_str, 'Chainid':self.networkChain, 'Region-Id':self.Region_obj.id if self.Region_obj else None}
            prnt('headers:',headers)
            if target_node:
                broadcast_list = {self_node_id:[target_node]}
            if self.networkChain.startswith(get_model_prefix('Node')):
                broadcast_list = {self_node_id:[self.networkChain]}
            elif not broadcast_list:
                from utils.locked import get_broadcast_list
                include_relays = False
                if 'chainId' in headers and headers['chainId'] in universalChains:
                    include_relays = True
                broadcast_list = get_broadcast_list(headers['Packet-Id'], dt=string_to_dt(headers['Dt']), region_id=headers['Chainid'], seed_nodes=[headers['Seedid']], include_relays=include_relays)
            prnt('dataPack broadcast_list',broadcast_list)
            if not broadcast_list:
                self.data = {}
                self.queued_dt = None
                self.notes[dt_to_string(now_utc())] = {'fail3': 'no broadcast_list'}
                self.save()
                return True
            elif not self.data and self.networkChain != _OperationsChain_genesisId:
                if self.queued_dt:
                    self.queued_dt = None
                    self.save()
                return None
            else:
                sending_data = None
                from utils.models import to_megabytes
                if 'send_items' not in self.notes:
                    self.notes['send_items'] = {}
                self.notes['send_items'][now_str] = {packet_id:{}}
                opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).order_by('-index', 'created').first() 
                if 'content' in self.data:
                    to_send_items = None
                    compressed_data = self.data['content']
                    sending_data = {'type' : 'DataPacket', 'opBlock': opBlock.id if opBlock else None, 'opBlock_hash': opBlock.hash if opBlock else None, 'sending_idens':[i['id'] for i in json.loads(self.data['content'])], 'content' : compressed_data}
                else:
                    try:
                        if self.Node_obj and self.Node_obj.id != self_node_id:
                            from utils.models import process_received_dp
                            processed_data = process_received_dp(self, skip_log_check=True, override_completed=True)
                            if 'data' in processed_data and 'content' in processed_data['data']:
                                sending_data = processed_data['data']
                    except Exception as e:
                        print('err 323',str(e))
                    if not sending_data:
                        data = dict(sorted(self.data.items(), key=lambda item: item[1]))
                        from itertools import islice
                        data, not_found, not_valid = get_data(dict(islice(data.items(), 500)), include_related=False)
                        if data:
                            total_mbs = 0
                            to_send_items = []
                            for d in data:
                                mbs = to_megabytes(d)
                                if (total_mbs + mbs) < 4:
                                    total_mbs += mbs
                                    to_send_items.append(d)
                                    if dp:
                                        dp.data[d['id']] = dt_to_string(get_timeData(d))
                                else:
                                    break
                            prnt('total_mbs',total_mbs)
                            # prnt('to_send_items:',[i['id'] for i in to_send_items])
                            if not_found or not_valid:
                                if not_found:
                                    self.notes['send_items'][now_str][packet_id]['not_found'] = not_found
                                    for i in not_found:
                                        if i in self.data:
                                            del self.data[i]
                                if not_valid:
                                    self.notes['send_items'][now_str][packet_id]['not_valid'] = [i['id'] for i in not_valid]
                                    for i in not_valid:
                                        if i['id'] in self.data:
                                            del self.data[i['id']]
                            self.save()
                            compressed_data = to_send_items
                            # compressed_data = compress_data(to_send_items)
                            sending_data = {'type' : 'DataPacket', 'opBlock': opBlock.id if opBlock else None, 'opBlock_hash': opBlock.hash if opBlock else None, 'sending_idens':[i['id'] for i in to_send_items], 'content' : compressed_data}
                if sending_data:
                    prnt('sending_idens',sending_data['sending_idens'])
                    sending_data = sign_for_sending(sending_data)
                    try:
                        if dp:
                            dp.headers = headers
                            dp.save()
                        prnt('headers',headers)
                        if self.func and 'assignement' in self.func:
                            url = 'network/receive_posts_for_validating'
                        else:
                            url = 'network/receive_data_packet'
                        successes = downstream_broadcast(broadcast_list, url, sending_data, headers=headers, skip_self=True, exclude=[self_node_id])
                        prnt('successes',successes)
                        if self_node_id in broadcast_list and successes >= len(broadcast_list[self_node_id]) or successes and successes >= Node.objects.exclude(activated_dt=None).filter(chain_array__contains=[self.networkChain], suspended_dt=None).count():
                            prnt('readdbroadcast p1')
                            self.notes['send_items'][now_str][packet_id]['sent'] = []
                            if packet_id != self.id:
                                if to_send_items:
                                    for i in to_send_items:
                                        if 'id' in i and i['id'] in self.data:
                                            del self.data[i['id']]
                                            self.notes['send_items'][now_str][packet_id]['sent'].append(i['id'])
                                
                                if len(self.notes['send_items']) > 20:
                                    x = 0
                                    copy = self.notes['send_items'].copy()
                                    for i in reversed(copy):
                                        x += 1
                                        if x > 20:
                                            del self.notes['send_items'][i]

                            if self.data:
                                prnt('readdbroadcast p3')
                                if not exists_in_worker('broadcast_dp', queue_name='chat', iden=self.id):
                                    run_at = now_utc() + datetime.timedelta(minutes=1)
                                    self.queued_dt = run_at
                                    prnt('add dp_broadcast to scheduler',run_at)
                                    django_rq.get_scheduler('chat').enqueue_at(run_at, self.broadcast_dp, iden=self.id, timeout=300)
                                # if not exists_in_worker('broadcast', self.id, queue_name='low', job_count=2):
                                # run_at = now_utc() + datetime.timedelta(minutes=random.randint(4, 9))
                                # self.queued_dt = run_at
                                # django_rq.get_scheduler('low').enqueue_at(run_at, self.broadcast, timeout=120)
                            else:
                                prnt('readdbroadcast p4')
                                self.queued_dt = None
                            self.save()
                            return True
                        else:
                            prnt('readdbroadcast p2')
                            self.notes['send_items'][now_str]['fail1'] = {'too few success':{'req':len(broadcast_list[self_node_id]),'achieved':successes}}
                            run_at = now_utc() + datetime.timedelta(minutes=random.randint(10, 25))
                            self.queued_dt = run_at
                            self.save()
                            # django_rq.get_scheduler('low').enqueue_at(run_at, self.broadcast, timeout=120)
                    except Exception as e:
                        prnt('readdbroadcast dp braod err 3824',str(e))
                        self.notes['send_items'][now_str]['fail2'] = str(e)
                        run_at = now_utc() + datetime.timedelta(minutes=random.randint(3, 8))
                        self.queued_dt = run_at
                        self.save()
                else:
                    self.data = {}
                    self.queued_dt = None
                    self.save()
                return False
            
    def add_item_to_share(self, obj):
        prnt('--datapackey add_item_to_share',self.id,'obj:',str(obj)[:250])
        exclude = ['cha']
        all = ['nod', 'nrev', 'reg', 'usr', 'upk','uver','udat']
        if not obj:
            return False

        # non-essential yet frequently updated objects can be broadcast less often, 60mins? (user updates/logins)
        # non-essential seldom updated objs can be broadcast with medium frequency, 30mins? (scraped content?)
        # essential updates broadcast often, 10mins (new users, upks, nodes)
        # should prioritize broadcast groups, eg. user updates broadcast to nodes currently assigned to user more often, rest of nodes less often


        def add_worker_job(dp):
            if not testing():
                operatorData = get_operatorData()
                if not 'syncingDB' in operatorData or operatorData['syncingDB'] != True:
                    if not self.queued_dt:
                        if not exists_in_worker('broadcast_dp', queue_name='chat', iden=dp.id):
                            run_at = now_utc() + datetime.timedelta(minutes=random.randint(1, 11))
                            self.queued_dt = run_at
                            prnt('add dp_broadcast to scheduler',run_at)
                            django_rq.get_scheduler('chat').enqueue_at(run_at, dp.broadcast_dp, iden=dp.id, timeout=300)
                            return True
            return False

        def send_to_all(obj):
            prnt('send_to_all',str(obj)[:150])
            allPacket = DataPacket.objects.filter(networkChain='All').first()
            save_all = False
            if isinstance(obj, list):
                for i in obj:
                    if isinstance(i, models.Model):
                        if i.id not in allPacket.data:
                            allPacket.data[i.id] = dt_to_string(get_timeData(i))
                            save_all = True
                    elif isinstance(i, dict):
                        if 'id' in i and i['id'] not in allPacket.data:
                            allPacket.data[i['id']] = dt_to_string(get_timeData(i))
                            save_all = True
                        else:
                            for key, value in i.items():
                                if key not in allPacket.data:
                                    allPacket.data[key] = value
                                    save_all = True
                    elif isinstance(i, str) and is_id(i):
                        if i not in allPacket.data:
                            allPacket.data[i] = dt_to_string(get_timeData(get_dynamic_model(i, id=i)))
                            save_all = True
            else:
                if isinstance(obj, models.Model):
                    if obj.id not in allPacket.data:
                        allPacket.data[obj.id] = dt_to_string(get_timeData(obj))
                        save_all = True
                elif isinstance(obj, dict):
                    if 'id' in obj and obj['id'] not in allPacket.data:
                        allPacket.data[obj['id']] = dt_to_string(get_timeData(obj))
                        save_all = True
                    else:
                        for key, value in obj.items():
                            if key not in allPacket.data:
                                allPacket.data[key] = value
                                save_all = True
                elif isinstance(obj, str) and is_id(i):
                    if obj not in allPacket.data:
                        allPacket.data[obj] = dt_to_string(get_timeData(get_dynamic_model(i, id=i)))
                        save_all = True
            prntDebug('save_all',save_all)
            if save_all:
                allPacket.save()
                add_worker_job(allPacket)
            prnt('donw send to all')

        if not self.data:
            self.data = {}
        to_all = []
        save_self = False
        obj_ids = []
        prnt('share_to_all:',share_to_all)
        if isinstance(obj, models.Model):
            if not obj.id.startswith(tuple(exclude)):
                if obj.id.startswith(tuple(share_to_all)) and self.networkChain != 'All' and not self.networkChain.startswith(get_model_prefix('Node')):
                    send_to_all(obj)
                elif obj.id.startswith(get_model_prefix('Validator')):
                    if any(d.startswith(tuple(share_to_all)) for d in obj.data):
                        send_to_all(obj)
                if obj.id not in self.data:
                    self.data[obj.id] = dt_to_string(get_timeData(obj))
                    prnt('save_self1')
                    add_worker_job(self)
                    self.save()
                    return True
        elif isinstance(obj, dict):
            if 'id' in obj:
                if not obj['id'].startswith(tuple(exclude)):
                    if obj['id'].startswith(tuple(share_to_all)) and self.networkChain != 'All' and not self.networkChain.startswith(get_model_prefix('Node')):
                        to_all.append(obj)
                    elif obj['id'].startswith(get_model_prefix('Validator')) and not self.networkChain.startswith(get_model_prefix('Node')):
                        if 'data' not in obj:
                            obj = Validator.objects.filter(id=obj['id']).first()
                            if obj and any(d.startswith(tuple(share_to_all)) for d in obj.data):
                                send_to_all(obj)
                        elif any(d.startswith(tuple(share_to_all)) for d in obj['data']):
                            send_to_all(obj)
                    if obj['id'] not in self.data:
                        self.data[obj['id']] = dt_to_string(get_timeData(obj))
                        prnt('save_self2')
                        add_worker_job(self)
                        self.save()
                        return True
            else:
                item_dict = obj
                for key, value in item_dict.items():
                    if not key.startswith(tuple(exclude)):
                        obj_ids.append(key)
                    if key.startswith(get_model_prefix('Validator')) and not self.networkChain.startswith(get_model_prefix('Node')):
                        if isinstance(value, models.Model):
                            if any(d.startswith(tuple(share_to_all)) for d in value.data):
                                send_to_all(value)
                val_ids = [i for i in obj_ids if i.startswith(get_model_prefix('Validator')) and i not in to_all]
                if val_ids and not self.networkChain.startswith(get_model_prefix('Node')):
                    for v in Validator.objects.filter(id__in=val_ids):
                        if any(d.startswith(tuple(share_to_all)) for d in v.data):
                            to_all.append(v)
                if obj_ids:
                    for i in obj_ids:
                        if i not in self.data:
                            self.data[i] = item_dict[i] # value may be hash of obj
                            save_self = True
                        if i.startswith(tuple(share_to_all)) and self.networkChain != 'All' and {i:item_dict[i]} not in to_all and not self.networkChain.startswith(get_model_prefix('Node')):
                            to_all.append({i:item_dict[i]})
                    if save_self:
                        prnt('save_self3')
                        add_worker_job(self)
                        self.save()
                    if to_all:
                        send_to_all(to_all)
                    return True
        elif isinstance(obj, list):
            item_dict = {}
            for o in obj:
                if isinstance(o, models.Model):
                    if not o.id.startswith(tuple(exclude)):
                        if o.id not in self.data:
                            obj_ids.append(o.id)
                            item_dict[o.id] = o
                        if o._meta.object_name == 'Validator' and not self.networkChain.startswith(get_model_prefix('Node')):
                            if any(d.startswith(tuple(share_to_all)) for d in o.data):
                                to_all.append(o)
                elif is_id(o):
                    if o not in self.data:
                        if not o.startswith(tuple(exclude)):
                            obj_ids.append(o)
            obj_ids = [item for item in obj_ids if not item.startswith(tuple(exclude))]
            val_ids = [i for i in obj_ids if i.startswith(get_model_prefix('Validator')) and i not in to_all]
            if val_ids and not self.networkChain.startswith(get_model_prefix('Node')):
                for v in Validator.objects.filter(id__in=val_ids):
                    if any(d.startswith(tuple(share_to_all)) for d in v.data):
                        to_all.append(v)
            if obj_ids:
                prnt('obj_idens_len',len(obj_ids), 'item_dict_len',len(item_dict))
                if len(item_dict) < len(obj_ids):
                    from utils.models import seperate_by_type
                    for model_name, iden_list in seperate_by_type(obj_ids).items():
                        items = get_dynamic_model(model_name, list=True, id__in=iden_list)
                        for i in items:
                            if i.id.startswith(tuple(share_to_all)) and self.networkChain != 'All' and i.id not in to_all and not self.networkChain.startswith(get_model_prefix('Node')):
                                to_all.append(i)
                            if i.id not in self.data:
                                self.data[i.id] = dt_to_string(get_timeData(i))
                                save_self = True
                else:
                    for i in obj_ids:
                        if i.startswith(tuple(share_to_all)) and self.networkChain != 'All' and i not in to_all and not self.networkChain.startswith(get_model_prefix('Node')):
                            to_all.append(i)
                        if i not in self.data:
                            self.data[i] = dt_to_string(get_timeData(item_dict[i]))
                            save_self = True
                prnt('save_self4',save_self)
                prnt('self.data len:',len(self.data))
                if save_self:
                    add_worker_job(self)
                    self.save()
                if to_all:
                    send_to_all(to_all)
                return True
        return False
    
    def updateShare(self, obj):
        if 'shareData' not in self.data:
            self.data['shareData'] = []
        if obj and obj.id not in self.data['shareData']:
            self.data['shareData'].append(obj.id)
            self.save()

    def save(self, share=False, *args, **kwargs):
        prntDebug('-dp save...', self.id)
        if self.networkChain and not self.chainName:
            if self.networkChain == 'All':
                self.chainName = 'All'
            else:
                chain = Blockchain.objects.filter(id=self.networkChain).first()
                if chain:
                    self.chainName = chain.genesisName
                    if chain.genesisId and get_pointer_type(chain.genesisId) == 'Region':
                        from posts.models import Region
                        region = Region.objects.filter(id=chain.genesisId).first()
                        if region:
                            self.Region_obj = region
        if self.func:
            self.func = self.func[:90]
        if not self.created:
            self.created = now_utc()
        if self.id is None:
            self = initial_save(self)
        else:
            prntDebug('dp save final',self.id, self.func)
            super(DataPacket, self).save(*args, **kwargs)
        prnt('done dp save')



class Node(models.Model):
    networkChain = models.CharField(max_length=50, default="Sonet", blank=True)
    is_modifiable = True
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    trust_score = models.FloatField(default=0.5)
    influence_score = models.FloatField(default=0.5)
    score_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, on_delete=models.SET_NULL)
    node_name = models.CharField(max_length=50, default="", blank=True, null=True)
    node_type = models.CharField(max_length=50, default="server/maintainer", blank=True, null=True)
    node_level = models.CharField(max_length=50, default="standard", blank=True, null=True)
    abilities = models.JSONField(default=dict, blank=True, null=True)
    software_version = models.JSONField(default=dict, blank=True, null=True)
    hardware_data = models.JSONField(default=dict, blank=True, null=True)
    address = models.CharField(max_length=80, default="", blank=True, null=True)
    onion = models.CharField(max_length=80, default="", blank=True, null=True)
    activated_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    suspended_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    expelled_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    not_responding_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    chain_array = ArrayField(models.CharField(max_length=50, default='', blank=True, null=True), size=250, null=True, blank=True)
    region_array = ArrayField(models.CharField(max_length=50, default='', blank=True, null=True), size=250, null=True, blank=True)
    plugin_array = ArrayField(models.CharField(max_length=50, default='', blank=True, null=True), size=250, null=True, blank=True)
    region_data = models.JSONField(default=dict, blank=True, null=True)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    pos = models.IntegerField(default=0)
    activeNode = models.BooleanField(default=False)
    rec_change = BinaryBase62Field(max_byte_length=30, default=None, blank=True, null=True)
    signed = models.JSONField(default=dict)
    iden_length = 11


    def __str__(self):
        return f'NODE: {self.node_name}-{self.id}'

    class Meta:
        ordering = ["-lastUpdate"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Node', 'networkChain': 'Sonet', 'modlVer': 1, 'id': None, 'created': None, 'lastUpdate': None, 'trust_score': 0.5, 'influence_score': 0.5, 'score_dt': None, 'User_obj': None, 'node_name': '', 'node_type': 'server/maintainer', 'node_level': 'standard', 'abilities': {}, 'software_version': {}, 'hardware_data': {}, 'address': '', 'onion': '', 'activated_dt': None, 'suspended_dt': None, 'expelled_dt': None, 'not_responding_dt': None, 'chain_array': None, 'region_array': None, 'plugin_array': None, 'region_data': {}, 'Block_obj': None, 'pos': 0, 'activeNode': False, 'rec_change': None, 'iden_length': 11, 'signed': {}}
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['created','User_obj', 'get_position']

    def no_sign_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['trust_score','influence_score','score_dt','suspended_dt','expelled_dt','not_responding_dt','pos','activeNode','rec_change']

    def get_position(self, mod=0, check_data=None):
        prnt('-get_position',self.id, mod, check_data)
        if check_data:
            prnt('check_data',check_data)
            if 'pos' not in check_data or str(check_data['pos']) == '0':
                prnt('fa0')
                return False
            if self.Block_obj and self.Block_obj.validated:
                if check_data['pos'] == self.Block_obj.data[self.id]['pos']:
                    prnt('tr0')
                    if self.pos != check_data['pos']:
                        self.pos = check_data['pos']
                        self.save()
                    return True
            else:
                if self.Block_obj:
                    latest_node = Node.objects.filter(Block_obj__validated=True, Block_obj__DateTime__lt=self.Block_obj.DateTime).order_by('-pos').first()
                else:
                    latest_node = Node.objects.filter(Block_obj__validated=True).order_by('-pos').first()
                if latest_node and latest_node.pos + 1 == check_data['pos']:
                    prnt('tr1')
                    if self.pos != check_data['pos']:
                        self.pos = check_data['pos']
                        self.save()
                    return True
                else:
                    if self.Block_obj:
                        check_block = self.Block_obj
                    else:
                        check_block = Block.objects.filter(Blockchain_obj__genesisType='Sonet', data__has_key=self.id).order_by('-index').first()
                    prnt('check_block',check_block)
                    if check_block:
                        same_block_nodes = {k:check_block.data[k]['pos'] for k in check_block.data if get_pointer_type(k) == 'Node'}
                        prnt('same_block_nodes',same_block_nodes)
                        if same_block_nodes:
                            sorted_nodes = dict(sorted(same_block_nodes.items(), key=lambda item: item[1]))
                            n = 1
                            for k in sorted_nodes:
                                prnt(k,same_block_nodes[k])
                                if latest_node and same_block_nodes[k] == latest_node.pos + n or check_data['pos'] == same_block_nodes[k] and k == self.id:
                                    if k == self.id:
                                        if self.pos != check_data['pos']:
                                            self.pos = check_data['pos']
                                            self.save()
                                        prnt('tr2')
                                        return True
                                    n += 1
                                else:
                                    prnt('fa1')
                                    return False
            prnt('fa3')
            return False
            
        latest_node = Node.objects.filter(Block_obj__validated=True).order_by('-pos').first()
        if latest_node:
            pos = latest_node.pos + 1
        else:
            pos = 1
        pos += mod

        self.pos = pos
        self.save()
        prnt({'pos':pos})
        return {'pos':pos}
        
    def on_confirmation(self, block):
        self.pos = block.data[self.id]['pos']
        if self.activated_dt:
            nodeChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
            if nodeChain:
                nodeChain.add_item_to_queue(self)
        return self

    def return_address(self):
        return {'address':self.address,'onion':self.onion}

    def assess_activity(self, self_node_id=None):
        prnt('-assess_activity',self.node_name)
        # if fail_count greater than fails_to_strike and nodes who determined the failures greater than fails_to_strike
        last_accessed = self.get_last_accessed()
        try:
            prnt('last_accessed',last_accessed,last_accessed.accessed)
        except Exception as e:
            prnt('err1', str(e))
        if last_accessed and last_accessed.accessed and last_accessed.accessed < now_utc() - datetime.timedelta(minutes=30):
            total_failures, recent_failures = self.get_failures()
            prnt('last_accessed',last_accessed,'total_failures',total_failures,'recent_failures',recent_failures)
            if last_accessed.accessed > recent_failures[0].last_fail:
                prnt(f'true1 - last_accessed.accessed:{last_accessed.accessed}, recent_failures[0].last_fail:{recent_failures[0].last_fail}')
                if self.suspended_dt:
                    self.suspended_dt = None
                    self.save(update_fields=['suspended_dt'])
                return True
            else:
                if self.suspended_dt:
                    return False
                now = now_utc()
                rev = NodeReview.objects.filter(TargetNode_obj=self, CreatorNode_obj__id=self_node_id).first()
                recent_failures = 0
                if rev and (not rev.accessed or rev.accessed < now - datetime.timedelta(hours=failure_range)):
                    for dt_str, value in rev.failures.items():
                        try:
                            dt = string_to_dt(dt_str)
                        except:
                            dt = string_to_dt(value)
                        if dt > now - datetime.timedelta(days=striking_days):
                            recent_failures += 1
                        # prnt('recent_failure_count',recent_failure_count)
                        if recent_failures >= recent_failure_count:
                            prnt('step2')
                            self.suspended_dt = now_utc() # this should be expelled/deactivated, not suspended
                            prnt('**suspend node**', self, self.suspended_dt)
                            self.save(update_fields=['suspended_dt'])

                            if not self_node_id:
                                self_node_id = get_operator_obj('self_nodeId')
                            
                            nodeChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
                            if nodeChain:
                                nodeChain.add_item_to_queue(self)
                                
                            nodePacket = DataPacket.objects.filter(Node_obj__id=self_node_id, func='share', networkChain=_OperationsChain_genesisId).first()
                            if nodePacket:
                                nodePacket.add_item_to_share(self)
                            strike = NodeReview.objects.filter(TargetNode_obj=self, CreatorNode_obj__id=self_node_id).first()
                            prnt('strike0',strike)
                            if not strike:
                                strike = NodeReview(TargetNode_obj=self, CreatorNode_obj_id=self_node_id)
                            prnt('strike.last_fail',strike.last_fail, 'now - datetime.timedelta(seconds=7)',now - datetime.timedelta(seconds=7))
                            # get most recent strike, count x failures since then, if greater than node_strike_count add another strike
                            # for key, value in strike.failures.items():
                            #     try:
                            #         dt = string_to_dt(key)
                            #     except:
                            #         dt = string_to_dt(value)
                            #     if dt > now - datetime.timedelta(days=striking_days):
                            #         try:
                            #             node_strikers[s.CreatorNode_obj.id] += 1
                            #         except:
                            #             node_strikers[s.CreatorNode_obj.id] = 1
                            # get most recent failures, for every x faileures since last_accessed, count 1 strike
                            if not strike.last_fail or strike.last_fail < now - datetime.timedelta(seconds=7):
                                prnt('add_last_fail')
                                strike.strikes = {dt_to_string(now):'excess_failures'}
                                strike.last_fail = now
                                strike.save()

                            self.too_many_strikes(active_nodes=None, last_accessed=last_accessed)
                            prnt('false1')
                            return False
        prnt('true2')
        return True

    def is_active(self): # not used
        def func():
            total, recent = self.get_failures()
            if last_accessed > recent[0].created:
                return True
            else:
                nodes_failed_to_access = []
                for r in recent:
                    if r.CreatorNode_obj.id not in nodes_failed_to_access:
                        nodes_failed_to_access.append(r.CreatorNode_obj.id)
                if len(nodes_failed_to_access) > 10 or len(nodes_failed_to_access) > (len(get_node_list())/2):
                    deactivate(node=self)
                    return False
                else:
                    return True
        if self.suspended_dt:
            return False
        else:
            try:
                deactivated = NodeReview.objects.exclude(suspended_dt=None).order_by('-created').first()
            except:
                deactivated = None
            last_accessed = self.get_last_accessed().accessed
            if deactivated:
                if last_accessed > deactivated.suspended_dt:
                    return True
                else:
                    return func()
            else:
                return func()

    def get_last_accessed(self):
        # prnt('-get_last_accessed')
        return NodeReview.objects.filter(TargetNode_obj=self).exclude(accessed=None).exclude(CreatorNode_obj=self).order_by('-accessed').first()

    def get_failures(self):
        prnt('-get_failures')
        all_failures = NodeReview.objects.filter(TargetNode_obj=self).exclude(last_fail=None).order_by('-created').count()
        # failures in past recent_failure_range days
        recent_failures = NodeReview.objects.filter(TargetNode_obj=self, last_fail__gte=now_utc() - datetime.timedelta(days=recent_failure_range)).only('last_fail').order_by('-last_fail')
        return all_failures, recent_failures
    
    def get_strikes(self):
        return NodeReview.objects.exclude(strikes=None).filter(TargetNode_obj=self).order_by('-created')
        
    def too_many_strikes(self, period=None, active_nodes=None, last_accessed=None):
        prnt('-too_many_strikes?', self)
        # if frequency of failures is high, even if still getting access, strike should occur
        if self.suspended_dt:
            return True
        if not last_accessed:
            last_accessed = self.get_last_accessed()
        if not last_accessed or not last_accessed.accessed:
            return False
        if period == 'any':
            strike_objects = NodeReview.objects.exclude(strikes=None).filter(TargetNode_obj=self, last_fail__gt=last_accessed.accessed).order_by('-last_fail')
        else:
            strike_objects = NodeReview.objects.exclude(strikes=None).filter(TargetNode_obj=self, last_fail__gt=last_accessed.accessed).order_by('-last_fail')
        node_strikers = {}
        # aacount for striking_days
        # strike_objects.strikes is stored as {creator_node.id:dt_of_strike}, should account for when strike occured. currently I think one list of strikes is built up, as soon as one new one occurs it will override last_accessed
        now = now_utc()
        for s in strike_objects:
            for iden, dt_str in s.strikes.items():
                try:
                    dt = string_to_dt(dt_str)
                except:
                    dt = string_to_dt(iden)
                if dt > now - datetime.timedelta(days=striking_days):
                    try:
                        node_strikers[s.CreatorNode_obj.id] += 1
                    except:
                        node_strikers[s.CreatorNode_obj.id] = 1
        prnt('node_strikers',node_strikers)
        if not active_nodes:
            active_nodes = Node.objects.exclude(Block_obj=None).exclude(activated_dt=None).filter(suspended_dt=None).count()
        prnt('active_nodes2',active_nodes,'(active_nodes/4*3)',(active_nodes/4*3))
        strikes = 0
        if len(node_strikers) >= too_many_strike_count or len(node_strikers) >= (active_nodes/4*3):
            for key, value in node_strikers.items():
                if int(value) >= too_many_strike_count:
                    strikes += 1
        prnt('strikes',strikes)
        if strikes >= too_many_strike_count or strikes >= (active_nodes/4*3):
            # report strike to network?
            self.suspended_dt = now_utc() # this should be expelled/deactivated, not suspended
            prnt('**expelled node**', self, self.suspended_dt)
            self.strikes = {'suspend_dt':self.suspended_dt}
            self.save(update_fields=['suspended_dt'])
            self_node_id = get_operator_obj('self_nodeId')
            nodeChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
            if nodeChain:
                nodeChain.add_item_to_queue(self)
            failure = NodeReview.objects.filter(CreatorNode_obj__id=self_node_id, TargetNode_obj=self).first()
            
            datapacket = DataPacket.objects.filter(Node_obj__id=self_node_id, func='share', networkChain=_OperationsChain_genesisId).first()
            if datapacket:
                datapacket.add_item_to_share(failure) 
            prnt('True')
            return True
        return False

    def add_failure(self, note='None', self_node=None):
        prnt('-add_failure',self, note)
        if self_node and isinstance(self_node, models.Model):
            self_node_id = self_node.id
        else:
            self_node_id = get_operator_obj('self_nodeId')
        if self_node_id != self.id:
            review = NodeReview.objects.filter(CreatorNode_obj__id=self_node_id, TargetNode_obj=self).only('last_fail','failures','interactions').first()
            if not review:
                review = NodeReview(TargetNode_obj=self, CreatorNode_obj_id=self_node_id)
            if not review.failures:
                review.failures = {}
            if len(review.failures) >= 250:
                sorted_keys = sorted(review.failures.keys(), key=lambda k: string_to_dt(k))
                review.failures.pop(sorted_keys[0])
            now = now_utc()
            if not review.last_fail or review.last_fail < now - datetime.timedelta(seconds=7):
                review.last_fail = now
                review.interactions += 1
                review.failures[dt_to_string(now)] = note
                review.save(update_fields=['last_fail','failures','interactions'])
            prnt('failure added I hope',self)
            self.assess_activity(self_node_id=self_node_id)  
            prnt('done add_failure')

    def accessed(self, response_time=None, address_type='address', self_node=None):
        prntDebug('-node accessed',self,address_type)
        if not self_node or isinstance(self_node, models.Model):
            self_node_id = get_operator_obj('self_nodeId')
        if self_node_id and self_node_id != self.id:
            review = NodeReview.objects.filter(TargetNode_obj=self, CreatorNode_obj__id=self_node_id).only('lastUpdate','avg_response_time','response_times','accessed','interactions').first()
            if not review:
                review = NodeReview(TargetNode_obj=self, CreatorNode_obj_id=self_node_id)
            review.accessed = now_utc()
            if response_time:
                if len(review.response_times) >= 250:
                    sorted_keys = sorted(review.response_times.keys(), key=lambda k: k)
                    review.response_times.pop(sorted_keys[0])
                review.response_times[dt_to_string(now_utc())] = {'addr':address_type, 'time':float(response_time)}
                avg = 0
                for value in review.response_times.values():
                    try:
                        avg += float(value['time'])
                    except:
                        pass
                review.avg_response_time = avg/len(review.response_times)
            review.lastUpdate = now_utc()
            review.interactions += 1
            review.save(update_fields=['lastUpdate','avg_response_time','response_times','accessed','interactions'])
                
        prnt('self.suspended_dt',self.suspended_dt)
        if self.suspended_dt:
            self.suspended_dt = None
            self.save(update_fields=['suspended_dt'])
            
    def deactivate(self):
        self.suspended_dt = now_utc()
        self.save(update_fields=['suspended_dt'])
    
    def reactivate(self):
        # self_node = get_self_node()
        # update = NodeReview.objects.filter(TargetNode_obj=self, CreatorNode_obj=self_node).first()
        # if not update:
        #     update = NodeReview(TargetNode_obj=self, CreatorNode_obj=self_node)
        self.suspended_dt = None
        # update.save()
        # update = sign_obj(update)
        # self.deactivated = False
        self.save(update_fields=['suspended_dt'])

    def broadcast_state(self, node_data=None):
        if node_data:
            from utils.models import sync_and_share_object
            self, is_valid = sync_and_share_object(self, node_data)
        else:
            is_valid = True
        if is_valid:
            prnt('-broadcast_state from self',self)
            from utils.locked import get_broadcast_list
            broadcast_list = get_broadcast_list(self)
            data = {'source':'server','objData' : get_signing_data(self, include_sig=True)}
            prnt('broadcast_list',broadcast_list)
            # starting_node = get_node_assignment(node_obj, creator_only=True)
            downstream_broadcast(broadcast_list, 'network/declare_node_state', data, skip_self=True, exclude=[self.id])
            prnt('finished rboadcast_state')

            if self.activated_dt and not self.suspended_dt:
                if self.id == get_self_node().id:
                    # update database
                    pass

    def initialize(self):
        self.modlVer = self.latestVer
        self.id = hash_obj_id(self)
        return self

    def boot(self, blockchain=None, datapacket=None):
        prnt('-boot node',self)
        sonet_chain = Blockchain.objects.filter(genesisType='Sonet').first()
        if sonet_chain:
            sonet_chain.add_item_to_queue(self)
        if not datapacket:
            from utils.models import get_latest_dataPacket
            datapacket = get_latest_dataPacket()
        if datapacket:
            datapacket.add_item_to_share(self) 
        self.save() 
        return self  
        
    def committed_data_matches(self):
        from utils.models import is_obj_commit_valid
        return is_obj_commit_valid(self)
    
    def save(self, bypass_upk_block=False, bypass_lock=False, sig=None, share=False, *args, **kwargs):
        if testing():
            super(Node, self).save()
        else:
            prnt('-saving node...bypass_upk_block:',bypass_upk_block,'bypass_lock:',bypass_lock)
            update_fields = kwargs.get('update_fields', None)
            if update_fields and len(update_fields) == 1:
                # if all(i for i in update_fields if i in ['activeNode']):
                if update_fields == ['activeNode'] or update_fields == ['suspended_dt'] or update_fields == ['expelled_dt']:
                    update_fields.append('updated_on_node')
                    kwargs['update_fields'] = update_fields
                    self.updated_on_node = now_utc()
                    prnt('saved Node block 2')
                    super(Node, self).save(*args, **kwargs)
            elif not is_locked(self) or bypass_lock:
                from accounts.models import UserPubKey
                if bypass_upk_block:
                    # upks = UserPubKey.objects.filter(User_obj=self.User_obj, created__lte=self.lastUpdate).exclude(Q(keyType='account')|Q(keyType='signing')|Q(keyType='security')) # includes nodekeys and superkeys
                    super(Node, self).save(*args, **kwargs)
                    prnt('Node saved!')
                    if not self.Block_obj:
                        sonetChain = Blockchain.objects.filter(genesisType='Sonet').first()
                        if sonetChain:
                            sonetChain.add_item_to_queue(self)
                else:
                    upks = UserPubKey.objects.filter(User_obj=self.User_obj, created__lte=self.lastUpdate, Block_obj__validated=True).exclude(Q(keyType='account')|Q(keyType='signing')|Q(keyType='security')) # includes nodekeys and superkeys
                    if not upks:
                        first_sonet_block = Block.objects.filter(Blockchain_obj__genesisType='Sonet', validated=True).values('id','added_to_node').first()
                        prnt('first_sonet_block',first_sonet_block)
                        if not first_sonet_block or first_sonet_block['added_to_node'] > now_utc() - datetime.timedelta(hours=24):
                            upks = UserPubKey.objects.filter(User_obj=self.User_obj, created__lte=self.lastUpdate).exclude(Q(keyType='account')|Q(keyType='signing')|Q(keyType='security')) # includes nodekeys and superkeys
                    for upk in upks:
                        prnt('upk',upk)
                        if not upk.end_life_dt or string_to_dt(self.lastUpdate) < upk.end_life_dt:
                            if verify_data(get_signing_data(self), upk.publicKey, signature=sig):
                                super(Node, self).save(*args, **kwargs)
                                prnt('Node saved!')
                                if not self.Block_obj:
                                    sonetChain = Blockchain.objects.filter(genesisType='Sonet').first()
                                    if sonetChain:
                                        sonetChain.add_item_to_queue(self)
                                return
    
    def delete(self, *args, **kwargs):
        return 0, {}

class NodeReview(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    TargetNode_obj = models.ForeignKey('network.Node', related_name='target_node_obj', blank=True, null=True, db_index=True, on_delete=models.SET_NULL)
    CreatorNode_obj = models.ForeignKey('network.Node', related_name='creator_node_obj', blank=True, null=True, on_delete=models.SET_NULL)
    special_attrs = models.JSONField(default=None, blank=True, null=True)
    accessed = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    response_times = models.JSONField(default=dict, blank=True, null=True)
    response_success = models.FloatField(default=0.5)
    job_success = models.FloatField(default=0.5)
    interactions = models.IntegerField(default=0)
    avg_response_time = models.DecimalField(max_digits=7, decimal_places=4, default=None, blank=True, null=True)
    last_fail = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    failures = models.JSONField(default=None, blank=True, null=True)
    strikes = models.JSONField(default=None, blank=True, null=True) #blockId if referencing strike for block
    trust_score = models.FloatField(default=0.5)
    signed = models.JSONField(default=dict)

    def __str__(self):
        return 'NODEREVIEW: %s'%(self.id)
    
    class Meta:
        ordering = ["-created"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'NodeReview', 'modlVer': 1, 'id': None, 'created': None, 'lastUpdate': None, 'TargetNode_obj': None, 'CreatorNode_obj': None, 'special_attrs': None, 'accessed': None, 'response_times': {}, 'response_success': 0.5, 'job_success': 0.5, 'interactions': 0, 'avg_response_time': None, 'last_fail': None, 'failures': None, 'strikes': None, 'trust_score': 0.5, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','TargetNode_obj','CreatorNode_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['id','TargetNode_obj','CreatorNode_obj']

    def update_data(self, share=False):
        self.modlVer = self.latestVer
        self.save(share=share)

    def save(self, share=False, *args, **kwargs):
        prntDev('-save NodeReveiw')
        if self.id is None:
            if not self.created:
                self.created = now_utc()
            self = initial_save(self)
        super(NodeReview, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return 0, {}

class NodeRecord(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    data = models.JSONField(default=dict, blank=True, null=True)
    networkChain = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    pointerType = models.CharField(max_length=50, default="", blank=True, null=True)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.CASCADE)
    is_valid = models.BooleanField(default=True)

    def __str__(self):
        return 'NODERECORD: %s'%(self.id)
    
    class Meta:
        ordering = ["-DateTime"]

    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['networkChain','DateTime','data','pointerId','pointerType']
    
    def update_data(self):
        self.modlVer = self.latestVer
        self.save()

    def save(self, *args, **kwargs):
        prntDev('-save NodeRecord')
        if self.id is None:
            if not self.created:
                self.created = now_utc()
            self = initial_save(self)
        super(NodeRecord, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return 0, {}



class Block(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    networkChain = models.CharField(max_length=50, default="")
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    Blockchain_obj = models.ForeignKey('network.Blockchain', blank=True, null=True, on_delete=models.CASCADE)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    CreatorNode_obj = models.ForeignKey('network.Node', blank=True, null=True, on_delete=models.PROTECT)
    Transaction_obj = models.ForeignKey('transactions.Transaction', blank=True, null=True, on_delete=models.CASCADE)
    index = models.IntegerField(default=1) 
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True) # created time round down to last 10 mins, except opChain round up to next 20 mins
    hash = models.CharField(max_length=100, default="", blank=True, null=True)
    prv_hash = models.CharField(max_length=100, default="", blank=True, null=True)
    validated = models.BooleanField(default=None, blank=True, null=True)
    opData = models.JSONField(default=dict, blank=True, null=True) # only used for operations chain
    opBlockId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    data = models.JSONField(default=dict, blank=True, null=True)
    extraData = models.JSONField(default=dict, blank=True, null=True)
    validations = models.JSONField(default=dict, blank=True, null=True)
    notes = models.JSONField(default=dict, blank=True, null=True)
    signed = models.JSONField(default=dict)


    def __str__(self):
        return f'BLOCK:{self.index} {self.networkChain}-{self.id}'
    
    class Meta:
        ordering = ['-index','-DateTime','created','validations','hash','Transaction_obj']
        indexes = [
            GinIndex(fields=['data'], name='Block_data_has_key_index'),
        ]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Block', 'modlVer': 1, 'networkChain': '', 'id': None, 'created': None, 'Blockchain_obj': None, 'Block_obj': None, 'CreatorNode_obj': None, 'Transaction_obj': None, 'index': 1, 'DateTime': None, 'hash': '', 'prv_hash': '', 'validated': None, 'opData': {}, 'opBlockId': None, 'data': {}, 'extraData': {}, 'validations': {}, 'notes': {}, 'signed': {}}
        
    def on_confirmation(self, obj=None):
        if any(prefix for prefix in reward_models if self.Blockchain_obj.genesisId.startswith(prefix)):
            from legis.models import Government
            gov = Government.objects.filter(id=self.genesisId).only('Region_obj').first()
            chain = Blockchain.objects.filter(genesisId=gov.Region_obj.id).first()
            chain.add_item_to_queue(self)
        if self.Blockchain_obj.genesisId in [_OperationsChain_genesisId, _KeyChain_genesisId, _AccountChain_genesisId]:
            chain = Blockchain.objects.filter(genesisName=_SonetChain_genesisName).first()
            chain.add_item_to_queue(self)
        return self
    
    def get_previous_block(self, is_validated=False, return_chain=True):
        if is_validated:
            block = Block.objects.filter(networkChain=self.networkChain, validated=True, hash=self.prv_hash).defer('data','extraData').order_by('-index','created').first()
        else:
            block = Block.objects.filter(networkChain=self.networkChain, hash=self.prv_hash).exclude(validated=False).defer('data','extraData').order_by('-index','created').first()
        if block:
            return block
        elif return_chain:
            return self.Blockchain_obj
        else:
            return None
        
    def get_previous_hash(self):
        prnt('-get_previous_hash',self)
        previous_block = self.get_previous_block(is_validated=True)
        prnt('previous_block',previous_block)
        if previous_block and previous_block._meta.object_name == 'Block':
            return previous_block.hash
        elif not previous_block or previous_block._meta.object_name == 'Blockchain':
            return '0000000'
    
    def is_latest(self, is_validated=True):
        if is_validated:
            next_block = Block.objects.filter(networkChain=self.networkChain, prv_hash=self.hash, validated=True).exists()
        else:
            next_block = Block.objects.filter(networkChain=self.networkChain, prv_hash=self.hash).exclude(validated=False).exists()
        return True if not next_block else False

    def get_assigned_nodes(self, fetch_broadcast_list=True, loop=True, opBlock_data={}):
        prnt('-get_assigned_nodes',self.id)
        from utils.locked import get_broadcast_list
        broadcast_list = {}
        if self.Transaction_obj:
            if not self.Transaction_obj.SenderWallet_obj: # reward transactions
                prnt('self.Transaction_obj',self.Transaction_obj)
                carry_on = False
                if 'BlockReward' in self.Transaction_obj.regarding and self.Transaction_obj.regarding['BlockReward'] == self.id:
                    return_receiverTransaction = False
                    carry_on = True
                    if not opBlock_data:
                        opBlock_data = get_relevant_nodes_from_block(obj=self, blockchain=get_chain_id(self.Transaction_obj.senderChainGenId))
                elif self.Transaction_obj.ReceiverWallet_obj and self.Transaction_obj.ReceiverWallet_obj.id == self.Blockchain_obj.genesisId:
                    return_receiverTransaction = True
                    carry_on = True
                    if not opBlock_data:
                        opBlock_data = get_relevant_nodes_from_block(obj=self, genesisId=self.Transaction_obj.ReceiverWallet_obj.id)
                if carry_on:
                    creator_nodes, validator_nodes = get_node_assignment(self, return_receiverTransaction=return_receiverTransaction, full_validator_list=True, opBlock_data=opBlock_data)
                    if fetch_broadcast_list:
                        broadcast_list = get_broadcast_list(self, relevant_nodes=opBlock_data['relevant_nodes'], peer_count=_number_of_peers, seed_nodes=creator_nodes, important_nodes=validator_nodes, loop=loop)
                    return creator_nodes, validator_nodes, broadcast_list
                else:
                    self.is_not_valid(note='transaction_err2')
                    prntDebug('px transaction_err2',self.id)
                    return [], [], {}
            else:
                # peer to peer transactions - will need work
                if not opBlock_data:
                    opBlock_data = get_relevant_nodes_from_block(obj=self, genesisId=self.Blockchain_obj.genesisId)
                if self.Transaction_obj.ReceiverWallet_obj == self.Blockchain_obj:
                    # transaction_type = 'sender'
                    creator_nodes, validator_nodes = get_node_assignment(self, return_receiverTransaction=True, full_validator_list=True, opBlock_data=opBlock_data)
                    if fetch_broadcast_list:
                        broadcast_list = get_broadcast_list(self.Transaction_obj, relevant_nodes=opBlock_data['relevant_nodes'], peer_count=_number_of_peers, seed_nodes=creator_nodes, important_nodes=validator_nodes, loop=loop)
                    return creator_nodes, validator_nodes, broadcast_list
                elif self.Transaction_obj.SenderWallet_obj == self.Blockchain_obj:
                    # transaction_type = 'receiver'
                    creator_nodes, validator_nodes = get_node_assignment(self.Transaction_obj, full_validator_list=True, opBlock_data=opBlock_data)
                    if fetch_broadcast_list:
                        broadcast_list = get_broadcast_list(self.Transaction_obj, relevant_nodes=opBlock_data['relevant_nodes'], peer_count=_number_of_peers, seed_nodes=creator_nodes, important_nodes=validator_nodes, loop=loop)
                    return creator_nodes, validator_nodes, broadcast_list
                
        elif self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            if not opBlock_data:
            #     opBlock_data = get_relevant_nodes_from_block(obj=self, genesisId=self.Blockchain_obj.genesisId, first_block_override=True)
                opBlock_data = get_relevant_nodes_from_block(dt=(string_to_dt(self.DateTime)-datetime.timedelta(minutes=20)), blockchain=self.Blockchain_obj, obj=self, include_relays=True, first_block_override=True)
            prnt('opBlock_data',opBlock_data)
            creator_nodes, validator_nodes = get_node_assignment(self, opBlock_data=opBlock_data, full_creator_list=True)

            return creator_nodes, validator_nodes, broadcast_list
        else:
            if not opBlock_data:
                opBlock_data = get_relevant_nodes_from_block(obj=self, blockchain=self.Blockchain_obj)
            creator_nodes, validator_nodes = get_node_assignment(self, full_validator_list=True, opBlock_data=opBlock_data)
            if fetch_broadcast_list:
                broadcast_list = get_broadcast_list(self, relevant_nodes=opBlock_data['relevant_nodes'], peer_count=_number_of_peers, seed_nodes=creator_nodes, important_nodes=validator_nodes, loop=loop, all_nodes=True)
            return creator_nodes, validator_nodes, broadcast_list
        
    def get_required_validator_count(self, node_ids=None, return_node_data=False, strings_only=True, opBlock_data=None):
        prnt('-block.get_required_validator_countxxo', self.id, self.Blockchain_obj.genesisName, self.networkChain)
        from utils.models import declare_var
        node_data = declare_var(opBlock_data, {})
        if not node_data:
            first_block_override = False
            include_relays = False
            opChainId = hash_obj_id(Blockchain, specific_data={'objType': 'Blockchain', 'genesisId': _OperationsChain_genesisId})
            prnt('opChainId',opChainId)
            opChainId = get_chain_id(_OperationsChain_genesisId)
            prnt('opChainId2',opChainId)
            if self.networkChain == _OperationsChain_genesisId:
                first_block_override = True
            if self.Blockchain_obj.genesisId in ['Sonet',_OperationsChain_genesisId]:
                include_relays = True
            node_data = get_relevant_nodes_from_block(dt=self.DateTime, obj=self, blockchain=self.Blockchain_obj, strings_only=strings_only, first_block_override=first_block_override, include_relays=include_relays)
        if not node_ids:
            node_ids = [iden for iden in node_data['relevant_nodes']]
        if self.networkChain == _OperationsChain_genesisId and self.index == 1:
            prev = self.get_previous_block()
            if not prev or prev._meta.object_name == 'Blockchain':
                if return_node_data:
                    return 1, node_data
                return 1
        elif self.networkChain == _OperationsChain_genesisId:
            count = (len(node_data['relevant_nodes'])*0.9)
            prnt('get_required_validator_count',node_data['relevant_nodes'])
            if count < 10:
                count = len(node_data['relevant_nodes'])
            if count > 400:
                count = 400
            if count < 1:
                count = 1
            if return_node_data:
                return count, node_data
            return count
        # if self.modlVer >= 1:
        opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=self.DateTime, validated=True).only('opData').order_by('-index', 'created').first()
        num = opBlock.opData['block_validator_count']
        if len(node_ids) <= 1:
            if return_node_data:
                return 1, node_data
            return 1
        elif len(node_ids) <= 5:
            if return_node_data:
                return len(node_ids) - 1, node_data
            return len(node_ids) - 1 # minus creator, all remaining
        elif num > len(node_ids):
            if return_node_data:
                return ((len(node_ids)-1)*0.75), node_data
            return ((len(node_ids)-1)*0.75) # minus creator, 75% of remaining
        else:
            if return_node_data:
                return num, node_data #_block_validator_count at time of block
            return num

    def get_required_consensus(self, version=None):
        if not version:
            version = self.modlVer
        if self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            if int(version) >= 1:
                return (1/3)*2
        if int(version) >= 1:
            return (1/3)*2
        
    def get_required_delay(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return block_time_delay(self) # should get from opBlock in use at time of block.Datetime

    def verify_validation(self):
        prnt('-verify_validation')
        found_idens, missing_idens = check_block_contents(self, retrieve_missing=True, log_missing=False, downstream_worker=False, return_missing=True)
        fail_reason = []
        if any(i for i in self.data if i not in found_idens):

            prnt('not valid 1')
            validated = False
            for iden, commit in self.data.items():
                if iden != 'meta' and iden not in found_idens:
                    validated = False
                    fail_reason.append(iden)
        if any(i for i in self.extraData if i not in found_idens):

            prnt('not valid 2')
            validated = False
            for iden, commit in self.extraData.items():
                if iden != 'meta' and iden not in found_idens:
                    validated = False
                    fail_reason.append(iden)
        prnt('opt3')
        return False

    def get_validators(self):
        returnData, not_found, not_valid = get_data(self.validations, include_related=True, verify_data=False)
        if self.Transaction_obj and self.Transaction_obj.ReceiverWallet_obj.id == self.Blockchain_obj.genesisId:
            txData, not_found, not_valid = get_data(self.Transaction_obj.validations, include_related=True, verify_data=False)
            returnData += txData
        # prntDebug('get block validators return:',returnData)
        return returnData

    def get_full_data(self, include_validators=True):
        # should also check against hash saved in block
        from utils.locked import verify_obj_to_data
        self_dict = convert_to_dict(self)
        data = {**self.data, **self.extraData}
        if self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            returnData = []
            id_list = []
            for chain, addresslist in data.items():
                for item in addresslist:
                    if item not in id_list:
                        id_list.append(item)
            nodes = Node.objects.filter(id__in=id_list)
            for obj in nodes:
                is_valid = verify_obj_to_data(obj, obj)
                if is_valid:
                    returnData.append(convert_to_dict(obj))
            nodeUpdates = NodeReview.objects.filter(TargetNode_obj__id__in=id_list)
            for obj in nodeUpdates:
                is_valid = verify_obj_to_data(obj, obj)
                if is_valid:
                    returnData.append(convert_to_dict(obj))

        else:
            returnData = []
            for chunk in chunk_dict(data, 300):
                storedModels, not_found, not_valid, delLogs = get_data(chunk, return_model=False, include_related=True, include_deletions=True, verify_data=False)
                for x in storedModels:
                    returnData.append(x)
                for x in delLogs:
                    returnData.append(x)
                storedModels.clear()
        returnData.append(self_dict)
        if include_validators:
            returnData2, not_found2, not_valid2 = get_data(self.validations, include_related=False, verify_data=False) 
            returnData = returnData2 + returnData
        return returnData

    def adjust_settings(self):
        prnt('r-adjust_settings')
        return
        from utils.models import write_operatorData
        now = now_utc()
        inactive_nodes = Node.objects.exclude(id__in=self.data['Active'], activeNode=True).defer('chain_array','Block_obj','User_obj','abilities','region_data')
        update_list = []
        for n in inactive_nodes:
            n.activeNode = False
            n.updated_on_node = now
            update_list.append(n)
        dynamic_bulk_update(model=Node, items_field_update=['activeNode','updated_on_node'], items=update_list) 
        update_list.clear()
        inactive_nodes = None

        nodes = Node.objects.filter(id__in=self.data['Active']).defer('chain_array','Block_obj','User_obj','abilities','region_data')
        update_list = []
        for n in nodes:
            n.activeNode = True
            n.suspended_dt = None
            n.updated_on_node = now
            update_list.append(n)
        dynamic_bulk_update(model=Node, items_field_update=['activeNode','suspended_dt','updated_on_node'], items=update_list) 
        update_list.clear()

        addresses = [n.return_address() for n in nodes]
        nodes_dict = {n.id: n for n in nodes}
        nodes = None

        # self.notes['node_data'] = {iden:{'addr':nodes_dict[iden].return_address(),'pos':nodes_dict[iden].pos,'pk':nodes_dict[iden].pkey, 'type':nodes_dict[iden].node_type} for iden in self.data['Active'] if iden in nodes_dict}
        nodes_dict.clear()
        # max_pos_node = Node.objects.filter(Block_obj__validated=True, Block_obj__DateTime__lte=self.DateTime).order_by('-pos').values('pos').first()
        # if max_pos_node:
        #     self.notes['max_pos'] = max_pos_node['pos']
        self.save(update_fields=['notes'])
        prev_block = self.get_previous_block(is_validated=True)
        if prev_block and prev_block._meta.object_name == 'Block':
            if 'node_data' in prev_block.notes:
                del prev_block.notes['node_data']
                prev_block.save(update_fields=['notes'])

        operatorData = get_operatorData()
        node_addresses = {iden:value['addr'] for iden, value in self.notes['node_data'].items()}
        operatorData['node_list'] = {'lastUpdate' : dt_to_string(now_utc()), 'block_data' : self.data, 'addresses':node_addresses}
        operatorData['ip_master_list'] = node_addresses
        write_operatorData(operatorData)

        import os
        # import shutil
        from os.path import expanduser
        homepath = expanduser("~")
        folder_path = os.path.expanduser(homepath + "/Sonet/.data/special")
        file_path = os.path.join(folder_path, "trusted_sources.py")
        if os.path.exists(file_path):
            prnt(f"The file '{file_path}' already exists!")
        else:
            with open(file_path, "w") as f:
                f.write("")

        formatted_addresses = []
        for ip in addresses:
            formatted_addresses.append(f'https://sosayus.com')
            formatted_addresses.append(f'http://sosayus.com')
        for ip in addresses:
            if ip:
                formatted_addresses.append(f'https://{ip}')
            # formatted_addresses.append(f'http://{ip}')

        f = open(homepath + "/Sonet/.data/special/trusted_sources.py", "r+")
        f.close()
        open(homepath + "/Sonet/.data/special/trusted_sources.py", "w").close()
        f = open(homepath + "/Sonet/.data/special/trusted_sources.py", "r+")
        # f.writelines(text)
        f.write(f"ADDRESSES = {repr(formatted_addresses)}\n")
        f.close

        open(homepath + "/Sonet/.data/special/cors.conf", "w").close()
        with open(homepath + "/Sonet/.data/special/cors.conf", "w") as f:
            f.write("map $http_origin $cors_origin {\n")
            f.write('    default "";\n')
            for address in addresses:
                f.write(f'    "https://{address}" $http_origin;\n')
            f.write("}\n")
        prnt('done adjust settings')
        # import time
        # time.sleep(30)
        return None

    def build_node_record(self):
        prnt('--build_node_record',self.id)
        prnt('self.data',self.data)
        
        def shuffle_order(node_ids, salt=''):
            if not node_ids:
                return {} if isinstance(node_ids, dict) else []
            dt_str = dt_to_string(self.DateTime)
            if isinstance(node_ids, list):
                node_ids.sort()
            elif isinstance(node_ids, dict):
                node_ids = dict(sorted(node_ids.items()))
            prnt('shuffle_nodes',node_ids)
            seed_input = f"shuffle_opBlock_{dt_str}_{salt}"
            seed_hash = hashlib.sha256(seed_input.encode('utf-8')).hexdigest()
            seed_int = int(seed_hash, 16)
            rng = random.Random(seed_int)
            shuffled_nodes = node_ids.copy()
            if isinstance(node_ids, dict):
                keys = list(shuffled_nodes.keys())
                rng.shuffle(keys)
                shuffled_nodes = {k: shuffled_nodes[k] for k in keys}
            else:
                rng.shuffle(shuffled_nodes)
            prnt('shuffled_nodes',shuffled_nodes)
            return shuffled_nodes

        ability_types = ['cloudflare']
        node_types = ['server','maintainer','server/maintainer','relay','intelligence']
        prev_opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, index__lt=self.index, validated=True).values('id').order_by('-index', 'created').first()
        if prev_opBlock:
            block_id = prev_opBlock['id']
        else:
            block_id = '0'
        prnt('block_id',block_id)

        def build_record(pointerId, pointerType):
            prnt('-build_record',pointerId,pointerType)

            existing_record = NodeRecord.objects.filter(pointerId=pointerId, pointerType=pointerType, Block_obj__id=self.id).first()
            prnt('existing_record',existing_record)
            if existing_record:
                if not existing_record.is_valid:
                    existing_record.is_valid = True
                    existing_record.save()
            else:
                prev_record = NodeRecord.objects.filter(pointerId=pointerId, pointerType=pointerType, Block_obj__id=block_id).first()
                prnt('prev_record',prev_record)
                if prev_record:
                    import copy
                    record_data = copy.deepcopy(prev_record.data)
                else:
                    record_data = {'active': {}, 'abilities': {}}
                prnt('record_data',record_data)
                # new_data = {}
                for node_id, node_data in self.data.items():
                    prnt('node_id',node_id)
                    prnt('node_data',node_data)
                    prnt("node_data['chain_array']",node_data['chain_array'])
                    prnt("node_data['plugin_array']",node_data['plugin_array'])
                    prnt("node_data['region_array']",node_data['region_array'])
                    prnt("get_chain_id(pointerId)",get_chain_id(pointerId))
                    node_supported = list(node_data['chain_array']) + list(node_data['plugin_array']) + list(node_data['region_array'])
                    prnt('node_supported',node_supported)
                    if node_data['chain_array'] and (pointerId in node_supported or get_chain_id(pointerId) in node_supported) and node_data['activated_dt'] and not node_data.get('suspended_dt', None) and not node_data.get('expelled_dt', None):
                        prnt('a1')
                        record_data['active'][node_id] = {'pos':node_data['pos'], 'type':node_data['node_type']}
                        for node_type in node_types:
                            prnt('node_type',node_type)
                            if node_type not in record_data:
                                record_data[node_type] = []
                            if node_data['node_type'] == node_type:
                                if node_id not in record_data[node_type]:
                                    record_data[node_type].append(node_id)
                            elif node_id in record_data[node_type]:
                                record_data[node_type].remove(node_id)
                        if node_data['abilities']:
                            prnt('a2')
                            for a in ability_types:
                                prnt('a',a)
                                if a not in record_data['abilities']:
                                    record_data['abilities'][a] = []
                                if a in node_data['abilities']:
                                    if node_id not in record_data['abilities'][a]:
                                        record_data['abilities'][a].append(node_id)
                                elif node_id in record_data['abilities'][a]:
                                    record_data['abilities'][a].remove(node_id)

                    else:
                        prnt('b1')
                        if node_id in record_data['active']:
                            del record_data['active'][node_id]
                        for node_type in node_types:
                            prnt('node_type',node_type)
                            if node_type in record_data and node_id in record_data[node_type]:
                                record_data[node_type].remove(node_id)
                        for a in ability_types:
                            prnt('a',a)
                            if a in record_data['abilities'] and node_id in record_data['abilities'][a]:
                                record_data['abilities'][a].remove(node_id)
                prnt('c1')
                # assign server/maintainer nodes either server or maintainer
                tiebreak = 'servers'
                if 'server/maintainer' in record_data:
                    servers = list(record_data['server'])
                    maintainers = list(record_data['maintainer'])
                    already_placed = set(servers) | set(maintainers)
                    to_distribute = [item for item in record_data['server/maintainer'] if item not in already_placed]
                    prnt('c2')
                    # remove duplicates within record_data['server/maintainer'] while preserving order
                    seen = set()
                    unique_to_distribute = []
                    for item in to_distribute:
                        if item not in seen:
                            seen.add(item)
                            unique_to_distribute.append(item)
                    prnt('c3')
                    # assign to shorter list
                    for item in unique_to_distribute:
                        len_servers, len_maintainers = len(servers), len(maintainers)
                        if len_servers < len_maintainers:
                            servers.append(item)
                        elif len_maintainers < len_servers:
                            maintainers.append(item)
                        else:
                            if tiebreak == "maintainers":
                                maintainers.append(item)
                            else:
                                servers.append(item)
                    prnt('c4')
                    # if either list is still under 3, backfill it from the other list's assigned items
                    MIN_SIZE = 3
                    if len(servers) < MIN_SIZE or len(maintainers) < MIN_SIZE:
                        all_distributed = set(unique_to_distribute)
                        if len(servers) < MIN_SIZE:
                            # pull items that were assigned to maintainers (not originally there)
                            candidates = [i for i in maintainers if i in all_distributed]
                            for item in candidates:
                                if len(servers) >= MIN_SIZE:
                                    break
                                servers.append(item)
                        if len(maintainers) < MIN_SIZE:
                            candidates = [i for i in servers if i in all_distributed]
                            for item in candidates:
                                if len(maintainers) >= MIN_SIZE:
                                    break
                                maintainers.append(item)
                    prnt('c5')
                    record_data['server'] = servers
                    record_data['maintainer'] = maintainers
                    del record_data['server/maintainer']
                prnt('c6')
                # for key, value in new_data.items():
                #     new_data[key] = shuffle_order(value, key)
                record_data['active'] =  shuffle_order(record_data['active'])
                for key, value in record_data.items():
                    if key != 'active':
                        if isinstance(value, list):
                            record_data[key] =  shuffle_order(value)
                        elif isinstance(value, dict):
                            for k, v in value.items():
                                if isinstance(ValueError, list):
                                    record_data[k] =  shuffle_order(v)

                prnt('new_data',record_data)
                new_record = NodeRecord(pointerId=pointerId, pointerType=pointerType, DateTime=self.DateTime, Block_obj_id=self.id, is_valid=True)
                new_record.data = record_data
                new_record.save()
                
                if pointerId == _OperationsChain_genesisId:
                    prnt('c7')
                    # if any node has gone online or offline create job assignment
                    # if job assigned create notifications for each node now online/offline targeted to node operator
                    # run the same as scraper jobs - two nodes create data, third node validates, then broadcasts to network
                    if prev_record and record_data:
                        prev_record_data = copy.deepcopy(prev_record.data)
                        newly_active_node_ids = record_data['active'].keys() - prev_record_data['active'].keys()
                        newly_deactive_node_ids = prev_record_data['active'].keys() - record_data['active'].keys()
                        prnt('newly_active_node_ids',newly_active_node_ids)
                        prnt('newly_deactive_node_ids',newly_deactive_node_ids)
                        if newly_active_node_ids or newly_deactive_node_ids:

                            func = 'alert_node_changes'
                            scrapers, validators = get_node_assignment(chainId=pointerId, func=func, dt=self.DateTime, nodeType='maintainer')
                            from utils.models import round_time, dt_to_string, create_share_object, get_operator_obj, save_and_return, finishScript
                            self_node_id = get_operator_obj("self_nodeId")
                            if self_node_id in scrapers:
                                prnt('c8')
                                from accounts.models import UserNotification, Notification
                                from posts.models import Region
                                from utils.locked import hash_obj_id 
                                earth = Region.objects.filter(Name='Earth').first()
                                log = create_share_object(func, earth, special=None, dt=self.DateTime, iden=None)

                                changed_nodes = Node.objects.filter(id__in=newly_active_node_ids | newly_deactive_node_ids)
                                by_id = {obj.id: obj for obj in changed_nodes}
                                prnt('by_id',by_id)
                                for node_id in newly_active_node_ids | newly_deactive_node_ids:
                                    prnt('node_id',node_id)
                                    node = by_id.get(node_id)

                                    operator = node.User_obj
                                    DateTime = self.DateTime
                                    title = f"{node.node_name} is now active"
                                    content = ''

                                    if node_id in prev_record_data['active']:
                                        title = f"{node.node_name} is now deactive"
                                        if self.data[node_id]['suspended_dt']:
                                            content = f"Node was suspended at {dt_to_string(self.data[node_id]['suspended_dt'])}."

                                    created = round_time(DateTime, 'down', 'hour')
                                    iden = hash_obj_id('Notification', specific_data=f"{created}_{title}_{operator.id}")
                                    prnt('iden',iden)
                                    if not Notification.objects.filter(id=iden).exists():
                                        noti = Notification(User_obj=operator)
                                        noti.id = iden
                                        noti.created = created
                                        noti.Title = title
                                        noti.Content = content
                                        noti.DateTime = DateTime
                                        noti.targetUsers={'by_id' : operator.id}, 
                                        noti.pointerId=node_id, 
                                        noti.Country_obj=earth, 
                                        noti.Region_obj=earth,
                                        notification, notificationU, notification_is_new, log = save_and_return(noti, None, log)
                                        prnt('saved noti',iden)

                                finishScript(log, None, None, send_off=False)

        mainChains = [_OperationsChain_genesisId,_KeyChain_genesisId,_AccountChain_genesisId,_EarthChain_genesisId]
        chains = mainChains + specialChains
        s = Sonet.objects.values('id').first()
        chains.append(s['id'])
        if 'New' in chains:
            chains.remove('New')
        prnt('chains',chains)
        for i in chains:
            build_record(i, 'ops')

        prnt('regions')
        plugins = Plugin.objects.exclude(Block_obj=None).exclude(Title__in=mainChains + ['Posts', 'Network']).values('id')
        # if not plugins:
        #     plugins = Plugin.objects.exclude(Title__in=mainChains + ['Posts', 'Network']).values('id')
        for plugin in plugins:
            build_record(plugin['id'], 'plugin')
        from posts.models import Region
        for region in Region.objects.filter(Validator_obj__is_valid=True).exclude(id=_EarthChain_genesisId):
            prnt('region',region)
            build_record(region.id, 'region')

        all_nodes = {'active':{}}
        chains = {}
        prnt('nodes')
        opRecord = NodeRecord.objects.filter(pointerId=_OperationsChain_genesisId, Block_obj__id=self.id, DateTime=self.DateTime, is_valid=True).only('data').first()

        if opRecord:
            nodes = Node.objects.filter(id__in=[i for i in opRecord.data['active']]).only('id','pos','chain_array')
        elif self.index == 1:
            nodes = Node.objects.exclude(activated_dt=None).only('id','pos','chain_array')
        else:
            nodes = []
        for node in nodes:
            prnt('node',node, node.chain_array)
            all_nodes['active'][node.id] = node.pos
            if node.chain_array:
                for chain in node.chain_array:
                    prnt('ch1',chain)
                    if chain not in chains:
                        chains[chain] = []
                    if node.id not in chains[chain]:
                        chains[chain].append(node.id)
            else:
                for chain in mainChains:
                    prnt('ch2',chain)
                    if chain not in chains:
                        chains[chain] = []
                    if node.id not in chains[chain]:
                        chains[chain].append(node.id)
        prnt('regions2')
        for region in Region.objects.exclude(Block_obj=None).exclude(id=_EarthChain_genesisId).only('id'):
            if region.id in chains:
                all_nodes[region.id] = chains[region.id]


        all_nodes['active'] =  shuffle_order(all_nodes['active'])
        for key, value in all_nodes.items():
            if key != 'active':
                if isinstance(value, list):
                    all_nodes[key] =  shuffle_order(value)
                elif isinstance(value, dict):
                    for k, v in value.items():
                        if isinstance(ValueError, list):
                            all_nodes[k] =  shuffle_order(v)
        prnt('save')
        new_record = NodeRecord(pointerId='Master', pointerType='ops', DateTime=self.DateTime, Block_obj_id=self.id, is_valid=True)
        new_record.data = all_nodes
        new_record.save()

        now = now_utc()
        nodes = Node.objects.filter(id__in=all_nodes['active']).defer('chain_array','Block_obj','User_obj','abilities','region_data')
        update_list = []
        for n in nodes:
            n.activeNode = True
            n.suspended_dt = None
            n.updated_on_node = now
            update_list.append(n)
        dynamic_bulk_update(model=Node, items_field_update=['activeNode','suspended_dt','updated_on_node'], items=update_list) 
        update_list.clear()

        inactive_nodes = Node.objects.exclude(id__in=all_nodes['active']).filter(activeNode=True).defer('chain_array','Block_obj','User_obj','abilities','region_data')
        update_list = []
        for n in inactive_nodes:
            n.activeNode = False
            n.updated_on_node = now
            update_list.append(n)
        dynamic_bulk_update(model=Node, items_field_update=['activeNode','updated_on_node'], items=update_list) 
        update_list.clear()


    def broadcast(self, broadcast_list=None, validations=None, validator_list=None, validators_only=False, target_node_id=None, skip_self=True, packet_id=None):
        prntn('--broadcast_block', self.id, 'now',now_utc(), 'packet_id', packet_id)
        prnt('broadcast_list',broadcast_list,'validator_list',validator_list,'validators_only',validators_only,'validations',validations)
        if e_brake(2) or not self.signed:
            return 
        try:
            self.refresh_from_db()
        except Exception as e:
            prnt('broadcst blcok err 8412', str(e))
            return
        log = logBroadcast(return_log=True)
        if self.id not in log.data:
            log.data[self.id] = {'first_broadcast':dt_to_string(now_utc())}
        proceed = True
        if proceed:
            if skip_self and now_utc() < self.DateTime + datetime.timedelta(minutes=60):
                skip_self = False
            if self.validated:
                loop = False
                all_nodes = True
            else:
                loop = True
                all_nodes = False
            if not target_node_id:
                target_node_id = self.CreatorNode_obj.id
            self_node = get_self_node()
            from utils.locked import sort_for_sign
        
            opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=self.DateTime, validated=True).order_by('-index', 'created').first()
            
            def add_to_block_list(block_list, block, validations):
                if not block:
                    return block_list
                if not validations:
                    validations = block.get_validators()
                elif isinstance(validations[0], models.Model):
                    validations = [convert_to_dict(v) for v in validations]
                if validations:
                    validations = [sort_for_sign(v) for v in validations]
                future_block_count = Block.objects.filter(networkChain=block.networkChain, index__gt=block.index, validated=True).count()
                block_list.append({'block_dict' : sort_for_sign(convert_to_dict(block, exclude=['notes','validations'])), 'block_transaction':block.get_transaction_data(), 'block_data' : [], 'validations' : validations, 'future_block_count':future_block_count, 'block_is_valid':block.validated, 'opBlock':opBlock.id if opBlock else None})
                return block_list
            
            block_list = add_to_block_list([], self, validations)
            next_block = Block.objects.filter(networkChain=self.networkChain, index__gt=self.index, validated=True).order_by('index').first()
            if next_block:
                block_list = add_to_block_list(block_list, next_block, None)
            prnt('self.networkChain:',self.networkChain)
            
            hash_history = [i['hash'] for i in reversed(Block.objects.filter(networkChain=self.networkChain, index__lt=self.index, validated=True).values("hash").order_by('-index')[:50])]
            sending_data = {'type' : 'Blocks',  'opBlock': opBlock.id if opBlock else None, 'opBlock_hash':opBlock.hash if opBlock else None, 'blockchainId' : self.networkChain, 'genesisId':self.Blockchain_obj.genesisId, 'hash_history':hash_history, 'block_list' : json.dumps(block_list), 'end_of_chain' : True}
            
            if opBlock and opBlock.index != opBlock.Blockchain_obj.chain_length:
                sending_data['opBlock_not_latest'] = True

            include_relays = False
            if self.networkChain in universalChains:
                include_relays = True
            if not packet_id:
                packet_id = hash_obj_id('DataPacket', specific_data=str(json.dumps(block_list))+str(validators_only))
            if self.Blockchain_obj.genesisId == _OperationsChain_genesisId: # opBlocks blasted widely and randomly
                # if not packet_id:
                #     packet_id = hash_obj_id('DataPacket')
                now = self.DateTime-datetime.timedelta(minutes=20)
                from utils.locked import get_broadcast_list
                lst = get_broadcast_list(packet_id, dt=now, region_id=self.networkChain, seed_nodes=[self.CreatorNode_obj.id], peer_count=10, loop=False, all_nodes=True, include_relays=include_relays)
            else:
                now = self.DateTime
                if validators_only:
                    prnt('1')
                    required_validators, node_data = self.get_required_validator_count(return_node_data=True) # ensure node_data consistency
                    from utils.locked import get_node_assignment
                    creator_nodes, validator_list = get_node_assignment(self, opBlock_data=node_data)
                    # lst = {self_node.id:validator_list}
                    from utils.locked import get_broadcast_list
                    prnt('validator_list',validator_list)
                    prnt('creator_nodes',creator_nodes)
                    v_list = creator_nodes + validator_list
                    v_nodes = Node.objects.filter(id__in=v_list)
                    prnt('v_list',v_list)
                    relevant_nodes = {node.id:node.return_address() for node in v_nodes}
                    lst = get_broadcast_list(packet_id, dt=now, region_id=self.networkChain, relevant_nodes=relevant_nodes, seed_nodes=[self.CreatorNode_obj.id], included_nodes=[self.CreatorNode_obj.id], loop=True, all_nodes=False, include_relays=include_relays)
                else:
                    prnt('3')
                    if not broadcast_list:
                        from utils.locked import get_broadcast_list
                        broadcast_list = get_broadcast_list(packet_id, dt=now, region_id=self.networkChain, seed_nodes=[self.CreatorNode_obj.id], included_nodes=[self.CreatorNode_obj.id], loop=loop, all_nodes=all_nodes, include_relays=include_relays)
                    lst = broadcast_list
            prnt('lst1',lst)
            if len(lst) == 1 and self_node.id in lst:
                skip_self = False
                if not lst[self_node.id]:
                    lst[self_node.id].append(self_node.return_address())
            prnt('lst2',lst)

            sending_data = sign_for_sending(sending_data)
            prnt('sending_data',sending_data)
            prnt('packet-id',packet_id)
            dp = DataPacket.objects.filter(id=packet_id).values('id','updated_on_node').first()
            if dp and dp['updated_on_node'] > now_utc() - datetime.timedelta(minutes=10):
                prnt('recently broadcast')
                return
            elif not dp:
                func = f'blockbroadcast:{self.id}'
                dp = DataPacket(id=packet_id, Node_obj=self_node, func=func, networkChain=self.networkChain)
                dp.save()
            headers = {'Packet-Id':packet_id, 'Packet-Origin-Dt':dt_to_string(now), 'Senderid':self_node.id, 'func':'blockbroadcast', 'Packet-Creator':self_node.id, 'Seedid':self.CreatorNode_obj.id, 'Dt':dt_to_string(now), 'Blockchainid' : self.networkChain, 'Genesisid':self.Blockchain_obj.genesisId, 'Blockid':self.id, 'Index':str(self.index), 'Prevhash':self.prv_hash, 'Blockdt':dt_to_string(self.DateTime), 'Rebroadcast':'True', 'Validators-only': str(validators_only)}
            successes = downstream_broadcast(lst, 'network/receive_blocks', sending_data, headers=headers, target_node_id=[target_node_id, self_node.id], stream=True, skip_self=skip_self)
            if successes:
                prnt('broadcast block successes:',successes)
                # if 'history' not in dp.notes:
                #     dp.notes['history'] = []
                # dp.notes['history'].append({'broadcast':dt_to_string(now_utc()), 'successes':successes})

                dp = DataPacket.objects.filter(id=packet_id).values('id','notes','func').first()
                if 'history' not in dp['notes']:
                    dp['notes']['history'] = []
                dp['notes']['history'].append({'broadcast':dt_to_string(now_utc()), 'successes':successes})
                func = dp['func']
                if 'completed' not in func and Node.objects.filter(activeNode=True, suspended_dt=None, expelled_dt=None).exclude(activated_dt=None).exclude(id=self_node.id).exclude(Block_obj=None).exists():
                    func = f'completed_blockbroadcast:{self.id}'
                DataPacket.objects.filter(id=dp['id']).update(updated_on_node=now_utc(), notes=dp['notes'], func=func)
            

    def is_not_valid(self, id=None, mark_strike=True, note='', check_posts=False, super_delete_content=False, remove_block=False, revision_limit=True):
        prnt('--is_not_valid',self,note,self.validated)
        from utils.models import get_self_node, superDelete, has_field, get_data
        if self.validated == False:
            prnt('already invalid')
            
            # obj data will need to be invalidated as well because creatorNode_obj/validatorNodeId is checked on reception of item in sync_model
            following_blocks = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, index__gt=self.index).exclude(validated=False).values('id','hash','prv_hash').order_by('index')
            # prnt('folowing_blocks',following_blocks)
            if following_blocks:
                invalidate = []
                initial_hash = self.hash
                for b in following_blocks:
                    if b['prv_hash'] == initial_hash:
                        invalidate.append(b['id'])
                        initial_hash = b['hash']
                    else:
                        break
                if invalidate:
                    for b in Block.objects.filter(id__in=invalidate):
                        if not exists_in_worker('is_not_valid', queue=['high','main'], id=b.id):
                            django_rq.get_queue('high').enqueue(b.is_not_valid, id=b.id, note=f'followed_previous_fail_b-{self.id}', super_delete_content=super_delete_content, revision_limit=False, job_timeout=120, result_ttl=7200)

            if self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
                for node_record in NodeRecord.objects.filter(Block_obj__id=self.id, is_valid=True):
                    node_record.is_valid = False
                    node_record.save()
                dynamic_bulk_update('Node', update_data={'rec_change': None}, id__in=[i for i in self.data], rec_change=self.id)
                dependent_blocks = Block.objects.filter(opBlockId=self.id).exclude(validated=False).defer('data','extraData','notes')
                prnt('dependent_blocks',dependent_blocks)
                if dependent_blocks:
                    for b in dependent_blocks:
                        if not exists_in_worker('is_not_valid', queue=['high','main'], id=b.id):
                            django_rq.get_queue('high').enqueue(b.is_not_valid, id=b.id, note=f'dependent_block_fail_b-{self.id}', super_delete_content=super_delete_content, revision_limit=False, job_timeout=120, result_ttl=7200)
            return
        if revision_limit:
            proceeding_block1 = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, prv_hash=self.hash, validated=True).values('hash').first()
            if proceeding_block1:
                proceeding_block2 = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, prv_hash=proceeding_block1['hash'], validated=True).values('hash').first()
                if proceeding_block2:
                    proceeding_block3 = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, prv_hash=proceeding_block2['hash'], validated=True).exists()
                    if proceeding_block3:

                        log = EventLog.objects.filter(pointerId=self.networkChain, type='block_logs').first()
                        if not log:
                            log = EventLog(pointerId=self.networkChain, type='block_logs', Node_obj=get_self_node())
                        if 'last_revision' in log.data:
                            revision_count = 0
                            for revision in log.data['history']:
                                if string_to_dt(revision['dt']) > now_utc() - datetime.timedelta(hours=1):
                                    revision_count += 1
                                    if revision_count > 3:
                                        prnt('too many revisions. last:',log.data['last_revision'], 'now:',dt_to_string(now_utc()))
                                        return
                        log.data['last_revision'] = dt_to_string(now_utc())
                        if 'history' not in log.data:
                            log.data['history'] = []
                        log.data['history'].append({'index':self.index, 'id': self.id, 'dt':log.data['last_revision'], 'future_count': Block.objects.filter(Blockchain_obj=self.Blockchain_obj, index__gt=self.index, validated=True).count()})
                        log.save()


        # if block.creator_node = self_node and block failed by validators, log failed items. if items repeatedly fail block creation, stop commit attmpts for those items
        self_node = get_self_node()
        now = now_utc()
        self.refresh_from_db()
        if mark_strike:
            # do not strike self
            strike = NodeReview.objects.filter(TargetNode_obj=self.CreatorNode_obj, CreatorNode_obj=self_node).first()
            if not strike:
                strike = NodeReview(TargetNode_obj=self.CreatorNode_obj, CreatorNode_obj=self_node)
            if not strike.strikes:
                strike.strikes = {}
            
            if self.id not in strike.strikes:
                strike.strikes[self.id] = dt_to_string(now)
                strike.save()
                self.CreatorNode_obj.too_many_strikes()

        if self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            for node_record in NodeRecord.objects.filter(Block_obj__id=self.id, is_valid=True):
                node_record.is_valid = False
                node_record.save()
            prev_block = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, index__lt=self.index, validated=True).order_by('-index').first()
            if prev_block:
                nodes = Node.objects.exclude(activated_dt=None).filter(suspended_dt=None, lastUpdate__gte=prev_block.DateTime).order_by('-lastUpdate')
            else:
                nodes = Node.objects.exclude(activated_dt=None).filter(suspended_dt=None).order_by('-lastUpdate')
            self.Blockchain_obj.add_item_to_queue(list(nodes), force_add=True)
        else:
            fail_vals = Validator.objects.filter(validatorType='Block', is_valid=False, jobId=self.id).exclude(signed={})

            start_time = time.time()
            for chunk in chunk_dict({**self.data, **self.extraData}, 500):
                storedModels, not_found, not_valid = get_data(chunk, return_model=True, verify_data=False, include_related=False)
                
                obj_ids = []
                add_to_chain = []
                for x in storedModels:
                    if super_delete_content:
                        superDelete(x, force_delete=True)
                    else:
                        if has_field(x, 'Block_obj') and x.Block_obj == self:
                            x.Block_obj = None
                            super(get_model(x._meta.object_name), x).save()
                        if x._meta.object_name != 'Transaction':
                            if not has_field(x, 'networkChain') or x.networkChain == self.networkChain:
                                add_to_chain.append(x)
                                if len(add_to_chain) >= 200:
                                    self.Blockchain_obj.add_item_to_queue(add_to_chain, force_add=True)
                                    add_to_chain = []
                            else:
                                network_chain, x, commit_chain = find_or_create_chain_from_object(x)
                                network_chain.add_item_to_queue(x, force_add=True)
    
                        for val in fail_vals:
                            if 'fail_reason' in val.data and isinstance(val.data['fail_reason'], list) and x.id in val.data['fail_reason']:
                                existing_block = Block.objects.filter(DateTime__gt=x.created).filter(data__has_any_keys=[x.id], validated=True).order_by('-created').only('id').first()
                                if existing_block:
                                    x.Block_obj = existing_block
                                break
                        obj_ids.append(x.id)
                if add_to_chain:
                    self.Blockchain_obj.add_item_to_queue(add_to_chain, force_add=True)

                if obj_ids:
                    if check_posts:
                        from posts.models import Post, Update
                        from accounts.models import Notification
                        for chunk in chunk_list(obj_ids, 500):
                            for p in Post.objects.filter(pointerId__in=chunk, blockId=self.id):
                                p.blockId = None
                                p.validated = p.verify_is_valid(check_update=False, use_assigned_val=True)
                                p.save()
                            updates = Update.objects.filter(id__in=chunk, validated=True)
                            for u in updates:
                                u.validated = u.verify_is_valid(use_assigned_val=True)
                                u.save()
                            notifications = Notification.objects.filter(id__in=chunk, validated=True)
                            for n in notifications:
                                n.validated = u.verify_is_valid(use_assigned_val=True)
                                u.save()
                    else:
                        from posts.models import Post
                        for chunk in chunk_list(obj_ids, 500):
                            Post.all_objects.filter(pointerId__in=chunk, blockId=self.id).update(blockId=None)
                    
        # should track failed objects, repeated failures should be excluded from commit attempts
        self.validated = False
        if not self.validations:
            self.validations = {}
        if note:
            self.notes['fail_position'] = note
        self.notes['fail_dt'] = dt_to_string(now)
        self.notes[dt_to_string(now)] = note
        super(Block, self).save()
        following_blocks = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, index__gt=self.index).exclude(validated=False).values('id','hash','prv_hash','validated').order_by('index')
        prnt('folowing_blocks',following_blocks)
        if following_blocks:
            invalidate = []
            initial_hash = self.hash
            for b in following_blocks:
                if b['prv_hash'] == initial_hash:
                    invalidate.append(b['id'])
                    initial_hash = b['hash']
                else:
                    break
            if invalidate:
                for b in Block.objects.filter(id__in=invalidate):
                    if not exists_in_worker('is_not_valid', queue_name=['high','main'], id=b.id):
                        django_rq.get_queue('high').enqueue(b.is_not_valid, id=b.id, note=f'followed_previous_fail_a-{self.id}', super_delete_content=super_delete_content, revision_limit=False, job_timeout=120, result_ttl=7200)
        
        if not following_blocks or not any(b for b in following_blocks if b['validated']):
            if self.Transaction_obj and self.Transaction_obj.SenderBlock_obj == self:
                prnt('a1')
                self.Transaction_obj.is_not_valid(omit=self, note=f'sender_fail-{self.id}') 
            elif self.Transaction_obj and self.Transaction_obj.ReceiverBlock_obj == self or self.Transaction_obj and self.Transaction_obj.ReceiverBlock_obj == None:
                prnt('a2')
                if self.Transaction_obj.ReceiverBlock_obj:
                    self.Transaction_obj.ReceiverBlock_obj = None
                    self.Transaction_obj.save(update_fields=['ReceiverBlock_obj'])
                if self.Transaction_obj.validated:
                    if Block.objects.filter(Blockchain_obj=self.Blockchain_obj, index=self.index, CreatorNode_obj=self.CreatorNode_obj, DateTime__gte=now_utc() - datetime.timedelta(minutes=10)).count() < 3:
                        self.Transaction_obj.send_for_block_creation(id=self.Transaction_obj.id)
            else:
                prnt('a3')

        if self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            dynamic_bulk_update('Node', update_data={'rec_change': None}, id__in=[i for i in self.data], rec_change=self.id)
            dependent_blocks = Block.objects.filter(opBlockId=self.id).exclude(validated=False).defer('data','extraData','notes')
            prnt('dependent_blocks',dependent_blocks)
            if dependent_blocks:
                for b in dependent_blocks:
                    # b.is_not_valid(note=f'dependent_block_fail-{self.id}', super_delete_content=super_delete_content, revision_limit=False)
                    if not exists_in_worker('is_not_valid', queue_name=['high','main'], id=b.id):
                        django_rq.get_queue('high').enqueue(b.is_not_valid, id=b.id, note=f'dependent_block_fail_a-{self.id}', super_delete_content=super_delete_content, revision_limit=False, job_timeout=120, result_ttl=7200)
        self.Blockchain_obj.chain_length = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, validated=True).order_by('-index').count()
        last_block = Block.objects.filter(Blockchain_obj=self.Blockchain_obj, validated=True).order_by('-created').first()
        if last_block:
            last_dt = last_block.created
        else:
            last_dt = self.Blockchain_obj.created
        self.Blockchain_obj.last_block_datetime = last_dt
        self.Blockchain_obj.save()
        
        if self.Blockchain_obj.queuedData and self.Blockchain_obj.genesisId != _OperationsChain_genesisId:
            if now.minute >= 50:
                if self.Blockchain_obj.last_block_datetime < now - datetime.timedelta(minutes=block_time_delay()-1):
                    prnt('check new block candidate',now,self.id, self.Blockchain_obj.id)
                    self.Blockchain_obj.new_block_candidate(self_node=self_node, dt=now)

        if remove_block:
            self.delete()
        prnt('done not valid')
        
    def is_valid_operations(self, id=None, attempts=1, downstream_worker=True):
        prnt('-is_valid_operations',self)
        self.refresh_from_db()
        def operations():
            if self.validated:
                prnt('already validated')
                if Block.objects.filter(networkChain=self.networkChain, index=self.index).exclude(validated=True).exclude(id=self.id).exclude(validated=False).exists():
                    for b in Block.objects.filter(networkChain=self.networkChain, index=self.index).exclude(validated=True).exclude(id=self.id).exclude(validated=False):
                        b.is_not_valid(note=f'index_taken-{self.id}')

                if Block.objects.filter(networkChain=self.networkChain, prv_hash=self.hash, validated__isnull=True).exists():
                    next_block = Block.objects.filter(networkChain=self.networkChain, prv_hash=self.hash, validated__isnull=True).defer('notes','validations','data','extraData').order_by('created').first()
                    if not exists_in_worker('check_validation_consensus', queue_name=['main','high'], block=next_block):
                        django_rq.get_queue('main').enqueue(check_validation_consensus, next_block, job_timeout=300, result_ttl=7200)

                if self.Transaction_obj and self != self.Transaction_obj.SenderBlock_obj:
                    from transactions.models import Transaction
                    if Transaction.objects.filter(validated=True, ReceiverBlock_obj=None, ReceiverWallet_obj=self.Transaction_obj.ReceiverWallet_obj).exists():
                        next_tx = Transaction.objects.filter(validated=True, ReceiverBlock_obj=None, ReceiverWallet_obj=self.Transaction_obj.ReceiverWallet_obj).order_by('created').first()
                        if next_tx:
                            if not exists_in_worker('send_for_block_creation', id=next_tx.id):
                                django_rq.get_queue('main').enqueue(next_tx.send_for_block_creation, id=next_tx.id, downstream_worker=False, job_timeout=60, result_ttl=7200)
                return True
            prnt('-perform operations',self)
            if self.index > 1 and not Block.objects.filter(networkChain=self.networkChain, hash=self.prv_hash, index=self.index-1, validated=True).exists():
                prnt('prev_block not validated')
                return False
            if Block.objects.filter(networkChain=self.networkChain, index=self.index, validated=True).exclude(id=self.id).exists():
                prnt('block index exists')
                return False
            nonlocal attempts
            nonlocal downstream_worker
            
            proceed = False
            self.validated = True
            self_node = get_self_node()
            if self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
                prnt('z1')
                obj_idens, problem_idens = check_block_contents(self, input_data=self.extraData, retrieve_missing=True, update_items=True, return_missing=True, downstream_worker=False)

                proceed = True
            elif self_node.id in self.validations and self.validations[self_node.id]['is_valid']: # self_node created validator, doesnt need to process contents again ?? how is Block_obj being set by nodes that validated or created?
                proceed = True
            prnt('proceed',proceed)

            if not proceed:
                obj_idens, problem_idens = check_block_contents(self, retrieve_missing=True, update_items=True, return_missing=True, downstream_worker=False)
                prnt('passed check_block_contents')
                if problem_idens or 'unsupported_chain' in self.notes:
                    self.refresh_from_db()
                    self.validated = True
                proceed = True
                prnt('len(obj_idens)1',len(obj_idens))

                from posts.models import Post, update_post
                opBlock_dict = {}
                iden_list = obj_idens.copy()
                prnt('len(iden_list)2',len(iden_list))
                now = now_utc()
                update_map = {}

                update_prefix = get_app_name(model_name='Update', return_prefix=True)
                if any(i.startswith(update_prefix) for i in obj_idens):
                    update_idens = [i for i in obj_idens if get_pointer_type(i) == 'Update']
                    for chunk in chunk_dict(update_idens, 300):
                        storedModels, not_found, not_valid = get_data(chunk, return_model=True, verify_data=False, include_related=False, include_deletions=False)
                        update_map.update({u.pointerId: u for u in storedModels})
                
                prnt('len(iden_list)3',len(iden_list))
                for chunk in chunk_list(iden_list, 500): # suspect this is not getting all items
                    prntDebug('val ops chunk',str(chunk))
                    bulk_update = []
                    fields = []
                    for p in Post.all_objects.filter(pointerId__in=chunk).exclude(validated=True):
                        ran_val = False
                        try:
                            pointer = p.get_pointer()
                            validated = False
                            if has_field(pointer, 'created'):
                                created_dt = dt_to_string(pointer.created)
                                if created_dt not in opBlock_dict:
                                    node_data = get_relevant_nodes_from_block(dt=pointer.created, genesisId=_OperationsChain_genesisId, include_relays=True)
                                    opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=self.DateTime, validated=True).only('opData').order_by('-index', 'created').first()
                                    opBlock_dict[created_dt] = {'node_ids':[n for n in node_data['relevant_nodes']],'number_of_peers':opBlock.opData['number_of_peers'],'relevant_nodes':node_data['relevant_nodes']}
                                validated = validate_obj(obj=p, opBlock_data=opBlock_dict[created_dt], save_obj=False, verify_validator=False, update_pointer=False)
                                ran_val = True
                        except Exception as e:
                            prnt('get node_data valid_operations fail 5324', str(e))
                        if not ran_val:
                            validated = validate_obj(obj=p, save_obj=False, verify_validator=False, update_pointer=False)
                        if validated:
                            p.validated = True
                            p.updated_on_node = now
                            p.blockId = self.id
                            p, updated_fields = update_post(p=p, save_p=False, update=update_map.get(p.pointerId))
                            bulk_update.append(p)
                            if updated_fields:
                                fields += [f for f in updated_fields if f not in fields]
                            iden_list.remove(p.pointerId)
                    prnt(f'val posts block_validate bulk_update: {str(bulk_update)}')
                    if bulk_update:
                        dynamic_bulk_update(model=Post, items_field_update=['validated', 'updated_on_node', 'blockId'] + fields, items=bulk_update)
                for chunk in chunk_list(iden_list, 500):
                    Post.all_objects.filter(pointerId__in=chunk).exclude(blockId=self.id).update(blockId=self.id)
                        
                for i in obj_idens:
                    if i in self.Blockchain_obj.queuedData:
                        del self.Blockchain_obj.queuedData[i]

                plugin_prefix = get_app_name(model_name='Plugin', return_prefix=True)
                if self.is_latest() and any(i.startswith(plugin_prefix) for i in obj_idens):
                    get_app_info(rerun=True)

            if not proceed:
                prnt('block_validate not proceed', self.id)
                return False
            self.notes['validated_dt'] = dt_to_string(now_utc())
            
            if self.is_latest():
                if self.Blockchain_obj.genesisId == _OperationsChain_genesisId:
                    self.build_node_record()
                    self.adjust_settings()
                    dynamic_bulk_update('Node', update_data={'rec_change': self.id}, id__in=[i for i in self.data])
                self.save(update_fields=['validated','notes'])
                if self.Transaction_obj:
                    self.Transaction_obj.mark_valid()
                self.Blockchain_obj.chain_length = self.index
                prnt('adjust self.Blockchain_obj.last_block_datetime',round_time(dt=self.created, dir='down', amount='10mins'))
                self.Blockchain_obj.last_block_datetime = round_time(dt=self.created, dir='down', amount='10mins')
                self.Blockchain_obj.save()

                if Block.objects.filter(networkChain=self.networkChain, index__gt=self.index, validated=True).exists():
                    items = []
                    for b in Block.objects.filter(networkChain=self.networkChain, index__gt=self.index, validated=True).values('id'):
                        items.append(b['id'])
                    dynamic_bulk_update('Block', update_data={'validated': None}, id__in=items)
                        
                required_validators = self.get_required_validator_count(return_node_data=False)
                creator_nodes, validator_list, broadcast_list = self.get_assigned_nodes(fetch_broadcast_list=False)
                prnt('creator_nodes',creator_nodes)
                prnt('self.validations',self.validations)
                validated_nodes = [i for i in validator_list[:required_validators] if i in [self.validations[i]['CreatorNode_obj'] for i in self.validations]]
                prnt('validated_nodes',validated_nodes)
                dynamic_bulk_update('EventLog', update_data={'func': 'completed_job:block_validation'}, jobId=self.id, Node_obj__id__in=validated_nodes, func='assigned_job:block_validation')

            else:
                self.save(update_fields=['validated','notes'])
                if self.Transaction_obj:
                    self.Transaction_obj.mark_valid(downstream_worker=downstream_worker)

            if Block.objects.filter(networkChain=self.networkChain, index=self.index).exclude(validated=True).exclude(id=self.id).exclude(validated=False).exists():
                for b in Block.objects.filter(networkChain=self.networkChain, index=self.index).exclude(validated=True).exclude(id=self.id).exclude(validated=False):
                    b.is_not_valid(note=f'index_taken-{self.id}')

            if Block.objects.filter(networkChain=self.networkChain, prv_hash=self.hash, validated__isnull=True).exists():
                next_block = Block.objects.filter(networkChain=self.networkChain, prv_hash=self.hash, validated__isnull=True).defer('notes','validations','data','extraData').order_by('created').first()
                if not exists_in_worker('check_validation_consensus', queue_name=['main','high'], block=next_block):
                    django_rq.get_queue('main').enqueue(check_validation_consensus, next_block, job_timeout=300, result_ttl=7200)

            if self.Transaction_obj and self != self.Transaction_obj.SenderBlock_obj:
                from transactions.models import Transaction
                if Transaction.objects.filter(validated=True, ReceiverBlock_obj=None, ReceiverWallet_obj=self.Transaction_obj.ReceiverWallet_obj).exists():
                    next_tx = Transaction.objects.filter(validated=True, ReceiverBlock_obj=None, ReceiverWallet_obj=self.Transaction_obj.ReceiverWallet_obj).order_by('created').first()
                    if next_tx:
                        if not exists_in_worker('send_for_block_creation', id=next_tx.id):
                            django_rq.get_queue('main').enqueue(next_tx.send_for_block_creation, id=next_tx.id, downstream_worker=False, job_timeout=60, result_ttl=7200)

            prnt('done mark validating',self)
            return True
        def assess_for_transactions():
            prnt('-assess_for_transactions',self)
            if self.Transaction_obj:
                prnt('do assess')
                if self.Transaction_obj.senderBlockId and not self.Transaction_obj.SenderBlock_obj:
                    self.Transaction_obj.SenderBlock_obj = Block.objects.filter(id=self.Transaction_obj.senderBlockId).first()
                    if self.Transaction_obj.SenderBlock_obj:
                        self.Transaction_obj.save(update_fields=['SenderBlock_obj'])
                if not self.Transaction_obj.ReceiverBlock_obj:
                    if self.id != self.Transaction_obj.senderBlockId:
                        self.Transaction_obj.ReceiverBlock_obj = self
                        self.Transaction_obj.save(update_fields=['ReceiverBlock_obj'])
                if self.Transaction_obj.SenderBlock_obj and self == self.Transaction_obj.SenderBlock_obj:
                    prntDebug('asses pq1')

                    # check if self_node is assigned to user

                    if not self.Transaction_obj.ReceiverBlock_obj or self.Transaction_obj.ReceiverBlock_obj.validated == None:
                        prntDebug('asses pq2')
                        if not self.Transaction_obj.ReceiverBlock_obj or not self.Transaction_obj.ReceiverBlock_obj.signed:
                            # send self.transaction and validators to receiverBlock validator nodes
                            receiverBlock = None
                            from utils.locked import get_node_assignment, get_broadcast_list
                            prntDebug('asses pq4')
                            if 'BlockReward' in self.Transaction_obj.regarding:
                                prnt('c')
                                if self.Transaction_obj.regarding['BlockReward'] == self.id:
                                    prntDebug('asses pq5')
                                    receiverBlock = self.Transaction_obj.send_for_block_creation(id=self.Transaction_obj.id, do_not_save=True)
                            else:
                                prnt('d')
                                prntDebug('asses pq6')
                                receiverBlock = self.Transaction_obj.send_for_block_creation(id=self.Transaction_obj.id, downstream_worker=False, do_not_save=True)

                            if not receiverBlock and self.DateTime + datetime.timedelta(minutes=block_time_delay(self)) > now_utc():
                                prnt('b')
                            
                                receiverBlock = Block.objects.filter(Transaction_obj=self.Transaction_obj, Blockchain_obj__genesisId=self.Transaction_obj.ReceiverWallet_obj.id).exclude(id=self.Transaction_obj.senderBlockId).exclude(validated=False).order_by('created').first()
                                prnt('receiverBlockId',receiverBlock)
                                
                                if not receiverBlock and retrieve_transaction(tx=self.Transaction_obj.id, block_type='receiver'):
                                    receiverBlock = Block.objects.filter(Transaction_obj=self.Transaction_obj, Blockchain_obj__genesisId=self.Transaction_obj.ReceiverWallet_obj.id).exclude(id=self.Transaction_obj.senderBlockId).exclude(validated=False).order_by('created').first()
                                    
                                else:
                                    prnt('b2')
                                    log = EventLog.objects.filter(type='Broadcast History', data__has_key=self.id).first()
                                    if not log:
                                        log = logBroadcast()
                                        log.data[self.id] = {'dt':dt_to_string(now_utc()),'to':'ReceiverBlock_obj.validators'}
                                        log.save()
                                        broadcast_list = get_broadcast_list(self.Transaction_obj)
                                        self.broadcast(broadcast_list=broadcast_list, validators_only=True, validations=[convert_to_dict(v) for v in Validator.objects.filter(id__in=list(self.validations.keys()))])
                                prnt('retreived receiverBlock10',receiverBlock)
                            else:
                                prnt('e')
                                if not receiverBlock and retrieve_transaction(tx=self.Transaction_obj.id, block_type='receiver'):
                                    receiverBlock = Block.objects.filter(Transaction_obj=self.Transaction_obj, Blockchain_obj__genesisId=self.Transaction_obj.ReceiverWallet_obj.id).exclude(id=self.Transaction_obj.senderBlockId).exclude(validated=False).order_by('created').first()
                                prnt('retreived receiverBlock1',receiverBlock)

                    prntDebug('asses pq7')
                    result = operations()
                    if result:
                        if self.Transaction_obj.ReceiverBlock_obj and self.Transaction_obj.ReceiverBlock_obj.signed and self.Transaction_obj.ReceiverBlock_obj.validated == None:
                            prntDebug('asses pq8')
                            is_valid, consensus_found, validations = check_validation_consensus(self.Transaction_obj.ReceiverBlock_obj, do_mark_valid=False, handle_discrepancies=False, backcheck=False, get_missing_blocks=False)
                            if is_valid and consensus_found:
                                    self.Transaction_obj.ReceiverBlock_obj.mark_valid(downstream_worker=downstream_worker)
                    return result
                
                elif self.Blockchain_obj.genesisId == self.Transaction_obj.ReceiverWallet_obj.id:
                    if not self.Transaction_obj.ReceiverBlock_obj or self.Transaction_obj.ReceiverBlock_obj != self:
                        self.Transaction_obj.ReceiverBlock_obj = self
                        self.Transaction_obj.save(update_fields=['ReceiverBlock_obj'])
                if self.Transaction_obj.ReceiverBlock_obj and self == self.Transaction_obj.ReceiverBlock_obj:
                    prntDebug('asses p1')
                    if not self.Transaction_obj.SenderBlock_obj or self.Transaction_obj.SenderBlock_obj.validated == None:
                        prntDebug('asses p2')
                        self_node = get_self_node()
                        if self.Transaction_obj.regarding and 'GenesisId' in self.Transaction_obj.regarding and self_node.chain_array and self.Transaction_obj.regarding['GenesisId'] in self_node.chain_array:
                            prntDebug('asses p3')
                            if not self.Transaction_obj.SenderBlock_obj or not self.Transaction_obj.SenderBlock_obj.signed:
                                prntDebug('asses p3a')
                                if self.DateTime < now_utc() - datetime.timedelta(minutes=block_time_delay(self)):
                                    senderBlock = Block.objects.filter(id=self.Transaction_obj.senderBlockId).first()
                                    if not senderBlock and retrieve_transaction(tx=self.Transaction_obj.id, block_type='sender'):
                                        senderBlock = Block.objects.filter(id=self.Transaction_obj.senderBlockId).defer('data').first()
                                    prnt('retreived senderBlocker2',senderBlock)
                                    if senderBlock:
                                        self.Transaction_obj.SenderBlock_obj = senderBlock
                                        self.Transaction_obj.save()
                            if self.Transaction_obj.SenderBlock_obj and self.Transaction_obj.SenderBlock_obj.validated:
                                return operations()
                            elif self.Transaction_obj.SenderBlock_obj and self.Transaction_obj.SenderBlock_obj.signed:
                                prntDebug('asses p4')
                                is_valid, consensus_found, validations = check_validation_consensus(self.Transaction_obj.SenderBlock_obj, do_mark_valid=False, handle_discrepancies=False, backcheck=False, get_missing_blocks=False)
                                if is_valid and consensus_found:
                                    sender_result = self.Transaction_obj.SenderBlock_obj.mark_valid(downstream_worker=downstream_worker)
                                    if sender_result:
                                        return operations()
                                    else:
                                        return None
                            else:
                                # send self to SenderBlock_obj validator nodes
                                log = EventLog.objects.filter(type='Broadcast History', data__has_key=self.id).first()
                                if not log:
                                    log = logBroadcast(return_log=True)
                                    log.data[self.id] = {'dt':dt_to_string(now_utc()),'to':'SenderBlock_obj.validators'}
                                    log.save()
                                    from utils.locked import get_node_assignment, get_broadcast_list
                                    creator_nodes, validator_nodes = get_node_assignment(self.Transaction_obj)
                                    broadcast_list = get_broadcast_list(self.Transaction_obj)
                                    self.broadcast(broadcast_list=broadcast_list, validator_list=validator_nodes, validators_only=True, validations=[convert_to_dict(v) for v in Validator.objects.filter(id__in=list(self.validations.keys()))])
                            return None
                        else:
                            prntDebug('asses p5')
                            return operations()
                    elif self.Transaction_obj.SenderBlock_obj and self.Transaction_obj.SenderBlock_obj.validated == False:
                        prntDebug('asses p6')
                        is_valid, consensus_found, validations = check_validation_consensus(self.Transaction_obj.SenderBlock_obj, do_mark_valid=False, handle_discrepancies=False, backcheck=False, get_missing_blocks=False)
                        if is_valid and consensus_found:
                            result = operations()
                            if result:
                                self.Transaction_obj.SenderBlock_obj.mark_valid(downstream_worker=downstream_worker)
                            return result
                        else:
                            self.is_not_valid(mark_strike=False, note='sender_fail')
                        return False
                    elif self.Transaction_obj.SenderBlock_obj and  self.Transaction_obj.SenderBlock_obj.validated:
                        return operations() # validate self, then broadcast to all - maybe needs broadcast_block() here
                    return None # wait for SenderBlock_obj validation
                else:
                    self.is_not_valid(mark_strike=False, note='tx_fail1')
                    return False
            else:
                return operations()
        return assess_for_transactions()


    def mark_valid(self, downstream_worker=True, worker_name='high', attempts=1):
        prnt('-mark_block_valid',self)
        if downstream_worker and not testing():
            prnt('run on worker',worker_name)
            queue = django_rq.get_queue(worker_name)
            if not exists_in_worker('is_valid_operations', queue=queue, id=self.id):
                queue.enqueue(self.is_valid_operations, id=self.id, attempts=attempts, downstream_worker=downstream_worker, job_timeout=1200, result_ttl=7200)
            return True
        else:
            return self.is_valid_operations(attempts=attempts, downstream_worker=downstream_worker)

    def get_transaction_data(self):
        if self.Transaction_obj:
            return convert_to_dict(self.Transaction_obj)
        return {}

    def save(self, share=False, sig=None, *args, **kwargs):
        prnt('-saving block...',self.id, self.networkChain)
        from utils.locked import verify_obj_to_data
        if self.id is None:
            self = initial_save(self)
        else:
            update_fields = kwargs.get('update_fields', [])
            prnt('update_fields',update_fields)
            # if update_fields and len(update_fields) == 1:
            if update_fields and all(i for i in update_fields if i in ['validations','validated','notes']):
                if Block.objects.filter(id=self.id).exists():
                    update_fields.append('updated_on_node')
                    kwargs['update_fields'] = update_fields
                    self.updated_on_node = now_utc()
                    prnt('save block 2')
                    super(Block, self).save(*args, **kwargs)
                elif not is_locked(self):
                    super(Block, self).save()
                    prnt('block saved 3')
            elif not is_locked(self):
                if not self.signed or verify_data(get_signing_data(self), self.signed, signature=sig):
                    super(Block, self).save(*args, **kwargs)
                    prnt('block saved 4')
        return self
    
    def delete(self, superDel=False):
        if not is_locked(self) or superDel:
            try:
                prnt('-deleting block',self)
                transaction = self.Transaction_obj
                try:
                    if transaction:
                        transaction.delete(superDel=superDel, skip_block=self.id)
                except Exception as e:
                    prnt('deleting block err 532',str(e))
                # for v in Validator.objects.filter(Block_obj=self):
                dynamic_bulk_update('Validator', update_data={'Block_obj':None}, Block_obj=self)
                super(Block, self).delete()
                prnt('deleted')
            except Exception as e:
                prnt('del block error 98523', str(e))
    
class Validator(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    networkChain = models.CharField(max_length=50, default=None, blank=True, null=True)
    validatorType = models.CharField(max_length=50, default="", blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    jobId = models.CharField(max_length=50, default=None, blank=True, null=True)
    func = models.CharField(max_length=50, default=None, blank=True, null=True)
    is_valid = models.BooleanField(default=False)
    CreatorNode_obj = models.ForeignKey('network.Node', blank=True, null=True, on_delete=models.PROTECT)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    data = models.JSONField(default=dict, blank=True, null=True)
    Validator_array = ArrayField(models.CharField(max_length=200, default='{default}'), size=20, blank=True, null=True)
    signed = models.JSONField(default=dict)

    def __str__(self):
        return f'VAL:{self.validatorType}-{self.id}'
    
    class Meta:
        ordering = ['-created']
        indexes = [
            GinIndex(fields=['data'], name='Validator_data_has_key_index'),
        ]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Validator', 'modlVer': 1, 'id': None, 'networkChain': None, 'validatorType': '', 'created': None, 'jobId': None, 'func': None, 'is_valid': False, 'CreatorNode_obj': None, 'Block_obj': None, 'data': {}, 'Validator_array': None, 'signed': {}}
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','is_valid','CreatorNode_obj','created']

    def dt_appropriate(self, obj):
        if self.func == 'super': # super bypass for Region which does not have 'is_modifiable' field
            return True
        if is_id(obj):
            obj = get_dynamic_model(obj, id=obj)
        if has_field(obj, 'is_modifiable'):
            if convert_to_datetime(self.created) < convert_to_datetime(obj.lastUpdate) + datetime.timedelta(days=max_validation_window) and convert_to_datetime(self.created) + datetime.timedelta(minutes=60) >= convert_to_datetime(obj.lastUpdate):
                return True
        elif convert_to_datetime(self.created) < convert_to_datetime(obj.created) + datetime.timedelta(days=max_validation_window) and convert_to_datetime(self.created) >= convert_to_datetime(obj.created):
            return True
        up = obj.lastUpdate if has_field(obj,'lastUpdate') else 'x'
        prnt(f'is_dt_appropriate? self.created:{self.created}-obj.created:{obj.created}-obj.lastUpdate:{up}')
        return False

    def boot(self):
        if self.networkChain == _OperationsChain_genesisId:
            chain = Blockchain.objects.filter(genesisType='Sonet').first()
            if chain:
                chain.add_item_to_queue(self)

    def save(self, sig=None, skip_check=False, share=False, *args, **kwargs):
        from utils.locked import verify_obj_to_data
        if self.id is None:
            if self.jobId and not isinstance(self.jobId, str):
                self.jobId = str(self.jobId)
            if not self.created:
                self.created = now_utc()
            prnt('new val iden data:',hash_obj_id(self, return_data=True))
            self.id = hash_obj_id(self)
            super(Validator, self).save(*args, **kwargs)
            self.boot()
        elif skip_check or not is_locked(self) and verify_data(get_signing_data(self), self.signed, signature=sig):
            super(Validator, self).save(*args, **kwargs)

    def delete(self, superDel=False):
        if superDel:
            super(Validator, self).delete()
        else:
            pass

class Blockchain(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    chain_length = models.IntegerField(default=0) 
    data_added_datetime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True) # when new data was added since last block created
    genesisType = models.CharField(max_length=50, default="0", blank=True, null=True)
    genesisId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    genesisName = models.CharField(max_length=50, default=None, blank=True, null=True)
    last_block_datetime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    queuedData = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        if len(self.genesisId) > 10:
            return f'chn:{self.genesisName}/{self.genesisType}/{str(self.genesisId)[5:17]}'
        else:
            return f'chn:{self.genesisName}/{self.genesisType}'

    class Meta:
        ordering = ['-chain_length','genesisType','genesisName','created']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Blockchain', 'modlVer': 1, 'id': None, 'created': None, 'chain_length': 0, 'data_added_datetime': None, 'genesisType': '0', 'genesisId': None, 'genesisName': None, 'last_block_datetime': None, 'queuedData': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','genesisId']
    
    def save(self, share=False, *args, **kwargs):
        prnt('-save blockchain',self.id)
        self.modlVer = self.latestVer
        update_fields = kwargs.get('update_fields', None)
        if update_fields and len(update_fields) == 1:
            ...
            # if all(i for i in update_fields if i in ['validators','notes']):
            #     update_fields.append('updated_on_node')
            #     update_fields.append('modlVer')
            #     kwargs['update_fields'] = update_fields
            #     self.updated_on_node = now_utc()
            #     prnt('save block 2')
            #     super(Block, self).save(*args, **kwargs)

        else:
            if self.id is None:
                if not self.created:
                    self.created = now_utc()
                prnt('self.created',self.created)
                self.id = hash_obj_id(self)
                prnt('new blockchain id',self.id, self.genesisId)
                self.last_block_datetime = string_to_dt(self.created) - datetime.timedelta(hours=2)
                # operatorData = get_operatorData()
                # if operatorData and 'chainData' in operatorData and 'supported' in operatorData['chainData'] and 'New' in operatorData['chainData']['supported']:
                #     operatorData['chainData']['supported'] += self.genesisId # does register to the network the node is supporting this chain, currently requires node software action, node obj must be signed and updated
                #     write_operatorData(operatorData)
            if self.queuedData:
                temp_data = self.queuedData
                if 'meta' in temp_data:
                    del temp_data['meta']
                if temp_data:
                    self.queuedData['meta'] = {'item_count' : len(temp_data)}
            super(Blockchain, self).save(*args, **kwargs)
    
    def delete(self):
        # deletes only if created less than 20 seconds ago
        if not isinstance(self.created, datetime.datetime):
            created = string_to_dt(self.created)
        else:
            created = self.created
        if created >= now_utc()-datetime.timedelta(seconds=20): 
            super(Blockchain, self).delete()
        else:
            pass

    def get_genesis_pointer(self):
        # prntDebug('-get_genesis_pointer')
        if self.genesisId == _OperationsChain_genesisId:
            return Node.objects.all().order_by('created').first()
        obj = get_dynamic_model(self.genesisType, id=self.genesisId)
        return obj

    def create_dummy_block(self, now=None):
        if not now:
            now = now_utc()
        prnt('-create_dummy_block', now)
        if self.genesisId == _OperationsChain_genesisId:
            dt = round_time(dt=(now+datetime.timedelta(minutes=20)), dir='down', amount='10mins') # opblock created 20 ahead of time to ensure the node list is already created when called upon
            prnt('dt1',dt)
            specific_data = {'objType':'Block','blockchainId':self.id,'DateTime':dt_to_string(dt),'CreatorNode_obj':get_operator_obj('self_nodeId')}
        else:
            dt = round_time(dt=now, dir='down', amount='10mins')
            prnt('dt2',dt)
            prev_block_id = '0000'
            prev_block = Block.objects.filter(Blockchain_obj=self, validated=True).values('id').order_by('-index').first()
            if prev_block:
                prev_block_id = prev_block['id']
            latest_sonet_block_id = '0000'
            latest_sonet_block = Block.objects.filter(Blockchain_obj__genesisId=_SonetChain_genesisName, validated=True).values('id').order_by('-index').first()
            if latest_sonet_block:
                latest_sonet_block_id = latest_sonet_block['id']
            specific_data = {'objType':'Block','blockchainId':self.id,'DateTime':dt_to_string(dt),'prev_block_id':prev_block_id,'latest_sonet_block_id':latest_sonet_block_id}
        dummy_block = Block(id=hash_obj_id('Block', specific_data=specific_data), Blockchain_obj=self, networkChain=self.genesisId, created=now, DateTime=dt)
        prnt('dummy_block:',dummy_block, dt)
        return dummy_block

    def new_block_candidate(self, self_node=None, dt=None, add_to_queue=True, updated_nodes=None, commit_to_chain=True):
        if not dt:
            dt = now_utc()
        prnt('-new_block_candidate',self, dt)
        # if node is repeadtedly failing to validate blocks while other nodes are successfully validating the same block, node should be removed from duties
        if self.queuedData != {} or self.genesisId == _OperationsChain_genesisId:
            last_block = self.get_last_block(is_validated=True)
            prnt('last_block',last_block)
            if not last_block or last_block._meta.object_name == 'Blockchain' or last_block.validated:
                dummy_block = self.create_dummy_block(now=dt) # dummy block needed to assign creator
                prnt('dummy_block',dummy_block)
                if not Block.objects.filter(id=dummy_block.id).exists():
                    # if self.genesisType == _OperationsChain_genesisId:
                        # dummy_block.data = self.get_new_opBlock_data(dt=dt)
                        # dummy_block.opData = get_default_opData()
                    do_commit = False
                    if self.genesisId == _OperationsChain_genesisId:
                        if commit_to_chain:
                            do_commit = True
                            validator_nodes = []
                            queue = django_rq.get_queue('high')
                    else:
                        creator_nodes, validator_nodes = get_node_assignment(dummy_block)
                        if not self_node or not isinstance(self_node, str):
                            self_node = get_operator_obj('self_nodeId')
                        prnt('creator_nodes',creator_nodes, 'self_node.id',self_node)
                        if not creator_nodes:
                            prnt('no creators available')
                        elif creator_nodes[0] == self_node:
                            prnt('do commit')
                            if commit_to_chain:
                                do_commit = True
                                queue = django_rq.get_queue('main')
                        else:
                            dummy_block.delete()
                            return False
                    
                    if do_commit:
                        if add_to_queue and not testing():
                            prnt('commit_to_chain1')
                            queue.enqueue(self.commit_to_chain, dummy_block=dummy_block, dt=dt, updated_nodes=updated_nodes, validator_nodes=validator_nodes, job_timeout=600, result_ttl=7200)
                        else:
                            prnt('commit_to_chain2')
                            self.commit_to_chain(dummy_block=dummy_block, dt=dt, updated_nodes=updated_nodes, validator_nodes=validator_nodes)
                    return dummy_block
        prnt('return f')
        return False
        
    def verify_new_opBlock_data(self, block):
        prnt('-verify_new_opBlock_data',self, block.id)
        creation_dt = block.created
        if block.index == 1 and block.Blockchain_obj.genesisId == _OperationsChain_genesisId:
            return True

        data_ids = [i for i in block.data if is_id(i)]
        nodes = []
        latest_data = {}
        data = {}
        latest_opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, index__lt=block.index, validated=True).values('DateTime','data').order_by('-index', 'created').first()
        prnt('latest_opBlock',latest_opBlock)
        if latest_opBlock:
            last_dt = latest_opBlock['DateTime'] - datetime.timedelta(minutes=20)
            nodes = Node.objects.exclude(Block_obj=None).filter(Q(lastUpdate__gte=last_dt)|Q(suspended_dt__gte=last_dt)|Q(expelled_dt__gte=last_dt)|Q(id__in=data_ids)).order_by('-pos')
            latest_data = latest_opBlock['data']
        elif not Block.objects.filter(Blockchain_obj__genesisType='Sonet', validated=True).exists():
            nodes = Node.objects.exclude(activated_dt=None).filter(suspended_dt=None).order_by('-pos')[:1]
            
        prnt('latest_data',latest_data)

        for node in nodes:
            prnt('node_id0',node.id)
            node_data = {
                'activated_dt': dt_to_string(node.activated_dt),
                'suspended_dt': dt_to_string(node.suspended_dt),
                'expelled_dt': dt_to_string(node.expelled_dt),
                'chain_array': node.chain_array,
                'plugin_array': node.plugin_array,
                'region_array': node.region_array,
                'abilities': node.abilities,
                'node_type': node.node_type,
                'node_level': node.node_level,
                'pos': node.pos,
                'block': node.Block_obj.id
            }
            prnt('node_data',node_data)

            proceed = True
            if node.rec_change:
                prnt('node.rec_change',node.rec_change)
                prev_node_change = Block.objects.filter(id=node.rec_change, validated=True).first()
                prnt('prev_node_change',prev_node_change)
                if prev_node_change and node.id in prev_node_change.data:
                    prnt('x',sort_for_sign(node_data),'xx--', sort_for_sign(prev_node_change.data[node.id]))
                    if sort_for_sign(node_data) == sort_for_sign(prev_node_change.data[node.id]):
                        proceed = False
            if proceed:        
                if node.id not in latest_data or node_data != latest_data[node.id]:
                    prnt('a1')
                    data[node.id] = node_data
        matches = []
        mismatches = []
        for node_id, node_data in data.items():
            prnt('node_id',node_id,'node_data',node_data)
            if node_id in block.data:
                block_data = block.data[node_id].copy()
                prnt('block_data',block_data)
                proceed = False
                if not node_data['activated_dt'] and not block_data['activated_dt']:
                    proceed = True
                elif node_data['activated_dt'] and block_data['activated_dt']:
                    proceed = True
                if proceed:
                    proceed = False
                    if not node_data['suspended_dt'] and not block_data['suspended_dt']:
                        proceed = True
                    elif node_data['suspended_dt'] and block_data['suspended_dt']:
                        proceed = True
                    if proceed:
                        proceed = False
                        if not node_data['expelled_dt'] and not block_data['expelled_dt']:
                            proceed = True
                        elif node_data['expelled_dt'] and block_data['expelled_dt']:
                            proceed = True
                if proceed:
                    del node_data['activated_dt']
                    del node_data['suspended_dt']
                    del node_data['expelled_dt']
                    del block_data['activated_dt']
                    del block_data['suspended_dt']
                    del block_data['expelled_dt']
                    if sort_for_sign(block_data) == sort_for_sign(node_data):
                        matches.append(node_id)
                    else:
                        prnt('sort_for_sign(block_data)',sort_for_sign(block_data))
                        prnt('sort_for_sign(data)',sort_for_sign(node_data))

            else:
                prnt('x2')
                mismatches.append(node_id)
        for node_id, node_data in block.data.items():
            prnt('node_id2',node_id)
            if node_id not in matches and node_id not in mismatches:
                prnt('x3')
                mismatches.append(node_id)

        total = len(matches) + len(mismatches)

        if total:
            matched = len(matches) >= 0.8 * total # requires 80% match for approval
            prnt('matched',matched)
            if matched:
                return True
        # if sort_for_sign(block.data) == sort_for_sign(data):
        #     return True
        prnt('total',total)
        return False
        
        
    def get_new_opBlock_data(self, dt=None):
        prnt('-get_new_opBlock_data',dt)
        if not dt:
            raise ValueError("dt must be a datetime or ISO string", dt)
        def shuffle_order(node_ids):
            if not node_ids:
                return []
            dt_str = dt_to_string(dt)
            prnt('shuffle_nodes',node_ids)
            seed_input = f"shuffle_opBlock_{dt_str}"
            seed_hash = hashlib.sha256(seed_input.encode('utf-8')).hexdigest()
            seed_int = int(seed_hash, 16)
            rng = random.Random(seed_int)
            shuffled_nodes = node_ids.copy()
            if isinstance(node_ids, dict):
                keys = list(shuffled_nodes.keys())
                rng.shuffle(keys)
                shuffled_nodes = {k: shuffled_nodes[k] for k in keys}
            else:
                rng.shuffle(shuffled_nodes)
            prnt('shuffled_nodes',shuffled_nodes)
            return shuffled_nodes

        # get node changes since last opBlock
        # activated_dt, new nodes, change in supported_regions, change in abilities, change in node_type
        nodes = []
        latest_data = {}
        data = {}
        latest_opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, validated=True).values('DateTime','data').order_by('-index', 'created').first()
        prnt('latest_opBlock',latest_opBlock)
        if latest_opBlock:
            last_dt = latest_opBlock['DateTime'] - datetime.timedelta(minutes=20)
            nodes = Node.objects.exclude(Block_obj=None).filter(Q(lastUpdate__gte=last_dt)|Q(suspended_dt__gte=last_dt)|Q(expelled_dt__gte=last_dt)|(Q(activated_dt__isnull=False)&Q(activeNode=False)&Q(expelled_dt=None)&Q(suspended_dt=None))).order_by('-pos')
            latest_data = latest_opBlock['data']
        elif not Block.objects.filter(Blockchain_obj__genesisType='Sonet', validated=True).exists():
            nodes = Node.objects.exclude(activated_dt=None).filter(suspended_dt=None).order_by('-pos')[:1]
        
        # prev_blocks = Block.objects.filter(networkChain=_OperationsChain_genesisId)

        for node in nodes:
            prnt('node',node)
            node_data = {
                'activated_dt': dt_to_string(node.activated_dt),
                'suspended_dt': dt_to_string(node.suspended_dt),
                'expelled_dt': dt_to_string(node.expelled_dt),
                'chain_array': node.chain_array,
                'plugin_array': node.plugin_array,
                'region_array': node.region_array,
                'abilities': node.abilities,
                'node_type': node.node_type,
                'node_level': node.node_level,
                'pos': node.pos,
                'block': node.Block_obj.id if node.Block_obj else None
            }
            proceed = True
            if node.rec_change:
                prnt('node.rec_change',node.rec_change)
                prev_node_change = Block.objects.filter(id=node.rec_change, validated=True).first()
                prnt('prev_node_change',prev_node_change)
                if prev_node_change and node.id in prev_node_change.data:
                    prnt('x',sort_for_sign(node_data),'xx--', sort_for_sign(prev_node_change.data[node.id]))
                    if sort_for_sign(node_data) == sort_for_sign(prev_node_change.data[node.id]):
                        proceed = False
            if proceed:
                if node.id not in latest_data or sort_for_sign(node_data) != sort_for_sign(latest_data[node.id]):
                    data[node.id] = node_data
        

        prnt('resultdata:',data)
        return data

    def commit_to_chain(self, dummy_block=None, dt=None, updated_nodes=None, validator_nodes=[], testing=False):
        prnt('--commit_to_chain', self.genesisType, self.genesisId, dummy_block)
        from utils.models import get_data, has_field, value_is_none, is_id, get_plugin
        from utils.locked import verify_obj_to_data
        from pathlib import Path
        import importlib.util
        if e_brake(1):
            return 
        self.refresh_from_db()
        
        if self.genesisId == _OperationsChain_genesisId:
            if not dummy_block:
                dummy_block = self.create_dummy_block(now=dt)
            dummy_block.data = self.get_new_opBlock_data(dt=dt)
            dummy_block.opData = get_default_opData()
            dummy_block = dummy_block.save()
            if not dummy_block.data:
                prnt('no new data')
                self.queuedData = {}
                self.data_added_datetime = now_utc()
                self.save()
                prnt('saved blockchain nodes')
                dummy_block.delete()
                return None

            new_block, reward = self.create_block(dummy_block=dummy_block)
            if new_block:
                creator_nodes = None
                # broadcast to all broadcast_list
                from utils.locked import get_node_assignment
                if not validator_nodes:
                    creator_nodes, validator_nodes = get_node_assignment(new_block)

                # if block has already been received, check if new_block has priority
                competing_blocks = Block.objects.filter(networkChain=new_block.networkChain, index=new_block.index).exclude(validated=False).exclude(id=new_block.id).defer('data','extraData')
                if competing_blocks:
                    current_block = new_block
                    if not creator_nodes:
                        creator_nodes, validator_nodes = get_node_assignment(new_block)
                    for block in competing_blocks:
                        prnt('competing_block',block)
                        try:
                            new_index = creator_nodes.index(block.CreatorNode_obj.id)
                            current_index = creator_nodes.index(current_block.CreatorNode_obj.id)
                        except Exception as e:
                            prnt('err xa2',str(e))
                            new_index = 1
                            current_index = 0
                        if new_index < current_index:
                            current_block.delete()
                            return None
                        elif current_index < new_index:
                            block.delete()
                    
                
                new_block.broadcast(validators_only=False, target_node_id=None, skip_self=True)

            # run_at = now_utc() + datetime.timedelta(minutes=2)
            # prnt('add dp_broadcast to scheduler',run_at)
            # django_rq.get_scheduler('main').enqueue_at(run_at, check_validation_consensus, new_block, timeout=300)

            return new_block

            
        elif self.queuedData:
            if not dummy_block:
                dummy_block = self.create_dummy_block(dt=dt)

            if self.chain_length == 0:
                if self.genesisId not in self.queuedData:
                    genesis_obj = get_dynamic_model(self.genesisType, id=self.genesisId)
                    self.add_item_to_queue(genesis_obj)
                    # if self.genesisType == 'User':
                    #     from accounts.models import UserPubKey
                    #     upk = UserPubKey.objects.filter(User_obj__id=self.genesisId)
                    #     for i in upk:
                    #         self.add_item_to_queue(i)
                    self.refresh_from_db() 
                    
            starting_data_len = len(self.queuedData)
            pending = None
            if 'pending' in self.queuedData:
                pending = self.queuedData['pending']
                del self.queuedData['pending']
            prnt('self.queuedData1',str(self.queuedData)[:2000])
            if not self.queuedData or len(self.queuedData) == 1 and 'meta' in self.queuedData:
                if 'meta' in self.queuedData:
                    self.queuedData['meta'] = 0
                if pending:
                    self.queuedData['pending'] = pending
                self.save()
                prnt('no data', self)
                return None
            else:
                prnt('els1')
                try:
                    if is_id(self.genesisId):
                        proceed = True
                        genesis_obj = get_dynamic_model(self.genesisId, id=self.genesisId)
                        if not has_field(genesis_obj, 'Block_obj'):
                            prnt('stoppage 1 for gen obj',genesis_obj)
                            proceed = False
                        elif genesis_obj.Block_obj and genesis_obj.Block_obj.Blockchain_obj == self and not genesis_obj._meta.object_name in ['Sonet']:
                            # Sonet is only genesis obj that starts a new tree
                            prnt('stoppage 2 for gen obj',genesis_obj, genesis_obj.Block_obj)
                            proceed = False
                        elif not genesis_obj._meta.object_name in ['Sonet'] and (not genesis_obj.Block_obj or not genesis_obj.Block_obj.validated):
                            prnt('stoppage 3 for gen obj',genesis_obj, genesis_obj.Block_obj)
                            proceed = False
                        if not proceed:
                            if genesis_obj:
                                from utils.models import find_or_create_chain_from_object
                                network_chain, obj, commit_chain = find_or_create_chain_from_object(genesis_obj)
                                if network_chain:
                                    network_chain.add_item_to_queue(genesis_obj)
                            return None
                    plugin_name = get_plugin(genesis_obj, True)
                    plugin_file = Path(f"{plugin_name}/utils.py")

                    spec = importlib.util.spec_from_file_location("utils", plugin_file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    for_commitment = getattr(module, "for_commitment", None)
                    
                except:
                    for_commitment = None
                    
                to_commit_data = {}
                added_dt = None
                filtered_dict = {k: v for k, v in self.queuedData.items() if is_id(k)}
                prnt('filtered_dict:',filtered_dict)
                data = dict(sorted(filtered_dict.items(), key=lambda item: item[1])) # sort by dt added to queue, oldest first
                prnt('queued data:',data)
                start_time = time.time()
                delled, removed = 0, 0
                dt_issue = []
                extra_data = 0
                new_nodes = 0
                for chunk in chunk_dict(data, 500):
                    storedModels, not_found, not_valid = get_data(chunk, include_related=False, return_model=True, special_request={'exclude':{'Validator_obj':None}})
                    prntDebug(f'commit_to_chain -- storedModels:{len(storedModels)}, not_found:{len(not_found)}, not_valid:{len(not_valid)}')
                    prnt(f'commit_to_chain -- storedModels:{len(storedModels)}, not_found:{len(not_found)}, not_valid:{len(not_valid)}')
                    if not_valid or not_found:
                        pass
                    for i in not_valid:
                        prntDebug('not valid',i.id)
                        if i.id in self.queuedData:
                            del self.queuedData[i.id]
                            prntDebug(f'removed from queue:{i.id}')
                            removed += 1
                        if get_timeData(i) < (now_utc() - datetime.timedelta(hours=6)):
                            if has_field(i, 'Validator_obj') and i.Validator_obj:
                                i.Validator_obj = None
                            i.delete()
                            delled += 1
                    for i in not_found:
                        prntDebug('not found',i)
                        if i in self.queuedData:
                            del self.queuedData[i]
                            prntDebug(f'removed from queue:{i}')
                            removed += 1

                    cq_list = []
                    added_dt = now_utc()
                    for i in storedModels:
                        cq = f'cq:{i.id}'
                        if i.id in self.queuedData:
                            cq = cq + '-A'
                            if i._meta.object_name == 'Validator' and i.validatorType == 'Block':
                                del self.queuedData[i.id]
                                cq = cq + 'V'
                                i_dt = None
                            else:
                                i_dt = get_timeData(i)
                            if i_dt:
                                cq = cq + 'a'
                                if not has_field(i, 'Validator_obj') or i.Validator_obj and i.Validator_obj.is_valid and i.id in i.Validator_obj.data and i.Validator_obj.data[i.id] == sigData_to_hash(i) and i.Validator_obj.dt_appropriate(i):
                                    cq = cq + 'B'
                                    chainType = None
                                    if has_field(i, 'commitChain') and i.commitChain in [self.genesisId, self.genesisType]:
                                        cq = cq + 'a'
                                        chainType = i.commitChain
                                    elif has_field(i, 'networkChain') and i.networkChain in [self.genesisId, self.genesisType]:
                                        cq = cq + 'b'
                                        chainType = i.networkChain
                                    else:
                                        del self.queuedData[i.id]
                                        cq = cq + 'f1'
                                        prnt(cq,now_utc())
                                        continue
                                    if has_field(i, 'Block_obj') and not i.Block_obj:
                                        cq = cq + 'C'
                                        if chainType:
                                            cq = cq + 'a'
                                            blocks = Block.objects.filter(Blockchain_obj__genesisType=chainType, created__gte=i_dt, validated=True, data__has_key=i.id).order_by('-created')
                                            if blocks:
                                                cq = cq + 'b'
                                                from utils.locked import check_commit_data
                                                for block in blocks:
                                                    if not i.Block_obj:
                                                        if i.id in block.data and i_dt < string_to_dt(block.DateTime) and check_commit_data(i, block.data[i.id]):
                                                            cq = cq + 'c'
                                                            i.Block_obj = block
                                                            if verify_obj_to_data(i, i, user=None, return_user=False, requireSuper=False, record_error=False):
                                                                i.save()
                                                                del self.queuedData[i.id]
                                                            else:
                                                                i.Block_obj = None
                                                        elif i.id in block.extraData and i_dt < string_to_dt(block.DateTime) and check_commit_data(i, block.extraData[i.id]):
                                                            cq = cq + 'd'
                                                            i.Block_obj = block
                                                            if verify_obj_to_data(i, i, user=None, return_user=False, requireSuper=False, record_error=False):
                                                                i.save()
                                                                del self.queuedData[i.id]
                                                            else:
                                                                i.Block_obj = None
                                    elif has_field(i, 'Block_obj') and i.Block_obj and has_field(i, 'is_modifiable') and i.is_modifiable:
                                        cq = cq + 'e'
                                        from utils.locked import check_commit_data
                                        if i.id not in i.Block_obj.data or not check_commit_data(i, i.Block_obj.data[i.id]):
                                            cq = cq + 'g'
                                            i.Block_obj = None

                                    cq = cq + 'D'
                                    if not has_field(i, 'Block_obj') or not i.Block_obj or i.Block_obj.Blockchain_obj.genesisId == i.id or self.genesisId == i.id:
                                        prev_fails = Validator.objects.filter(validatorType='Block', is_valid=False, created__gt=i_dt, data__fail_reason__contains=[i.id]).exclude(signed={}).distinct('jobId','CreatorNode_obj__id').order_by('jobId','CreatorNode_obj__id').count()
                                        cq = cq + f'pf:{prev_fails}:'
                                        # prnt('--prev_fails--',prev_fails)
                                        if prev_fails > 3:
                                            prnt('too many attempts',prev_fails)
                                            cq = cq + '-x1' # consider extra action such as making a note of this on the obj
                                            del self.queuedData[i.id]
                                            dt_issue.append(i.id)
                                        else:
                                            cq = cq + 'a'
                                            if not has_method(i, 'block_conditions') or i.block_conditions():
                                                # to_commit_data[i.id] = {'dt':i_dt, 'commit':get_commit_data(i)}
                                            # if i_dt >= dummy_block.DateTime - datetime.timedelta(days=max_commit_window) and i_dt < dummy_block.DateTime:
                                                cq = cq + 'b'
                                                if i._meta.object_name == 'Plugin':
                                                    if not i.app_name in default_apps:
                                                        to_commit_data[i.id] = {'dt':i_dt, 'commit':get_commit_data(i, extra_data)}
                                                        extra_data += 1
                                                    else:
                                                        to_commit_data[i.id] = {'dt':i_dt, 'commit':get_commit_data(i, 0)}
                                                elif i._meta.object_name == 'Node':
                                                    to_commit_data[i.id] = {'dt':i_dt, 'commit':get_commit_data(i, new_nodes)}
                                                    new_nodes += 1
                                                # elif i._meta.object_name == 'Block':

                                                #         ...
                                                else:
                                                    if i._meta.object_name == 'Validator':
                                                        eligible = True
                                                    else:
                                                        try:
                                                            eligible = for_commitment(i, genesis_obj, dummy_block)
                                                        except:
                                                            eligible = True

                                                    if eligible:
                                                        to_commit_data[i.id] = {'dt':i_dt, 'commit':get_commit_data(i)}
                                                    else:
                                                        prnt('ineligible')

                                            else:
                                                cq = cq + 'f2'
                                                dt_issue.append(i.id)
                                    else:
                                        cq = cq + 'f3'
                                        dt_issue.append(i.id)
                                        if has_field(i, 'Block_obj') and i.Block_obj and i.Block_obj.validated and i.id in self.queuedData:
                                            del self.queuedData[i.id]
                                else:
                                    del self.queuedData[i.id]
                                    cq = cq + 'f4'
                                    dt_issue.append(i.id)
                            else:
                                cq = cq + 'f5'
                                dt_issue.append(i.id)
                            cq = cq + f'-i_dt:{dt_to_string(i_dt) if i_dt else None}-added_dt:{dt_to_string(added_dt) if added_dt else None}'
                        prnt(cq,now_utc())
                        cq_list.append(cq)

                    storedModels.clear()
                    if dt_issue:
                        prnt('dt_issue!',dt_issue)
                    if (time.time() - start_time) > 60:
                        prnt('breaking off chunking') 
                        break
                prnt('added_dt',dt_to_string(added_dt))

                # sort to_commit_data by i_dt, oldest first
                for iden, value in to_commit_data.items():
                    dt = value['dt']
                    prnt('adding',iden, dt)
                    dummy_block.data[iden] = value['commit']
                    if iden in self.queuedData and not testing:
                        del self.queuedData[iden]
                
                to_commit_data.clear()
                for iden in dt_issue:
                    if iden in self.queuedData:
                        self.queuedData.pop(iden)
                        self.queuedData[iden] = dt_to_string(now_utc())

                elapsed_time = time.time() - start_time
                dummy_block.notes['build_time'] = f"{int(elapsed_time // 60):02}:{int(elapsed_time % 60):02}"
                if pending:
                    self.queuedData['pending'] = pending
                self.save()
                if not dummy_block.data:
                    dummy_block.notes['no data'] = True
                    dummy_block.notes['dt_issue'] = dt_issue
                    dummy_block.validated = False
                    try:
                        dummy_block.delete()
                    except:
                        pass
                    prnt('dummy_block.data = none')
                    return None
                dummy_block.notes['data_length'] = len(dummy_block.data)
                prnt('-has queue')
                new_block, reward = self.create_block(dummy_block=dummy_block)
                prnt('new_block',new_block, 'reward',reward)
                if new_block and not testing:

                    # broadcast to all broadcast_list
                    from utils.locked import get_node_assignment, get_broadcast_list
                    if not validator_nodes:
                        creator_nodes, validator_nodes = get_node_assignment(new_block)
                        new_block.notes['creator_nodes'] = creator_nodes
                    # broadcast_list = get_broadcast_list(new_block)
                    new_block.notes['validator_nodes'] = validator_nodes
                    new_block.save()
                    # prnt('broadcast_list',broadcast_list,'validator_nodes',validator_nodes)
                    new_block.broadcast(validator_list=validator_nodes, validators_only=True, target_node_id=None, skip_self=False)
                return new_block
        
        return 'did_not_pass'

    def create_block(self, dummy_block=None, block_dict=None, transaction=None, dt=None, is_reward=False, storedModels=None):
        prnt('--create_block',dummy_block, self.genesisType, self.genesisId)
        from utils.models import has_field, value_is_none, round_time, get_self_node, sigData_to_hash, save_sigs
        from utils.locked import verify_obj_to_data
        err = 'start'
        operatorData = get_operatorData()
        chain_length = Block.objects.filter(Blockchain_obj=self, validated=True).order_by('-index').values('index').first()
        if chain_length:
            chain_length = chain_length['index']
        else:
            chain_length = 0
        def add_default_data(dummy_block):
            # vals with jobId=prev_block get added to dummy_block.extraData
            if not dummy_block.extraData:
                dummy_block.extraData = {}
            # prev_block = self.get_last_block(is_validated=True)
            prev_block = Block.objects.filter(Blockchain_obj=self, validated=True).defer('data','extraData','notes').order_by('-index', 'created').first()
            if prev_block:
                for v in Validator.objects.filter(jobId=prev_block.id, validatorType='Block'):
                    prnt('v-extra',v.id)
                    if v.id in dummy_block.data:
                        del dummy_block.data[v.id]
                    if v.id not in dummy_block.extraData and verify_obj_to_data(v, v):
                        dummy_block.extraData[v.id] = get_commit_data(v)
            elif dummy_block.index == 1:
                genesis_obj = get_dynamic_model(self.genesisId, id=self.genesisId)
                if has_field(genesis_obj, 'Block_obj') and verify_obj_to_data(genesis_obj, genesis_obj):
                    dummy_block.data[genesis_obj.id] = get_commit_data(genesis_obj)
            
            for b in Block.objects.filter(Blockchain_obj=self, validated=True, Block_obj=None):
                if b.id in dummy_block.data:
                    del dummy_block.data[b.id]
                dummy_block.extraData[b.id] = get_commit_data(b)
            if self.genesisId != _OperationsChain_genesisId:

                if prev_block and has_field(prev_block, 'Transaction_obj') and prev_block.Transaction_obj and prev_block.id != prev_block.Transaction_obj.senderBlockId: # prev_block is receiverBlock
                    prnt('prev_block.Transaction_obj',prev_block.Transaction_obj)
                    prnt('prev_block.Transaction_obj.senderBlockId',prev_block.Transaction_obj.senderBlockId)
                    prnt('prev_block.Transaction_obj.senderChainGenId',prev_block.Transaction_obj.senderChainGenId)
                    for v in Validator.objects.filter(jobId=prev_block.Transaction_obj.senderBlockId, networkChain=prev_block.Transaction_obj.senderChainGenId, validatorType='Block'):
                        prnt('v-extra2',v.id)
                        if v.id in dummy_block.data:
                            del dummy_block.data[v.id]
                        if v.id not in dummy_block.extraData and verify_obj_to_data(v, v):
                            dummy_block.extraData[v.id] = get_commit_data(v)

                if self.genesisType == 'Sonet':

                    recent_universal_blocks = Block.objects.filter(Blockchain_obj__genesisId__in=[_KeyChain_genesisId, _AccountChain_genesisId, _OperationsChain_genesisId], validated=True).order_by('Blockchain_obj__id', '-index', 'created').distinct('Blockchain_obj__id')
                    for prev_b in recent_universal_blocks:
                        for v in Validator.objects.filter(jobId=prev_b.id, validatorType='Block').exclude(Block_obj=None):
                            prnt('v-extra',v.id)
                            if v.id in dummy_block.data:
                                del dummy_block.data[v.id]
                            if v.id not in dummy_block.extraData and verify_obj_to_data(v, v):
                                dummy_block.extraData[v.id] = get_commit_data(v)
                        
                        if not prev_b.Block_obj:
                            if prev_b.id in dummy_block.data:
                                del dummy_block.data[prev_b.id]
                            dummy_block.extraData[prev_b.id] = get_commit_data(prev_b)
                elif self.genesisType == 'Wallet': 
                    ...
                    # add to user chain

                    # # wallet blocks are added to sonet chain only if next wallet block is not created first - would cause validators to spread network wide - this is not being checked for in validate_block, only checks prev_block
                    # for v in Validator.objects.filter(networkChain='Wallet', validatorType='Block', Block_obj=None):
                    #     if v.id not in dummy_block.data and verify_obj_to_data(v, v):
                    #         dummy_block.data[v.id] = get_commit_data(v)

            return dummy_block
        
        if block_dict:
            from utils.locked import verify_obj_to_data
            from utils.models import get_or_create_model, sync_model
            transaction_obj = None
            valid_transaction = False
            ReceiverBlock_obj = None
            SenderBlock_obj = None
            new_block = None
            if 'block_dict' in block_dict:
                block_transaction = block_dict['block_transaction']
                try:
                    block_transaction = json.loads(block_transaction)
                except:
                    pass
                block_dict = block_dict['block_dict']
                try:
                    block_dict = json.loads(block_dict)
                except:
                    pass
                if block_transaction:
                    transaction_obj, transaction_is_new = get_or_create_model(block_transaction['objType'], return_is_new=True, id=block_transaction['id'])
                    if transaction_is_new:
                        transaction_obj, sigs, valid_transaction, updatedDB = sync_model(transaction_obj, block_transaction, get_missing_blocks=False)
            
            if dummy_block:
                new_block = dummy_block
            else:
                new_block = Block.objects.filter(id=block_dict['id']).first()
                if not new_block:
                    prnt('block not exists')
                    new_block = Block()
            prnt('new_block2345',new_block)
            sigs = []
            if not new_block.validated:
                for field, value in block_dict.items():
                    if not value_is_none(value):
                        if '_obj' in field:
                            obj = get_dynamic_model(value, id=value)
                            setattr(new_block, field, obj)
                        elif field == 'signed':
                            new_sig_value = {}
                            for dt, sig_data in value.items():
                                sig_obj = Signature.objects.filter(pointerId=block_dict['id'], Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).exists()
                                if not sig_obj:
                                    sig_obj = Signature(pointerId=block_dict['id'], Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                    sigs.append(sig_obj)
                                new_sig_value[dt] = {'pk':sig_data['pk']}
                            setattr(new_block, field, new_sig_value)
                        else:
                            setattr(new_block, field, value)
                new_block.validated = None
                super(Block, new_block).save()
                save_sigs(sigs)
             
            if not verify_obj_to_data(new_block, new_block):
                prnt('BLOCK failed verify', block_dict['id'])
                new_block.is_not_valid(note='block_failed_verify')
                return None
            
            required_validators = new_block.get_required_validator_count(return_node_data=False)
            creator_nodes, validator_list, broadcast_list = new_block.get_assigned_nodes()
            self_node = get_self_node()
            from posts.models import Region
            for node_id in validator_list[:required_validators]:
                if node_id != self_node.id:
                    log = EventLog(
                        jobId=new_block.id, 
                        created=new_block.DateTime,
                        Node_obj_id=node_id,
                        func=f'assigned_job:block_validation',
                        type='job_tracker',
                        )
                    region = Region.objects.filter(id=self.genesisId).only('id').first()
                    if region:
                        log.Region_obj = region
                    log.save()
            return new_block
        elif transaction:
            prnt('has transaction')
            new_block = Block.objects.filter(Transaction_obj=transaction, Blockchain_obj__genesisId=transaction.ReceiverWallet_obj.id).exclude(id=transaction.senderBlockId).exclude(validated=False).order_by('created').first()
            if new_block:
                return new_block
            block_iden = None
            while not block_iden or Block.objects.filter(id=block_iden).exists():
                block_iden = hash_obj_id('Block')
            prnt('ReceiverBlock_id111 self.id',self.id,'dt_to_string(transaction.created)',dt_to_string(transaction.created),'transaction.id',transaction.id)
            prnt('block_iden',block_iden)
            self_node = get_self_node()
            if not dummy_block:
                if not dt:
                    dt = round_time(now_utc(), amount='10mins')
                new_block = self.create_dummy_block(now=dt)
            else:
                new_block = dummy_block
            new_block.id = block_iden
            new_block.created = now_utc()
            new_block.index = chain_length + 1
            new_block.CreatorNode_obj = self_node
            prev_block = self.get_last_block(do_not_return_self=True)
            if prev_block:
                if not prev_block.validated: # wait for previous transactions to complete
                    prnt('r1 prev_block',prev_block.validated)
                    return None
                new_block.prv_hash = prev_block.hash
            else:
                new_block.prv_hash = '0000000'

            if self.genesisId == transaction.ReceiverWallet_obj.id:
                new_block.data['value'] = {'before':transaction.ReceiverWallet_obj.value,'value':str(transaction.token_value.normalize())}
            elif transaction.SenderWallet_obj and self.genesisId == transaction.SenderWallet_obj.id:
                new_block.data['value'] = {'before':transaction.SenderWallet_obj.value,'value':f'-{str(transaction.token_value.normalize())}'}
            else:
                prnt('r2','self.genesisId',self.genesisId, 'transaction.ReceiverWallet_obj.id',transaction.ReceiverWallet_obj.id)
                return None
            
            new_block.opBlockId = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=new_block.created, validated=True).order_by('-index', 'created').values('id').first()['id']
            new_block.data[transaction.id] = get_commit_data(transaction)
            new_block.Transaction_obj = transaction
            new_block = add_default_data(new_block)
            keys = get_operator_obj('keyPair', operatorData=operatorData)
            from utils.locked import convert_to_dict
            prnt('new_block ==',convert_to_dict(new_block))
            new_block = new_block.save()
            new_block.hash = sigData_to_hash(new_block, exclude_fields=['signed'])
            new_block = sign_obj(new_block, keys=keys)
            prnt('transaction block created',new_block.id)

            if 'pending' not in self.queuedData:
                self.queuedData['pending'] = {}
            if self.genesisId == transaction.ReceiverWallet_obj.id:
                self.queuedData['pending'][transaction.id] = {'block':new_block.id,'index':new_block.index,'created':dt_to_string(transaction.created),'before':transaction.ReceiverWallet_obj.value,'value':str(transaction.token_value.normalize())}
            elif transaction.SenderWallet_obj and self.genesisId == transaction.SenderWallet_obj.id:
                self.queuedData['pending'][transaction.id] = {'block':new_block.id,'index':new_block.index,'created':dt_to_string(transaction.created),'before':transaction.SenderWallet_obj.value,'value':f'-{str(transaction.token_value.normalize())}'}
            self.save()
            prnt('done create block')

            prev_block = self.get_last_block(is_validated=True, do_not_return_self=True)
            if prev_block:
                prev_block_is_valid, consensus_found, validations = check_validation_consensus(prev_block, next_block=new_block, do_mark_valid=False, get_missing_blocks=False)
                if not prev_block_is_valid:
                    prnt('prev_block_not_valid2 - skipping new_block')
                    new_block.is_not_valid(mark_strike=False, note='create_block_fail1')
                    return None
            return new_block

        elif dummy_block:
            err = '0'
            self_node = get_self_node()
            new_block = Block.objects.filter(id=dummy_block.id).exclude(validated=True).first()
            if not new_block:
                new_block = dummy_block
            new_block.created = now_utc()
            new_block.index = chain_length + 1
            new_block.CreatorNode_obj = self_node
            reward = None
            if self.genesisType == 'Region':
                from posts.models import Region
                if Region.objects.filter(id=self.genesisId, Block_obj__validated=True, is_supported=True).exists():
                    from transactions.models import Transaction
                    reward = Transaction(ReceiverWallet_obj=self_node.User_obj.get_wallet(f'Rewards-{self_node.id}'), regarding={'BlockReward':'coming'}, created=new_block.DateTime)
                    reward.save()
                    new_block.Transaction_obj = reward
            if 'meta' in self.queuedData:
                del self.queuedData['meta']
            if self.genesisId == _OperationsChain_genesisId:
                err = 'nodestart'
                self.queuedData = {}
            else:
                err = 'A'
                if not new_block.data:
                    prnt('-no transfre data')
                    # logEvent(f'No Block Data: {self.genesisName} - err:{err}', log_type='Tasks')
                    return None, None

                self.queuedData = {k: v for k, v in self.queuedData.items() if k not in new_block.data.keys() and k not in new_block.extraData.keys()}

            keys = get_operator_obj('keyPair', operatorData=operatorData)

            if self.genesisId == _OperationsChain_genesisId:
                opBlock = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=new_block.DateTime, validated=True).exclude(id=self.id).order_by('-index', 'created').values('id').first()
                if opBlock:
                    new_block.opBlockId = opBlock['id']
            else:
                new_block.opBlockId = Block.objects.filter(Blockchain_obj__genesisId=_OperationsChain_genesisId, DateTime__lte=new_block.DateTime, validated=True).exclude(id=self.id).order_by('-index', 'created').values('id').first()['id']
            
            new_block = add_default_data(new_block)

            prnt('should save new_block here')
            new_block = new_block.save() # save before creating hash

            prev_block = self.get_last_block(is_validated=True, do_not_return_self=True)
            if prev_block:
                new_block.prv_hash = prev_block.hash
            else:
                new_block.prv_hash = '0000000'

            if prev_block:
                prnt('check previous block')
                # if self.genesisId == _OperationsChain_genesisId:
                #     # next_block = Block.objects.filter(networkChain='Sonet', opBlockId=prev_block.id, validated=True).order_by('DateTime').first()
                #     prev_block_is_valid, consensus_found, validations = check_validation_consensus(prev_block, next_block=next_block, do_mark_valid=False, get_missing_blocks=False)
                # else:
                prev_block_is_valid, consensus_found, validations = check_validation_consensus(prev_block, next_block=new_block, do_mark_valid=False, get_missing_blocks=False)
                if not prev_block_is_valid:
                    prnt('prev_block_not_valid3 - skipping new_block')
                    return None, None
            if new_block.Transaction_obj:

                if any(prefix for prefix in reward_models if new_block.Blockchain_obj.genesisId.startswith(prefix)):
                    from legis.models import Government
                    gov = Government.objects.filter(id=new_block.Blockchain_obj.genesisId, Validator_obj__is_valid=True).first()
                    if not gov or not gov.StartDate:
                        prnt('not gov stop',gov)
                        return None, None
                    
                    future_govs = Government.objects.filter(Region_obj=gov.Region_obj, StartDate__gte=gov.StartDate, Validator_obj__is_valid=True).values('id')
                    if future_govs and Blockchain.objects.filter(genesisId__in=[g['id'] for g in future_govs], chain_length__gt=0).exists():
                        prnt('future_govs stop',future_govs)
                        return None, None
                    
                    if not future_govs and self.chain_length == 0:
                        prev_gov = Government.objects.filter(Region_obj=gov.Region_obj, StartDate__lt=gov.StartDate, Validator_obj__is_valid=True).order_by('-StartDate').first()
                        if prev_gov and not prev_gov.EndDate:
                            prnt('prev_gov stop',prev_gov)
                            return None, None
                        elif prev_gov and prev_gov.EndDate:
                            from utils.locked import check_commit_data
                            if not prev_gov.Block_obj or not (prev_gov.id in prev_gov.Block_obj.data and check_commit_data(prev_gov, prev_gov.Block_obj.data[prev_gov.id])):
                                prnt('prev_gov check_commit_data stop',prev_gov)
                                return None, None

                from utils.locked import calculate_reward
                reward.token_value = calculate_reward(new_block.DateTime, prev_block)
                # receiverBlock_id = hash_obj_id('Block', specific_data={'objType':'Block','DateTime':dt_to_string(reward.created), 'regarding':reward.id})
                prnt('ReceiverBlock_id222 self.id',self.id,'dt_to_string(reward.created)',dt_to_string(reward.created),'reward.id',reward.id)
                reward.regarding = {'BlockReward':new_block.id,'GenesisId':self.genesisId}
                reward.SenderBlock_obj = new_block
                reward.senderBlockId = new_block.id
                # reward.receiverBlockId = receiverBlock_id
                reward.senderChainGenId = self.genesisId
                reward = sign_obj(reward, keys=keys)
                new_block.data[reward.id] = get_commit_data(reward)
            new_block.hash = sigData_to_hash(new_block, exclude_fields=['signed'])
            new_block = sign_obj(new_block, keys=keys)
            from utils.locked import verify_obj_to_data, convert_to_dict
            prnt('c2d:',convert_to_dict(new_block))
            prnt('verify_obj_to_data(new_block, new_block)',verify_obj_to_data(new_block, new_block))
            prnt('-block created')
            if not self.queuedData:
                self.data_added_datetime = None
            self.save()

            prnt('-done create_block', new_block, reward)
            return new_block, reward
    
    def get_last_block(self, is_validated=False, do_not_return_self=False):
        # prntDebug('--get_last_block from chain',is_validated)
        if is_validated:
            block = Block.objects.filter(Blockchain_obj=self, validated=True).defer('data','extraData').order_by('-index').first()
        else:
            block = Block.objects.filter(Blockchain_obj=self).exclude(validated=False).defer('data','extraData').order_by('-index','created').first()
        if block:
            return block
        else:
            return None if do_not_return_self else self 


    def add_item_to_queue(self, post, force_add=False, skip=None, back_of_line=False):
        prntDebug('-add_item_to_blockchain',self,str(post))
        from utils.models import get_self_node, has_field, value_is_none, round_time, get_data
        from utils.locked import verify_obj_to_data
        added_items = []
        added = False
        try:
            if post:
                err = '0'
                if not self.queuedData:
                    err = err + '1'
                    self.queuedData = {}
                def add_data(p):
                    if p._meta.object_name == 'Validator' and p.validatorType == 'Block' and not Block.objects.filter(id=p.jobId).exists():
                        return False
                    if not force_add and not has_field(p, 'is_modifiable') and has_field(p, 'Block_obj') and p.Block_obj and p.Block_obj.validated and p.Block_obj.Blockchain_obj == self:
                        prnt('previously committed')
                        return False
                    to_commit = None
                    if p._meta.object_name == 'Region' and has_field(p, 'ParentRegion_obj'):
                        if p.ParentRegion_obj and self.genesisId != p.ParentRegion_obj.id:
                            parentChain = Blockchain.objects.filter(genesisId=p.ParentRegion_obj.id).first()
                        elif not p.ParentRegion_obj:
                            parentChain = Blockchain.objects.filter(genesisType='Sonet').first()
                        else:
                            parentChain = None
                        if parentChain:
                            add_dt = dt_to_string(now_utc())
                            parentChain.queuedData[p.id] = add_dt
                            if not parentChain.data_added_datetime:
                                parentChain.data_added_datetime = now_utc()
                            parentChain.save()

                    if has_field(p, 'commitChain'):
                        prnt('add to second chain')
                        network_chain, p, commit_chain = find_or_create_chain_from_object(p)
                        if commit_chain and commit_chain != self and commit_chain != skip:
                            prnt('-commit_chain add_to',commit_chain)
                            commit_chain.add_item_to_queue(p, skip=self)
                        elif network_chain and network_chain != self and network_chain != skip:
                            prnt('-network_chain add_to',network_chain)
                            network_chain.add_item_to_queue(p, skip=self)
                    if p.id not in self.queuedData:
                        add_dt = dt_to_string(now_utc())
                        self.queuedData[p.id] = add_dt
                        return True
                    return False

                if isinstance(post, models.Model) and post._meta.object_name == 'Node':
                    err = err + '2'
                    add_dt = dt_to_string(now_utc())
                    self.queuedData[post.id] = add_dt
                    added = True
                    added_items.append(post.id)
                elif isinstance(post, list):
                    err = err + '3'
                    if not isinstance(post[0], models.Model):
                        err = err + '4'
                        post, not_found, not_valid = get_data(post, return_model=True)
                        err = err + '5'
                    for p in post:
                        if has_field(p, 'networkChain') or has_field(p, 'blockchainId'):
                            if add_data(p):
                                added_items.append(p.id)
                                added = True
                elif isinstance(post, dict):
                    err = err + '8'
                    post, not_found, not_valid = get_data(post, return_model=True)
                    err = err + '9'
                    for p in post:
                        if has_field(p, 'networkChain') or has_field(p, 'blockchainId'):
                            if add_data(p):
                                added_items.append(p.id)
                                added = True
                elif has_field(post, 'networkChain') or has_field(post, 'blockchainId'):
                    err = err + '11a'
                    if add_data(post):
                        err = err + 'b'
                        added_items.append(post)
                        added = True
                if added_items:
                    if not self.data_added_datetime:
                        self.data_added_datetime = now_utc()
                    self.save()
                prnt('added items:', added_items, self, err)
                return added
        except Exception as e:
            prnt('add_item_to_queue err 53254', str(e), err)
            # logError(f'additem to queue {str(e)}', code='53254', func='add_item_to_queue', region=None, extra={'err':err,'chainId':self.id,'post':str(post)[:500]})
        prnt('done add to blockchain.queue')
        return False



class EventLog(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    type = models.CharField(max_length=90, default=None, blank=True, null=True)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    data = models.JSONField(default=dict, blank=True, null=True)
    func = models.CharField(max_length=90, default=None, blank=True, null=True)
    jobId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    Node_obj = models.ForeignKey('network.Node', blank=True, null=True, on_delete=models.CASCADE)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    signed = models.JSONField(default=dict)
    
    def __str__(self):
        if self.Node_obj:
            return 'EventLog: %s/%s - %s'%(self.created, self.type, self.Node_obj.node_name)
        else:
            return 'EventLog: %s/%s - %s'%(self.created, self.type, self.Node_obj)
    
    class Meta:
        ordering = ["-created"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'EventLog', 'modlVer': 1, 'id': None, 'created': None, 'type': None, 'pointerId': None, 'data': {}, 'func': None, 'jobId': None, 'Node_obj': None, 'Region_obj': None, 'signed': {}}
        
    def updateShare(self, obj): #not used
        if 'shareData' not in self.data:
            self.data['shareData'] = []
        if obj.id not in self.data['shareData']:
            self.data['shareData'].append(obj.id)
            self.save()
    
    def completed(self, fail=None):
        if fail:
            self.type = self.type.replace('process','failed').replace('scrape','failed')
            self.type = self.type + f"-{fail.replace('process','prcs')}"
        else:
            self.type = self.type.replace('process','completed').replace('scrape','completed')
        self.save()

    def save(self, *args, **kwargs):
        if self.id is None:
            self.id = hash_obj_id(self)
        if not self.created:
            self.created = now_utc()
        if not self.Node_obj:
            self.Node_obj = get_self_node()
        if self.type:
            self.type = self.type[:90]
        # prnt('self dict',model_to_dict(self))
        super(EventLog, self).save(*args, **kwargs)

class Tidy:
    

    def invalid_posts_run(self):
        prnt('-invalid_posts_run',now_utc())
        dt=now_utc()
        prnt('dt',dt)
        from utils.models import logEvent
        from posts.models import Post
        # num = 250
        invalid_posts = Post.all_objects.exclude(validated=True).filter(updated_on_node__lte=dt - datetime.timedelta(minutes=120)).order_by('updated_on_node')[:500]
        model_types = []
        delled = 0
        valled = 0
        skipped = 0
        runs = 0
        exclude_ids = []
        n = 0
        while invalid_posts and runs < 65:
            prnt('invalid_posts_run run:',runs,invalid_posts.count())
            runs += 1
            n += 500
            for p in invalid_posts:
                prnt('p',p)
                exclude_ids.append(p.id)
                try:
                    if p.verify_is_valid(check_update=False):
                        p.validate()
                        valled += 1
                    else:
                        try:
                            obj = p.get_pointer()
                            prnt('obj:',obj.id)
                            if not obj.signed and has_field(obj, 'created') and obj.created < dt - datetime.timedelta(hours=6) or has_field(obj, 'created') and obj.created < dt - datetime.timedelta(hours=18):
                            # if has_field(obj, 'created') and obj.created < dt - datetime.timedelta(days=2) or not obj.signed and has_field(obj, 'created') and obj.created < dt - datetime.timedelta(hours=8):
                                deleted = obj.delete()
                                delled += 1
                                m_type = get_pointer_type(p.pointerId)
                                if m_type not in model_types:
                                    model_types.append(m_type)
                            else:
                                skipped += 1
                                prnt('skipped')
                        except Exception as e:
                            prnt('fail7534',p,str(e))
                            # p.delete()
                            # delled += 1
                            # m_type = get_pointer_type(p.pointerId)
                            # if m_type not in model_types:
                            #     model_types.append(m_type)
                except Exception as e:
                    print('invalid post run fail',str(e))
                    if 'matching query does not exist.' in str(e):
                        p.delete()
                        delled += 1
                        m_type = get_pointer_type(p.pointerId)
                        if m_type not in model_types:
                            model_types.append(m_type)
            prntDebug(f'run {runs} result, delled: {delled}, model_types:{model_types}, validated:{valled}, skipped:{skipped}')
            invalid_posts = Post.all_objects.exclude(validated=True).exclude(id__in=exclude_ids).filter(updated_on_node__lte=dt - datetime.timedelta(minutes=120)).order_by('updated_on_node')[:500]
        r = f'removing posts, delled: {delled}, model_types:{model_types}, validated:{valled}, skipped:{skipped}'
        if delled or valled:
            logEvent(r, log_type='Tasks')
        prnt(r)
        return r

    def invalid_updates_run(self):
        prnt('-invalid_updates_run',now_utc())
        dt=now_utc()
        from utils.models import logEvent
        from posts.models import Update
        # num = 250
        invalid_updates = Update.objects.exclude(validated=True).filter(created__lte=dt - datetime.timedelta(minutes=120)).order_by('created').iterator(chunk_size=500)
        model_types = []
        delled = 0
        valled = 0
        runs = 0
        exclude_ids = []
        while invalid_updates and runs < 20:
            runs += 1
            for u in invalid_updates:
                exclude_ids.append(u.id)
                if u.verify_is_valid():
                    u.validate()
                    valled += 1
                elif u.created < dt - datetime.timedelta(hours=18):
                    if not u.signed or not u.validated:
                        delled += 1
                        m_type = get_pointer_type(u.pointerId)
                        if m_type not in model_types:
                            model_types.append(m_type)
                        u.delete()
            invalid_updates = Update.objects.exclude(validated=True).exclude(id__in=exclude_ids).filter(created__lte=dt - datetime.timedelta(minutes=120)).order_by('created').iterator(chunk_size=500)
        r = f'removing updates, delled: {delled}, model_types:{model_types}, validated:{valled}'
        if delled or valled:
            logEvent(r, log_type='Tasks')
        return r

    def unvalidator_run(self):
        prnt('-unvalidator_run',now_utc())
        from utils.models import logEvent
        dt=now_utc()
        # from utils.models import get_app_name, get_model
        del_chains = []
        for model_name, model_data in get_app_name(return_model_list=True).items():
            if model_name not in ['Post', 'Update', 'Notification']:
                prnt(model_name)
                model = get_model(model_name)
                if has_field(model, 'Validator_obj'):
                    time_field = get_timeData(model, sort='created', first_string=True)
                    objs = list(model.objects.filter(Validator_obj=None).filter(**{f'{time_field}__lte': dt - datetime.timedelta(hours=4)}).iterator(chunk_size=200))
                    exclude_idens = set()
                    delled = 0
                    item_tracker = []
                    skipped = 0
                    validated = 0
                    runs = 0
                    val_count = 0
                    while objs and runs < 20:
                        runs += 1
                        unvalled_obj_count = 0
                        for i in objs:
                            unvalled_obj_count += 1
                        item_tracker.append(unvalled_obj_count)
                        # query = Q()
                        # for key in [obj.id for obj in objs]:
                        #     query |= Q(data__has_key=key)
                        # vals = Validator.objects.filter(is_valid=True).filter(query).order_by('-created')
                        # prnt('vals',vals)
                        vals = Validator.objects.filter(is_valid=True, data__has_any_keys=[i.id for i in objs]).order_by('-created')
                        val_count += len(vals)
                        if vals:
                            val_map = {obj: val for val in vals for obj in val.data.keys()}
                            for obj in objs:
                                # creator_nodes, validator_nodes = get_scraping_order(dt=obj.created, chainId=obj.blockchainId, func_name=obj.func)
                                creator_nodes, validator_nodes = get_node_assignment(dt=obj.created, chainId=obj.networkChain, func=obj.func)
                                val_found = False
                                val = val_map.get(obj.id)
                                if val and val.CreatorNode_obj.id in validator_nodes and obj.id in val.data:
                                    if validate_obj(obj=None, pointer=obj, validators=[val], opBlock_data={}):
                                    # if val.data[obj.id] == sigData_to_hash(obj):
                                        validated += 1
                                        val_found = True
                                        # obj.Validator_obj = val
                                        # super(get_model(obj._meta.object_name), obj).save()
                                        # blockchain, obj, secondChain = find_or_create_chain_from_object(obj)
                                        # if blockchain:
                                        #     blockchain.add_item_to_queue(obj)
                                if not val_found and getattr(obj, time_field) < dt - datetime.timedelta(days=2) or not obj.signed and has_field(obj, 'created') and obj.created < dt - datetime.timedelta(hours=8):
                                    if obj._meta.object_name == obj.networkChain:
                                        del_chains.append(obj.id)
                                    if obj.id not in exclude_idens:
                                        exclude_idens.add(obj.id)
                                    obj.delete()
                                    delled += 1
                                else:
                                    skipped += 1
                                    if obj.id not in exclude_idens:
                                        exclude_idens.add(obj.id)
                        else:
                            for obj in objs:
                                if getattr(obj, time_field) < dt - datetime.timedelta(days=2) or not obj.signed and has_field(obj, 'created') and obj.created < dt - datetime.timedelta(hours=8):
                                    if obj._meta.object_name == obj.networkChain:
                                        del_chains.append(obj.id)
                                    if obj.id not in exclude_idens:
                                        exclude_idens.add(obj.id)
                                    obj.delete()
                                    delled += 1
                                else:
                                    skipped += 1
                                    if obj.id not in exclude_idens:
                                        exclude_idens.add(obj.id)
                        objs = list(model.objects.filter(Validator_obj=None).exclude(id__in=exclude_idens).filter(**{f'{time_field}__lte': dt - datetime.timedelta(hours=4)}).iterator(chunk_size=200))
                    r = f'unvalidator_run {model_name}, item_tracker:{item_tracker} validated:{validated} delled:{delled} skipped:{skipped} val_count:{val_count} runs:{runs}'
                    if validated or delled or skipped:
                        logEvent(r, log_type='Tasks')
                    prnt(r)

        if del_chains:
            prnt('del_chains',del_chains)
            logEvent(f'removing chains:{del_chains}', log_type='Tasks')
            chains = Blockchain.objects.filter(genesisId__in=del_chains)
            if chains:
                for c in chains:
                    if not c.get_genesis_pointer():
                        prnt('chain deletion 432',c)
                        super(Blockchain, c).delete()
        
    def invalid_notifications_run(self):
        prnt('-invalid_notifications_run',now_utc())
        from utils.models import logEvent
        from accounts.models import Notification
        dt=now_utc()
        invalid_notifications = Notification.objects.exclude(validated=True).filter(updated_on_node__lte=dt - datetime.timedelta(minutes=120))
        if invalid_notifications:
            model_types = []
            delled = 0
            valled = 0
            for n in invalid_notifications:
                if n.verify_is_valid():
                    n.validate()
                    valled += 1
                elif n.created < dt - datetime.timedelta(hours=18) or not n.signed and has_field(n, 'created') and n.created < dt - datetime.timedelta(hours=6):
                    delled += 1
                    m_type = get_pointer_type(n.pointerId)
                    if m_type not in model_types:
                        model_types.append(m_type)
                    n.delete()
            r = f'removing notifications, count: {delled}, model_types:{model_types}, validated:{valled}'
            if delled or valled:
                logEvent(r, log_type='Tasks')
            return r

    def uncommitted_posts_run(self, hours=4):
        prnt('-uncommitted_posts_run',now_utc(), hours)
        from utils.models import logEvent, get_latest_dataPacket
        from utils.locked import check_commit_data
        dt=now_utc()
        # from utils.models import get_model
        def run_me(model_name):
            prnt('run_me',model_name)
            model = get_model(model_name)
            if model_name == 'Post':
                uncommitted_posts = list(model.objects.filter(blockId=None, created__lte=dt - datetime.timedelta(hours=hours)).iterator(chunk_size=500))
            elif model_name == 'Update':
                uncommitted_posts = list(model.objects.filter(Block_obj=None, validated=True, created__lte=dt - datetime.timedelta(hours=hours)).iterator(chunk_size=500))
            elif has_field(model, 'Block_obj'):
                uncommitted_posts = list(model.objects.filter(Block_obj=None, created__lte=dt - datetime.timedelta(hours=hours)).iterator(chunk_size=500))
            else:
                uncommitted_posts = []
            runs = 0
            exclude_idens = set()
            request_types = ['UserPubKey','Plugin']
            
            while uncommitted_posts and runs < 20:
                runs += 1
            # if uncommitted_posts:
                prnt('has uncommitted_posts',runs)
                logEvent(f'uncommitted_posts, model_name:{model_name} run:{runs}', log_type='Tasks')
                obj_idens = []
                has_block = {}
                add_to_queue = {}
                found_in_queue = []
                run_posts = []
                earliest_dt = dt
                request_idens = []
                for p in uncommitted_posts:
                    p_dt = get_timeData(p)
                    if not earliest_dt or p_dt < earliest_dt:
                        earliest_dt = p_dt
                    exclude_idens.add(p.id)
                    run_posts.append(p)
                    if p._meta.object_name == 'Post':
                        obj_idens.append(p.pointerId)
                    else:
                        obj_idens.append(p.id)
                    # if p.Update_obj:
                    #     obj_idens.append(p.Update_obj.id)
                prntDebug('earliest_dt',earliest_dt,'obj_idens',obj_idens)
                # if obj_idens:
                #     in_queue = Blockchain.objects.filter(queuedData__has_any_keys=obj_idens)
                # else:
                #     in_queue = None
                # if in_queue:
                #     for c in in_queue:
                #         found_in_queue = [i for i in c.queuedData if i in obj_idens]
                found_in_queue = []
                prnt('found_in_queue',found_in_queue)
                if obj_idens:
                    obj_idens_copy = obj_idens.copy()
                    existing_blocks = Block.objects.filter(DateTime__gte=earliest_dt).filter(data__has_any_keys=list(set(obj_idens) - set(found_in_queue))).exclude(validated=False).order_by('created')
                    for b in existing_blocks:
                        prnt('b',b)
                        for key in obj_idens:
                            prnt('k',key)
                            if key in b.data:
                                prnt('a1')
                                if key in obj_idens_copy:
                                    prnt('a2')
                                    obj_idens_copy.remove(key)
                                    prnt('obj_idens_copy',obj_idens_copy)
                                if key not in has_block:
                                    prnt('a3')
                                    has_block[key] = b
                                elif not has_block[key].validated:
                                    prnt('a4')
                                    has_block[key] = b
                                prntDebug('rmv2', key)
                            if not obj_idens_copy:
                                break
                # if model_name in []
                if has_block:
                    prnt('has has_block',has_block)
                else:
                    prnt('no beat')
                counter = 0
                prnt('len run_posts',len(run_posts))
                add_to_chain = 0
                for p in run_posts:
                    if add_to_chain >= 500:
                        add_to_chain = 0
                        prnt('has add_to_queue1')
                        for chain, idens in add_to_queue.items():
                            chain.add_item_to_queue(idens)
                        add_to_queue = {}
                            
                    counter += 1
                    prnt('counter',counter,p)
                    if p._meta.object_name == 'Post':
                        obj_iden = p.pointerId
                    else:
                        obj_iden = p.id
                    if obj_iden in has_block:
                        # or has_field(p, 'Update_obj') and p.Update_obj and p.Update_obj.id in has_block:
                        prnt('opt1')
                        # if p.pointerId in has_block:
                        if has_field(p, 'blockId') and has_method(p, 'get_pointer'):
                            p.blockId = has_block[obj_iden].id
                            p.save()
                            pointer = p.get_pointer()
                            if has_field(pointer,'Block_obj'):
                                if not pointer.Block_obj or (pointer.id not in pointer.Block_obj.data or not check_commit_data(pointer, pointer.Block_obj.data[pointer.id]) and pointer.id not in pointer.Block_obj.extraData or not check_commit_data(pointer, pointer.Block_obj.extraData[pointer.id])):
                                    if has_block[p.pointerId].validated:
                                        if p.pointerId in has_block[p.pointerId].data and check_commit_data(pointer, has_block[p.pointerId].data[p.pointerId]) or p.id in has_block[p.pointerId].extraData and check_commit_data(pointer, has_block[p.pointerId].extraData[p.pointerId]):
                                            # has_block[p.pointerId].data[p.pointerId] == get_commit_data(pointer):
                                            pointer.Block_obj = has_block[p.pointerId]
                                            super(get_model(pointer._meta.object_name), pointer).save()
                        elif has_field(p, 'Block_obj'):
                            if not p.Block_obj or (p.id not in p.Block_obj.data or not check_commit_data(p, p.Block_obj.data[p.id]) and p.id not in p.Block_obj.extraData or not check_commit_data(p, p.Block_obj.extraData[p.id])):
                                if has_block[p.id].validated:
                                    if p.id in has_block[p.id].data and check_commit_data(p, has_block[p.id].data[p.id]) or p.id in has_block[p.id].extraData and check_commit_data(p, has_block[p.id].extraData[p.id]):
                                        p.Block_obj = has_block[p.id]
                                        super(get_model(p._meta.object_name), p).save()
                            # else:
                                # prnt('get_commit_data(p)',get_commit_data(p))
                                # prnt('has_block[p.id].data[p.id]',has_block[p.id].data[p.id])

                        # if p.Update_obj and has_field(p.Update_obj,'Block_obj') and not p.Update_obj.Block_obj:
                        #     p.Update_obj.Block_obj = has_block[p.Update_obj.id]
                        #     super(get_model(pointer._meta.object_name), pointer).save()
                
                    elif obj_iden in obj_idens:
                        prnt('opt2')
                        if p._meta.object_name == 'Post':
                            pointer = p.get_pointer()
                        else:
                            pointer = p
                        # if has_field(pointer, 'Block_obj') and pointer.Block_obj:
                        #     pointer.Block_obj = None
                        #     super(get_model(pointer._meta.object_name), pointer).save()

                        find_chain = True
                        if has_field(pointer, 'created'):
                            # if pointer.created < dt - datetime.timedelta(days=max_commit_window):
                            #     # if post is valid, invalidate
                            #     if p.validated:
                            #         p.validated = False
                            #         p.save()
                            #     find_chain = False
                            #     ...
                            if pointer.created < dt - datetime.timedelta(hours=12):
                                dataPacket = get_latest_dataPacket(pointer)
                                if dataPacket:
                                    dataPacket.add_item_to_share(pointer)
                            if pointer._meta.object_name in request_types and pointer.created < dt - datetime.timedelta(hours=6):
                                request_idens.append(pointer.id)

                        if find_chain:
                            network_chain, obj, commit_chain = find_or_create_chain_from_object(pointer)
                            prntDebug('networkChainxxy',network_chain)
                            if network_chain:
                                if network_chain not in add_to_queue:
                                    add_to_queue[network_chain] = []
                                add_to_queue[network_chain].append(pointer)
                                prnt('pointer add_to_queue',pointer,network_chain)
                                add_to_chain += 1
                            # elif has_field(p, 'blockId') and has_field(pointer, 'proposed_modification') and not pointer.proposed_modification:
                            #     p.blockId = 'N/A'
                            #     p.save()
                    # elif p.Update_obj and p.Update_obj.id in obj_idens:
                    #     # prnt('opt3')
                    #     blockchain, obj, secondChain = find_or_create_chain_from_object(p.Update_obj)
                    #     if blockchain:
                    #         if blockchain not in add_to_queue:
                    #             add_to_queue[blockchain] = []
                    #         add_to_queue[blockchain].append(p.Update_obj)
                prnt('done run',runs)
                if add_to_queue:
                    prnt('has add_to_queue2')
                    for chain, idens in add_to_queue.items():
                        chain.add_item_to_queue(idens)
                prnt('request_idens',request_idens)
                if request_idens:
                    from utils.models import request_items
                    request_items(requested_items=request_idens, nodes=None, check_consensus=True, downstream_worker=True)

                if model_name == 'Post':
                    uncommitted_posts = list(model.objects.exclude(id__in=exclude_idens).filter(blockId=None, created__lte=dt - datetime.timedelta(hours=hours)).iterator(chunk_size=500))
                elif model_name == 'Update':
                    uncommitted_posts = list(model.objects.exclude(id__in=exclude_idens).filter(Block_obj=None, validated=True, created__lte=dt - datetime.timedelta(hours=hours)).iterator(chunk_size=500))
                else:
                    uncommitted_posts = list(model.objects.exclude(id__in=exclude_idens).filter(Block_obj=None, created__lte=dt - datetime.timedelta(hours=hours)).iterator(chunk_size=500))

        run_me('UserPubKey')
        run_me('User')
        run_me('Plugin')
        run_me('Region')
        run_me('Node')
        run_me('Wallet')
        run_me('Post')
        run_me('Update')
        run_me('UserVote')

    def get_missing_items(self, dt=now_utc()):
        prnt('-skipping get_missing_items')
        # self_node = get_self_node()
        
        # start_of_month = round_time(dt=dt, dir='down', amount='month')
        # logs = EventLog.objects.filter(type='missing_items', Node_obj=self_node, created__gte=start_of_month).exclude(data={})
        # for log in logs:
        #     save_log = False
        #     result = request_items(requested_items=[key for key in log.data], nodes=None, return_updated_ids=True, return_missing=True, downstream_worker=False) # should get nodes by region if applicable
        #     prnt(f'received missing idens for {log.id}:', str(result)[:100])
        #     if result and isinstance(result, dict):
        #         if 'found' in result and isinstance(result['found'], list):
        #             for i in result['found']:
        #                 prnt('i',i)
        #                 if i in log.data:
        #                     del log.data[i]
        #                     save_log = True
        #         if 'not found' in result and isinstance(result['not found'], list):
        #             if result['not found']:
        #                 for i in result['not found']:
        #                     if i in log.data:
        #                         del log.data[i]
        #                         save_log = True

        #     if save_log:
        #         log.save()

    def check_transactions(self, dt=now_utc()):
        prnt('-check_transactions',dt)
        from transactions.models import Transaction
        transactions = Transaction.objects.exclude(validated=True).exclude(validated=False).filter(created__lt=dt-datetime.timedelta(hours=2))
        for t in transactions:
            prnt('t1',t)
            if t.assess_validation():
                t.mark_valid(skip_assess=True)
            else:
                t.is_not_valid(note='cleaned')
        transactions = Transaction.objects.filter(validated=True,enacted=False,enact_dt__lt=dt)
        for t in transactions:
            prnt('t2',t)
            t.enact_transaction()

    def random_block_check(self, dt=now_utc()):
        block = Block.objects.all().order_by('?').first()
        prnt('-random_block_check',block)
        check_block_contents(block, retrieve_missing=True, log_missing=True, downstream_worker=False)

    def remove_zeros(self, dt=now_utc()):
        # check all models for id='0', if found and older than 10 mins, delete
        ...

    def prune_old(self, dt=now_utc()):
        # blocks are removed when invalid, validators for those should be removed after a time if not committed
        for block in Block.objects.filter(validated=False, created__lt=dt - datetime.timedelta(days=3)):
            block.delete()
        # also prune old datapackets and eventlogs
        for dp in DataPacket.objects.filter(updated_on_node__lt=dt-datetime.timedelta(days=10)):
            dp.delete()

    def assess_nodes(self, dt=now_utc()):
        # check nodeReviews for nodes that have not been accessed by self_node recently, run node.assess_activity()
        pass

    def check_storage_space(self, dt=now_utc()):
        # check storage space available, deactivate if too little
        ...

    def rotate_logs(self):
        prnt('-rotate_logs',now_utc())
        # import os
        # import shutil

        # LOG_DIR = os.path.expanduser("~/Sonet/.data/logs")
        # # LOG_FILE = "gunicorn.log"
        # MAX_LOGS = 10
        # MAX_SIZE_MB = 5  # rotate if gunicorn.log exceeds this size

        # rotate_me = ["gunicorn.log", "gunicorn_err.log", "nginx.log", "nginx_err.log", "rqscheduler.log", "supervisor.log", "supervisord.log", "supervisor.err"]
        # for LOG_FILE in rotate_me:
        #     prnt('LOG_FILE',LOG_FILE)
        #     log_path = os.path.join(LOG_DIR, LOG_FILE)
            
        #     # Only rotate if the log file exists and is too large
        #     if not os.path.exists(log_path):
        #         prnt("Log file does not exist.")
        #         return
            
        #     if os.path.getsize(log_path) < MAX_SIZE_MB * 1024 * 1024:
        #         prnt("Log file is not large enough to rotate.")
        #         return

        #     # Delete the oldest log if it exists
        #     oldest = os.path.join(LOG_DIR, f"{LOG_FILE}.{MAX_LOGS}")
        #     if os.path.exists(oldest):
        #         os.remove(oldest)

        #     # Shift all logs down by one
        #     for i in range(MAX_LOGS - 1, 0, -1):
        #         src = os.path.join(LOG_DIR, f"{LOG_FILE}.{i}")
        #         dst = os.path.join(LOG_DIR, f"{LOG_FILE}.{i+1}")
        #         if os.path.exists(src):
        #             os.rename(src, dst)

        #     # Rename current log to .1
        #     rotated = os.path.join(LOG_DIR, f"{LOG_FILE}.1")
        #     shutil.move(log_path, rotated)

        #     # Create a new empty log file (optional: match owner/permissions)
        #     open(log_path, "a").close()

        #     prnt(f"Rotated {log_path} to {rotated}")


    def _add_all_jobs(self, dt=now_utc(), all_jobs=False, only_job=None, *args, **kwargs):
        # logEvent(f'tidying', log_type='Tasks')
        prnt('-tidying',dt)

        for block in Block.objects.filter(validated__isnull=True, DateTime__lt=dt - datetime.timedelta(days=1)):
            block.is_not_valid(mark_strike=False, note='day_old')

        # maybe once randomly per week?
        # from utils.models import run_database_maintenance
        #     queue = django_rq.get_queue('main')
        #     queue.enqueue(run_database_maintenance)

        import inspect
        if dt.hour == 20 or all_jobs:
            from utils.cronjobs import clear_old_jobs
            queue = django_rq.get_queue('low')
            queue.enqueue(clear_old_jobs, job_timeout=20)
            jobs = {name:method for name, method in inspect.getmembers(self, predicate=inspect.ismethod) if not name.startswith('_')}
        else:
            skip_jobs = ['random_block_check','prune_old','check_storage_space']
            jobs = {name:method for name, method in inspect.getmembers(self, predicate=inspect.ismethod) if not name.startswith('_') and not name in skip_jobs}

        items = list(jobs.items())
        random.shuffle(items)
        jobs = dict(items)
        prnt(jobs)
        if only_job:
            jobs = {only_job:jobs[only_job]}
        # prnt('tidying methods',methods)
        queue = django_rq.get_queue('low')
        task_length = {'invalid_posts_run':1200, 'invalid_updates_run':1200, 'unvalidator_run':1200, 'uncommitted_posts_run':1200}
        for name, method in jobs.items():
            if name in task_length:
                job_time = task_length[name]
            else:
                job_time = 600
            queue.enqueue(method, job_timeout=job_time, result_ttl=7200)



# # Add to the top of views.py
# from django.core.cache import cache
# from django.http import HttpResponse
# import time
# potentially store keys or ids instead of using get_operatorData() so often
# def rate_limit(request, limit=60, period=60):
#     """Limit requests to 'limit' per 'period' seconds per IP"""
#     client_ip = get_client_ip(request)
#     cache_key = f"rate_limit:{client_ip}"
    
#     # Get current request count
#     request_history = cache.get(cache_key, [])
#     now = time.time()
    
#     # Filter out old requests
#     request_history = [t for t in request_history if now - t < period]
    
#     # Check if limit exceeded
#     if len(request_history) >= limit:
#         return False
        
#     # Add current request time and update cache
#     request_history.append(now)
#     cache.set(cache_key, request_history, period)
#     return True

# # Then in your view:
# @csrf_exempt
# def receive_data_view(request):
#     if not rate_limit(request, limit=100, period=60):
#         return JsonResponse({'message': 'Rate limit exceeded'}, status=429)





