from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db.models import Q
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from posts.models import get_point_value, Post
from network.models import Blockchain
from transactions.models import Wallet
from utils.models import BinaryBase62Field, BinaryBase64urlField, prnt, prntDebug, prntn, is_locked, now_utc, initial_save, is_dt_string, string_to_dt, has_field, find_or_create_chain_from_object, get_latest_dataPacket, get_self_node, is_obj_commit_valid
from utils.locked import hash_obj_id, verify_obj_to_data, get_signing_data, verify_data

import datetime
import json
import decimal


model_prefixes = {'User':'usr','UserData':'udat',
    'UserPubKey':'upk','UserVerification':'uver','SuperSign':'sup','Notification':'not','UserNotification':'unot',
    'UserAction':'act',
    }


class BaseAccountModel(models.Model):
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    signed = models.JSONField(default=dict)

    class Meta:
        abstract = True

class ModifiableAccountModel(BaseAccountModel):
    is_modifiable = True

    class Meta:
        abstract = True

    def committed_data_matches(self):
        return is_obj_commit_valid(self)



class UserManager(BaseUserManager):
    def create_user(self, password=None, **extra_fields):
        user = self.model(**extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def create_superuser(self, password=None, **extra_fields):
        # extra_fields.setdefault('is_staff', True)
        # extra_fields.setdefault('is_superuser', True)
        return self.create_user(password=password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    networkChain = models.CharField(max_length=50, default="User", blank=True)
    commitChain = models.CharField(max_length=50, default="Accounts", blank=True)
    is_modifiable = True
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    nodeCreatorId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    username = models.CharField(max_length=150, blank=True, null=True)
    pattern = models.IntegerField(default=0)
    signkey_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    alerts = models.JSONField(default=dict, blank=True, null=True)
    signed = models.JSONField(default=dict)
    UserData_obj = models.ForeignKey('accounts.UserData', blank=True, null=True, on_delete=models.PROTECT)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    UserVerification_obj = models.ForeignKey('accounts.UserVerification', blank=True, null=True, on_delete=models.PROTECT)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    iden_length = 11
    
    objects = UserManager()

    USERNAME_FIELD = 'id'
    REQUIRED_FIELDS = []  # empty, only `id` is needed

    def __str__(self):
        return 'USER:%s' %(self.username)
    
    class Meta:
        ordering = ['created']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'User', 'password': '', 'last_login': None, 'is_superuser': False, 'networkChain': 'User', 'commitChain': 'Accounts', 'id': None, 'modlVer': 1, 'created': None, 'lastUpdate': None, 'nodeCreatorId': None, 'username': None, 'pattern': 0, 'signkey_dt': None, 'alerts': {}, 'UserData_obj': None, 'Block_obj': None, 'UserVerification_obj': None, 'iden_length': 11, 'signed': {}}
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['created','nodeCreatorId','pattern']

    def no_sign_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['alerts','UserVerification_obj','Block_obj','UserData_obj']
    
    def get_absolute_url(self):
        return f"/so/{self.username}"
    
    def get_title(self):
        return f"so/{self.username}"
    
    def get_userLink_html(self):
        if self.is_superuser:
            return f'''<span style='font-size:85%; color:#0b559a' title='SuperUser'>So</span><span style='color:gray'>/</span><a href='{self.get_absolute_url()}'>{ self.username }</a>'''
        elif self.UserVerification_obj:
            return f'''<span style='font-size:85%; color:#b78e12' title='Verified User'>V</span><span style='color:gray'>/</span><a href='{self.get_absolute_url()}'>{ self.username }</a>'''
        else:
            return f'''<span style='font-size:90%; color:gray' title='anonymous'>a</span><a href='{self.get_absolute_url()}'>{ self.username }</a>'''

    def get_follow_topics(self):
        if self.UserData_obj and self.UserData_obj.follow_topics:
            return json.loads(self.UserData_obj.follow_topics)
        return []

    def get_interests(self):
        if self.UserData_obj and self.UserData_obj.interests:
            return json.loads(self.UserData_obj.interests)
        return []
    
    def verify_sig(self, data, signature=None, pubKey=None, simple_verify=False, keyType='', signed_dt=None, nodeId=None, dt=None):
        # avoid this - does not support multi sigs - only used for node to node contact
        # should use verify_obj_to_data for model objs, or verify_data for str
        prntDebug('-user verify sig:',self,simple_verify, 'sig',str(signature)[:20], 'pk',str(pubKey)[:20], 'data',str(data)[:40])
        from network.models import Block
        if is_dt_string(data):
            dt = string_to_dt(data)
        elif isinstance(data, (dict, str)):
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception as e:
                    pass
            if isinstance(data, dict):
                if 'Block_obj' in data and data['Block_obj']:
                    block = Block.objects.filter(id=data['Block_obj'], validated=True).values('DateTime').first()
                    if block:
                        dt = string_to_dt(block['DateTime'])
                    else:
                        from utils.models import request_items
                        retreived_objs = request_items([data['Block_obj']], return_updated_objs=True)
                        for obj in retreived_objs:
                            if obj.id == data['Block_obj']:
                                block = obj
                                dt = string_to_dt(block.DateTime)
                if not dt and 'lastUpdate' in data:
                    dt = string_to_dt(data['lastUpdate'])
                if 'created' in data and data['created'] or 'dt' in data and data['dt']:
                    if 'created' in data:
                        data_dt = string_to_dt(data['created'])
                    elif 'dt' in data:
                        data_dt = string_to_dt(data['dt'])
                    if data_dt < string_to_dt(self.created):
                        prnt('data created before user')
                        return False
                    if not dt:
                        dt = data_dt

        elif isinstance(data, models.Model):
            if has_field(data, 'Block_obj') and data.Block_obj and data.Block_obj.validated:
                dt = string_to_dt(data.Block_obj.DateTime)
            elif has_field(data, 'lastUpdate'):
                dt = string_to_dt(data.lastUpdate)
            if has_field(data, 'created') and data.created and self.created:
                if string_to_dt(data.created) < string_to_dt(self.created):
                    prnt('data created before user')
                    return False
                if not dt:
                    dt = string_to_dt(data.created)

        else:
            prnt('else type:',type(data))

        if not dt and signed_dt:
            dt = string_to_dt(signed_dt)
        elif not dt:
            raise ValueError("dt not found")
        prnt('dt',dt,'pubKey',pubKey)
        try:
            from utils.models import get_sigData
            sigData = get_sigData(data)
            if not pubKey:
                pubKey = sigData['pk']
            if not signature:
                signature = sigData['sig']
        except:
            pass
        if simple_verify:
            if isinstance(data, dict):
                from utils.locked import sort_for_sign
                sorted_dict = sort_for_sign(data)
                signed_Data = json.dumps(sorted_dict, separators=(',', ':'))
            else:
                signed_Data = str(data)
        else:
            signed_Data = get_signing_data(data)
        prnt('verifing sigData -',str(signed_Data))
        if keyType == 'node' or nodeId:
            if Block.objects.filter(Blockchain_obj__genesisId=self.id, validated=True, DateTime__gte=dt).exists():
                if nodeId:
                    upks = UserPubKey.objects.filter(User_obj=self, created__lte=dt, Block_obj__validated=True, nodeId=nodeId, keyType='node').filter(Q(end_life_dt=None)|Q(end_life_dt__gte=dt)).only('publicKey','end_life_dt')
                else:
                    upks = UserPubKey.objects.filter(User_obj=self, created__lte=dt, Block_obj__validated=True, keyType='node').filter(Q(end_life_dt=None)|Q(end_life_dt__gte=dt)).only('publicKey','end_life_dt')
            else:
                if nodeId:
                    upks = UserPubKey.objects.filter(User_obj=self, created__lte=dt, nodeId=nodeId, keyType='node').filter(Q(end_life_dt=None)|Q(end_life_dt__gte=dt)).only('publicKey','end_life_dt')
                else:
                    upks = UserPubKey.objects.filter(User_obj=self, created__lte=dt, keyType='node').filter(Q(end_life_dt=None)|Q(end_life_dt__gte=dt)).only('publicKey','end_life_dt')
        else:
            if Block.objects.filter(Blockchain_obj__genesisId=self.id, validated=True, DateTime__gte=dt).exists():
                upks = UserPubKey.objects.filter(User_obj=self, created__lte=dt, Block_obj__validated=True).filter(Q(end_life_dt=None)|Q(end_life_dt__gte=dt)).only('publicKey','end_life_dt')
            else:
                upks = UserPubKey.objects.filter(User_obj=self, created__lte=dt).filter(Q(end_life_dt=None)|Q(end_life_dt__gte=dt)).only('publicKey','end_life_dt')
        for upk in upks:
            prnt('upk',upk)
            if not pubKey or upk.id == pubKey or upk.publicKey == pubKey:
                    is_valid = verify_data(signed_Data, upk.publicKey, signature)
                    if is_valid:
                        return True
        return False
    
    def assess_super_status(self, dt=None):
        prnt('-assess_super_status', self, dt)
        if not dt:
            dt = now_utc()
        upks = UserPubKey.objects.filter(User_obj=self, keyType='guardian').filter(Q(end_life_dt=None) | Q(end_life_dt__gt=dt)).only('publicKey', 'end_life_dt')
        for upk in upks:
            prnt('upk',upk)
            if upk.super_level('guardian', dt=dt):
                prnt('is super')
                if not self.is_superuser:
                    self.is_superuser = True
                    self.is_staff = True
                    prnt('add super1',self)
                    self.save()
                return True
        if self.is_superuser:
            self.is_superuser = False
            self.is_staff = False
            self.save()
        prnt('not super')
        return False

    def assess_verification(self):
        pass

    def alert(self, title, link, body, obj=None, share=False):
        # prnt('-alert')
        if title == 'Yesterday in Government':
            x = link.find('?date=') + len('?date=')
            date = link[x:]
            workingTitle = date + ' in Government'
        else:
            if body:
                if len(body) > 11:
                    b = body[:11] + '...'
                else:
                    b = body
                workingTitle = title + ' - ' + b
            else:
                workingTitle = title
        n = Notification.objects.filter(title=workingTitle, link=link, User_obj=self).first()
        if not n:
            n = Notification(title=workingTitle, link=link, User_obj=self)
            if obj:
                n.pointerId = obj.id
            n.save(share=share)
            try:
                from firebase_admin.messaging import Notification as fireNotification
                from firebase_admin.messaging import Message as fireMessage
                from fcm_django.models import FCMDevice
                if link:
                    link = link.replace('file://', '')
                    if link[0] == '/':
                        link = 'https://sovote.center' + link
                else:
                    link = 'https://sovote.center'
                fcm_devices = FCMDevice.objects.filter(user=self, active=True)
                for device in fcm_devices:
                    try:
                        
                        prnt(device)
                        device.send_message(fireMessage(notification=fireNotification(title=title, body=body), data={"click_action" : "FLUTTER_NOTIFICATION_CLICK","link" : link}))
                        prnt('away')
                    except Exception as e:
                        prnt(str(e))
            except:
                pass
    
    def get_keys(self, dt=None, data=None, keyType=None):
        if dt:
            if not isinstance(dt, datetime.datetime):
                dt = string_to_dt(dt)
            if keyType:
                return UserPubKey.objects.filter(User_obj=self, keyType=keyType, created__lte=dt, Block_obj__validated=True).filter(Q(end_life_dt__gte=dt)|Q(end_life_dt=None))
            else:
                return UserPubKey.objects.filter(User_obj=self, created__lte=dt, Block_obj__validated=True).filter(Q(end_life_dt__gte=dt)|Q(end_life_dt=None))
        elif data:
            if 'lastUpdate' in data:
                dt = data['lastUpdate']
            elif 'created' in data:
                dt = data['created']
            else:
                return None
            dt = string_to_dt(dt)
            from network.models import Block
            if Block.objects.filter(Blockchain_obj__genesisId=self.id, validated=True, DateTime__gte=dt).exists():
                if keyType:
                    return UserPubKey.objects.filter(User_obj=self, keyType=keyType, created__lte=dt, Block_obj__validated=True).filter(Q(end_life_dt__gte=dt)|Q(end_life_dt=None))
                else:
                    return UserPubKey.objects.filter(User_obj=self, created__lte=dt, Block_obj__validated=True).filter(Q(end_life_dt__gte=dt)|Q(end_life_dt=None))
            else:
                return UserPubKey.objects.filter(User_obj=self, created__lte=dt).filter(Q(end_life_dt__gte=dt)|Q(end_life_dt=None))
        else:
            if keyType:
                return UserPubKey.objects.filter(User_obj=self, keyType=keyType, end_life_dt=None, Block_obj__validated=True)
            else:
                return UserPubKey.objects.filter(User_obj=self, end_life_dt=None, Block_obj__validated=True)
    
    def get_wallet(self, name=None):
        # prnt('-get_wallet',self, 'name:',name)
        if name:
            wal = Wallet.objects.filter(User_obj=self, Name=name).first()
            return wal
        else:
            return Wallet.objects.filter(User_obj=self).first()

    def get_chain(self):
        # prnt('-get_chain',self.id)
        return Blockchain.objects.filter(genesisId=self.id).first()
    
    def create_walletChain(self): # not used
        prnt('-create wallet')
        wallet = Wallet.objects.filter(User_obj=self).first()
        if not wallet:
            blockchain, self, secondChain = find_or_create_chain_from_object(self)
            blockchain.add_item_to_queue(self)
            wallet = Wallet(User_obj=self, name='Main')
            wallet.save()
            blockchain.add_item_to_queue(wallet)
            datapacket = get_latest_dataPacket()
            if datapacket:
                datapacket.add_item_to_share([self, wallet])
        return wallet

    def initialize(self): # in preperation for new object
        prnt('-initialize user')
        self.modlVer = self.latestVer
        if self.id is None:
            from utils.locked import hash_obj_id
            self.id = hash_obj_id(self)
            self.networkChain = self.id
        if not self.created:
            self.created = now_utc()
        try:
            if not self.nodeCreatorId:
                self.nodeCreatorId = get_self_node().id
        except:
            pass
        return self
    
    def boot(self): # after new object saved
        prntDebug('--booting user')

        from network.models import _AccountChain_genesisId
        accountChain = Blockchain.objects.filter(genesisName=_AccountChain_genesisId).defer('queuedData').first()
        if not accountChain:
            accountChain = Blockchain(genesisName=_AccountChain_genesisId, genesisType=_AccountChain_genesisId, genesisId=_AccountChain_genesisId, created=self.created)
            accountChain.save()
        if not self.Block_obj:
            accountChain.add_item_to_queue(self)

        datapacket = get_latest_dataPacket()
        if datapacket:
            datapacket.add_item_to_share(self)
        for key in self.get_keys():
            key.boot(datapacket=datapacket)
    
    def committed_data_matches(self):
        return is_obj_commit_valid(self)
    
    def save(self, sig=None, share=False, is_new=False, bypass_verify=False, *args, **kwargs):
        prnt('-save user(), is_new', is_new, self.id)
        if is_new:
            prnt('is_new, created:',self.created, 'now_utc()',now_utc())
            created = string_to_dt(self.created)
            if created >= now_utc()-datetime.timedelta(seconds=22):
                from network.models import Node, Block
                self_node = get_self_node()
                if not self_node and not Block.objects.filter(validated=True).exists() and Node.objects.all().count() <= 1:
                    pass
                else:
                    self.nodeCreatorId = self_node.id
                prnt('saving1...', self)
                super(User, self).save(*args, **kwargs)
                self.boot()
        elif bypass_verify:
            super(User, self).save(*args, **kwargs)
        elif verify_data(get_signing_data(self), self.signed, signature=sig):
            prnt('saving2...', self)
            super(User, self).save(*args, **kwargs)
        prnt('done user save\n')

    def delete(self):
        # deletes only if username previously registered to different user or user created less than 20 seconds ago
        if not isinstance(self.created, datetime.datetime):
            created = string_to_dt(self.created)
        else:
            created = self.created
        if created >= now_utc()-datetime.timedelta(seconds=20): 
            wallet = self.get_wallet()
            if wallet:
                walletChain = wallet.get_chain()
                if walletChain:
                    super(Blockchain, walletChain).delete()
                super(Wallet, wallet).delete()
            super(User, self).delete()

class UserData(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    signed = models.JSONField(default=dict)
    userId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)

    region_set_date = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    localities = models.TextField(default='[]', blank=True, null=True)
    interests = models.TextField(default='[]', blank=True, null=True)
    follow_topics = models.TextField(default='[]', blank=True, null=True)
    
    def __str__(self):
        return 'UserData:%s' %(self.userId)
        
    class Meta:
        ordering = ['id']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'UserData', 'modlVer': 1, 'id': None, 'created': None, 'lastUpdate': None, 'userId': None, 'region_set_date': None, 'localities': '[]', 'interests': '[]', 'follow_topics': '[]', 'signed': {}}

    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','userId']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['created','userId']
            
    def save(self, *args, **kwargs):
        if self.id is None:
            self.modlVer = self.latestVer
            self.id = hash_obj_id(self)
        super(UserData, self).save(*args, **kwargs)




class UserPubKey(models.Model):
    is_modifiable = True
    latestVer = 1
    networkChain = models.CharField(max_length=25, default='Keys')
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    end_life_dt = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, on_delete=models.CASCADE)
    keyType = models.CharField(max_length=25, default="signing")
    algorithm = models.CharField(max_length=25, default="secp256k1")
    nodeId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    publicKey = BinaryBase64urlField(max_byte_length=2592, null=True, blank=True)
    signed = models.JSONField(default=dict)
    
    def __str__(self):
        return 'UPK:%s' %(self.id)
        
    class Meta:
        ordering = ['-created', 'id']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'UserPubKey', 'networkChain': 'Keys', 'modlVer': 1, 'id': None, 'created': None, 'end_life_dt': None, 'lastUpdate': None, 'Block_obj': None, 'User_obj': None, 'keyType': 'signing', 'algorithm': 'secp256k1', 'nodeId': None, 'publicKey': None, 'signed': {}}
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['User_obj','created','end_life_dt','publicKey','signed']

    def yes_sign_fields(self, version=None):
        # prnt('-yes_sign_fields')
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['networkChain']

    def readable_strength(self):
        if self.algorithm:
            if self.algorithm == 'secp256k1':
                return 'Military Grade Level 1 (secp256k1)'
            elif self.algorithm == 'P521':
                return 'Military Grade Level 2 (P521)'
            elif self.algorithm == 'ML_DSA_44':
                return 'Quantum Grade Level 3 (ML_DSA_44)'
            elif self.algorithm == 'ML_DSA_65':
                return 'Quantum Grade Level 4 (ML_DSA_65)'
            elif self.algorithm == 'ML_DSA_87':
                return 'Quantum Grade Level 5 (ML_DSA_87)'
        return ''

    def super_level(self, level, dt=None):
        prnt('-super_level', self, level, dt)
        if self.keyType == level:
            if level in ['guardian', 'super']:
                if not dt:
                    dt = now_utc()
                if not self.end_life_dt or self.end_life_dt > dt:
                    from utils.locked import check_commit_data, detect_security
                    if detect_security(self.publicKey, key_type='pubkey') == 'ML_DSA_87':
                        return True
        return False

    def verify(self, data, signature=None, publicKey=None):
        # avoid this - only used in specific cases
        # should use verify_obj_to_data for model objs, or verify_data for str
        from utils.models import prnt
        prnt('-upk_verify',data,str(signature)[:100],str(publicKey)[:100])
        try:
            iden = 'x'
            f = 'upk unknown'
            if not isinstance(data, dict):
                try:
                    data = json.loads(data)
                except:
                    data = data
            elif not isinstance(data, str):
                data = str(data)
                f = 'upk verify data stringified: ' + data
            else:
                f = 'upk verify data else - ' + str(data)[:25]
        except Exception as e:
            f = '-upk verify data: ' + str(e)
        if publicKey and not self.publicKey:
            pubKey = publicKey
        else:
            pubKey = self
        prnt('self.verify:',self,str(data)[:100],str(pubKey)[:100])
        return verify_data(data, pubKey, signature)

    def initialize(self):
        self.modlVer = self.latestVer
        if not self.created:
            self.created = now_utc()
        self.id = hash_obj_id(self)
        return self
    
    def boot(self, datapacket=None):
        prntDebug('-boot upk', self.id)
        from network.models import _KeyChain_genesisId
        keyChain = Blockchain.objects.filter(genesisName=_KeyChain_genesisId).defer('queuedData').first()
        if not keyChain:
            keyChain = Blockchain(genesisName=_KeyChain_genesisId, genesisType=_KeyChain_genesisId, genesisId=_KeyChain_genesisId, created=self.created)
            keyChain.save()
        super(UserPubKey, self).save()
        prnt('post save')
        if not self.Block_obj:
            keyChain.add_item_to_queue(self)
            if not datapacket:
                datapacket = get_latest_dataPacket()
            if datapacket:
                datapacket.add_item_to_share(self)
        prnt('finish boot upk')
    
    def on_confirmation(self, obj=None):
        # should be given end-of-life block if reached end-of-life, different from creation block
        return self

    def committed_data_matches(self):
        return is_obj_commit_valid(self)
    
    def save(self, sig=None, share=False, is_new=False, bypass_verify=False):
        prntDebug('-save upk',self.id)
        if is_new:
            prnt('is new')
            upk = UserPubKey.objects.filter(id=self.id).exists()
            if not upk:
                if string_to_dt(self.created)+datetime.timedelta(seconds=420) >= now_utc():
                    self.boot()
        elif bypass_verify:
            super(UserPubKey, self).save()
        elif verify_data(get_signing_data(self), self.signed, signature=sig):
            super(UserPubKey, self).save()
        else:
            prnt('not saved')
        prnt('finish save upk',self.id)

    def delete(self, signature=None):
        created = string_to_dt(self.created)
        if created > now_utc()-datetime.timedelta(seconds=60):
            super(UserPubKey, self).delete()

class UserVerification(ModifiableAccountModel):
    networkChain = models.CharField(max_length=50, default="User", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    CreatorNode_obj = models.ForeignKey('network.Node', blank=True, null=True, on_delete=models.PROTECT)
    validatorNodeId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    Validator_obj = models.ForeignKey('network.Validator', blank=True, null=True, on_delete=models.PROTECT)
    valid_until = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    userId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    isVerified = models.BooleanField(default=False)
    super_invalid = models.BooleanField(default=False)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    
    def __str__(self):
        return 'UserVerification:%s' %(self.id)
        
    class Meta:
        ordering = ['-created', 'id']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'UserVerification', 'id': None, 'created': None, 'lastUpdate': None, 'networkChain': 'User', 'modlVer': 1, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'valid_until': None, 'userId': None, 'isVerified': False, 'super_invalid': False, 'Block_obj': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','User_obj','created']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','isVerified','signed','User_obj','valid_until']

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self, share=share)
            # broadcast changes immediatly
        elif not is_locked(self):
            super(UserVerification, self).save(*args, **kwargs)

    def delete(self):
        if not is_locked(self):
            super(UserVerification, self).delete()



class SuperSign(BaseAccountModel):
    networkChain = models.CharField(max_length=50, default="Sonet", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.SET_NULL)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, on_delete=models.CASCADE)
    data = models.JSONField(default=dict, blank=True, null=True)
    
    def __str__(self):
        return 'SuperSign:%s' %(self.id)
        
    class Meta:
        ordering = ['-created', 'id']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'SuperSign', 'id': None, 'created': None, 'lastUpdate': None, 'networkChain': 'Sonet', 'modlVer': 1, 'Block_obj': None, 'pointerId': None, 'User_obj': None, 'data': {}, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','User_obj','pointerId','data'] # fields not editable after initial save

    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','User_obj','pointerId','created']

    def save(self, sig=None, share=False, *args, **kwargs):
        if self.id is None and self.User_obj.assess_super_status():
            self = initial_save(self)
        elif self.User_obj.assess_super_status() and verify_data(get_signing_data(self), self.signed, signature=sig):
            super(SuperSign, self).save(*args, **kwargs)

    def delete(self):
        if not is_locked(self):
            super(SuperSign, self).delete()

class UserNotification(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    Notification_obj = models.ForeignKey('accounts.Notification', blank=True, null=True, on_delete=models.CASCADE)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, db_index=True, on_delete=models.CASCADE)
    new = models.BooleanField(default=True)
    signed = models.JSONField(default=dict)
    iden_length = 20

    def __str__(self):
        return 'UserNotification-%s' %(self.id)  
    
    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'UserNotification', 'modlVer': 1, 'id': None, 'created': None, 'lastUpdate': None, 'Notification_obj': None, 'DateTime': None, 'User_obj': None, 'new': True, 'iden_length': 20, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','User_obj','Notification_obj']
    

    def update_data(self, share=False):
        self.modlVer = self.latestVer
        self.save(share=share)

    def save(self, share=False, *args, **kwargs):
        prnt('save usernotification')
        if self.id is None:
            self.modlVer = self.latestVer
            self.id = hash_obj_id(self)
            self.created = self.Notification_obj.created
            self.DateTime = self.Notification_obj.DateTime
            # assess if self_node is fcm_capable and selected to send fcm notification, then User_obj.alert() which needs modification
        # 'new' should be signed by User_obj - look into this - if not signed, new = True
        super(UserNotification, self).save(*args, **kwargs)

class Notification(models.Model): 
    # needs work, should remove chamber field, set networkChain to match pointerId - fetch network in find_or_create_chain_from_obj by pointerId
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    networkChain = models.CharField(max_length=25, default='Region')
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    func = models.CharField(max_length=50, default=None, blank=True, null=True)
    CreatorNode_obj = models.ForeignKey('network.Node', blank=True, null=True, on_delete=models.PROTECT)
    validatorNodeId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    Validator_obj = models.ForeignKey('network.Validator', blank=True, null=True, on_delete=models.SET_NULL)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.SET_NULL)

    Chamber = models.CharField(max_length=100, default="", blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.CASCADE)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)

    Title = models.CharField(max_length=400, blank=True, null=True, default="")
    Link = models.CharField(max_length=500, blank=True, null=True, default="")
    Content = models.TextField(blank=True, null=True, default=None)
    targetUsers = models.JSONField(default=dict, blank=True, null=True)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    validated = models.BooleanField(default=False, blank=True, null=True)
    signed = models.JSONField(default=dict)

    def __str__(self):
        return 'Notification-%s' %(self.Title)   
    
    class Meta:
        ordering = ["-created", '-id']
    
    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Notification', 'modlVer': 1, 'id': None, 'networkChain': 'Region', 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': '', 'Region_obj': None, 'Country_obj': None, 'DateTime': None, 'Title': '', 'Link': '', 'Content': None, 'targetUsers': {}, 'pointerId': None, 'validated': False, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','Chamber','Region_obj','Country_obj','DateTime','Title']

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self, share=share)
        elif not is_locked(self):
            super(Notification, self).save(*args, **kwargs)

    def verify_is_valid(self, use_assigned_val=False):
        from network.models import Validator
        from utils.locked import get_node_assignment
        from utils.models import sigData_to_hash
        if use_assigned_val:
            v = self.Validator_obj
        else:
            v = Validator.objects.filter(data__has_key=self.id, is_valid=True).order_by('-created').first()
        if v:
            if self.id in v.data and v.data[self.id] == sigData_to_hash(self):
                if verify_obj_to_data(v, v):
                    creator_nodes, validator_nodes = get_node_assignment(None, dt=self.added_to_node, func=self.func, chainId=self.networkChain)
                    if self.validatorNodeId in validator_nodes:
                        return True
        return False

    def validate(self, validators=None, add_to_queue=True, save_self=True, verify_validator=True, opBlock_data={}):
        prnt('--validate notification', self.id)
        from utils.locked import validate_obj
        return validate_obj(obj=self, pointer=None, validators=validators, save_obj=save_self, update_pointer=False, verify_validator=verify_validator, add_to_queue=add_to_queue, opBlock_data=opBlock_data)

    def delete(self, force_delete=False):
        if force_delete or not is_locked(self):
            super(Notification, self).delete()



class UserAction(models.Model):
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    networkChain = models.CharField(max_length=25, default='User')
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)

    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, on_delete=models.CASCADE)
    Post_obj = models.ForeignKey(Post, blank=True, null=True, on_delete=models.SET_NULL)
    postId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True) # points to post_obj.pointer, not post
    pointerHash = models.CharField(max_length=100, default="", blank=True, null=True)
    addonId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    addonKey = models.ForeignKey(ContentType, on_delete=models.PROTECT, null=True, blank=True, default=None)
    Addon_obj = GenericForeignKey('addonKey', 'addonId')
    addonHash = models.CharField(max_length=100, default="", blank=True, null=True)
    updateId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    updateHash = models.CharField(max_length=100, default="", blank=True, null=True)

    voteValue = models.CharField(max_length=20, default='', blank=True, null=True)
    saved = models.BooleanField(default=None, blank=True, null=True)
    follow = models.BooleanField(default=None, blank=True, null=True)
    data = models.JSONField(default=dict, blank=True, null=True)
    rmv = models.BooleanField(default=None, blank=True, null=True)
    signed = models.JSONField(default=dict)
    iden_length = 20

    def __str__(self):
        return f'UserAction: user:{self.User_obj}, pointerId:{self.pointerId}'

    class Meta:
        ordering = ["-lastUpdate"]
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['postId','pointerId','pointerHash','addonId','updateId','updateHash','lastUpdate','voteValue','signed']
        
    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'UserAction', 'id': None, 'networkChain': 'User', 'modlVer': 1, 'created': None, 'lastUpdate': None, 'User_obj': None, 'Post_obj': None, 'postId': None, 'pointerId': None, 'pointerHash': '', 'addonId': None, 'addonKey': None, 'addonHash': '', 'updateId': None, 'updateHash': '', 'voteValue': '', 'saved': None, 'follow': None, 'data': {}, 'rmv': None, 'iden_length': 20, 'signed': {}}
        
    def get_hash_to_id(self):
        return ['objType','User_obj.id','pointerId','created']
    
    def new_version(self):
        self.id = hash_obj_id('UserAction')
        return self

    def calculate_vote(self, vote, forceVote):
        if self.Post_obj:
            p = self.Post_obj
        # elif self.Archive_obj:
        #     p = self.Archive_obj
        score = get_point_value(p)
        if vote == 'yea' or vote == 'Yea':
            # r.UserVote_obj.voteValue == 'yea'
            if self.isYea == False or forceVote:
                if self.isYea == True:
                    p.total_yeas -= 1
                self.isYea = True
                if self.isNay == True:
                    p.total_nays -= 1
                self.isNay = False
                points = decimal.Decimal(score)
                p.rank += points
                p.total_yeas += 1
                if not forceVote:
                    p.total_votes += 1
                # self = set_keywords(self, 'add', None)
            elif self.isYea == True:
                self.isYea = False
                points = decimal.Decimal(score)
                p.rank -= points
                p.total_votes -= 1
                p.total_yeas -= 1
                # self = set_keywords(self, 'remove', None)
        elif vote == 'nay' or vote == 'Nay':
            # self.cast_vote = ''
            if self.isNay == False or forceVote:
                if self.isNay == True:
                    p.total_nays -= 1
                self.isNay = True
                if self.isYea == True:
                    self.isYea = False
                    points = decimal.Decimal(score)
                    p.rank -= points
                    p.total_yeas -= 1
                p.total_nays += 1
                if not forceVote:
                    p.total_votes += 1
            elif self.isNay == True:
                self.isNay = False
                p.rank += points
                # self = set_keywords(self, 'add', None)
                p.total_votes -= 1
                p.total_nays -= 1
        p.save()
        self.save()

    def save(self, share=False, *args, **kwargs):
        # check valid?
        super(UserAction, self).save(*args, **kwargs)
    
    def delete(self):
        if not is_locked(self):
            from utils.models import superDelete
            superDelete(self)

