
from django.template.defaulttags import register
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render

from legis.models import Government, Agenda, Bill, Meeting
from .models import Post,Update,Region
from accounts.models import User, Notification,UserNotification,UserAction
from .forms import AgendaForm
from utils.locked import get_signing_data
from utils.models import prnt, now_utc, get_operator_obj, is_id, dt_to_string, skipwords


from django.db.models import Q
from collections import Counter
# from uuid import uuid4
import json
import random
import datetime
# from unidecode import unidecode



def render_view(request, context, country=None, feed=False):
    prnt('-renderview')
    style = request.GET.get('style', 'index')
    if style == 'feed' or feed:
        if feed:
            template = f"{feed}/templates/utils/feed.html"
        else:
            template = "utils/feed.html"
        prnt('template',template)
        return render(request, template, get_paginator_url(request, context))
    else:
        fcmDeviceId = None
        # try:
        #     fcmDeviceId = request.GET.get('fcmDeviceId', '')
        #     if not fcmDeviceId:
        #         fcmDeviceId = request.COOKIES['fcmDeviceId']
        #     # prnt('dviceId', fcmDeviceId)
        #     if fcmDeviceId:
        #         # from fcm_django.models import FCMDevice
        #         fcm_device = CustomFCM.objects.filter(registration_id=fcmDeviceId).first()
        #         if not fcm_device:
        #             fcm_device = CustomFCM()
        #             fcm_device.registration_id = fcmDeviceId
        #         fcm_device.user = request.user
        #         fcm_device.active = True
        #         fcm_device.save()
        #         # prnt('saved device')
        # except Exception as e:
        #     # prnt(str(e))
        #     pass
        
        ctx = get_cookies(request,context,country=country)
        response = render(request, "home.html", ctx)
        width = request.GET.get('width', '')
        if width:
            response.set_cookie(key='deviceWidth', value=width, expires=datetime.datetime.today()+datetime.timedelta(days=3650))
        if fcmDeviceId:
            response.set_cookie(key='fcmDeviceId', value=fcmDeviceId, expires=datetime.datetime.today()+datetime.timedelta(days=3650))
        return response
    
def default_setup(request, title=None, region=None, plugin=None):
    # prnt('-default_setup')
    style = request.GET.get('style', 'preload')
    if style == 'preload':
        context = {
            'title': title,
            'style': style,
        }
        return render(request, "home.html", get_cookies(request,context))
    elif style == 'index':
        user_id = request.GET.get('user', None)
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
        context = get_index(request, country_dict, gov_dict)
        context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
        context = get_user_sending_data(user_id, context)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)
        if plugin:
            context['index_template'] = f"{plugin}/templates/utils/index.html"
        else:
            context['index_template'] = ""
        prnt("context['index_template']",context['index_template'])
        
        return render(request, "utils/index.html", context)
    else:
        return False
    
def default_context(request, setlist, cards='', nav_options=None, sort='Latest', view='Latest', paginate=True):
    if paginate:
        setlist = paginater(setlist, request.GET.get('page', 1), request)
    context = {
        'view': request.GET.get('view', view),
        'sort': request.GET.get('sort', sort),
        'page': request.GET.get('page', 1),
        'style': request.GET.get('style', 'preload'),
        'nav_bar': nav_options,
        'cards': cards,
        'feed_list': setlist,
        'useractions': get_useractions(request, setlist),
        'isMobile': get_isMobile(request),
        'self_node': get_operator_obj('self_nodeId'),
    }
    return context
    
def getTrendingTop(Chamber, country):
    if Chamber and country:
        try:
            posts = TopPost.objects.filter(Chamber=Chamber, country=country.Name)
            return posts
        except:
            pass
    return []

def get_trending_keys(dt, include_list, orgs):
    trends = Post.objects.filter(Chamber__in=orgs).filter(Q(DateTime__lte=datetime.datetime.now() + datetime.timedelta(hours=1))|Q(DateTime__gte=datetime.datetime.now() + datetime.timedelta(days=dt.days))).filter(pointerType__in=include_list).order_by('-rank', '-DateTime')[:200]
    keys = []
    for p in trends:
        if p.keyword_array:
            keys = keys + p.keyword_array
    return keys

def algorithim(user, include_list, chamber_list, country, view='Recommended', page=1, provState_name=None):
    prnt('-algo', chamber_list)
    orgs = chamber_list
    if 'Bill' in include_list:
        try:
            dateQuery = Bill.objects.filter(Chamber__in=orgs).order_by('-lastUpdate')[:10]
            dateQuery = list(dateQuery)[::-1][0]
            date = dateQuery.lastUpdate
        except Exception as e:
            date = now_utc()
        dt = now_utc() - date
    elif 'Meeting' in include_list or 'Statement' in include_list:
        try:
            dateQuery = Meeting.objects.filter(meeting_type='Debate', Chamber__in=orgs).filter(DateTime__gte=now_utc()-datetime.timedelta(days=100)).order_by('-DateTime')[:10]
            dateQuery = list(dateQuery)[::-1][0]
            date = dateQuery[12].DateTime
        except Exception as e:
            date = now_utc()
        dt = now_utc() - date
    if view == 'Recommended' and user and json.loads(user.interest_array):
        keys = json.loads(user.interest_array)
    else:
        if view == 'Recommended' and user and not json.loads(user.interest_array):
            pass
        else:
            view = 'Trending'
        keys = get_trending_keys(dt, include_list, orgs)
    # randomNum = 255
    def get_posts(dayRange, firstKeys, secondKeys, reorder):
        randomNum = random.randint(1, 333) # picks 1/333th (333 = 8hrs by rank) of hansardItems randomly
        # prnt('randInt', randomNum)
        plusRange = randomNum + 8 # sets range for randomNum used in query below
        minusRange = randomNum - 8
        counter = Counter(firstKeys)
        firstCommonKeys = counter.most_common(500)
        if secondKeys == firstKeys:
            firstCommonKeys = firstCommonKeys[:500]
            secondCommonKeys = firstCommonKeys
        else:
            counter = Counter(secondKeys)
            secondCommonKeys = counter.most_common(500)
        
        posts = Post.objects.filter(Country_obj__id=country['id'], Chamber__in=orgs).filter(DateTime__gte=datetime.datetime.now()-datetime.timedelta(days=dayRange)).filter(pointerType__in=include_list).filter(Q(pointerType='Bill')&Q(keyword_array__overlap=firstKeys)|Q(pointerType='Meeting')&Q(keyword_array__overlap=secondKeys)).order_by('-rank', '-DateTime')[:1000]
        # prnt('posts', posts)
        if reorder:
            querylist = {}
            for p in posts:
                keywords = []
                if p.keyword_array:
                    keywords = p.keyword_array
                if p.pointerType == 'Meeting':
                    y = [{c:k} for c in secondCommonKeys for k in keywords if c[0] == k]
                else:
                    y = [{c:k} for c in firstCommonKeys for k in keywords if c[0] == k]
                for i in y:
                    for key, value in i:
                        if key not in skipwords:
                            if p in querylist:
                                querylist[p] += value
                            else:
                                querylist[p] = value                    
            return querylist
        else:
            return posts
    if len(keys) > 4:
        querylist = get_posts(dt.days, keys, keys, True)
        querylist = sorted(querylist.items(), key=operator.itemgetter(1),reverse=True)
    else:
        querylist = []
    posts = []
    for p in querylist:
        posts.append(p[0])
    prnt('len(posts)',len(posts))
    if len(posts) <= 20:
        trendKeys = get_trending_keys(dt, include_list, orgs)
        querylist = get_posts(dt.days, trendKeys, keys, True)
        querylist = sorted(querylist.items(), key=operator.itemgetter(1),reverse=True)
        for p in querylist:
            if p[0] not in posts:
                posts.append(p[0])
    if len(posts) <= 20 * (int(page)):
        # prnt('less than 22 algotrithim')
        trendKeys = get_trending_keys(dt, include_list, orgs)
        querylist = get_posts(90, trendKeys, keys, False)
        for p in querylist:
            if p not in posts:
                posts.append(p)
    if len(posts) <= 20 * (int(page)):
        # prnt('less than 33 algotrithim')
        trendKeys = get_trending_keys(dt, include_list, orgs)
        querylist = get_posts(200, trendKeys, keys, False)
        for p in querylist:
            if p not in posts:
                posts.append(p)
    return posts, view


def get_index(request, country_dict=None, gov_dict=None):
    context = {
        'self_node': get_operator_obj('self_nodeId'),
        'is_mobile': get_isMobile(request),
        'style': request.GET.get('style', 'preload'),
        "country": country_dict,
        'gov': gov_dict,
    }
    return context

def get_paginator_url(request, c):
    # prnt('-get_paginator_url')
    paginatorURL = ''
    try:
        paginatorURL = paginatorURL + '&sort=%s' %(c['sort'])
    except Exception as e:
        pass
    try:
        paginatorURL = paginatorURL + '&view=%s' %(c['view'])
    except:
        pass
    try:
        paginatorURL = paginatorURL + '&time=%s' %(c['time'])
    except:
        pass
    try:
        paginatorURL = paginatorURL + '&topic=%s' %(c['topic'])
    except:
        pass
    try:
        paginatorURL = paginatorURL + '&id=%s' %(c['id'])
    except:
        pass
    try:
        paginatorURL = paginatorURL + '&speaker_id=%s' %(c['speaker_id'])
    except Exception as e:
        pass     
    return {**{'paginatorURL': paginatorURL}, **c}

def get_cookies(request, received_cxt, country=None, gov=None):
    # prnt('-get_cookies')
    try:
        theme = request.COOKIES['theme']
    except:
        theme = 'day'
    notifications = []

    # include server data json detailing version number and latest modlVers
    # user device will store a blank copy of user models

    width = request.GET.get('width', '')
    if not width:
        try:
            width = request.COOKIES['deviceWidth']
        except:
            width = None
    mobile = get_isMobile(request)
    xRequest = False
    if request.headers.get('X-Requested-With') and 'sonetapp' in request.headers.get('X-Requested-With'):
        if width and float(width) < 810:
            xRequest = True
    ua = request.META.get('HTTP_USER_AGENT', '').lower()
    if 'iphone' in str(ua):
        iphone = 'true'
    elif 'ipad' in str(ua):
        mobile = False
        iphone = None
    else:
        iphone = None
    # return server copy of userData for user to locally verify
    # if request.user.is_authenticated:
    #     userData = get_user_sending_data(request.user)
    # else:
    #     userData = None
    # prnt('utils.py UserData', userData)
    nodeData = {}
    from network.models import Block, Sonet, NodeRecord
    latest_opBlock = Block.objects.filter(networkChain='Operations', validated=True).values('id','DateTime','opData').order_by('-index').first()
    if latest_opBlock:
        prnt('latest_opBlock',latest_opBlock['id'])
        nodeData['blockId'] = latest_opBlock['id']
        nodeData['blockDatetime'] = dt_to_string(latest_opBlock['DateTime'])
        nodeData['max_pos'] = latest_opBlock['opData']['max_pos']
        nodeRecord = NodeRecord.objects.filter(networkChain='master', Block_obj_id=latest_opBlock['id'], is_valid=True).values('data').first()
        if nodeRecord:
            nodeData['id_data'] = nodeRecord['data']
    else:
        from network.models import _OperationsChain_genesisId, Blockchain, Node
        nodes = Node.objects.exclude(activated_dt=None).filter(suspended_dt=None)
        if nodes:
            nodeChain = Blockchain.objects.filter(genesisId=_OperationsChain_genesisId).first()
            if nodeChain:
                nodeChain.add_item_to_queue(list(nodes))
        
        nodeData['blockId'] = 'none'
        nodeData['blockDatetime'] = dt_to_string(now_utc())
        nodeData['max_pos'] = 1
                
    if 'id_data' not in nodeData or not nodeData['id_data']:
        nodeData['id_data'] = {}
        from network.models import Node
        node = Node.objects.all().values('id').first()
        if node:
            nodeData['id_data'] = {'active':{node['id']:{'pos':1}}}

    # prnt('returning nodeData',json.dumps(nodeData))

    sonet = Sonet.objects.values('Title','Subtitle','LogoLink','created','Domain').first()
    if not sonet:
        sonet = {'Title' : 'Nonet', 'LogoLink' : "img/default_logo.png", 'Domain':''}
        nodeData['sonetInitializedDatetime'] = dt_to_string(now_utc())
    else:
        nodeData['sonetInitializedDatetime'] = dt_to_string(sonet['created'])
    nodeData['Domain'] = sonet['Domain']

    context = {
        "sonet": sonet,
        "nodeData": json.dumps(nodeData),
        "theme": theme,
        "notifications": notifications,
        'isMobile': mobile,
        'xRequest': xRequest,
        'iphone': iphone,
    }
    return {**context, **get_paginator_url(request, received_cxt)}

def get_user_data(request):
    prnt('-get_user_data')
    try:
        userData = request.POST.get('userData')
        userData = json.loads(userData)
    except:
        userData = None
    try:
        if request.user.is_authenticated:
            return userData, request.user
        else:
            user_id = request.GET.get('userId', '')
            # prnt(request.COOKIES['userData'])
            try:
                user = User.objects.filter(id=user_id).first()
            except Exception as e:
                prnt('get_user_data err 1',str(e))
                user = None
            return userData, user
    except Exception as e:
        prnt('get_user_data err 2',str(e))
        return userData, None

def get_user_sending_data(user, context):
    prnt('-get_user_sending_data',user)
    if isinstance(user, str):
        user = User.objects.filter(id=user).first()
    if user:
        context['user'] = user
        x = get_signing_data(user, include_sig=True, sort_data=False)
        u = User
        user_json = json.loads(x)
        user_json['latestVer'] = u.latestVer
        user_json['signed'] = user.signed
        if u.latestVer != user.modlVer:
            user_json['updated_model'] = json.dumps(get_signing_data(u))
        userData = json.dumps(user_json, separators=(',', ':'))
        context['userData'] = userData
    else:
        context['userData'] = None
        from utils.locked import generate_id
        context['anonId'] = 'tusrSo' + generate_id(length=20)

    return context

def get_isMobile(request):
    width = request.GET.get('width', '')
    if not width:
        try:
            width = request.COOKIES['deviceWidth']
        except:
            width = None
    try:
        if float(width) < 810:
            mobile = request.user_agent.is_mobile
            width = int(width)
        else:
            mobile = False  
    except Exception as e:
        # prnt(str(e))
        mobile = request.user_agent.is_mobile    
    return mobile

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_regions(request, region, user):
    from django.db.models import Model
    prnt('-get_regions', region)
    try:
        if request.subdomain == 'us':
            region = 'USA'
        elif request.subdomain == 'ca':
            region = 'Canada'
        elif request.subdomain == 'uk':
            region = 'United Kingdom'
        else:
            region = 'Unknown Region'
    except:
        pass
    if isinstance(region, Model):
        country_obj = region
    elif isinstance(region, str):
        country_obj = Region.supported_objects.filter(Name__iexact=region, nameType='Country').first()
    else:
        country_obj = Region.supported_objects.filter(nameType='Country', Name='USA').first()
        if not country_obj:
            country_obj = Region.supported_objects.filter(nameType='Country').first()
    # prnt('country_obj',country_obj)
    return country_obj, None, None, None
    
def get_location(request, user):
    prnt('-get location')
    Country = None
    def run_region(request):
        try:
            from django.contrib.gis.geoip2 import GeoIP2
            g = GeoIP2('geoip')
            # prnt(g.country('google.com'))
            # prnt(g.city('google.com'))
            ip = request.META.get('REMOTE_ADDR', None)
            if not ip:
                #https
                ip = request.META.get('HTTP_X_REAL_IP', None)
            if ip:
                data = g.city(ip)
                city_city = data['city']
                provState_abbrv = data['region']
                country_name = data['country_name']
                lat = data['latitude']
                long = data['longitude']
            Country = Region.objects.filter(Name=country_name, nameType='Country').first()
            try:
                p = Region.objects.filter(AbbrName=provState_abbrv, is_supported=True, nameType__in=['State','Province','Territory']).first()
                return Country, p, p.lowerName(), long, lat
            except Exception as e:
                return Country, None, 'None', None, None
        except Exception as e:
            try:
                Country = Region.supported_objects.filter(Name='USA', nameType='Country').first()
            except:
                Country = None
            return Country, None, 'None', None, None
    def run():
        Country_obj, ProvState, ProvState_name, long, lat = run_region(request)

        # def locate_user(user):
        #     locations = {}
        #     for p in user.longLat:
        #         try:
        #             if not p in locations:
        #                 locations[p] = 1
        #             else:
        #                 locations[p] += 1
        #         except:
        #             pass
        #     locations = sorted(locations.items(), key=operator.itemgetter(1),reverse=True)
        #     mostOccured = locations[0][0]
        #     mostOccured = json.loads(mostOccured)
        #     mostLongitude = next(iter(mostOccured))
        #     mostLatitude = mostOccured[mostLongitude]
        #     url = 'https://represent.opennorth.ca/boundaries/?contains=%s,%s' %(mostLatitude, mostLongitude)
        #     user.clear_region()
        #     user.get_data(url)

        return Country_obj, ProvState, ProvState_name
    if user:
        if user.ProvState_obj:
            ProvState = user.ProvState_obj
            if ProvState.is_supported:
                ProvState_name = ProvState.lowerName()
            else:
                ProvState_name = 'None'
        else:
            Country, ProvState, ProvState_name = run()
    else:
        Country, ProvState, ProvState_name = run()
    return Country, ProvState, ProvState_name

def nav_item(type, text, target=None, var=None, fields=None, key=None, new_tab=None):
    x = {'type':type, 'text':text, 'target':target, 'var':var}
    if fields:
        x['fields'] = fields
    if key:
        x['key'] = key
    if new_tab:
        x['new_tab'] = new_tab
    return x

def get_theme(request):
    try:
        theme = request.COOKIES['theme']
    except:
        theme = 'day'
    return {"theme": theme}

def get_notifications(user, country):
    if user.is_authenticated:
        n = UserNotification.objects.filter(User_obj=user, new=True).order_by("-DateTime", '-created')[:40]
        if n:
            return n
        else:
            return Notification.objects.filter(validated=True, Region_obj=country).order_by("-DateTime", '-created')[:40]
    else:
        return Notification.objects.filter(validated=True, Region_obj=country).order_by("-DateTime", '-created')[:40]

def set_session_data(request, country_dict=None, gov_dict=None, subRegions=None, subGovernments=None, current_chamber_name=None):
    if country_dict:
        try:
            request.session.setdefault('region_id', country_dict['id'])
            request.session['region_id'] = country_dict['id']
        except:
            pass
    if current_chamber_name:
        try:
            request.session.setdefault('chamber', current_chamber_name)
            request.session['chamber'] = current_chamber_name
        except:
            pass
    return request

def get_regions_and_govs(region, request=None):
    country_dict = {}
    gov_dict = {}
    subRegions = []
    subGovernments = []
    if is_id(region):
        country_dict = Region.supported_objects.filter(id=region).values('id','Name','nameType').first()
    elif isinstance(region, str):
        country_dict = Region.supported_objects.filter(Name__iexact=region, nameType='Country').values('id','Name','nameType').first()
    else:
        country_dict = Region.supported_objects.filter(nameType='Country', Name='USA').values('id','Name','nameType').first()
        if not country_dict:
            country_dict = Region.supported_objects.filter(nameType='Country').values('id','Name','nameType').first()
    if country_dict:
        gov_dict = Government.valid_objects.filter(Region_obj__id=country_dict['id'], Validator_obj__is_valid=True).values('menuItem_array','Chamber_array','Office_array').first()
        if not gov_dict:
            gov_dict = {'menuItem_array':[],'Chamber_array':[],'Office_array':[]}
        subGovernments = Government.valid_objects.filter(Country_obj__id=country_dict['id'], Validator_obj__is_valid=True).values('menuItem_array','Chamber_array','Office_array')

    return country_dict, gov_dict, subRegions, subGovernments

def get_trending(request, country, provState=None, county=None, city=None, current_chamber='All', all_chambers=[]):
    from posts.models import KeyphraseTrend
    prnt('-get trend')
    region_ids = []
    if country:
        region_ids.append(country['id'])
    if provState:
        region_ids.append(provState.id)
    if county:
        region_ids.append(county.id)
    if city:
        region_ids.append(city.id)
    trendList = []
    try:
        if current_chamber != 'All':
            kt = KeyphraseTrend.objects.filter(Region_obj__id__in=region_ids).exclude(recent_occurences=0).filter(Chamber=current_chamber)[:20]
        else:
            # Chambers = ['House', 'Senate', 'Assembly', 'Municipality']
            kt =  KeyphraseTrend.objects.filter(Region_obj__id__in=region_ids).exclude(recent_occurences=0)[:20]
    except Exception as e:
        prnt('trend err 1',str(e))
        kt = []
    for t in kt:
        trend = {}
        trend['key'] = t.key
        trend['get_absolute_url'] = t.get_absolute_url()
        trend['recentOccurences'] = t.recent_occurences
        for i in trendList:
            if i['key'] == t.key:
                trend['recentOccurences'] += i['recentOccurences']
                trendList.remove(i)
                break
        trendList.append(trend)
    agenda_list, agendaForm = get_agenda(request, country, provState, county, city, current_chamber, all_chambers)
    return {'trend_list':trendList, 'agenda_list':agenda_list, 'agendaForm':agendaForm}

def get_agenda(request, country, provState, county, city, current_chamber, all_chambers):
    prnt('-get agenda',country)
    agenda_list = []
    if current_chamber == 'All' and all_chambers:
        if country and isinstance(country, dict):
            agendas = Agenda.objects.filter(Region_obj__id=country['id'], Chamber__in=all_chambers).exclude(Validator_obj=None).order_by('-Chamber','-DateTime').distinct('Chamber')
            agenda_list = list(agendas)
        if provState:
            a = Agenda.objects.filter(Region_obj=provState, Chamber__in=all_chambers).exclude(Validator_obj=None).order_by('-DateTime').first()
            if a:
                agenda_list.append(a)
        if county:
            a = Agenda.objects.filter(Region_obj=county, Chamber__in=all_chambers).exclude(Validator_obj=None).order_by('-DateTime').first()
            if a:
                agenda_list.append(a)
        if city:
            a = Agenda.objects.filter(Region_obj=city, Chamber__in=all_chambers).exclude(Validator_obj=None).order_by('-DateTime').first()
            if a:
                agenda_list.append(a)
    elif country and isinstance(country, dict):
        agendas = Agenda.objects.filter(Country_obj__id=country['id'], Chamber=current_chamber).exclude(Validator_obj=None).order_by('-Chamber', '-DateTime').distinct('Chamber')
        agenda_list = list(agendas)
    return agenda_list, AgendaForm()

def get_gov(country, gov_levels, govNum=None, session=None):
    # prnt('-get__gov_levels', gov_levels, country)
    try:
        if govNum and session:
            govs = Government.objects.filter(Country_obj=country, gov_level__in=gov_levels, GovernmentNumber=govNum, SessionNumber=session).exclude(Block_obj=None).distinct('gov_level').order_by('gov_level', '-DateTime')
        else:
            govs = Government.objects.filter(Country_obj=country, gov_level__in=gov_levels).exclude(Block_obj=None).distinct('gov_level').order_by('gov_level', '-DateTime')
    except Exception as e:
        prnt('get_gov err',str(e))
        govs = []
    return govs

def get_chambers(request, gov_dict, provState=None, county=None, city=None, chamber=None):
    # prnt('-get_chambers:', gov_dict, provState, county, city, chamber)
    chambers = []
    if 'Chamber_array' in gov_dict:
        chambers = gov_dict['Chamber_array']        
    if provState:
        provState_name = provState.Name
    else:
        provState_name = 'none'
    if county:
        county_name = county.Name
    else:
        county_name = 'none'
    if city:
        city_name = city.Name
    else:
        city_name = 'none'
    if provState:
        chambers.append(f'{provState_name}-Assembly')
    if county:
        chambers.append(f'{county_name}-Council')
    gov_levels = []
    if not chamber:
        chamber = request.GET.get('chamber', None)
        if not chamber:
            try:
                chamber = request.session['chamber']
            except Exception as e:
                chamber = 'All'
        words = chamber.split(' ')
        chamber = ''
        for w in words:
            if chamber:
                chamber = chamber + ' '
            chamber = chamber + w[0].upper() + w[1:]
        request.session.setdefault('chamber', chamber)
        request.session['chamber'] = chamber
    if chamber.lower() == 'assembly':
        r = f'{provState_name}-Assembly'
        gov_levels.append('Provincial')
        gov_levels.append('State')
    elif chamber.lower() == 'council':
        r = f'{county_name}-Council'
        gov_levels.append('Municipal')
    elif chamber.lower() == 'house':
        gov_levels.append('Federal')
    elif chamber.lower() == 'senate':
        gov_levels.append('Federal')
    if chamber.lower() == 'all':
        target_chamber = chambers
        gov_levels = ['Federal', 'Provincial', 'State', 'Territory', 'Municipal', 'County', 'City']
    else:
        target_chamber = [chamber]
    return target_chamber, chamber, chambers, gov_levels

def get_Chamber(request):
    Chamber = request.GET.get('Chamber', '')
    if 'Assembly' in Chamber:
        Chamber = 'Assembly'
    if Chamber:
        request.session.setdefault('Chamber', Chamber)
        request.session['Chamber'] = Chamber
    else:
        try:
            Chamber = request.session['Chamber']
        except Exception as e:
            Chamber = 'All'
    return Chamber

def getDaily(request, country, provState, date):
    # must receive region
    try:
        if request.user.is_authenticated:
            try:
                if date:
                    daily = Daily.objects.filter(User_obj=request.user, DateTime=date).first()
                else:
                    daily = Daily.objects.filter(User_obj=request.user).first()
            except:
                if provState and provState.is_supported:
                    if date:
                        daily = Daily.objects.filter(Region_obj=provState.Name + '-Assembly', DateTime=date).first()
                    else:
                        daily = Daily.objects.filter(Region_obj=provState.Name + '-Assembly').first()
                else:
                    if date:
                        daily = Daily.objects.filter(Country_obj=country, Chamber='Federal', DateTime=date).first()
                    else:
                        daily = Daily.objects.filter(Country_obj=country, Chamber='Federal').first()
        else:
            if date:
                daily = Daily.objects.filter(Country_obj=country, Chamber='Federal', DateTime=date).first()
            else:
                daily = Daily.objects.filter(Country_obj=country, Chamber='Federal').first()
    except: 
        prnt('daily fail')  
        if date: 
            daily = Daily.objects.filter(Country_obj=country, Chamber='Federal', DateTime=date).first()
        else:
            daily = Daily.objects.filter(Country_obj=country, Chamber='Federal').first()
    return daily

def get_reps(user):
    # user = request.user
    # prnt('get reps')
    # userId = request.GET.get('userId', '')
    # countryId = request.GET.get('countryId', '')
    # provStateId = request.GET.get('provStateId', '')
    # regionalMunicipalId = request.GET.get('regionalMunicipalId', '')
    # # prnt('rmid', regionalMunicipalId)
    # municipalId = request.GET.get('municipalId', '')
    # federalDistrictId = request.GET.get('federalDistrictId', '')
    # federalDistrictName = request.GET.get('federalDistrictName', '')
    # provStateDistrictId = request.GET.get('provStateDistrictId', '')
    # regionalMunicipalityDistrictId = request.GET.get('regionalMunicipalityDistrictId', '')
    # wardId = request.GET.get('wardId', '')
    regions = []
    if user.Municipality_obj:
        regions.append(user.Municipality_obj.id)
    districts = []
    if user.Federal_District_obj:
        districts.append(user.Federal_District_obj.id)
    if user.ProvState_District_obj:
        districts.append(user.ProvState_District_obj.id)
    if user.Greater_Municipal_District_obj:
        districts.append(user.Greater_Municipal_District_obj.id)
    if user.Municipal_District_obj:
        districts.append(user.Municipal_District_obj.id)
    context = {}
    Uroles = Update.objects.filter(pointerType='Role', Role_obj__District_obj__in=districts, data__icontains='"Current": true')
    elections = Election.objects.filter(end_date__gte=now_utc()-datetime.timedelta(days=30)).filter(District_obj__id__in=districts)

    for r in Uroles:
        context[r.Role_obj.gov_level] = r
    for e in elections:
        if e.District_obj == user.Federal_District_obj:
            context['MP_election'] = e
        elif e.District_obj == user.ProvState_District_obj:
            context['MPP_election'] = e
        elif e.District_obj == user.Greater_Municipal_District_obj:
            context['greater_municipal_election'] = e
        elif e.District_obj == user.Municipal_District_obj:
            context['municipal_election'] = e

    return context

def fetch_updated_objs(setlist, requestList):
    prnt('-fetch_updated_objs')
    objs = {}
    data = {}
    try:
        for p in setlist:
            if p.Update_obj:
                for a in requestList:
                    ar = a + '_id'
                    if ar in p.Update_obj.data:
                        if a in objs:
                            objs[a].append(p.Update_obj.data[ar])
                        else:
                            objs[a] = [p.Update_obj.data[ar]]
        from posts.models import subRegions
        for key, valueList in objs.items():
            try:
                if key in subRegions:
                    items = get_dynamic_model('Region', list=True, id__in=valueList)
                else:
                    items = get_dynamic_model(key, list=True, id__in=valueList)
                data[key] = [i for i in items]
            except Exception as e:
                pass
    except Exception as e:
        prnt('fetch_updated_objs err',str(e))
        pass
    return data

def get_useractions(user, setlist):
    # prnt('-get_useractions')
    from accounts.models import UserAction
    try:
        user = user.GET.get('user', None)
    except:
        pass
    if user and setlist:
        id_list = []
        actions = {}
        id_list = [p.id for p in setlist if p]
        if is_id(user):
            action_list = UserAction.objects.filter(User_obj__id=user, postId__in=id_list).order_by('postId').distinct('postId')
        else:
            action_list = UserAction.objects.filter(User_obj=user, postId__in=id_list).order_by('postId').distinct('postId')
        actions = {r.postId:r for r in action_list}
        return actions
    else:
        return {}

def paginater(queryset_list, page, request):
    if not queryset_list:
        return None
    if 'id=' in str(page):
        # include context for discussions
        # maybe doesn't work on mac
        def clamp(n, minn):
            return max(minn, n)
        iden = page.replace('id=', '')
        queryset = []
        x = 0
        for i in queryset_list:
            if i.pointerType == 'Statement':
                if (isinstance(iden, int) or (isinstance(iden, str) and iden.strip('-').isdigit())) and i.Statement_obj.order == int(iden) or isinstance(iden, str) and i.Statement_obj.id == iden:
                    z = clamp((x-7), 0)
                    for y in queryset_list[z:]:
                        queryset.append(y)
                    break
            x += 1
        queryset_list = queryset
    paginator = Paginator(queryset_list, 20)
    try:
        queryset = paginator.page(page)
    except PageNotAnInteger:
        queryset = paginator.page(1)
    except EmptyPage:
        try:
            queryset = paginator.page(paginator.num_pages)
        except:
            pass
    if any(p._meta.object_name == 'Post' for p in queryset):
        from utils.utils import get_model
        obj_types = {}
        for p in queryset:
            if p._meta.object_name == 'Post' and p.pointerType:
                if p.pointerType not in obj_types:
                    obj_types[p.pointerType] = []
                obj_types[p.pointerType].append(p.pointerId)
        if obj_types:
            objs = {}
            for objType, iden_list in obj_types.items():
                z = {obj.id:obj for obj in get_model(objType).objects.filter(id__in=iden_list)}
                objs = objs | z
            if objs:
                for p in queryset:
                    if p._meta.object_name == 'Post' and p.pointerId in objs:
                        p.Pointer_obj = objs[p.pointerId]

    return queryset

def get_sort_order(sort):
    if sort == 'Oldest':
        ordering = 'DateTime'
    elif sort == 'Newest':
        ordering = '-DateTime'
    elif sort == 'Random':
        ordering = '?'
    elif sort == 'Loudest':
        ordering = '-rank'
    return ordering

def get_chatgpt_model(text): # not used?
    def get_token_count(string: str, encoding_name: str) -> int:
        encoding = tiktoken.get_encoding(encoding_name)
        num_tokens = len(encoding.encode(string))
        return num_tokens
    def reduce_text(text, n):
        text = text[:-n]
        num_tokens = get_token_count(text, "cl100k_base")
        return num_tokens, text
    num_tokens = get_token_count(text, "cl100k_base")
    if num_tokens <= 3500:
        model = 'gpt-3.5-turbo'
    elif num_tokens <= 6000:
        # n = 0
        while num_tokens > 3500:
            # n += 1
            num_tokens, text = reduce_text(text, 500)
        model = 'gpt-3.5-turbo'
    elif num_tokens <= 15500:
        model = 'gpt-3.5-turbo-16k'
    elif num_tokens > 15500:
        # n = 0
        while num_tokens > 15500 and num_tokens > 4000:
            # n += 1
            while num_tokens > 20000:
                num_tokens, text = reduce_text(text, 5000)
            num_tokens, text = reduce_text(text, 500)
        model = 'gpt-3.5-turbo-16k'
    return model, text

def get_party(list):
    people_list = []
    for p in list:
        people_list.append(p.Person)
    roles = Role.objects.filter(Person_obj__in=people_list).exclude(Party_obj=None).select_related('Party_obj')
    return roles

def get_matches(user, person, govs):
    prnt('-get_matches')
    actions = UserAction.objects.filter(User_obj=user, Post_obj__pointerType='Bill').filter(Post_obj__Bill_obj__Government_obj__in=govs).order_by('-Post_obj__DateTime')
    votes = {}
    my_votes = {}
    return_votes = []
    vote_matches = 0
    total_matches = 0
    match_percentage = None
    for r in actions:
        try:
            bill = r.Post_obj.Bill_obj
            if r.isYea:
                votes[bill] = 'Yea'
            elif r.isNay:
                votes[bill] = 'Nay'
        except:
            pass
    matched = []
    def match_vote(m, person, votes, bill, vote_matches, total_matches, return_votes):
        try:
            v = RepVote.objects.filter(Motion_obj=m, Person_obj=person).order_by('-Motion_obj__DateTime').first()
            total_matches += 1
            return_votes.append(v)
            if v.VoteValueName == votes[bill]:
                vote_matches += 1
                # prnt('match')
            return 'match', vote_matches, total_matches, return_votes
        except Exception as e:
            pass
        return 'nomatch', vote_matches, total_matches, return_votes
    for bill in votes:
        try:
            motions = Motion.objects.filter(Bill_obj=bill).order_by('-DateTime')
            for m in motions:
                my_votes[m.id] = votes[bill]
                result, vote_matches, total_matches, return_votes = match_vote(m, person, votes, bill, vote_matches, total_matches, return_votes)
                if result == 'match':
                    matched.append(m)
                    break
        except Exception as e:
            prnt('get_matches err',str(e))
    try:
        match_percentage = int((vote_matches / total_matches) * 100)
    except Exception as e:
        match_percentage = None
    return match_percentage, total_matches, vote_matches, my_votes, return_votes