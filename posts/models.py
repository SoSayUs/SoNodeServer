from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.fields import ArrayField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from urllib.parse import urljoin

from utils.models import (
    BinaryBase62Field, prnt, prntDebug, get_dynamic_model, has_method, is_obj_commit_valid, 
    now_utc, has_field, string_to_dt, initial_save, save_mutable_fields, 
    find_or_create_chain_from_object, baseline_time, safe_dt,
    get_operator_obj, is_locked, superDelete, get_pointer_type, get_timeData
    )
from utils.locked import sign_obj, hash_obj_id
from utils.utils import (
    get_plugin
)

import random
import pytz
import datetime
import decimal
from nltk.corpus import stopwords


model_prefixes = {'Post':'pst','Update':'upd','Spren':'spr','ImageFile':'img','Keyphrase':'key','KeyphraseTrend':'kytr','Region':'reg'}

class BaseModel(models.Model):
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    added_to_node = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    func = models.CharField(max_length=50, default=None, blank=True, null=True)
    CreatorNode_obj = models.ForeignKey('network.Node', blank=True, null=True, on_delete=models.PROTECT)
    validatorNodeId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    Validator_obj = models.ForeignKey('network.Validator', blank=True, null=True, on_delete=models.PROTECT)
    Block_obj = models.ForeignKey('network.Block', blank=True, null=True, on_delete=models.PROTECT)
    signed = models.JSONField(default=dict)
    
    class Meta:
        abstract = True


class ValidObjsQuerySet(models.QuerySet):
    def default_filter(self):
        return self.filter(proposed_modification=None)

class ValidObjsManager(models.Manager):
    def get_queryset(self):
        return ValidObjsQuerySet(self.model, using=self._db).default_filter()

    def all(self, *args, **kwargs):
        return self.get_queryset()

    def include_invalid(self):
        return super().get_queryset()
    
class ModifiableModel(BaseModel):
    is_modifiable = True
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    proposed_modification = models.CharField(max_length=200, default=None, blank=True, null=True) # only for script created models like District
    
    objects = models.Manager()
    valid_objects = ValidObjsManager()

    class Meta:
        abstract = True

    def propose_modification(self):
        prnt('-propose_modification',self)
        if self.Validator_obj and self.Validator_obj.is_valid:
            if self.id != None and not self.proposed_modification:
                mod = get_dynamic_model(self._meta.object_name, proposed_modification=self.id)
                from utils.models import super_sync, create_dynamic_model, save_sigs
                if not mod:
                    mod = create_dynamic_model(self._meta.object_name)
                from utils.locked import convert_to_dict
                mod, sigs = super_sync(mod, convert_to_dict(self), if_empty_fields=['created'], skip_fields=['Block_obj','Validator_obj','signed','CreatorNode_obj','validatorNodeId'])
                if not mod.proposed_modification:
                    mod.proposed_modification = self.id
                    mod.id = hash_obj_id(mod)
                if has_method(mod, 'update_data'):
                    mod.update_data()
                else:
                    mod.signed = {}
                    mod.modlVer = mod.latestVer
                    mod.lastUpdate = now_utc()
                    mod.save()
                save_sigs(sigs)
                prnt('new mod',mod.id,mod)
                return mod
        prnt('no mod')
        return self

    def committed_data_matches(self):
        return is_obj_commit_valid(self)

GLOBAL_EXCLUDE_FIELDS = {'objType','created','added_to_node','updated_on_node',
                        'modlVer','latestVer','networkChain','commitChain',
                        'is_modifiable','lastUpdate','proposed_modification','func'}
GLOBAL_SIGNING_FIELDS = {'signed'}

class LimitedFieldsQuerySet(models.QuerySet):
    def default(self):
        """Default: excludes global + model-specific fields"""
        return self._exclude_combined_fields()

    def exclude_fields(self, *fields):
        """Custom: excludes only specified fields"""
        return self._exclude_combined_fields(excluded=fields)
    
    def include_fields(self, *fields):
        """Custom: excludes only specified fields"""
        return self._exclude_combined_fields(included=fields)
    
    def sign_fields(self):
        signing_fields = {'signed'}
        return self._exclude_combined_fields(included=signing_fields)

    def all_fields(self):
        """Includes all fields (no exclusions)"""
        return self

    def _exclude_combined_fields(self, excluded=(), include=()):
        model_excludes = getattr(self.model._meta, 'exclude_fields_by_default', set())
        combined_excludes = GLOBAL_EXCLUDE_FIELDS.union(model_excludes, set(excluded))
        combined_excludes -= set(include)

        all_fields = set(
            f.name for f in self.model._meta.get_fields()
            if f.concrete and not f.is_relation
        )
        public_fields = list(all_fields - combined_excludes)
        return self.only(*public_fields)


class LimitedFieldsManager(models.Manager):
    def get_queryset(self):
        return LimitedFieldsQuerySet(self.model, using=self._db).default()

    def default(self):
        return self.get_queryset().default()

    def exclude_fields(self, *fields):
        return self.get_queryset().exclude_fields(*fields)
    
    def include_fields(self, *fields):
        return self.get_queryset().include_fields(*fields)
    
    def sign_fields(self):
        return self.get_queryset().sign_fields()

    def all_fields(self):
        return self.get_queryset().all_fields()

# objects = LimitedFieldsManager()
# # Default behavior: excludes global + model-specific fields
# MyModel.objects.all()

# # Explicitly limited (same as default)
# MyModel.objects.only_public()

# # Include all fields (no exclusions)
# MyModel.objects.with_all_fields()

# # Custom: exclude only "email"
# MyModel.objects.exclude_fields('email')

# MyModel.objects.exclude_fields('email', include={'created'})

# # Fetch all fields if needed
# qs_all = MyModel.objects.with_all_fields().all()
# # Includes: name, email, sensitive_data, internal_notes
    

def get_latest_update(pointerId):
    return Update.objects.filter(pointerId=pointerId).order_by('-created').first()


def create_keyphrases(obj, create_person_trend=False):
    # prnt('-create keyphrase')
    from utils.models import skipwords
    from utils.locked import dt_to_string
    phrases = []
    terms = []
    if has_field(obj, 'Terms_array'):
        if obj.Terms_array:
            for t in obj.Terms_array:
                if t not in skipwords:
                    terms.append(t)
    if has_field(obj, 'Person_obj') and create_person_trend:
        if obj.Person_obj and obj.Person_obj.Update_obj:
            if has_field(obj, 'keyword_array'):
                if not obj.keyword_array:
                    obj.keyword_array = [] 
                if 'FullName' in obj.Person_obj.Update_obj.data and obj.Person_obj.Update_obj.data['FullName'] not in obj.keyword_array:
                    obj.keyword_array.append(obj.Person_obj.Update_obj.data['FullName'])
            if obj.Person_obj.Update_obj.data['FullName'] not in skipwords:
                terms.append(obj.Person_obj.Update_obj.data['FullName'])
    if has_field(obj, 'keyword_array'):
        if obj.keyword_array:
            for t in obj.keyword_array:
                if t not in skipwords:
                    terms.append(t)
    if has_field(obj, 'DateTime') and obj.DateTime:
        dt = obj.DateTime
    elif has_field(obj, 'Started') and obj.Started:
        dt = obj.Started
    elif has_field(obj, 'created') and obj.created:
        dt = obj.created
    else:
        dt = now_utc()

    for t in terms:
        if t:
            keyphrase = Keyphrase.objects.filter(key=t[:300]).first()
            if not keyphrase:
                keyphrase = Keyphrase(key=t[:300])
                keyphrase.created = dt

            phraseData = {'obj_id':obj.id, 'Region':obj.Region_obj.id, 'Country':obj.Country_obj.id, 'Chamber':obj.Chamber, 'DateTime':dt_to_string(dt)}
            if phraseData not in keyphrase.pointer_array:
                if not keyphrase.first_occured or keyphrase.first_occured > dt:
                    keyphrase.first_occured = dt
                if keyphrase.pointer_array and len(keyphrase.pointer_array) >= 10000:
                    keyphrase.pointer_array.pop(0)
                keyphrase.pointer_array.append(phraseData)

                keyphrase.lastUpdate = now_utc()
                if keyphrase.last_occured and keyphrase.last_occured > dt:
                    pass
                else:
                    keyphrase.last_occured = dt
                keyphrase.save()
                keyphrase.set_trend()

def get_keywords(obj, text, numOfKeys=7):
    prnt('-get keyowrds')
    from utils.models import skipwords
    if len(text.strip().split(' ')) > 20:
        import re
        text = re.sub(r'\s+', ' ', text)  # Remove extra whitespace
        text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
        text = text.lower().strip()
        start_time = datetime.datetime.now()
        if obj._meta.object_name == 'Statement':
            statement = text
            text = ''
            if obj.OrderOfBusiness:
                text = text + obj.OrderOfBusiness + '\n'
            if obj.SubjectOfBusiness:
                text = text + obj.SubjectOfBusiness + '\n'
            text = text + statement
        try:
            import yake
            try:
                from spacy.lang.en.stop_words import STOP_WORDS
                spacy_stopwords = STOP_WORDS
            except Exception as e:
                prnt('keyowrds yake',str(e))
                spacy_stopwords = set()
                try:
                    import spacy

                    nlp = spacy.load("en_core_web_sm")
                    spacy_stopwords = nlp.Defaults.stop_words
                except Exception as e:
                    prnt('keyowrds spacy',str(e))

            try:
                try:
                    from nltk.corpus import stopwords
                    import nltk
                    nltk_stopwords = set(stopwords.words("english"))
                except:
                    from nltk.corpus import stopwords
                    import nltk
                    nltk.download("stopwords") # only needs to run the first time
                    nltk_stopwords = set(stopwords.words("english"))
            except Exception as e:
                prnt('fail keyowrkds nltk',str(e))
                nltk_stopwords = set()

            stop_w = set(skipwords)
            final_stopwords = nltk_stopwords | stop_w | spacy_stopwords
            
            def extract_keywords(text, n=3, top_n=6):
                kw_extractor = yake.KeywordExtractor(n=n, top=top_n, stopwords=final_stopwords)
                keywords = [kw[0] for kw in kw_extractor.extract_keywords(text)]
                return keywords

            spares = {}
            obj.keyword_array = []
            x = extract_keywords(text, n=5, top_n=2)
            n = 0
            terms = ''
            for i in x:
                if i not in stop_w and i not in obj.keyword_array and n < numOfKeys and not i.replace(' ','').isnumeric():
                    obj.keyword_array.append(i)
                    n += 1
                    terms = terms + i + ' '
            x = extract_keywords(text, n=4, top_n=2)
            for i in x:
                if i not in obj.keyword_array and i not in stop_w and i not in obj.keyword_array and n < numOfKeys and not i.replace(' ','').isnumeric():
                    obj.keyword_array.append(i)
                    n += 1
                    terms = terms + i + ' '
            x = extract_keywords(text, n=2, top_n=3)
            for i in x:
                if i not in stop_w and i not in obj.keyword_array and n < numOfKeys and not i.replace(' ','').isnumeric():
                    obj.keyword_array.append(i)
                    n += 1
                    terms = terms + i + ' '
            x = extract_keywords(text, n=1, top_n=7)
            for i in x:
                if i not in stop_w and not i.isnumeric():
                    if i in str(terms):
                        if i in spares:
                            spares[i] += 1
                        else:
                            spares[i] = 1
                    elif n < numOfKeys:
                        obj.keyword_array.append(i)
                        stop_w.add(i)
                        n += 1
            if spares:
                prnt('spares',spares)
            
        except Exception as e:
            prnt('get_keywords fail', str(e))
        finish_time = datetime.datetime.now() - start_time
        prnt('keywords time:',finish_time)
    return obj


def get_point_value(post):
    if post.total_yeas > 1000:
        score = 0.042 # ~1hr per 1000 upvotes
    elif post.total_yeas > 500:
        score = 0.417 # ~1hr per 100 upvotes
    elif post.total_yeas > 75:
        score = 1.04 # ~1hr per 40 upvotes
    elif post.total_yeas > 10:
        score = 4.166 # ~1hr per 10 upvotes
    else:
        score = 41.66 # ~1hr added to rank per upvote for first 10 votes
    return score

def scoreMe(post, save_item=True):
    prnt('-scoreMe',post,save_item)
    if post.randomizer == 0:
        post.randomizer = random.randint(1,333) #used in algorithim to reduce number of hansardItems and mix up content by up to 8hrs -- not used anymore
    baseline = baseline_time()
    try:
        t = post.DateTime - baseline
    except Exception as e:
        # prnt(str(e))
        t = post.DateTime - baseline.replace(tzinfo=pytz.UTC)
    secs = t.seconds * (1000 / 86400) # converts 24hrs in seconds to 1000, so there isnt' a big jump in rank numbers at the end of the day
    r = ((t.days * 1000) + secs)  #1000 - 1 day == 1000 on rank scale, 1 minute = 0.694 rank score
    post = post.tally_votes()
    score = get_point_value(post)
    post.rank = decimal.Decimal(r) + decimal.Decimal((post.total_yeas*score))
    post.verifiedRank = decimal.Decimal(r) + decimal.Decimal((post.total_verified_yeas*score))
    if save_item:
        post.save()



subRegions = ['ProvState', 'Country', 'Region', 'Continent', 'Province', 'State', 'County', 'City', 'Ward']


def new_post(obj):
    prnt('-new_post()')
    p = Post.all_objects.filter(pointerId=obj.id).first()
    if not p or not p.get_pointer(set_pointer=False):
        if not p:
            p = Post(pointerId=obj.id)

        if has_field(obj, 'DateTime') and obj.DateTime:
            p.DateTime = obj.DateTime
        elif has_field(obj, 'Started') and obj.Started:
            p.DateTime = obj.Started
        elif has_field(obj, 'created') and obj.created:
            p.DateTime = obj.created

        if has_field(obj, 'created') and obj.created:
            p.created = obj.created

        p.pointerId = obj.id
        p.pointerType = obj._meta.object_name
        pointer, p = p.set_pointer(do_save=False, return_self=True)
        p.keyword_array = []

        if has_field(obj, 'Country_obj'):
            p.Country_obj = obj.Country_obj
        if has_field(obj, 'Government_obj') and obj.Government_obj:
            p.Government_obj = obj.Government_obj
            p.filters['gov_level'] = obj.Government_obj.gov_level
        elif has_field(obj, 'objType') and obj._meta.object_name == 'Government':
            p.Government_obj = obj
            p.filters['gov_level'] = obj.gov_level
        if has_field(obj, 'Chamber'):
            p.filters['Chamber'] = obj.Chamber
        if has_field(obj, 'Region_obj'):
            p.Region_obj = obj.Region_obj
        if not has_field(obj, 'networkChain'):
            p.blockId = 'N/A'
        prnt('return p 1')
        return p
    prnt('return p 2')
    return p

def find_post(obj):
    p = Post.all_objects.filter(pointerId=obj.id).first()
    if not p:
        try:
            p = Archive.objects.filter(pointerId=obj.id).first()
        except:
            p = None
    return p

def update_post(obj=None, p=None, save_p=True, update=None):
    updated_fields = []
    if obj and has_method(obj, 'boot') or p and p.pointerId:
        if obj and not p:
            p = Post.all_objects.filter(pointerId=obj.id).first()
        elif p and not obj:
            obj = p.get_pointer() 
        if not p or not p.get_pointer(set_pointer=False):
            obj.boot()
        else:
            dt = None
            if has_field(obj, 'DateTime'):  
                dt = obj.DateTime
            elif has_field(obj, 'created'):
                dt = obj.created
            if dt and p.DateTime != dt:
                p.DateTime = dt
                updated_fields.append('DateTime')
            elif has_field(obj, 'created') and obj.created:
                if not p.DateTime or p.DateTime < obj.created:
                    p.DateTime = obj.created
                    updated_fields.append('DateTime')
            if has_field(obj, 'created'):
                if not p.created or p.created != obj.created:
                    p.created = obj.created
                    updated_fields.append('created')
            if update and update != p.Update_obj:
                if not p.Update_obj or safe_dt(update.created) > safe_dt(p.Update_obj.created):
                    returned_post = update.sync_with_post(post=p, pointer=obj, do_save=False)
                    if returned_post and isinstance(returned_post, models.Model) and returned_post._meta.object_name == 'Post':
                        p = returned_post
                        updated_fields.append('Update_obj')
                        updated_fields.append('filters')
                        updated_fields.append('keyword_array')
                        if 'DateTime' not in updated_fields:
                            updated_fields.append('DateTime')

            if p.Update_obj:
                if not p.DateTime or not dt or p.Update_obj.DateTime and safe_dt(p.Update_obj.DateTime) > dt:
                    p.DateTime = p.Update_obj.DateTime
                    if 'DateTime' not in updated_fields:
                        updated_fields.append('DateTime')

            if has_field(obj, 'keyword_array') and obj.keyword_array:
                for i in obj.keyword_array[:20]:
                    if i not in p.keyword_array:
                        p.keyword_array.append(i)
                        if 'keyword_array' not in updated_fields:
                            updated_fields.append('keyword_array')
            if has_field(obj, 'Country_obj') and p.Country_obj != obj.Country_obj:
                p.Country_obj = obj.Country_obj
                updated_fields.append('Country_obj')
            if has_field(obj, 'Government_obj') and obj.Government_obj:
                if p.Government_obj != obj.Government_obj:
                    p.Government_obj = obj.Government_obj
                    updated_fields.append('Government_obj')
                if has_field(obj, 'gov_level') and p.gov_level != obj.gov_level:
                    p.gov_level = obj.Government_obj.gov_level
                    updated_fields.append('gov_level')
            elif has_field(obj, 'objType') and obj._meta.object_name == 'Government' and has_field(obj, 'gov_level') and p.gov_level != obj.gov_level:
                p.gov_level = obj.gov_level
                updated_fields.append('gov_level')
            if has_field(obj, 'Chamber') and p.Chamber != obj.Chamber:
                p.Chamber = obj.Chamber
                updated_fields.append('Chamber')
            if has_field(obj, 'Region_obj') and p.Region_obj != obj.Region_obj:
                p.Region_obj = obj.Region_obj
                updated_fields.append('Region_obj')
            if not has_field(obj, 'networkChain') and p.blockId != 'N/A':
                p.blockId = 'N/A'
                updated_fields.append('blockId')
            if save_p:
                p.save()
    return p, updated_fields

    
class SupportedObjsQuerySet(models.QuerySet):
    def default_filter(self):
        return self.filter(is_supported=True)

class SupportedObjsManager(models.Manager):
    def get_queryset(self):
        return SupportedObjsQuerySet(self.model, using=self._db).default_filter()

    def all(self, *args, **kwargs):
        return self.get_queryset()

    def include_unsupported(self):
        return super().get_queryset()
    

class Region(BaseModel):
    networkChain = models.CharField(max_length=50, default="Region", blank=True)
    commitChain = models.CharField(max_length=50, default="ParentRegion", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    ParentRegion_obj = models.ForeignKey('posts.Region', blank=True, null=True, on_delete=models.SET_NULL)
    nameType = models.CharField(max_length=20, default="Country", blank=True) # Continent, Country, Province, State, Territory, County, City, Ward - modifiable/user facing
    Name = models.CharField(max_length=100, default="", blank=True)
    AbbrName = models.CharField(max_length=10, default=None, blank=True, null=True)
    FullName = models.CharField(max_length=100, default=None, blank=True, null=True)
    ImgLinks = models.JSONField(default=None, blank=True, null=True)
    timezone = models.CharField(max_length=20, default="US/Eastern", null=True, blank=True)
    Wiki = models.URLField(default=None, null=True, blank=True)
    is_supported = models.BooleanField(default=False)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    data = models.JSONField(default=None, blank=True, null=True)

    objects = models.Manager()
    supported_objects = SupportedObjsManager()

    def __str__(self):
        return 'REGION:%s/%s' %(self.Name, self.nameType)
    
    class Meta:
        ordering = ['Name', "created"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Region', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'networkChain': 'Region', 'commitChain': 'ParentRegion', 'modlVer': 1, 'ParentRegion_obj': None, 'nameType': 'Country', 'Name': '', 'AbbrName': None, 'FullName': None, 'ImgLinks': None, 'timezone': 'US/Eastern', 'Wiki': None, 'is_supported': False, 'lastUpdate': None, 'data': None, 'signed': {}}
            
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','Name','ParentRegion_obj','nameType']

    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['ParentRegion_obj','Name','nameType']
        
    def lowerName(self):
        return self.Name.lower()

    def initialize(self):
        self.created = now_utc()
        if self.commitChain == 'ParentRegion' and self.ParentRegion_obj:
            self.commitChain = self.ParentRegion_obj.id
        
        return self

    def save(self, sig=None, share=False, *args, **kwargs):
        if self.id is None:
            self = initial_save(self)
        elif not is_locked(self):
            save_mutable_fields(self, sig=sig, *args, **kwargs)

    def boot(self):
        prnt('-boot',self)
        network_chain, self, commit_chain = find_or_create_chain_from_object(self)
        prnt('network_chain',network_chain)
        prnt('commit_chain',commit_chain)
        self.save()
        network_chain.add_item_to_queue(self)

    def delete(self):
        pass


class Keyphrase(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    key = models.CharField(max_length=1000, default="", blank=True, null=True)
    pointer_array = ArrayField(models.JSONField(default=dict, blank=True, null=True), size=10000, null=True, blank=True, default=list)
    last_occured = models.DateTimeField(auto_now=False, auto_now_add=False, blank=False, null=True)
    first_occured = models.DateTimeField(auto_now=False, auto_now_add=False, blank=False, null=True)

    class Meta:
        ordering = ['-last_occured']
    
    def __str__(self):
        return 'KEYPHRASE:(%s)' %(self.key)
    
    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Keyphrase', 'modlVer': 1, 'id': None, 'lastUpdate': None, 'key': '', 'pointer_array': [], 'last_occured': None, 'first_occured': None}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','key']
    
    def set_score(self, trend):
        # prnt('-set_score')
        utc_tz = pytz.utc
        trend.total_occurences += 1
        start_date = '%s-%s-%s' %(trend.lastUpdate.year, trend.lastUpdate.month, trend.lastUpdate.day)
        day = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        day = utc_tz.localize(day)
        dayRange = datetime.datetime.strftime(day - datetime.timedelta(days=7), '%Y-%m-%d')
        sevenDays = datetime.datetime.strptime(dayRange, '%Y-%m-%d')
        sevenDays = utc_tz.localize(sevenDays)
        occurences = 0
        for i in self.pointer_array:
            if i['Chamber'] == trend.Chamber and i['Country'] == trend.Country_obj.id and string_to_dt(i['DateTime']) >= sevenDays and string_to_dt(i['DateTime']) <= self.last_occured:
                occurences += 1
        trend.recent_occurences = occurences
        settime = datetime.datetime(2022, 10, 23, 1, 0).replace(tzinfo=pytz.UTC)
        t = trend.lastUpdate - settime
        secs = t.seconds * (12 / 86400) # converts 24hrs in seconds to 12
        r = ((t.days * 12) + secs) # 24 hour bump == 12 recent_occurences over 7 days
        trend.trend_score = r + trend.recent_occurences
        trend.save()

    def set_trend(self, pos=-1):
        # prnt('-set_trend')
        from utils.models import skipwords
        if self.key and not self.key.startswith('*') and self.key not in skipwords and len(self.key) >= 4:
            trend = KeyphraseTrend.objects.filter(Chamber=self.pointer_array[pos]['Chamber'], Country_obj__id=self.pointer_array[pos]['Country'], Region_obj__id=self.pointer_array[pos]['Region'], key__iexact=self.key[:300]).first()
            if trend:
                if self.pointer_array[pos] in trend.pointer_array:
                    return 
            else:
                trend = KeyphraseTrend(Chamber=self.pointer_array[pos]['Chamber'], Country_obj_id=self.pointer_array[pos]['Country'], Region_obj_id=self.pointer_array[pos]['Region'], key=self.key[:300])
            trend.lastUpdate = now_utc()
            if trend.pointer_array and len(trend.pointer_array) >= 10000:
                trend.pointer_array.pop(0)
            trend.pointer_array.append(self.pointer_array[pos])
            trend.save()
            self.set_score(trend)
        return

    def save(self, share=False, *args, **kwargs):
        # prnt('-keyphrase save')
        if self.id is None:
            self.modlVer = self.latestVer
            self.id = hash_obj_id(self)
        super(Keyphrase, self).save(*args, **kwargs)
    
    def delete(self):
        for k in KeyphraseTrend.objects.filter(key=self.key):
            k.delete()
        super(Keyphrase, self).delete()

class KeyphraseTrend(models.Model):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=True, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    Chamber = models.CharField(max_length=20, default=None, blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.CASCADE)
    lastUpdate = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    pointer_array = ArrayField(models.JSONField(default=dict, blank=True, null=True), size=10000, null=True, blank=True, default=list)
    key = models.CharField(max_length=300, default="", blank=True, null=True)
    total_occurences = models.IntegerField(default=0, blank=True, null=True)
    recent_occurences = models.IntegerField(default=0, blank=True, null=True)
    trend_score = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    class Meta:
        ordering = ['-trend_score', 'recent_occurences', 'total_occurences']
    
    def __str__(self):
        return 'KEYPHRASETREND:(%s/%s)' %(self.Chamber, self.key)

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'KeyphraseTrend', 'modlVer': 1, 'id': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'lastUpdate': None, 'pointer_array': [], 'key': '', 'total_occurences': 0, 'recent_occurences': 0, 'trend_score': 0.0}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','key','Chamber','Region_obj','Country_obj']
    
    def get_absolute_url(self):
        return "%s/topic/%s" %(self.Country_obj.Name, self.key)

    def save(self, share=False, *args, **kwargs):
        if self.id is None:
            self.modlVer = self.latestVer
            self.id = hash_obj_id(self)
        super(KeyphraseTrend, self).save(*args, **kwargs)
    


class Spren(BaseModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    networkChain = models.CharField(max_length=50, default="", blank=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    pointerKey = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, default=None)
    Pointer_obj = GenericForeignKey('pointerKey', 'pointerId')
    re = models.CharField(max_length=500, default="", blank=True, null=True)
    type = models.CharField(max_length=250, default="", blank=True, null=True)
    pointerType = models.CharField(max_length=250, default="", blank=True, null=True)
    data = models.JSONField(blank=True, null=True)
    extra = models.JSONField(blank=True, null=True)
    
    def __str__(self):
        return f'SPREN:{self.id}, {self.pointerId}'

    class Meta:
        ordering = ["-DateTime"]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Spren', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'modlVer': 1, 'networkChain': '', 'Region_obj': None, 'DateTime': None, 'pointerId': None, 'pointerKey': None, 're': '', 'type': '', 'pointerType': '', 'data': None, 'extra': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','pointerId','re','type','Region_obj']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash']

    def on_confirmation(self, obj=None):
        self.sync_with_post(do_save=True)
        return self

    def get_post(self):
        p = Post.all_objects.filter(Spren_obj=self).first()
        return p

    def sync_with_post(self, post=None, pointer=None, do_save=True):
        prnt('-sync_w_post',self)
        if not self.pointerType:
            prnt('sync skipped')
            return True
        if Post.all_objects.filter(pointerType=self.pointerType, Spren_obj=self).filter(Q(pointerId=self.pointerId)|Q(pointerId=self.re)|Q(pointerId=self.id)).exists():
            prnt('previously completed')
            return True
        post = Post.all_objects.filter(pointerType=self.pointerType).filter(Q(pointerId=self.pointerId)|Q(pointerId=self.re)|Q(pointerId=self.id)).first()
        if not post:
            pointer = self.Pointer_obj
            if not pointer:
                if self.pointerId and not self.pointerKey:
                    pointer = get_dynamic_model(self.pointerId, id=self.pointerId)
                    if pointer:
                        self.pointerKey = ContentType.objects.get_for_model(pointer)
                        self.save()
                if not pointer:
                    from utils.models import request_items, logMissing
                    fetch_result = request_items(requested_items=[self.pointerId], nodes=[self.CreatorNode_obj.id], return_updated_objs=True, downstream_worker=False)
                    prnt('fetch_result',fetch_result)
                    if fetch_result:
                        if isinstance(fetch_result, list):
                            try:
                                pointer = [i for i in fetch_result if i.id == self.pointerId]
                            except Exception as e:
                                prnt('update pointer fail 325', str(e))
                if not pointer:
                    logMissing(self.pointerId, reg=self.Region_obj.id, context={'update':self.id})
            
            post = Post.all_objects.filter(pointerType=self.pointerType).filter(Q(pointerId=self.pointerId)|Q(pointerId=self.re)|Q(pointerId=self.id)).first()
        prnt('post',post)
        if post:
            if post.Spren_obj != self and self.Validator_obj:
                if not post.Spren_obj or safe_dt(self.created) > safe_dt(post.Spren_obj.created):
                    prntDebug('syncing...')
                    post.Spren_obj = self
                    if do_save:
                        post.save()
                prnt('synced, do_save:',do_save)
                return True if do_save else post
        return False if do_save else post

    def list_spren_items(self, field):
        prnt('-list_spren_items',self.id,field)
        try:
            l = []
            for iden, text in self.data[field].items():
                l.append((iden, text))
            return l
        except Exception as e:
            prnt('list_spren_items err',str(e))
            return None

    def save(self, sig=None, share=False, *args, **kwargs):
        prnt('-start save spren',self.id)
        
        if self.id is None:
            if self.pointerId and not self.pointerKey:
                pointer = get_dynamic_model(self.pointerId, id=self.pointerId)
                self.pointerKey = ContentType.objects.get_for_model(pointer)
            elif self.pointerKey:
                pointer = self.Pointer_obj
                self.pointerId = pointer.id
            if has_field(pointer, 'DateTime') and pointer.DateTime:
                self.DateTime = pointer.DateTime
            elif has_field(pointer, 'lastUpdate') and pointer.lastUpdate:
                self.DateTime = pointer.lastUpdate
                
            try:
                self.Region_obj = pointer.Region_obj
            except:
                pass
            self.networkChain = pointer.networkChain
            self = initial_save(self)
        elif not is_locked(self) and save_mutable_fields(self, sig=sig, *args, **kwargs):
            prnt('done save spren',self.id)

    def delete(self):
        if not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        if not self.DateTime:
            self.DateTime = self.created
            self.save()
        p = new_post(self)
        p.save()
        prnt('saved spren post')
        return p

class GenericModel(BaseModel):
    networkChain = 'Region'
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    distinction = models.CharField(max_length=50, default=None, null=True, blank=True) # allows for unique id if DateTime, pointerId and type are repeated
    type = models.CharField(max_length=90, default=None, blank=True, null=True)

    Chamber = models.CharField(max_length=20, default=None, blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', blank=True, null=True, on_delete=models.CASCADE)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    data = models.JSONField(default=dict, blank=True, null=True)
    
    class Meta:
        ordering = ['-DateTime']

    def __str__(self):
        return f'GenericModel:({self.type})-id:{self.id}-pointer:{self.pointerId}'

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'GenericModel', 'networkChain': 'Region', 'id': '0', 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': '', 'Validator_obj': None, 'blockchainId': '', 'Block_obj': None, 'modlVer': version, 'pointerId': None, 'distinction': None, 'type': None, 'Chamber': None, 'Region_obj': None, 'Country_obj': None, 'DateTime': None, 'data': {}, 'signed': {}}

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
            compensate_save(self, GenericModel, *args, **kwargs)

    def delete(self, force_delete=False):
        if force_delete or not is_locked(self):
            superDelete(self)

    def boot(self, share=False):
        p = new_post(self)
        if self.DateTime:
            p.DateTime = self.DateTime
        p.save(share=share)
        return p


from django.core.files.storage import FileSystemStorage
class OverwriteStorage(FileSystemStorage):
    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return name

class ImageFile(BaseModel):
    networkChain = models.CharField(max_length=50, default="", blank=True)
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    source_url = models.URLField()
    file_path = models.CharField(max_length=50, default="", blank=True)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    pointerKey = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, default=None)
    Pointer_obj = GenericForeignKey('pointerKey', 'pointerId')
    pointerType = models.CharField(max_length=250, default="", blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    imageField = models.ImageField(upload_to="images/", storage=OverwriteStorage())
    
    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f'ImageFile:{self.id}-{self.imageField}'

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'ImageFile', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'networkChain': '', 'modlVer': 1, 'source_url': '', 'file_path': '', 'pointerId': None, 'pointerKey': None, 'pointerType': '', 'Region_obj': None, 'imageField': None, 'signed': {}}
    
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['imageField','source_url','file_path']
    
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','pointerId','source_url','file_path']

    def upon_validation(self):
        pointer = self.Pointer_obj
        if self.Validator_obj and pointer and has_field(pointer, 'ImageFile_obj'):
            if not pointer.ImageFile_obj or pointer.ImageFile_obj.created < self.created:
                pointer.ImageFile_obj = self
                pointer.save()

    def get_image(self):
        if self.imageField:
            base = f"https://{get_operator_obj('address')}/"
            return urljoin(base, self.imageField.url)
        return None
        
    def save(self, sig=None, share=False, *args, **kwargs):
        # prnt('-saving img:')
        if self.id is None:
            if not self.Pointer_obj and self.pointerId:
                pointer = get_dynamic_model(self.pointerId, id=self.pointerId)
                if pointer:
                    self.pointerKey = ContentType.objects.get_for_model(pointer)
                    self.pointerType = pointer._meta.object_name
            self = initial_save(self)
        elif not is_locked(self) and save_mutable_fields(self, sig=sig, *args, **kwargs):
            prnt('saved imageFile')

    def delete(self, force_delete=False):
        if force_delete or not is_locked(self):
            prnt('-delete imageFile',self.id)
            if self.imageField:
                self.imageField.delete(False)
            super(ImageFile, self).delete()



class UpdateQuerySet(models.QuerySet):
    def with_deferred_text(self):
        return self.defer('extra')

    def include_text(self):
        return self

class UpdateManager(models.Manager):
    def get_queryset(self):
        return UpdateQuerySet(self.model, using=self._db).with_deferred_text()

class ValidUpdateManager(UpdateManager):
    def get_queryset(self):
        return super().get_queryset().filter(validated=True)

    
class Update(BaseModel):
    latestVer = 1
    modlVer = models.IntegerField(default=latestVer)
    networkChain = models.CharField(max_length=50, default="", blank=True)
    validated = models.BooleanField(default=False, null=True, blank=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', blank=True, null=True, on_delete=models.CASCADE)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    pointerId = BinaryBase62Field(max_byte_length=30, db_index=True, null=True, blank=True)
    pointerKey = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, default=None)
    Pointer_obj = GenericForeignKey('pointerKey', 'pointerId')
    prevVersion = models.CharField(max_length=50, db_index=True, default="", blank=True)
    data = models.JSONField(default=dict, blank=True, null=True)
    extra = models.JSONField(blank=True, null=True)
    objects = UpdateManager()
    valid_objects = ValidUpdateManager()

    def __str__(self):
        return 'UPDATE:%s-%s' %(get_pointer_type(self.pointerId),self.id)

    class Meta:
        ordering = ["-created","-DateTime","pointerId"]
        indexes = [
            GinIndex(fields=['data'], name='gin_index_jsonb_path_ops', opclasses=['jsonb_path_ops']),
        ]

    def get_version_fields(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return {'objType': 'Update', 'id': None, 'created': None, 'func': None, 'CreatorNode_obj': None, 'validatorNodeId': None, 'Validator_obj': None, 'Block_obj': None, 'modlVer': 1, 'networkChain': '', 'validated': False, 'Region_obj': None, 'DateTime': None, 'pointerId': None, 'pointerKey': None, 'prevVersion': '', 'data': {}, 'extra': None, 'signed': {}}
        
    def get_hash_to_id(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['objType','pointerId','created','Region_obj']
        
    def commit_data(self, version=None):
        if not version:
            version = self.modlVer
        if int(version) >= 1:
            return ['hash','pointerId','created']

    def block_conditions(self):
        if self.validated:
            return True
        if self.validated == None:
            from utils.locked import validate_obj
            if validate_obj(obj=self, save_obj=True, verify_validator=True, update_pointer=False):
                self.on_confirmation()
                return True
        return False
    
    def on_confirmation(self, obj=None):
        self.sync_with_post(do_save=True)
        if not self.validated:
            self.validate(validator=None, save_self=False, verify_validator=True, opBlock_data={})
        return self

    skipFields = ['id', 'func', 'created', 'added_to_node', 'lastUpdate', 'modlVer', 'signed', 'updated_on_node', 'CreatorNode_obj', 'validatorNodeId', 'Validator_obj', 'Block_obj', 'Pointer_obj', 'validated']

    def create_next_version(self, obj=None):
        from network.models import round_time
        prnt('-create_next_version', obj)
        if not self.created:
            self.created=round_time(dt=now_utc(), dir='down', amount='hour') # obj can be updated once per hour, once validated is no longer updateable until next hour
        if obj:
            latest = Update.objects.filter(pointerId=obj.id, validated=True).first()
            if latest and safe_dt(latest.created) < safe_dt(self.created):
                prnt('latest 1',latest.id)
                fields = latest._meta.fields
                for f in fields:
                    if f.name not in self.skipFields:
                        attr = getattr(latest, f.name)
                        setattr(self, f.name, attr)
                self.prevVersion = latest.id
            else:
                latest = Update.objects.filter(pointerId=obj.id, created__gte=self.created).first()
                if latest:
                    prnt('latest 2',latest.id)
                    return latest
        else:
            latest = Update.objects.filter(pointerId=self.pointerId, validated=True).first()
            if latest and safe_dt(latest.created) < safe_dt(self.created):
                prnt('latest 3',latest.id)
                fields = latest._meta.fields
                for f in fields:
                    if f.name not in self.skipFields:
                        attr = getattr(latest, f.name)
                        setattr(self, f.name, attr)
                self.prevVersion = latest.id
            else:
                latest = Update.objects.filter(pointerId=self.pointerId, created__gte=self.created).first()
                if latest:
                    prnt('latest 4',latest.id)
                    return latest
        prnt('no latest update')
        return self

    def get_pointer(self):
        return self.Pointer_obj
        
    def verify_is_valid(self, use_assigned_val=False):
        from network.models import Validator, sigData_to_hash
        from utils.locked import verify_obj_to_data, get_node_assignment
        from utils.utils import get_plugin
        if use_assigned_val:
            v = self.Validator_obj
        else:
            v = Validator.objects.filter(data__has_key=self.id, is_valid=True).order_by('-created').first()
        if v:
            if self.id in v.data and v.data[self.id] == sigData_to_hash(self):
                if verify_obj_to_data(v, v):
                    creator_nodes, validator_nodes = get_node_assignment(dt=self.created, chainId=self.networkChain, plugin_id=get_plugin(self.networkChain, id=True), func=self.func, strings_only=True)
                    prnt(f'self.validatorNodeId:{self.validatorNodeId}, validator_nodes:{validator_nodes}')
                    if self.validatorNodeId in validator_nodes:
                        prnt('-verify_is_valid 1',self, True)
                        return True
        prnt('-verify_is_valid 2',self, False)
        return False


    def save_if_new(self, func=None, share=False):
        prnt('-save update if new', self.id)
        if not self.data:
            prnt('no data')
            return None, False
        match = False
        if self.id is None:
            latest = Update.valid_objects.filter(pointerId=self.pointerId, DateTime=self.DateTime).include_text().order_by('-created').first()
            if latest:
                prnt('latest',latest)
                from utils.locked import sort_for_sign
                if sort_for_sign(self.data) == sort_for_sign(latest.data) and sort_for_sign(self.extra) == sort_for_sign(latest.extra):
                    match = True
        else:
            latest = Update.valid_objects.exclude(id=self.id).filter(pointerId=self.pointerId, DateTime=self.DateTime).include_text().order_by('-created').first()
            if latest:
                prnt('latest',latest)
                from utils.locked import sort_for_sign
                if sort_for_sign(self.data) == sort_for_sign(latest.data) and sort_for_sign(self.extra) == sort_for_sign(latest.extra):
                    match = True
        if match and latest.validated:
            prnt('self, false')
            return self, False
        else:
            prnt('true2')
            self.save()
            return self, True

    def validate(self, validators=None, save_self=True, verify_validator=True, opBlock_data={}):
        prnt('-validate update', self.id)
        from utils.locked import validate_obj
        return validate_obj(obj=self, pointer=None, validators=validators, save_obj=save_self, update_pointer=False, verify_validator=verify_validator, add_to_queue=False, opBlock_data=opBlock_data)

    def sync_with_post(self, post=None, pointer=None, do_save=True):
        prnt('-sync_w_post',self)
        if Post.all_objects.filter(pointerId=self.pointerId, Update_obj=self).exists():
            prnt('previously completed')
            return True
        if not post:
            post = Post.all_objects.filter(pointerId=self.pointerId).first()
        if not post:
            prnt('no post yet')
            pointer = self.Pointer_obj
            if not pointer:
                if self.pointerId and not self.pointerKey:
                    pointer = get_dynamic_model(self.pointerId, id=self.pointerId)
                    if pointer:
                        self.pointerKey = ContentType.objects.get_for_model(pointer)
                        self.save()
                if not pointer:
                    from utils.models import request_items, logMissing
                    fetch_result = request_items(requested_items=[self.pointerId], nodes=[self.CreatorNode_obj.id], return_updated_objs=True, downstream_worker=False)
                    prnt('fetch_result',fetch_result)
                    if fetch_result:
                        if isinstance(fetch_result, list):
                            try:
                                pointer = [i for i in fetch_result if i.id == self.pointerId]
                            except Exception as e:
                                prnt('update pointer fail 325', str(e))
                if not pointer:
                    logMissing(self.pointerId, reg=self.Region_obj.id, context={'update':self.id})
                if pointer and has_field(pointer, 'Update_obj'):
                    if not pointer.Update_obj or pointer.Update_obj.created < self.created:
                        pointer.Update_obj = self
                        pointer.save()
            post = Post.all_objects.filter(pointerId=self.pointerId).first()
        prnt('post',post)
        if post:
            if post.Update_obj != self and self.Validator_obj:
                if not post.Update_obj or safe_dt(self.created) > safe_dt(post.Update_obj.created):
                    prntDebug('syncing...')
                    if post.Update_obj:
                        # add operator option to preserve/remove historical data
                        # post.Update_obj.log_deletion(data={'replaced_by':self.id})
                        pass
                    if 'Chamber' in self.data and self.data['Chamber']:
                        post.filters['Chamber'] = self.data['Chamber']
                    if 'gov_level' in self.data and self.data['gov_level']:
                        post.filters['gov_level'] = self.data['gov_level']
                    if 'has_text' in self.data and self.data['has_text']:
                        post.filters['has_text'] = self.data['has_text']
                    if 'Position' in self.data and self.data['Position']:
                        post.filters['Position'] = self.data['Position']
                    if 'LastName' in self.data and self.data['LastName']:
                        post.filters['LastName'] = self.data['LastName']
                    if 'FullName' in self.data and self.data['FullName'] not in post.keyword_array:
                        post.keyword_array.append(self.data['FullName'])
                    post.Update_obj = self
                    if self.DateTime:
                        post.DateTime = self.created
                    if do_save:
                        post.save()
                    if not pointer:
                        pointer = self.Pointer_obj
                    if has_method(pointer, 'new_update'):
                        try:
                            pointer.new_update(self)
                        except Exception as e:
                            prnt('meeting update fail:',str(e))
                    elif has_field(pointer, 'Update_obj'):
                        if not pointer.Update_obj or not pointer.Update_obj.validated or safe_dt(pointer.Update_obj.created) < safe_dt(self.created):
                            pointer.Update_obj = self
                            pointer.save()
                prnt('synced, do_save:',do_save)
                return True if do_save else post
                
        return False if do_save else post

    def save(self, sig=None, share=False, *args, **kwargs):
        prnt('-saveupdate',self.id)
        if self.id is None:
            if self.pointerId and not self.pointerKey:
                pointer = get_dynamic_model(self.pointerId, id=self.pointerId)
                self.pointerKey = ContentType.objects.get_for_model(pointer)
            elif self.pointerKey:
                pointer = self.Pointer_obj
                self.pointerId = pointer.id
            prnt('pointer',pointer)
            if has_field(pointer, 'DateTime') and pointer.DateTime:
                self.DateTime = pointer.DateTime
            elif has_field(pointer, 'lastUpdate') and pointer.lastUpdate:
                self.DateTime = pointer.lastUpdate
                
            try:
                self.Region_obj = pointer.Region_obj
            except:
                pass
            network_chain, item, commit_chain = find_or_create_chain_from_object(pointer)
            if commit_chain:
                self.networkChain = commit_chain.genesisId
            elif network_chain:
                self.networkChain = network_chain.genesisId
            self = initial_save(self)
        elif not is_locked(self) and save_mutable_fields(self, sig=sig, *args, **kwargs):
            prnt('done save u')
    
    def log_deletion(self, data={}):
        if self.validated:
            from datetime import timezone
            from network.models import EventLog, Blockchain
            from utils.models import get_self_node, round_time, get_latest_dataPacket
            self_node = get_self_node()
            now = now_utc()
            start_of_month = round_time(dt=now, dir='down', amount='month')
            delLog = EventLog.objects.filter(type='Deletion_Log', Node_obj=self_node, Region_obj=self.Region_obj, created__gte=start_of_month).first()
            if not delLog:
                delLog = EventLog(type='Deletion_Log', Node_obj=self_node, Region_obj=self.Region_obj, created__gte=start_of_month)
            if self.id not in delLog.data:
                jsonData = {'dt':now}
                for key in data:
                    jsonData[key] = data[key]
                delLog.data[self.id] = jsonData
                delLog = sign_obj(delLog)
                chain = Blockchain.objects.filter(genesisId=self.Region_obj.id).first()
                datapacket = get_latest_dataPacket(self)
                if datapacket:
                    datapacket.add_item_to_share(delLog)
        self.delete()

    def delete(self, force_delete=False):
        if force_delete or not is_locked(self):
            prnt('-delete update',self.id)
            super(Update, self).delete()



class ValidPostQuerySet(models.QuerySet):
    def default_filter(self):
        return self.filter(validated=True)

class ValidPostManager(models.Manager):
    def get_queryset(self):
        return ValidPostQuerySet(self.model, using=self._db).default_filter()

    def all(self, *args, **kwargs):
        return self.get_queryset()

    def include_invalid(self):
        return super().get_queryset()

class Post(models.Model):
    id = BinaryBase62Field(max_byte_length=30, primary_key=True, default=None)
    created = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    updated_on_node = models.DateTimeField(auto_now=True, auto_now_add=False, blank=True, null=True)
    networkChain = models.CharField(max_length=50, default="Plugin", blank=True)
    validated = models.BooleanField(default=False, null=True, blank=True)
    blockId = models.CharField(max_length=50, default=None, blank=True, null=True)
    Chamber = models.CharField(max_length=20, default=None, db_index=True, blank=True, null=True)
    Region_obj = models.ForeignKey('posts.Region', related_name='%(class)s_region_obj', db_index=True, blank=True, null=True, on_delete=models.CASCADE)
    Country_obj = models.ForeignKey('posts.Region', related_name='%(class)s_country_obj', db_index=True, blank=True, null=True, on_delete=models.CASCADE)
    Government_obj = models.ForeignKey('legis.Government', related_name='%(class)s_government_obj', blank=True, null=True, on_delete=models.SET_NULL)
    DateTime = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
    gov_level = models.CharField(max_length=250, default="", blank=True, null=True)
    filters = models.JSONField(default=dict, blank=True, null=True)
    pointerId = BinaryBase62Field(max_byte_length=30, null=True, blank=True)
    pointerType = models.CharField(max_length=50, default="", db_index=True)
    pointerKey = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, default=None)
    Pointer_obj = GenericForeignKey('pointerKey', 'pointerId')
    Update_obj = models.ForeignKey('posts.Update', blank=True, null=True, on_delete=models.SET_NULL)
    Spren_obj = models.ForeignKey(Spren, blank=True, null=True, on_delete=models.SET_NULL)
    Plugin_obj = models.ForeignKey('network.Plugin', blank=True, null=True, on_delete=models.PROTECT)

    rank = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    verifiedRank = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    randomizer = models.IntegerField(blank=True, null=True) 
    keyword_array = ArrayField(models.CharField(max_length=200, default='{default}'), size=20, blank=True, null=True)
    total_votes = models.IntegerField(blank=True, null=True) 
    total_yeas = models.IntegerField(blank=True, null=True) 
    total_nays = models.IntegerField(blank=True, null=True) 
    total_verified_votes = models.IntegerField(blank=True, null=True) 
    total_verified_yeas = models.IntegerField(blank=True, null=True) 
    total_verified_nays = models.IntegerField(blank=True, null=True) 
    total_comments = models.IntegerField(blank=True, null=True) 
    total_saves = models.IntegerField(blank=True, null=True) 
    total_shares = models.IntegerField(blank=True, null=True) 

    notes = models.JSONField(default=dict, blank=True, null=True)

    all_objects = models.Manager()
    objects = ValidPostManager()

    def __str__(self):
        return 'POST-%s/%s' %(str(self.pointerId)[:20], str(self.id)[:20])     
    
    class Meta:
        ordering = ['-created','-DateTime','validated']
        indexes = [
            GinIndex(fields=["filters"], name="gin_index_filters", opclasses=["jsonb_ops"]),
            GinIndex(fields=['keyword_array'], name='keyword_array_overlap_index'),
        ]

    def get_hash_to_id(self, version=None):
        if not version:
            version = 1
        if int(version) >= 1:
            return ['objType','pointerId']
    
    def get_absolute_url(self):
        if self.pointerType == 'Person':
            if not self.Update_obj:
                if self.Person_obj.GovIden:
                    return f"/profile/{self.Person_obj.GovIden}"
                else:
                    return f"/profile/{self.Person_obj.id}"
            if self.Person_obj.GovIden:
                return "/profile/%s/%s_%s/%s" % (self.Region_obj.Name, self.Update_obj.data['FirstName'].replace(' ', '_'), self.Update_obj.data['LastName'].replace(' ', '_'), self.Person_obj.GovIden)
            else:
                return "/profile/%s/%s_%s/%s" % (self.Region_obj.Name, self.Update_obj.data['FirstName'].replace(' ', '_'), self.Update_obj.data['LastName'].replace(' ', '_'), self.Person_obj.id)
        
    def get_title(self): # not used?
        if self.Agenda_obj:
            return '%s agenda %s' %(self.Agenda_obj.Chamber, datetime.datetime.strftime(self.Agenda_obj.DateTime, '%d/%m/%Y'))
        elif self.Bill_obj and self.Bill_obj.Title:
            return 'Bill %s %s' %(self.Bill_obj.NumberCode, self.Bill_obj.Title)
        elif self.Bill_obj and self.Bill_obj.ShortTitle:
            return 'Bill %s %s' %(self.Bill_obj.NumberCode, self.Bill_obj.ShortTitle)
        elif self.Meeting_obj:
            return '%s %s %s' %(self.Meeting_obj.Chamber, self.Meeting_obj.meeting_type, self.Meeting_obj.DateTime)
        elif self.pointerType == 'Statement':
            if self.Pointer_obj.Person_obj:
                return '%s Stated %s' %(self.Pointer_obj.Person_obj.FullName, self.Pointer_obj.DateTime)
            else:
                return '%s Stated %s' %(self.Pointer_obj.PersonName, self.Pointer_obj.DateTime)
        elif self.Motion_obj:
            return 'Bill %s Motion %s' %(self.Motion_obj.billCode, self.Motion_obj.DateTime)
        else:
            return '%s' %(self.pointerType)

    def tally_votes(self):
        prnt('-tally_votes',self)
        from accounts.models import UserAction
        actions = UserAction.objects.filter(pointerId=self.pointerId).exclude(UserVote_obj=None)
        self.total_votes = actions.count()
        self.total_yeas = len([r for r in actions if r.UserVote_obj.voteValue == 'yea'])
        self.total_nays = len([r for r in actions if r.UserVote_obj.voteValue == 'nay'])
        self.total_verified_votes = len([r for r in actions if r.User_obj.UserVerification_obj])
        self.total_verified_yeas = len([r for r in actions if r.UserVote_obj.voteValue == 'yea' and r.User_obj.UserVerification_obj])
        self.total_verified_nays = len([r for r in actions if r.UserVote_obj.voteValue == 'nay' and r.User_obj.UserVerification_obj])
        prnt('self.total_votes',self.total_votes)
        return self

    def validate(self, validators=None, save_self=True, update_pointer=True, verify_validator=True, opBlock_data={}):
        prnt('-validate _post', self.id)
        from utils.locked import validate_obj
        return validate_obj(obj=self, pointer=None, validators=validators, save_obj=save_self, update_pointer=update_pointer, verify_validator=verify_validator, add_to_queue=False, opBlock_data=opBlock_data)

    def verify_is_valid(self, check_update=True, use_assigned_val=False):
        prnt('-verify_is_valid', self.id)
        update_valid = None
        pointer_valid = False
        from network.models import Validator
        from utils.locked import verify_obj_to_data, get_node_assignment
        from utils.models import sigData_to_hash
        from utils.utils import get_plugin
        pointer = self.get_pointer()
        if use_assigned_val:
            v = pointer.Validator_obj
        else:
            v = Validator.objects.filter(data__has_key=self.pointerId, is_valid=True).order_by('-created').first()
        if v:
            if self.pointerId in v.data and v.data[self.pointerId] == sigData_to_hash(pointer):
                if verify_obj_to_data(v, v):
                    if v.func == 'super' and pointer.func == 'super' and v.CreatorNode_obj.User_obj.assess_super_status(dt=v.created):
                        pointer_valid = True
                    else:
                        creator_nodes, validator_nodes = get_node_assignment(dt=pointer.created, func=pointer.func, chainId=pointer.networkChain, plugin_id=get_plugin(pointer.networkChain, id=True), strings_only=True)
                        if pointer.validatorNodeId in validator_nodes:
                            pointer_valid = True

        if check_update and self.Update_obj:
            update_valid = False
            if self.Update_obj.verify_is_valid():
                update_valid = True
        if check_update:
            return pointer_valid, update_valid
        return pointer_valid

    def get_pointer(self, set_pointer=True, return_self=False, do_save=True):
        pointer = self.Pointer_obj
        if not pointer and set_pointer:
            if return_self:
                pointer, self = self.set_pointer(return_self=return_self, do_save=do_save)
            else:
                pointer = self.set_pointer(return_self=return_self, do_save=do_save)
        if return_self:
            return pointer, self
        return pointer

    def set_pointer(self, do_save=True, return_self=False):
        prnt('-set_pointer')
        pointer = None
        if self.pointerId and not self.pointerKey:
            pointer = get_dynamic_model(self.pointerId, id=self.pointerId)
            self.pointerKey = ContentType.objects.get_for_model(pointer)
        elif self.pointerKey:
            pointer = self.Pointer_obj
            self.pointerId = pointer.id
        prnt('pointer',pointer,'now',now_utc())
        if do_save:
            super(Post, self).save()
        if return_self:
            return pointer, self
        return pointer

    def set_score(self, save_item=True):
        prnt('-set_score',self.id,save_item)
        scoreMe(self, save_item=save_item)

    def save(self, share=False, *args, **kwargs):
        prnt('-save post', self.pointerId, self.id)
        pointer = None
        if self.id is None:
            self.id = hash_obj_id(self)
            pointer, self = self.get_pointer(return_self=True, do_save=False)
            if not self.created:
                if has_field(pointer, 'created'):
                    self.created = pointer.created
                else:
                    self.created = get_timeData(pointer)
            if has_field(pointer, 'Government_obj'):
                self.Government_obj = pointer.Government_obj
                if pointer.Government_obj:
                    self.filters['gov_level'] = pointer.Government_obj.gov_level
            if has_field(pointer, 'Chamber') and pointer.Chamber:
                self.filters['Chamber'] = pointer.Chamber
            if has_field(pointer, 'Country_obj'):
                self.Country_obj = pointer.Country_obj
            if has_field(pointer, 'Region_obj'):
                self.Region_obj = pointer.Region_obj
            if has_method(pointer, 'set_keywords'):
                self = pointer.set_keywords(self)
            if not self.networkChain:
                self.networkChain = pointer.networkChain
            if not self.Plugin_obj:
                plugin = get_plugin(pointer)
                self.Plugin_obj = plugin
            if not self.networkChain:
                self.networkChain = self.Plugin_obj.id
                
        if not self.DateTime:
            if not pointer:
                pointer, self = self.get_pointer(return_self=True, do_save=False)
            if has_field(pointer, 'DateTime'):
                self.DateTime = pointer.DateTime
            elif has_field(pointer, 'lastUpdate'):
                self.DateTime = pointer.lastUpdate
            elif has_field(pointer, 'created'):
                self.DateTime = pointer.created
        if self.rank == 0:
            self.set_score(save_item=False)
        save_mutable_fields(self, *args, **kwargs)
    
    def delete(self, *args, **kwargs):
        if not self.validated:
            super(Post, self).delete(*args, **kwargs)






