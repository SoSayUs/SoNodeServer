from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from utils.models import CompressedJSONField, BinaryBase62Field, prntDebug, prnt, compensate_save, get_model_and_update, superDelete, now_utc, is_locked, initial_save
from utils.locked import hash_obj_id
from posts.models import create_keyphrases, find_post, Update, BaseModel, ModifiableModel, Post, new_post

import re
import json
import pytz
import datetime
from django.utils import timezone


model_prefixes = {'Government':'gov','Agenda':'agn','Bill':'bil','BillText':'btxt',
                'Meeting':'mtg','Statement':'sta','Committee':'com','Action':'act',
                'Motion':'mot','RepVote':'rvot','Election':'elc',
                'Party':'prt','Person':'per','District':'dis',
                'LegisUserAction':'lact','LegisUserSettings':'lset','UserRegisteredVote':'urvot'}

from posts.models import BaseModel

class LegisModel(BaseModel):
    commitChain = models.CharField(max_length=50, default="Government", blank=True)
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    Chamber = models.CharField(max_length=20, default=None, blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.PROTECT)
    Government_obj = models.ForeignKey('legis.Government', related_name='%(class)s_government_obj', blank=True, null=True, on_delete=models.SET_NULL)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    
    class Meta:
        abstract = True


class LegisUserAction(models.Model):
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.SET_NULL)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    District_obj = models.ForeignKey('legis.District', default=None, related_name='%(class)s_district_obj', blank=True, null=True, on_delete=models.PROTECT)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    User_obj = models.ForeignKey('accounts.User', blank=True, null=True, on_delete=models.CASCADE)
    voteValue = models.CharField(max_length=20, default='', blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    signed = models.JSONField(default=dict)

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Government', 'is_modifiable': True, 'networkChain': 'Region', 'id': '0', 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': '', 'Validator_obj': None, 'blockchainId': '', 'Block_obj': None, 'lastUpdate': None, 'proposed_modification': None, 'modlVer': version, 'Region_obj': None, 'Country_obj': None, 'DateTime': None, 'LogoLinks': None, 'GovernmentNumber': None, 'SessionNumber': 1, 'gov_level': '', 'gov_type': '', 'menuItem_array': None, 'Chamber_array': None, 'Office_array': None, 'signed': {}}
        
    def required_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['District_obj', 'pointerId', 'voteValue']
        return []

class LegisUserSettings(models.Model):
    networkChain = models.CharField(max_length=50, default="Plugin", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    is_modifiable = True
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)

    # custom fields

    data = models.JSONField(default=dict, blank=True, null=True)
    signed = models.JSONField(default=dict)
    
    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Government', 'is_modifiable': True, 'networkChain': 'Region', 'id': '0', 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': '', 'Validator_obj': None, 'blockchainId': '', 'Block_obj': None, 'lastUpdate': None, 'proposed_modification': None, 'modlVer': version, 'Region_obj': None, 'Country_obj': None, 'DateTime': None, 'LogoLinks': None, 'GovernmentNumber': None, 'SessionNumber': 1, 'gov_level': '', 'gov_type': '', 'menuItem_array': None, 'Chamber_array': None, 'Office_array': None, 'signed': {}}
        
class UserRegisteredVote(models.Model):
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    is_modifiable = True
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.SET_NULL)
    User_obj = models.ForeignKey('accounts.User', related_name='%(class)s_user_obj', blank=True, null=True, on_delete=models.CASCADE)
    Voter_obj = models.ForeignKey('accounts.User', related_name='%(class)s_voter_obj', blank=True, null=True, on_delete=models.SET_NULL)
    District_obj = models.ForeignKey('legis.District', default=None, related_name='%(class)s_district_obj', blank=True, null=True, on_delete=models.PROTECT)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    delegate_history = models.JSONField(default=dict, blank=True, null=True)
    signed = models.JSONField(default=dict)
    
    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Government', 'is_modifiable': True, 'networkChain': 'Region', 'id': '0', 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': '', 'Validator_obj': None, 'blockchainId': '', 'Block_obj': None, 'lastUpdate': None, 'proposed_modification': None, 'modlVer': version, 'Region_obj': None, 'Country_obj': None, 'DateTime': None, 'LogoLinks': None, 'GovernmentNumber': None, 'SessionNumber': 1, 'gov_level': '', 'gov_type': '', 'menuItem_array': None, 'Chamber_array': None, 'Office_array': None, 'signed': {}}
            
    def required_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['User_obj', 'Voter_obj', 'signed']
        return []

    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['User_obj','Voter_obj','delegate_history']



class Government(ModifiableModel):
    commitChain = models.CharField(max_length=50, default="Government", blank=True)
    networkChain = models.CharField(max_length=50, default="Government", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.PROTECT)
    LogoLinks = models.JSONField(blank=True, null=True)
    GovernmentNumber = models.IntegerField(blank=True, null=True)
    SessionNumber = models.IntegerField(default=1, blank=True, null=True)
    StartDate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=False, null=True)
    EndDate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=False, null=True)
    gov_level = models.CharField(max_length=100, default="", blank=True, null=True) # Federal, Provincial, State, Greater Municipal, Municipal, County, City
    gov_type = models.CharField(max_length=100, default="", blank=True, null=True) # Parliament, Congress or Government
    menuItem_array = ArrayField(models.CharField(max_length=50, default='', blank=True, null=True), size=7, null=True, blank=True)
    Chamber_array = ArrayField(models.CharField(max_length=30, default='', blank=True, null=True), size=10, null=True, blank=True)
    Office_array = ArrayField(models.CharField(max_length=30, default='', blank=True, null=True), size=25, null=True, blank=True)
    
    def __str__(self):
        return 'GOV:(%s-%s)' %(self.GovernmentNumber, self.SessionNumber)
    
    class Meta:
        ordering = ['-GovernmentNumber','-SessionNumber']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Government', 'is_modifiable': True, 'networkChain': 'Government', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'lastUpdate': None, 'proposed_modification': None, 'modlVer': 1, 'Region_obj': None, 'Country_obj': None, 'LogoLinks': None, 'GovernmentNumber': None, 'SessionNumber': 1, 'StartDate': None, 'EndDate': None, 'gov_level': '', 'gov_type': '', 'menuItem_array': None, 'Chamber_array': None, 'Office_array': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['GovernmentNumber','SessionNumber','gov_level','Country_obj','Region_obj']
    
    def no_sign_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) == 1:
            return ['proposed_modification']
        return []
    
    def required_for_validation(self):
        return ['Region_obj.Validator_obj','Region_obj.is_supported','GovernmentNumber','gov_level']

    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['Region_obj','GovernmentNumber','SessionNumber','gov_level','StartDate']

    def get_chains(self, obj=None):
        from network.models import Blockchain
        commit_chain = None
        prev_gov = Government.objects.filter(Region_obj=self.Region_obj, StartDate__lt=self.StartDate, Validator_obj__is_valid=True).order_by('-StartDate').values('id').first()
        if prev_gov:
            commit_chain = Blockchain.objects.filter(genesisId=prev_gov['id']).first()

        if not commit_chain:
            commit_chain = Blockchain.objects.filter(genesisId=self.Region_obj.id).first()

        network_chain = Blockchain.objects.filter(genesisId=self.id).first()
        if not network_chain:
            network_chain = Blockchain(genesisId=self.id, genesisType=self._meta.object_name, genesisName=str(self), created=self.created)
            network_chain.save()

        return network_chain, commit_chain

    def migrate_data(self):
        if self.SessionNumber:
            previousGov = Government.objects.filter(Region_obj=self.Region_obj, gov_level=self.gov_level, GovernmentNumber__lte=self.GovernmentNumber, SessionNumber__lte=self.SessionNumber, Validator_obj__is_valid=True).exclude(id=self.id).first()
        else:
            previousGov = Government.objects.filter(Region_obj=self.Region_obj, gov_level=self.gov_level, GovernmentNumber__lte=self.GovernmentNumber, Validator_obj__is_valid=True).exclude(id=self.id).first()
        if previousGov:
            self.LogoLinks = previousGov.LogoLinks
            self.gov_type = previousGov.gov_type
            self.menuItem_array = previousGov.menuItem_array
            self.Chamber_array = previousGov.Chamber_array
            self.Office_array = previousGov.Office_array
            if not self.StartDate:
                if previousGov.EndDate:
                    self.StartDate = previousGov.EndDate + datetime.timedelta(days=1)
                else:
                    from utils.models import round_time
                    self.StartDate = round_time(dt=now_utc(), dir='down', amount='day')
        currentGov = Government.objects.filter(Region_obj=self.Region_obj, gov_level=self.gov_level, Validator_obj__is_valid=True).exclude(id=self.id).first()
        if currentGov and currentGov.StartDate > self.StartDate:
            self.LogoLinks = currentGov.LogoLinks
            self.gov_type = currentGov.gov_type
            self.menuItem_array = currentGov.menuItem_array
            self.Chamber_array = currentGov.Chamber_array
            self.Office_array = currentGov.Office_array
            self.EndDate = currentGov.StartDate - datetime.timedelta(days=1)

        return self

    def end_previous(self, func): # not currently working - why not?
        print('-end_previous')
        # dt = datetime.date.today()
        dt_now = now_utc()
        today = dt_now - datetime.timedelta(hours=dt_now.hour, minutes=dt_now.minute, seconds=dt_now.second, microseconds=dt_now.microsecond)
        print('today',today)
        from utils.locked import convert_to_dict, dt_to_string
        print('d:',convert_to_dict(self))
        previousCongress = Government.objects.filter(Region_obj=self.Region_obj, gov_level=self.gov_level, GovernmentNumber__lte=self.GovernmentNumber, SessionNumber__lte=self.SessionNumber).exclude(id=self.id).first()
        print('previousCongress',previousCongress)
        if previousCongress:
            obj, update, is_new = get_model_and_update(self._meta.object_name, obj=previousCongress)
            if 'EndDate' not in update.data or not self.EndDate:
                if not self.EndDate:
                    self.EndDate = today - datetime.timedelta(days=1)
                    self.save()
                if not update.data.get('EndDate', None):
                    update.data['EndDate'] = dt_to_string(self.EndDate)
                    # update.data = updateData
                    update.func = func
                    update, u_is_new = update.save_if_new()
                    if update and u_is_new:
                        return update
        return None

    def get_gov_num(self):
        return f'{self.GovernmentNumber}-{self.SessionNumber}'

    def add_office(self, office_name):
        prnt('-add_office',office_name)
        if not self.Office_array:
            self.Office_array = []
        if office_name not in self.Office_array:
            self.Office_array.append(office_name)
            self.update_data()
            return True
        else:
            return False
        
    def add_chamber(self, chamber_name):
        prnt('-add_chamber',chamber_name)
        if not self.Chamber_array:
            self.Chamber_array = []
        if chamber_name not in self.Chamber_array:
            self.Chamber_array.append(chamber_name)
            self.update_data()
            return True
        else:
            return False

    def add_menu_item(self, item_name):
        prnt('-add_menu_item',item_name)
        if not self.menuItem_array:
            self.menuItem_array = []
        if item_name not in self.menuItem_array:
            self.menuItem_array.append(item_name)
            self.update_data()
            return True
        else:
            return False

    def update_data(self, share=False):
        self.signed = {}
        self.modlVer = self.latestVer
        self.lastUpdate = now_utc()
        self.save()
    
    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            dt_now = now_utc()
            if not self.StartDate:
                self.StartDate = dt_now - datetime.timedelta(hours=dt_now.hour, minutes=dt_now.minute, seconds=dt_now.second, microseconds=dt_now.microsecond)
            self = initial_save(self)
        elif not is_locked(self):
            compensate_save(self, Government, *args, **kwargs)    

    def delete(self):
        if not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        p.save()
        return p

class Agenda(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    bill_dict = models.JSONField(default=None, blank=True, null=True)
    data = models.JSONField(default=None, blank=True, null=True)

    def __str__(self):
        return 'AGENDA:%s-%s' %(self.DateTime, self.Chamber)

    class Meta:
        ordering = ['-DateTime']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Agenda', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'bill_dict': None, 'data': None, 'signed': {}}
    
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','DateTime','Chamber','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash']

    def get_absolute_url(self):
        est = pytz.timezone('US/Eastern')
        return "/agenda-item/%s/%s" %(self.Chamber, self.DateTime.astimezone(est).strftime("%Y-%m-%d/%H:%M"))

    @property
    def is_today(self):
        def convert_to_localtime(utctime):
            fmt = '%Y-%m-%d'
            utc = utctime.replace(tzinfo=pytz.UTC)
            localtz = utc.astimezone(timezone.get_current_timezone())
            return localtz.strftime(fmt)
        return str(datetime.date.today()) == convert_to_localtime(self.DateTime)
        
    def is_last(self):
        a = Agenda.objects.first()
        if self == a:
            return True
        else:
            return False

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self, share=share)
        elif not is_locked(self):
            compensate_save(self, Agenda, *args, **kwargs)

    def delete(self):
        if not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        p.save(share=share)
        return p


class BillText(BaseModel):
    commitChain = models.CharField(max_length=50, default="Government", blank=True)
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    pointerId = models.CharField(max_length=100, default="", blank=True)
    data = models.JSONField(default=dict, blank=True, null=True)
    text = CompressedJSONField(default=dict, blank=True, null=True)
    keyword_array = ArrayField(models.CharField(max_length=50, blank=True, null=True, default=[]), size=20, null=True, blank=True)

    def __str__(self):
        return f'BillText:{self.id}-{self.pointerId}'

    class Meta:
        ordering = ['-created', "pointerId"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'BillText', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'modlVer': 1, 'Region_obj': None, 'pointerId': '', 'data': {}, 'text': {}, 'keyword_array': None, 'signed': {}}

    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','pointerId','data']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','pointerId']
        
    def on_confirmation(self, obj=None):
        bill = Bill.objects.filter(id=self.pointerId).first()
        if not bill:
            #request
            ...
        if bill and bill.BillText_obj != self:
            bill.BillText_obj = self
            bill.save()
        post = Post.objects.filter(id=self.pointerId).first()
        if post and post.Spren_obj and post.Spren_obj.pointerId != self.id:
            post.Spren_obj = None
            post.save()
        return None

    def fetch_text(self):
        return self.text

    def store_text(self, text=None):
        return self.text
    
    def save(self, share=False, region=None, *args, **kwargs):
        if self.text and not isinstance(self.text, bytes):
            self.text = self.store_text(self.text)

        if self.id is None:
            if region and not self.Region_obj:
                self.Region_obj = region
            elif self.pointerId and not self.Region_obj:
                pointer = Bill.objects.filter(id=self.pointerId).only('Region_obj').first()
                if pointer and pointer.Region_obj:
                    self.Region_obj = pointer.Region_obj
            self = initial_save(self)
        elif not is_locked(self):
            compensate_save(self, BillText, *args, **kwargs)

    def delete(self):
        if not is_locked(self):
            superDelete(self)

class Bill(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Person_obj = models.ForeignKey('legis.Person', blank=True, null=True, on_delete=models.PROTECT) #sponsor
    GovIden = models.IntegerField(default=0, blank=True, null=True)
    LegisLink = models.URLField(null=True, blank=True) #official link to text of bill
    Started = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    Party_obj = models.ForeignKey('legis.Party', blank=True, null=True, on_delete=models.PROTECT)
    District_obj = models.ForeignKey('legis.District', related_name='%(class)s_district_obj', blank=True, null=True, on_delete=models.PROTECT)
    BillText_obj = models.ForeignKey('legis.BillText', related_name='%(class)s_billtext_obj', blank=True, null=True, on_delete=models.SET_NULL)
    NumberCode = models.CharField(max_length=20, default="", blank=True, null=True)
    amendedNumberCode = models.CharField(max_length=20, default="", blank=True, null=True) #removes dash for search
    NumberPrefix = models.CharField(max_length=20, default="", blank=True, null=True)
    Number = models.IntegerField(blank=True, null=True)
    Subjects = models.CharField(max_length=1000, default="", blank=True, null=True)
    Title = models.CharField(max_length=1000, default="", blank=True, null=True)
    ShortTitle = models.CharField(max_length=1000, default="", blank=True, null=True)
    BillDocumentTypeName = models.CharField(max_length=56, default="", blank=True, null=True) # bill / resolution / ...
    IsGovernmentBill = models.CharField(max_length=10, default="", blank=True, null=True)
    SponsorPersonName = models.CharField(max_length=100, default="", blank=True, null=True)
    SponsorCode = models.CharField(max_length=100, default="", blank=True, null=True)
    keyword_array = ArrayField(models.CharField(max_length=50, blank=True, null=True, default=[]), size=20, null=True, blank=True)
    
    def __str__(self):
        if self.Government_obj:
            return 'BILL:(%s-%s) %s :%s' %(self.Government_obj.GovernmentNumber, self.Government_obj.SessionNumber, self.NumberCode, self.id)
        else:
            return 'BILL:(%s-%s) %s :%s' %('x', 'x', self.NumberCode, self.id)

    class Meta:
        ordering = ['-created', "-NumberCode"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Bill', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'Person_obj': None, 'GovIden': 0, 'LegisLink': None, 'Started': None, 'Party_obj': None, 'District_obj': None, 'BillText_obj': None, 'NumberCode': '', 'amendedNumberCode': '', 'NumberPrefix': '', 'Number': None, 'Subjects': '', 'Title': '', 'ShortTitle': '', 'BillDocumentTypeName': '', 'IsGovernmentBill': '', 'SponsorPersonName': '', 'SponsorCode': '', 'keyword_array': None, 'signed': {}}

    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','NumberCode','Government_obj.GovernmentNumber','Chamber','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','NumberCode','Title','DateTime','Region_obj']

    def user_action_addon(self, user_id, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            if not LegisUserAction.objects.filter(pointerId=self.id, User_obj__id=user_id, Block_obj=None).exists():
                return LegisUserAction(id=hash_obj_id(LegisUserAction), Region_obj=self.Region_obj, networkChain=self.networkChain, pointerId=self.id)
            else:
                return LegisUserAction.objects.filter(pointerId=self.id, User_obj__id=user_id, Block_obj=None).first()


    def required_for_validation(self):
        return ['Government_obj.signed']
    
    def get_absolute_url(self):
        if self.Government_obj and self.Government_obj.GovernmentNumber:
            return "/bill/%s/%s/%s/%s/%s" %(self.Country_obj.Name, self.Chamber, self.Government_obj.GovernmentNumber, self.Government_obj.SessionNumber, self.NumberCode)
        else:
            return "/bill/%s/%s/%s/%s/%s" %(self.Country_obj.Name, self.Chamber, '00', '00', self.NumberCode)
    
    def get_update_url(self):
        return "/utils/update_bill/%s" %(self.id)

    def get_fields(self):
        return ['%s: %s' %(field.name, field.value_to_string(self)) for field in Bill._meta.fields[:61]]
    
    def choose_nav(self, nav):
        try:
            d = json.loads(nav)
            return list(d.items())
        except Exception as e:
            print('choose_nav err',str(e))
            return None

    def get_nav(self):
        if self.bill_text_nav:
            d = json.loads(self.bill_text_nav)
            result = list(d.items())
        else:
            result = None
        return result

    def remove_tags(text):
        TAG_RE = re.compile(r'<[^>]+>')
        return TAG_RE.sub('', text)

    def get_latest_version(self):
        return Post.objects.filter(BillVersion_obj__Bill_obj=self, BillVersion_obj__current=True).first()

    def get_bill_keywords(self):
        # prnt('-get_bill_keywords')
        def strip_tags(text):
            TAG_RE = re.compile(r'<[^>]+>')
            return TAG_RE.sub('', text)
        if self.BillText_obj and self.BillText_obj.data and 'TextHTML' in self.BillText_obj.data:
            text = self.BillText_obj.data['TextHtml']
            if 'TextNav' in self.BillText_obj.data:
                text = text.replace(self.BillText_obj.data['TextNav'], '')
            text = strip_tags(text)
            from posts.models import get_keywords
            self = get_keywords(self, text)
        return self

    def update_keywords(self):
        self.keyword_array = []
        if self.Person_obj and self.Person_obj not in self.keyword_array:
            self.keyword_array.append(self.Person_obj.get_field('FullName'))
        elif not self.Person_obj:
            self.keyword_array.append(self.SponsorPersonName)
        if self.ShortTitle:
            title = f'{self.Chamber} {self.BillDocumentTypeName} {self.amendedNumberCode} ({self.Government_obj.GovernmentNumber}-{self.Government_obj.SessionNumber}): {self.ShortTitle}'
            if title not in self.keyword_array:
                self.keyword_array.append(title)
        self = self.get_bill_keywords()
        return self

    def set_keywords(self, post):
        if self.NumberCode:
            post.filters['NumberCode'] = self.NumberCode
        if self.amendedNumberCode:
            post.filters['amendedNumberCode'] = self.amendedNumberCode
        if self.Title:
            post.filters['Title'] = self.Title
        if self.ShortTitle:
            post.filters['ShortTitle'] = self.ShortTitle
        if self.BillDocumentTypeName:
            post.filters['BillType'] = self.BillDocumentTypeName
        return post

    def save(self, share=False, *args, **kwargs):
        # print('-save bill')
        if len(self.Title) > 1000:
            self.Title = self.Title[:997] + '...'
        if self.id is None:
            if not self.ShortTitle:
                if len(self.Title) > 50:
                    self.ShortTitle = self.Title[:50] + '...'
                else:
                    self.ShortTitle = self.Title
            self.amendedNumberCode = self.NumberCode.replace('-', '').replace('.', '').replace(' ', '')
            self = initial_save(self)
        elif not is_locked(self):
            compensate_save(self, Bill, *args, **kwargs)

    def delete(self):
        if not is_locked(self):
            for text in BillText.objects.filter(pointerId=self.id):
                text.delete()
            superDelete(self)

    def boot(self):
        prnt('-boot bill')
        self = self.update_keywords()
        p = new_post(self)
        if not p.keyword_array:
            p.keyword_array = []
            for k in self.keyword_array:
                if k and k.lower() not in p.keyword_array:
                    p.keyword_array.append(k.lower())
        p.save()
        billtext = BillText.objects.filter(pointerId=self.id, Validator_obj__is_valid=True).first()
        if billtext and self.BillText_obj != billtext:
            self.BillText_obj = billtext
            self.save()
        return p

    def upon_validation(self):
        create_keyphrases(self, create_person_trend=True)

    def update_post_time(self):
        p = find_post(self)
        p.DateTime = self.DateTime
        p.set_score()
        if not self.keyword_array:
            self.update_keywords(p)
        versions = Post.objects.filter(BillVersion_obj__Bill_obj=self, BillVersion_obj__empty=False)
        for v in versions:
            v.BillVersion_obj.boot()


class Meeting(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    meeting_type = models.CharField(max_length=100, default="", blank=True, null=True) # Debate, Committee
    GovPage = models.CharField(max_length=150, default="", blank=True, null=True)
    Title = models.CharField(max_length=150, default="", blank=True, null=True)
    PublicationId = models.CharField(max_length=100, default="", blank=True, null=True)
    hide_time = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return 'MEETING:(%s) %s' %(self.id, self.Title)
    
    class Meta:
        ordering = ['-DateTime', 'Title']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Meeting', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'meeting_type': '', 'GovPage': '', 'Title': '', 'PublicationId': '', 'hide_time': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','meeting_type','GovPage','PublicationId','Government_obj','Chamber','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','Title','DateTime','Region_obj']

    def get_absolute_url(self):
        if self.Title:
            return "/%s/%s-meeting/%s/%s/%s" %(self.Government_obj.Region_obj.Name, self.Chamber, self.Government_obj.GovernmentNumber, self.Government_obj.SessionNumber, self.Title.replace(' ','_'))
        else:
            return "/%s/%s-meeting/%s/%s/%s" %(self.Government_obj.Region_obj.Name, self.Chamber, self.Government_obj.GovernmentNumber, self.Government_obj.SessionNumber, self.id)

    def apply_terms(self, meeting=None, meetingU=None, meeting_is_new=False):
        if not meeting:
            meeting = self
        if not meetingU:
            meeting, meetingU, meeting_is_new = get_model_and_update('Meeting', obj=self)
        if not meetingU.data:
            meetingU.data = {}
        statements = Statement.objects.filter(Meeting_obj=self).order_by('created')
        meetingU.data['statement_count'] = statements.count()

        H_people = {}
        meeting_terms = {}
        update_items = []
        order = 1
        for s in statements:
            if s.order == None:
                s.order = order
                update_items.append(s)
            order += 1
            p_item = None
            p_item = json.dumps({'Name':s.PersonName, 'obj_id':s.PersonName})
            if p_item:
                try:
                    if not p_item in H_people:
                        H_people[p_item] = 1
                    else:
                        H_people[p_item] += 1
                except Exception as e:
                    pass
            if s.Terms_array:
                for t in s.Terms_array:
                    if t in meeting_terms:
                        meeting_terms[t] += 1
                    else:
                        meeting_terms[t] = 1
            if s.keyword_array:
                for t in s.keyword_array:
                    if t in meeting_terms:
                        meeting_terms[t] += 1
                    else:
                        meeting_terms[t] = 1
            if s.SubjectOfBusiness:
                if s.SubjectOfBusiness in meeting_terms:
                    meeting_terms[s.SubjectOfBusiness] += 1
                else:
                    meeting_terms[s.SubjectOfBusiness] = 1
        if update_items:
            from utils.models import dynamic_bulk_update
            dynamic_bulk_update(model_name='Statement', items_field_update=['order','update_on_node'], items=update_items, compensate_save=True, return_items=False, retrieve_missing=False)

        def sort_by_value_then_key(d):
            return dict(
                sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
            )

        result  = sort_by_value_then_key(H_people)
        meetingU.data['People'] = [{key: value} for key, value in list(result.items())]

        meeting_result = sort_by_value_then_key(meeting_terms)
        meetingU.data['Terms'] = [{key: value} for key, value in list(meeting_result.items())[:150]]

        return meeting, meetingU, meeting_is_new

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self, share=share)
        elif not is_locked(self):
            compensate_save(self, Meeting, *args, **kwargs)

    def delete(self, force_delete=False):
        if force_delete or not is_locked(self):
            for s in Statement.objects.filter(Meeting_obj=self):
                s.delete(force_delete)
            superDelete(self, force_delete=force_delete)

    def new_update(self, update):
        data = update.data
        if 'Terms' in data:
            terms = data['Terms']
            p = Post.objects.filter(pointerId=self.id).first()
            if p:
                p.keyword_array = [list(d.keys())[0].lower() for d in update.data['Terms'][:20]]
                p.save()

    def boot(self, share=False):
        p = new_post(self)
        if not p.keyword_array:
            update = Update.objects.filter(pointerId=self.id).first()
            if update and 'Terms' in update.data:
                data = update.data['Terms']
                p.keyword_array = [key.lower() for z in data for key, value in z.items()]
            if update and update.DateTime:
                p.DateTime = update.DateTime
        if not p.DateTime:
            p.DateTime = self.DateTime
        p.save()
        return p

    def list_people(self):
        try:
            d = json.loads(self.People_json)
            l = list(d.items())[:10]
            speakers = {}
            keys = []
            for key, value in l:
                keys.append(key)
            people = Person.objects.filter(id__in=keys)
            for p, value in [[p, value] for p in people for key, value in l if p.id == key]:
                speakers[p] = value
            return list(speakers.items())
        except Exception as e:
            print('list_people err',str(e))
            return None

class Statement(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Meeting_obj = models.ForeignKey('legis.Meeting', blank=True, null=True, related_name='debate_key', on_delete=models.SET_NULL)
    Person_obj = models.ForeignKey('legis.Person', blank=True, null=True, on_delete=models.PROTECT)
    PersonName = models.CharField(max_length=250, default="", blank=True, null=True)
    Party_obj = models.ForeignKey('legis.Party', blank=True, null=True, on_delete=models.PROTECT)
    District_obj = models.ForeignKey('legis.District', related_name='%(class)s_district_obj', blank=True, null=True, on_delete=models.PROTECT)
    keyword_array = ArrayField(models.CharField(max_length=50, blank=True, null=True, default='{default}'), size=15, null=True, blank=True)
    bill_dict = models.JSONField(blank=True, null=True)
    ItemId = models.CharField(max_length=100, default="", blank=True, null=True)
    EventId = models.CharField(max_length=100, default="", blank=True, null=True)
    source_link = models.CharField(max_length=350, default="", blank=True, null=True)
    OrderOfBusiness = models.CharField(max_length=255, default="", blank=True, null=True)
    SubjectOfBusiness = models.CharField(max_length=450, default="", blank=True, null=True)
    Language = models.CharField(max_length=54, default="English", blank=True, null=True)
    Content = models.TextField(default='', blank=True, null=True)
    order = models.PositiveIntegerField(blank=True, null=True) # order of statements made during meeting
    word_count = models.PositiveIntegerField(blank=True, null=True)
    Terms_array = ArrayField(models.CharField(max_length=300, blank=True, null=True, default=[]), size=20, null=True, blank=True)
    
    def __str__(self):
        return 'STATEMENT:%s(%s-%s)' %(self.PersonName, self.id, self.DateTime)

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Statement', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'Meeting_obj': None, 'Person_obj': None, 'PersonName': '', 'Party_obj': None, 'District_obj': None, 'keyword_array': None, 'bill_dict': None, 'ItemId': '', 'EventId': '', 'source_link': '', 'OrderOfBusiness': '', 'SubjectOfBusiness': '', 'Language': 'English', 'Content': '', 'order': None, 'word_count': None, 'Terms_array': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','Meeting_obj','Person_obj','PersonName','Content','order','Government_obj','Chamber','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','Meeting_obj','PersonName']

    def required_for_validation(self):
        return ['Meeting_obj.signed']
    
    def get_absolute_url(self):
        if self.order:
            return '%s?id=%s' %(self.Meeting_obj.get_absolute_url(), self.order)
        else:
            return '%s?id=%s' %(self.Meeting_obj.get_absolute_url(), self.id)
        
    def remove_tags(self):
        return re.sub('<[^<]+?>', '', self.Content)

    class Meta:
        ordering = ['-order', '-DateTime', 'created']

    def add_term(self, term, bill, share=False):
        if not self.Terms_array:
            self.Terms_array = []
        if term and term not in self.Terms_array:
            self.Terms_array.append(term)
        if bill and bill.NumberCode not in self.Terms_array:
            self.Terms_array.append(bill.NumberCode)
        if bill:
            if not self.bill_dict:
                self.bill_dict = {}
            self.bill_dict[bill.NumberCode] = {'obj_id':bill.id, 'localLink':bill.get_absolute_url()}
        return self

    def get_item_keywords(self, share=False):
        def strip_tags(text):
            TAG_RE = re.compile(r'<[^>]+>')
            return TAG_RE.sub('', text)
        text = strip_tags(self.Content)
        from posts.models import get_keywords
        self = get_keywords(self, text)
        return self

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            if not self.PersonName and self.Person_obj:
                self.PersonName = self.Person_obj.get_name()
            if not self.DateTime:
                try:
                    self.DateTime = self.Meeting_obj.DateTime
                except:
                    pass
            if not self.Chamber:
                if self.Meeting_obj:
                    self.Chamber = self.Meeting_obj.Chamber
            if not self.Country_obj:
                self.Country_obj = self.Government_obj.Country_obj
            if not self.word_count:
                self.word_count = len(self.Content.strip().split(' '))
            self = initial_save(self)
        elif not is_locked(self):
            compensate_save(self, Statement, *args, **kwargs)
        
    def delete(self, force_delete=False):
        if force_delete or not is_locked(self):
            superDelete(self, force_delete=force_delete)

    def boot(self, create_person_trend=False, share=False):
        self = self.get_item_keywords()
        p = new_post(self) 
        if not p.keyword_array:
            from utils.models import skipwords
            p.keyword_array = []
            if create_person_trend and p.Person_obj: # not used
                if 'FullName' in p.Person_obj.Update_obj.data and p.Person_obj.Update_obj.data['FullName'].lower() not in p.keyword_array:
                    p.keyword_array.append(p.Person_obj.Update_obj.data['FullName'].lower())
            if self.Terms_array:
                for t in self.Terms_array:
                    if t not in p.keyword_array and t not in skipwords:
                        p.keyword_array.append(t.lower())
            if self.keyword_array:
                for t in self.keyword_array:
                    if t not in p.keyword_array and t not in skipwords:
                        p.keyword_array.append(t.lower())
        p.DateTime = self.DateTime
        p.save()
        return p
    
    def upon_validation(self):
        create_keyphrases(self, create_person_trend=False)
        personPost = Post.objects.filter(Person_obj=self.Person_obj).first()
        if personPost and personPost.DateTime < self.DateTime:
            personPost.DateTime = self.DateTime
            personPost.save()

class Committee(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Chair_obj = models.ForeignKey('legis.Person', related_name='committee_chair', blank=True, null=True, on_delete=models.PROTECT)
    members = models.JSONField(blank=True, null=True)
    Code = models.CharField(max_length=50, default="", blank=True, null=True)
    Title = models.CharField(max_length=251, default="", blank=True, null=True)
    GovURL = models.CharField(max_length=500, default="", blank=True, null=True)
    
    def __str__(self):
        if self.Government_obj.GovernmentNumber:
            return 'COMMITTEE:(%s-%s) %s' %(self.Government_obj.GovernmentNumber, self.Government_obj.SessionNumber, self.Title)
        else:
            return 'COMMITTEE:(unknownGov) %s' %(self.Title)
    
    class Meta:
        ordering = ['-created', 'Code']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Committee', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'Chair_obj': None, 'members': None, 'Code': '', 'Title': '', 'GovURL': '', 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','Title','Government_obj.GovernmentNumber','DateTime','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','Title','Government_obj','DateTime']

    def get_absolute_url(self):
        if self.Chamber == 'Senate':
            pref = 'senate-committee'
        elif self.Chamber == 'House of Commons' or self.Chamber == 'House':
            pref = 'house-committee'
        else:   
            pref = 'committee'
        if self.Government_obj:
            govNum = self.Government_obj.GovernmentNumber
            govSess = self.Government_obj.SessionNumber
        else:
            govNum = '00'
            govSess = '00'
        return f"/{pref}/{govNum}/{govSess}/{self.Code}"

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self, share=share)
        elif not is_locked(self):
            compensate_save(self, Committee, *args, **kwargs)

    def delete(self):
        if not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        p.save(share=share)
        return p


class Motion(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Bill_obj = models.ForeignKey(Bill, blank=True, null=True, on_delete=models.SET_NULL)
    billCode = models.CharField(max_length=30, default="", blank=True, null=True)
    Person_obj = models.ForeignKey('legis.Person', blank=True, null=True, on_delete=models.PROTECT)
    result_data = models.JSONField(blank=True, null=True)
    GovUrl = models.URLField(null=True, blank=True)
    VoteNumber = models.IntegerField(blank=True, null=True) #DecisionDivisionNumber
    Subject = models.CharField(max_length=500, default="", blank=True, null=True)
    MotionText = models.TextField(blank=True, null=True)
    DecisionType = models.CharField(max_length=750, default="", blank=True, null=True)
    Yeas = models.IntegerField(default=0, blank=True, null=True)
    Nays = models.IntegerField(default=0, blank=True, null=True)
    Present = models.IntegerField(blank=True, null=True)
    Absent = models.IntegerField(blank=True, null=True)
    TotalVotes = models.IntegerField(default=0, blank=True, null=True)
    Result = models.CharField(max_length=200, default="", blank=True, null=True)
    is_official = models.BooleanField(default=None, blank=True, null=True)
    
    def __str__(self):
        if self.Government_obj:
            return 'MOTION:(%s-%s) %s/%s' %(self.Government_obj.GovernmentNumber, self.Government_obj.SessionNumber, self.VoteNumber, self.Result)
        else:
            return 'MOTION:(%s-%s) %s/%s' %('unknownGov', 'unknownGov', self.VoteNumber, self.Result)

    def get_absolute_url(self):
        if self.Government_obj:
            return "/%s/%s-motion/%s/%s/%s" %(self.Country_obj.Name.lower(), self.Chamber.lower(), self.Government_obj.GovernmentNumber, self.Government_obj.SessionNumber, self.VoteNumber)
        else:
            return "/%s/%s-motion/%s/%s/%s" %(self.Country_obj.Name.lower(), self.Chamber.lower(), 'unknownGov', 'unknownGov', self.VoteNumber)

    class Meta:
        ordering = ["-DateTime", '-VoteNumber', '-created']

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Motion', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'Bill_obj': None, 'billCode': '', 'Person_obj': None, 'result_data': None, 'GovUrl': None, 'VoteNumber': None, 'Subject': '', 'MotionText': None, 'DecisionType': '', 'Yeas': 0, 'Nays': 0, 'Present': None, 'Absent': None, 'TotalVotes': 0, 'Result': '', 'is_official': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','VoteNumber','Person_obj','Government_obj','Chamber','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','DateTime','VoteNumber','Result','Subject','MotionText','billCode']

    def required_for_validation(self):
        return ['Result','TotalVotes','Government_obj.signed']

    def save(self, share=False, *args, **kwargs):
        if self.DecisionType and len(self.DecisionType) > 750:
            self.DecisionType = str(self.DecisionType)[:750]
        if self.Subject and len(self.Subject) > 500:
            self.Subject = str(self.Subject)[:500]
        if self.id is None:
            if self.VoteNumber and isinstance(self.VoteNumber, str):
                self.VoteNumber = int(self.VoteNumber)
            self = initial_save(self, share=share)
        elif not is_locked(self):
            compensate_save(self, Motion, *args, **kwargs)

    def return_votes(self):
        try:
            return self.result_data['Votes']
        except:
            return []
        
    def return_parties(self):
        try:
            return self.result_data['Parties']
        except:
            return []
    
    def delete(self):
        if not is_locked(self):
            for v in RepVote.objects.filter(Motion_obj=self):
                v.delete()
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        if not p.keyword_array:
            p.keyword_array = []
            p.keyword_array.append(self.Subject.lower())
        p.save(share=share)
        return p

class RepVote(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Motion_obj = models.ForeignKey(Motion, blank=True, null=True, on_delete=models.PROTECT)
    Person_obj = models.ForeignKey('legis.Person', blank=True, null=True, on_delete=models.PROTECT)
    Party_obj = models.ForeignKey('legis.Party', blank=True, null=True, on_delete=models.PROTECT)
    District_obj = models.ForeignKey('legis.District', related_name='%(class)s_district_obj', blank=True, null=True, on_delete=models.PROTECT)
    ConstituencyName = models.CharField(max_length=150, default="", blank=True, null=True)
    VoteValue = models.CharField(max_length=20, default="", blank=True, null=True)
    PersonFullName = models.CharField(max_length=100, default="", blank=True, null=True)
    ConstituencyProvStateName = models.CharField(max_length=100, default="", blank=True, null=True)
    CaucusName = models.CharField(max_length=50, default="", blank=True, null=True)
    IsVoteYea = models.CharField(max_length=10, default="", blank=True, null=True)
    IsVoteNay = models.CharField(max_length=10, default="", blank=True, null=True)
    IsVotePresent = models.CharField(max_length=10, default="", blank=True, null=True)
    IsVoteAbsent = models.CharField(max_length=10, default="", blank=True, null=True)
    PersonId = models.CharField(max_length=20, default="", blank=True, null=True)

    def __str__(self):
        return 'REPVOTE:voter-%s-%s-%s' %(self.VoteValue, self.PersonFullName, self.id)

    class Meta:
        ordering = ['PersonFullName', 'ConstituencyName', "-created"]
    
    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'RepVote', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'Motion_obj': None, 'Person_obj': None, 'Party_obj': None, 'District_obj': None, 'ConstituencyName': '', 'VoteValue': '', 'PersonFullName': '', 'ConstituencyProvStateName': '', 'CaucusName': '', 'IsVoteYea': '', 'IsVoteNay': '', 'IsVotePresent': '', 'IsVoteAbsent': '', 'PersonId': '', 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','Motion_obj','Person_obj','PersonFullName']

    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','PersonFullName','Motion_obj','VoteValue']

    def required_for_validation(self):
        return ['Motion_obj.signed']
    
    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self)
        elif not is_locked(self):
            compensate_save(self, RepVote, *args, **kwargs)

    def delete(self):
        if not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        p.save(share=share)
        return p


class Action(BaseModel):
    commitChain = models.CharField(max_length=50, default="Government", blank=True)
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    pointerId = models.CharField(max_length=100, db_index=True, default=None, null=True, blank=True)
    distinction = models.CharField(max_length=50, default=None, null=True, blank=True) # allows for unique id if DateTime, pointerId and type are repeated
    Data = models.JSONField(default=dict, blank=True, null=True)
    type = models.CharField(max_length=90, default=None, blank=True, null=True)
    Chamber = models.CharField(max_length=20, default=None, blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.PROTECT)
    Government_obj = models.ForeignKey('legis.Government', related_name='%(class)s_government_obj', blank=True, null=True, on_delete=models.SET_NULL)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    
    class Meta:
        ordering = ['-DateTime']

    def __str__(self):
        return f'Action:({self.type})-id:{self.id}-pointer:{self.pointerId}'

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Action', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'modlVer': 1, 'pointerId': None, 'distinction': None, 'Data': {}, 'type': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','pointerId','type','DateTime','distinction','Government_obj','Chamber','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','pointerId']

    def updateShare(self, obj):
        if 'shareData' not in self.Data:
            self.Data['shareData'] = []
        self.Data['shareData'].append(obj.id)
        self.save()

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self.distinction = str(self.distinction)[:50]
            self = initial_save(self)
        elif not is_locked(self):
            self.distinction = str(self.distinction)[:50]
            from utils.models import compensate_save
            compensate_save(self, Action, *args, **kwargs)

    def delete(self, force_delete=False):
        if force_delete or not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        if self.DateTime:
            p.DateTime = self.DateTime
        p.save(share=share)
        return p


class Election(LegisModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    type = models.CharField(max_length=25, default="", blank=True, null=True)
    gov_level = models.CharField(max_length=20, default=None, blank=True, null=True)
    District_obj = models.ForeignKey('legis.District', blank=True, null=True, on_delete=models.PROTECT)

    def __str__(self):
        return 'ELECTION:%s %s' %(self.Chamber, self.type)

    class Meta:
        ordering = ["-DateTime"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Election', 'networkChain': 'Region', 'commitChain': 'Government', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'Government_obj': None, 'DateTime': None, 'modlVer': 1, 'type': '', 'gov_level': None, 'District_obj': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','DateTime','gov_level','type','District_obj','Chamber','Region_obj','Country_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','DateTime','Region_obj']

    def get_absolute_url(self):
        return '/election/%s/%s/%s' %(self.Chamber, self.Government_obj.Country.Name, self.id)

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self, share=share)
        elif not is_locked(self):
            compensate_save(self, Election, *args, **kwargs)

    def delete(self):
        if not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        p.save(share=share)
        return p

class Party(ModifiableModel):
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Chamber = models.CharField(max_length=100, default="", blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.PROTECT)
    ProvState_obj = models.ForeignKey('posts.Region', related_name='%(class)s_provstate_obj', blank=True, null=True, on_delete=models.PROTECT)
    Name = models.CharField(max_length=100, default="", blank=True, null=True)
    AltName = models.CharField(max_length=100, default=None, blank=True, null=True)
    ShortName = models.CharField(max_length=100, default=None, blank=True, null=True)
    gov_level = models.CharField(max_length=20, default=None, blank=True, null=True)
    Leader = models.CharField(max_length=30, default=None, blank=True, null=True)
    Color = models.CharField(max_length=30, default="#808080")
    InfoLink = models.URLField(null=True, blank=True)
    LogoLink = models.URLField(null=True, blank=True)
    StartDate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    EndDate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    Website_array = ArrayField(models.CharField(max_length=50, default='', blank=True, null=True), size=10, null=True, blank=True)
    Wiki = models.URLField(null=True, blank=True)

    def __str__(self):
        return 'PARTY:%s-%s' %(self.Name, self.gov_level)

    class Meta:
        ordering = ['-proposed_modification', "Name"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Party', 'is_modifiable': True, 'networkChain': 'Region', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'lastUpdate': None, 'proposed_modification': None, 'modlVer': 1, 'Chamber': '', 'Region_obj': None, 'Country_obj': None, 'ProvState_obj': None, 'Name': '', 'AltName': None, 'ShortName': None, 'gov_level': None, 'Leader': None, 'Color': '#808080', 'InfoLink': None, 'LogoLink': None, 'StartDate': None, 'EndDate': None, 'Website_array': None, 'Wiki': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['Name','gov_level','Country_obj','Chamber']
        
    def no_sign_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) == 1:
            return ['proposed_modification']
        return []
    
    def update_data(self, share=False):
        self.signed = {}
        self.modlVer = self.latestVer
        self.lastUpdate = now_utc()
        self.save(share=share)

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            if self.Color == "#808080":
                self.Color = self.set_color()
            self = initial_save(self)
        elif not is_locked(self):
            compensate_save(self, Party, *args, **kwargs)

    def set_color(self):
        colorList = {
            'country' : {
                'Canada' : {
                    'Liberal' : '#ED2E38',
                    'Conservative' : '#002395',
                    'NDP' : '#FF5800',
                    'Bloc Québécois' : '#0088CE',
                    'Green Party' : '#427730',
                    'Progressive Senate Group' : '#ED2E38',
                    'Canadian Senators Group' : '#386B67',
                    'Independent Senators Group' : '#845B87',
                    'Conservative Party of Canada' : '#002395',
                },
                'USA' : {
                    'Republican' : '#D61F26',
                    'Democratic' : '#0044C8',
                    'Libertarian' : '#FED000',
                    'Green' : '#427730',
                }
            },
            'Republican' : '#D61F26',
            'Democratic' : '#0044C8',
            'Libertarian' : '#FED000',
            'Green' : '#427730',
        }
        try:
            return colorList[self.Region_obj.modelType][self.Region_obj.Name][self.Name]
        except:
            try:
                return colorList[self.Region_obj.modelType][self.Name]
            except:
                try:
                    return colorList[self.Name]
                except:
                    return self.Color

    def boot(self, share=False):
        p = new_post(self)
        if not p.keyword_array:
            p.keyword_array = []
            p.keyword_array.append(self.Name.lower())
        if self.AltName and self.AltName.lower() not in p.keyword_array:
            p.keyword_array.append(self.AltName.lower())
        p.save(share=share)
        return p

    def delete(self):
        pass

    def fillout(self): # not used
        print('-fillout - party: %s' %(self.Name))
        try:
            if not self.Leader:
                print('opening browser')
                chrome_options = Options()
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument("--headless")
                driver = webdriver.Chrome(options=chrome_options)
                caps = DesiredCapabilities().CHROME
                caps["pageLoadStrategy"] = "normal"  #  Waits for full page load
                # caps["pageLoadStrategy"] = "eager"   # Do not wait for full page load
                driver = webdriver.Chrome(desired_capabilities=caps, options=chrome_options)
                # url= 'https://lop.parl.ca/sites/ParlInfo/default/en_CA/Parties/Profile?partyId=15161'
                print(self.InfoLink)
                driver.get(self.InfoLink)
                element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="gridPartyLeaders"]/div/div[5]'))
                WebDriverWait(driver, 15).until(element_present)
                # time.sleep(1)
                try:
                    div = driver.find_element(By.ID, 'PartyPic')
                    try:
                        img = div.find_element(By.CSS_SELECTOR, 'img').get_attribute('src')
                        if 'LogoNA' not in img:
                            self.LogoLink = img
                    except:
                        self.LogoLink = None
                    try:
                        div = driver.find_element(By.ID, 'PartyInfo')
                        h = div.find_element(By.CSS_SELECTOR, 'h2').text
                        a = h.find('(')
                        b = h[a:].find(' - ')
                        date = h[a:a+b]
                        date_time = datetime.datetime.strptime(date, '(%Y-%m-%d')
                        self.start_date = date_time
                    except:
                        pass
                    info = div.find_elements(By.CSS_SELECTOR, 'p')
                    website = div.find_element(By.CSS_SELECTOR, 'tr').find_element(By.CSS_SELECTOR, 'a').get_attribute('href')
                    self.Websites_array = website
                except Exception as e:
                    prnt('party fillout err2', str(e))
                driver.close()
                # wikipedia
            if not self.Wikipedia:
                name = '%s Canada' %(self.Name)
                title = wikipedia.search(name)[0].replace(' ', '_')
                self.Wikipedia = 'https://en.wikipedia.org/wiki/' + title
                if not self.LogoLink:
                    r = requests.get('https://en.wikipedia.org/wiki/' + title)
                    soup = BeautifulSoup(r.content, 'html.parser')
                    td = soup.find('td', {'class':'logo'})
                    img = td.find('img')['src']
                    self.LogoLink = img
                    
            self.save()
        except Exception as e:
            prnt('party fillout err2', str(e))
            self.save()

class Person(BaseModel):
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    GovIden = models.CharField(max_length=50, blank=True, null=True)
    GovProfilePage = models.CharField(max_length=500, blank=True, null=True)
    Update_obj = models.ForeignKey('posts.Update', related_name='%(class)s_update_obj', blank=True, null=True, on_delete=models.SET_NULL)
    ImageFile_obj = models.ForeignKey('posts.ImageFile', related_name='%(class)s_imagefile_obj', blank=True, null=True, on_delete=models.SET_NULL)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.PROTECT)

    def __str__(self):
        if self.Country_obj and self.Country_obj.Name:
            return 'PERSON:%s-%s %s' %(self.id, self.GovIden, self.Country_obj.Name)
        else:
            return 'PERSON:%s-%s NoCountry' %(self.id, self.GovIden)

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Person', 'networkChain': 'Region', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'modlVer': 1, 'GovIden': None, 'GovProfilePage': None, 'Update_obj': None, 'ImageFile_obj': None, 'Region_obj': None, 'Country_obj': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','GovIden','Region_obj']

    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','Region_obj','GovIden']

    def no_sign_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['ImageFile_obj']

    def get_name(self, update_obj=None):
        if not update_obj:
            update_obj = self.Update_obj
        if update_obj:
            if 'Honorific' in update_obj.data:
                return '%s %s %s' %(update_obj.data['Honorific'], update_obj.data['FirstName'], update_obj.data['LastName'])
            else:
                return '%s %s' %(update_obj.data['FirstName'], update_obj.data['LastName'])
        else:
            return None

    def get_field(self, field, update_obj=None):
        update_obj = self.Update_obj
        if update_obj:
            if field in update_obj.data:
                return update_obj.data[field]
            if field == 'FullName' and 'FirstName' in update_obj.data and 'LastName' in update_obj.data:
                return self.get_name(update_obj)
        return None

    def get_image(self):
        if self.ImageFile_obj:
            return self.ImageFile_obj.get_image()
        return None

    class Meta:
        ordering = ["GovIden", 'Country_obj', 'id']

    def update_role(self, update_obj, role=None, current=False, data=None):
        # prnt('-update_role', update_obj, role)
        found = False
        if not update_obj.extra:
            update_obj.extra = {}
        if 'roles' not in update_obj.extra:
            update_obj.extra['roles'] = []
        if data:
            role = data['role']
            for r in update_obj.extra['roles']:
                if r['role'] == role:
                    r.update(data)
                    found = True
                    break
            if not found:
                update_obj.extra['roles'].append(data)
        else:
            for r in update_obj.extra['roles']:
                if r['role'] == role:
                    r['current'] = current
                    found = True
                    break
            if not found:
                update_obj.extra['roles'].append({'role':role, 'current':current})

    def get_absolute_url(self):
        if self.Update_obj:
            if self.GovIden:
                return "/profile/%s/%s_%s/%s" % (self.Region_obj.Name, self.Update_obj.data['FirstName'].replace(' ', '_'), self.Update_obj.data['LastName'].replace(' ', '_'), self.GovIden)
            else:
                return "/profile/%s/%s_%s/%s" % (self.Region_obj.Name, self.Update_obj.data['FirstName'].replace(' ', '_'), self.Update_obj.data['LastName'].replace(' ', '_'), self.id)
        else:
            if self.GovIden:
                return f"/profile/{self.GovIden}"
            else:
                return f"/profile/{self.id}"

    def upon_validation(self):
        create_keyphrases(self, create_person_trend=True)
        if not self.Update_obj:
            u = Update.objects.filter(pointerId=self.id, validated=True).order_by('-DateTime').first()
            if u:
                self.Update_obj = u
                self.save()

    def save(self, share=False, *args, **kwargs):
        # prntDebug('-saving person....',self.id)
        if self.id is None:
            if self.Country_obj and not self.Region_obj:
                self.Region_obj = self.Country_obj
            self = initial_save(self)
        else:
            compensate_save(self, Person, *args, **kwargs)

    def boot(self, share=False):
        p = new_post(self)
        if not p.keyword_array:
            p.keyword_array = []
        p.save()
        return p
    
    def delete(self):
        superDelete(self)
        

class District(ModifiableModel):
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    Chamber = models.CharField(max_length=100, default="", blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.PROTECT)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.PROTECT)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    Office_array = ArrayField(models.CharField(max_length=30, default='', blank=True, null=True), size=25, null=True, blank=True)
    nameType = models.CharField(max_length=100, default="", blank=True, null=True) # Riding, District, Ward
    Name = models.CharField(max_length=100, default="", blank=True, null=True)
    AltName = models.CharField(max_length=100, default="", blank=True, null=True)
    gov_level = models.CharField(max_length=100, default="", blank=True, null=True) # Federal, Provincial, State, Greater Municipal, Municipal
    ProvState_obj = models.ForeignKey('posts.Region', related_name='%(class)s_provstate_obj', blank=True, null=True, on_delete=models.PROTECT)
    Population = models.IntegerField(blank=True, null=True)
    StartDate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    MapLink = models.URLField(null=True, blank=True)
    InfoLink = models.URLField(null=True, blank=True)
    Info = models.TextField(blank=True, null=True)
    Wiki = models.URLField(null=True, blank=True)

    def __str__(self):
        if self.ProvState_obj:
            return 'DISTRICT:%s-%s/%s' %(self.Name, self.ProvState_obj.Name, self.Region_obj.Name)
        elif self.Region_obj:
            return 'DISTRICT:%s-%s' %(self.Name, self.Region_obj.Name)
        else:
            return 'DISTRICT:%s' %(self.Name)

    class Meta:
        ordering = ['-proposed_modification', "Name"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'District', 'is_modifiable': True, 'networkChain': 'Region', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'lastUpdate': None, 'proposed_modification': None, 'Chamber': '', 'Region_obj': None, 'Country_obj': None, 'modlVer': 1, 'Office_array': None, 'nameType': '', 'Name': '', 'AltName': '', 'gov_level': '', 'ProvState_obj': None, 'Population': None, 'StartDate': None, 'MapLink': None, 'InfoLink': None, 'Info': None, 'Wiki': None, 'signed': {}}

    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['Name','gov_level','Country_obj','ProvState_obj']
    
    def no_sign_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) == 1:
            return ['proposed_modification']
        return []
    
    def add_office(self, office_name):
        if not self.Office_array:
            self.Office_array = []
        if office_name not in self.Office_array:
            if office_name:
                self.Office_array.append(office_name)
            self.update_data()
            return True
        else:
            return False
    
    def update_data(self, share=False):
        self.signed = {}
        self.modlVer = self.latestVer
        self.lastUpdate = now_utc()
        self.save(share=share)

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            if not self.Region_obj:
                self.Region_obj = self.Country_obj
            self = initial_save(self, share=share)
        elif not is_locked(self):
            compensate_save(self, District, *args, **kwargs)

    def boot(self, share=False):
        p = new_post(self)
        p.save()
        return p

    def delete(self):
        if not is_locked(self):
            superDelete(self)

    def fillout(self): # not used
        prnt('-fillout - Riding: %s' %(self.Name))
        try:
            if not self.map_link:
                chrome_options = Options()
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument("--headless")
                driver = webdriver.Chrome(options=chrome_options)
                caps = DesiredCapabilities().CHROME
                caps["pageLoadStrategy"] = "normal"  #  Waits for full page load
                # caps["pageLoadStrategy"] = "eager"   # Do not wait for full page load
                driver = webdriver.Chrome(desired_capabilities=caps, options=chrome_options)
                prnt(self.parlinfo_link)
                driver.get(self.parlinfo_link)
                element_present = EC.presence_of_element_located((By.XPATH, '//*[@id="RidingPic"]'))
                WebDriverWait(driver, 10).until(element_present)
                div = driver.find_element(By.ID, 'RidingPic')
                img = div.find_element(By.CSS_SELECTOR, 'img').get_attribute('src')
                self.map_link = img
                div = driver.find_element(By.ID, 'RidingInfo')
                h = div.find_element(By.CSS_SELECTOR, 'h2').text
                a = h.find('(')
                b = h[a:].find(' - ')
                date = h[a:a+b]
                try:
                    date_time = datetime.datetime.strptime(date, '(%Y-%m-%d')
                    self.StartDate = date_time
                except:
                    try:
                        date_time = datetime.datetime.strptime(date, '(%Y-%m')
                        self.StartDate = date_time
                    except:
                        pass
                text = driver.find_element(By.ID, 'RidingNotes').text
                self.info = text
                driver.close()
                # wikipedia
            if not self.wikipedia:
                name = '%s %s federal electoral district' %(self.Name, self.Region_obj.Name)
                title = wikipedia.search(name)[0].replace(' ', '_')
                self.wikipedia = 'https://en.wikipedia.org/wiki/' + title
                
            self.save()
        except Exception as e:
            prnt('district fillout err',str(e))
            self.save()

