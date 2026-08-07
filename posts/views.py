
from django.shortcuts import render, redirect
from django.template.defaulttags import register

from accounts.forms import *
from .forms import SearchForm
from .utils import *
from .models import Region, Post, Update
from network.models import Blockchain, Block
from legis.models import Statement,Person,District
from utils.models import string_to_dt, prnt, get_pointer_type

from django.db.models import Q, Value, F
from collections import Counter
from operator import itemgetter as _itemgetter

import datetime
import re
from django.http import JsonResponse
from unidecode import unidecode
import pytz

@register.filter
def get_item(dictionary, key):
    try:
        return dictionary.get(key)
    except Exception as e:
        prnt('get_item err',str(e),'key',key)
        return None

@register.filter
def get_list_item(lst, pos):
    try:
        return lst[pos]
    except Exception as e:
        prnt('get_list_item err',str(e),'pos',pos)
        return None

@register.filter
def get_updated_field(item, args):
    fields = args.split(",")
    # prnt('-get_updated_field', fields)
    if item and item._meta.object_name == 'Update':
        update = item
        if 'extra'in fields:
            fields.remove('extra')
            data = update.extra
        else:
            data = update.data
        if data and fields[0] in data:
            result = data[fields[0]]
        else:
            result = ''
            try:
                obj = getattr(update, fields[0])
                if obj != None:
                    if len(fields) > 1:
                        subresult = getattr(result, fields[1])
                        return subresult
                    return obj
            except Exception as e:
                # prnt(str(e))
                pass
            try:
                obj_field = str(update.pointerType) + '_obj'
                obj = getattr(update, 'Pointer_obj')
                result = getattr(obj, fields[0])
                if len(fields) > 1:
                    subresult = getattr(result, fields[1])
                    return subresult
                elif result:
                    return result
                else:
                    return None
            except Exception as e:
                # prnt(str(e))
                pass
        return result
    elif item:
        try:
            obj = getattr(item, fields[0])
            if len(fields) > 1:
                subresult = getattr(obj, fields[1])
                return subresult
            else:
                return obj
        except:
            return None
    else:
        return None

@register.filter
def get_person_field(obj, field):
    try:
        if obj and obj._meta.object_name == 'Person':
            return obj.get_field(field)
    except Exception as e:
        prnt('get_person_field fail',str(e))
        pass
    return None

@register.filter
def parse_extra_data(key, dictionary):
    try:
        modelType = get_pointer_type(key)
        if modelType == 'Region':
            for r in subRegions:
                for x in dictionary[r]:
                    if x.id == key:
                        return x
        else:
            for x in dictionary[modelType]:
                if x.id == key:
                    return x
    except Exception as e:
        prnt('parse_extra_data fail',str(e))
        pass
    return None

@register.filter
def get_update(obj):
    return Update.objects.filter(pointerId=obj.id).first()

@register.filter
def modelNameByRegion(region, model_name):
    if region.data:
        if model_name in region.data and 'name' in region.data[model_name] and region.data[model_name]['name']:
            return region.data[model_name]['name']
    return model_name

@register.filter
def dt_object(dt):
    try:
        return string_to_dt(dt)
    except Exception as e:
        return dt

@register.filter
def timezonify(dt, obj):
    prnt('-timezonify filter',dt,obj)
    try:
        to_zone = pytz.timezone(obj.Region_obj.timezone)
        local_dt = dt.astimezone(to_zone)
        return local_dt
    except:
        pass
    return dt
    
@register.filter
def is_obj(text):
    if text.endswith('Id') or text.endswith('_obj'):
        return True
    if 'So' in text and len(text) > 33:
        return True
    return False

@register.filter
def replace_spaces(text):
    try:
        return text.replace(' ','_')
    except Exception as e:
        # prnt(str(e))
        return text
    
@register.filter
def jsonify(obj):
    try:
        return json.loads(obj)
    except Exception as e:
        return None

@register.filter
def to_int(num):
    try:
        return int(num)
    except:
        return num

@register.filter
def is_int(obj):
    # prnt('-is_int',obj)
    if isinstance(obj, bool):
        return False
    if isinstance(obj, int):
        return True
    return False
    
@register.filter
def list_all_terms(update):
    # prnt('-list all terms', update)
    try:
        d = update.data
        terms = d['Terms']
        return terms
    except Exception as e:
        # prnt(str(e))
        return None

@register.filter
def list_75_terms(update):
    # prnt('-list 75')
    try:
        d = update.data
        terms = d['Terms']
        l = []
        for item in terms[:75]:
            for key, value in item.items():
                if key not in skipwords:
                    l.append((key, value))
        return l
    except Exception as e:
        # prnt(str(e))
        return None

@register.filter
def get_terms_overflow(update, num):
    # prnt('-get_terms_overflow')
    try:
        d = update.data
        terms = d['Terms']
        total = len(terms)
        if total > num:
            remaining = total - num
        else:
            remaining = None
        return remaining
    except:
        return None

@register.filter # not used
def list_all_people(update):
    prnt('-list all people')
    try:
        d = update.data
        people_json = json.loads(d['People_json'])
        speakers = {}
        keys = []
        for key, value in people_json.items():
            keys.append(key)
        people = Person.objects.filter(id__in=keys)
        for p, value in [[p, value] for p in people for key, value in people_json.items() if p.id == key]:
            speakers[p] = value
        H_people = sorted(speakers.items(), key=_itemgetter(1),reverse=True)
        return H_people
    except Exception as e:
        prnt('list_all_people fail',str(e))
        return None

@register.filter
def get_count(lst, num):
    num = int(num)
    more = None
    x = []
    for i in lst[:num]:
        x.append(i)

    if len(lst) > num:
        more = len(lst) - num
    return [x, more]

@register.filter
def get_ordinal(num):
    # prnt('-get ordinal', num)
    if not num:
        return '1st'
    if isinstance(num, str):
        num = int(num)
    n = num
    while n > 100:
        n -= 100
    if n >= 10 and n <= 20:
        return str(num) + 'th'
    elif n % 10 == 1:
        return str(num) + 'st'
    elif n % 10 == 2:
        return str(num) + 'nd'
    elif n % 10 == 3:
        return str(num) + 'rd'
    else:
        return str(num) + 'th'

@register.filter
def order_terms(terms, termList):
    order = []
    if terms:
        lowerTerms = [term.lower() for term in terms]
        if termList and terms:
            for t in termList:
                if t.lower() in lowerTerms:
                    # prnt(t)
                    order.append(t)
        if terms:
            for t in terms:
                if t not in order:
                    order.append(t)
    return order

@register.filter
def html_json(text):
    return None
    try:
        return text.replace('"', "'").replace('\n', '').strip()
    except:
        return None
    text = ''.join(text.splitlines())
    return text.replace('"', "'").replace('\n', '').strip()
    text = unidecode(text)
    return text.replace('"', "'").replace(';','').replace('\n', '').strip()

@register.filter
def remove_tags(text):
    try:
        TAG_RE = re.compile(r'<[^>]+>')
        text = TAG_RE.sub('', text).replace('"', "'").replace('\n', '').strip()
        text = ''.join(text.splitlines())
        text = unidecode(text)
        return text
    except:
        return None

@register.filter
def short_gov(gov_type):
    try:
        if gov_type == 'Congress':
            return 'Congr.'
        elif gov_type == 'Parliament':
            return 'Parl.'
        else:
            return 'Gov.'
    except:
        return gov_type

@register.filter
def get_toc(obj):
    if obj:
        try:
            toc = None
            if obj._meta.object_name == 'BillText':
                if 'TextNav' in obj.data:
                    toc = obj.data['TextNav']
            elif obj._meta.object_name == 'Update':
                if 'TextNav' in obj.extra:
                    toc = obj.extra['TextNav']
            if toc and isinstance(toc, list):
                return toc
        except Exception as e:
            prnt('get_toc fail', str(e))
            pass
    return None
    
@register.filter
def convert_prntable(text):
    # text = unidecode(text)
    # prntable = set(string.prntable)
    # return ''.join(filter(lambda x: x in prntable, text))
    # return text.encode('ascii',errors='ignore')
    return text

@register.filter
def get_bill_term(hansard, bill):
    d = ''
    try:
        from posts.models import Keyphrase
        for key, value in hansard.list_all_terms():
            try:
                k = Keyphrase.objects.annotate(string=Value(key)).filter(string__icontains=F('text')).filter(bill=bill, hansardItem__hansard=hansard)[0]
                num = value + 1
                term = key
                return "<li><span>(" + str(num) + ")</span>&nbsp; <a href='" + hansard.get_absolute_url() + "/?topic=" + term + "' title='" + term + "'>" + term + " </a></li>"
            except Exception as e:
                # prnt(str(e))
                pass
    except:
        pass
    return d

@register.filter
def match_terms(update, keywords):
    if 'Terms' in update.data and keywords:
        terms = update.data['Terms']
        count = 0
        n = 0
        order = {}
        for t in terms:
            for key, value in t.items():
                if n <= 5 and key in keywords:
                    n += 1
                    if key not in order:
                        order[key] = value
            if n > 5:
                break
        count = n
        extras = 0
        for t in terms:
            if count < 75:
                count += 1
                for key, value in t.items():
                    if key not in order:
                        order[key] = value
            else:
                extras += 1
        return [order, extras]
    else:
        return []

@register.simple_tag
def call_method(obj, method_name, arg):
    return getattr(obj, method_name)(arg)

@register.filter
def list_spren_items(spren):
    # prnt('-list_spren_items')
    try:
        l = []
        for iden, text in spren.data['items'].items():
            l.append((iden, text))
        return l
    except Exception as e:
        prnt('list_spren_items fail',str(e))
        return None

def test_view(request):
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', 'recent')

    context = {
        'sort': sort,
    }
    return render_view(request, context)

def testor_script(num):
        prnt('testor script', num)
        time.sleep(30)
        prnt('done',num)

def splash_view(request):
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    
    if style == 'preload':
        prnt('HI!splash_view')
        context = {
            'title': "Welcome",
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        if style == 'index':
            country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(None)
            current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)
            return render(request, "utils/fetch_index.html", context)
        else:
            from network.models import Sonet
            context = {
                'title': 'Welcome',
                'cards': 'splash',
                'sonet': Sonet.objects.values('Title','LogoLink').first(),
                'supported_regions': Region.supported_objects.filter(is_supported=True).order_by('Name'),
            }
            return render_view(request, context)

def home_view(request, region):
    prnt('--homeview')
    prnt(region)
    
    # user_data, user = get_user_data(request)
    # country, provState, county, city = get_regions(request, region, user)
    
    country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
    chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, gov_dict)
    prnt('country_dict, gov_dict, subRegions, subGovernments',country_dict, gov_dict, subRegions, subGovernments)
    prnt('Chamber', chambers, current_chamber, all_chambers, gov_levels)

    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', 'recent')
    if sort == 'trending':
        sort_link = '?sort=recent'
        sort_type = '-date_time'
    else:
        sort_link = '?sort=trending'
        sort_type = '-date_time'
    if request.user.is_authenticated:
        view = request.GET.get('view', 'Recommended')
    else:
        view = request.GET.get('view', 'Trending')
    page = request.GET.get('page', 1)
    getDate = request.GET.get('date', None)
    if request.user.is_authenticated:
        nav_options = [nav_item('button', f'Chamber: {current_chamber}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'),
                    nav_item('button', f'Page: {page}', 'subNavWidget', 'pageForm'), 
                    nav_item('link', 'Recommended', f'?view=Recommended', None), 
                    nav_item('link', 'Trending', f'?view=Trending', None)]
    else:
        nav_options = [nav_item('button', f'Chamber: {current_chamber}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'),
                    nav_item('button', f'Page: {page}','subNavWidget', 'pageForm'),
                    nav_item('link', 'Trending', f'?view=Trending', None)
                    ]
    cards = 'home_view'
    title = 'The Government of %s' %(country_dict['Name'])
    if style == 'index' and page == 1:
        context = {
            'title': title,
            'nav_bar': nav_options,
            'view': view,
            'cards': cards,
            'sort': sort,
            'style':style
        }
        return render_view(request, context, country=country_dict)
    else:
        if view == 'Recommended':
            include_list = ['Bill', 'Meeting']
            posts, view = algorithim(None, include_list, current_chamber, country_dict, view, page)

        else:   
            include_list = ['Bill','Meeting']
            cards = 'top_cards'
            posts = getTrendingTop(current_chamber, None)
            if posts.count() == 0:
                posts, view = algorithim(None, include_list, current_chamber, country_dict, view, page)
                cards = 'home_view'
        setlist = paginate(posts, page, request)
        prnt('view',view)
        user = None
        if view == 'Recommended' and user and user.UserData_obj:
            userKeys = [k for k, value in Counter(user.UserData_obj.get_interests()).most_common()]
        else:
            if current_chamber == 'House':
                orgs = ['House', 'House of Commons', 'Congress']
            elif current_chamber == 'Senate':
                orgs = ['Senate']
            elif current_chamber == 'All':
                orgs = ['Senate', 'House', 'House of Commons', 'Congress']
            try:
                dateQuery = Statement.objects.filter(meeting_type='Debate', Chamber__in=orgs).order_by('-DateTime')[12].DateTime
                dt = datetime.datetime.now().replace(tzinfo=pytz.UTC) - dateQuery
            except:
                dt = datetime.datetime.now().replace(tzinfo=pytz.UTC) - datetime.datetime.now().replace(tzinfo=pytz.UTC)
            userKeys = get_trending_keys(dt, include_list, orgs)
        daily = None
        if page == 1:
            # daily = getDaily(request, province, getDate)
            pass
        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None
        context = {
            'title': title,
            'nav_bar': nav_options,
            'isApp': isApp,
            'view': view,
            'cards': cards,
            'dailyCard': daily,
            'sort': sort,
            'feed_list':setlist,
            'style':style,
            'useractions': get_useractions(request.user, setlist),
            'myRepVotes': getMyRepVotes(None, setlist),
        }
        return render_view(request, context)

def following_view(request):
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', 'recent')
    view = request.GET.get('view', 'Current')
    page = request.GET.get('page', 1)
    user_data, user = get_user_data(request)
    u = user
    country, provState, county, city = get_regions(request, None, user)
    if not user:
        return redirect('/')
    nav_options = [nav_item('link', 'Current', '?view=Current', None), 
                    nav_item('link', 'Upcoming','?view=Upcoming', None),
                    nav_item('link', 'Following','%s?view=Following' %(user.get_absolute_url()), None)]
    cards = 'home_list'
    title = 'Following'
    if style == 'index':
        context = {
            'title': title,
            'nav_bar': nav_options,
            'view': view,
            'cards': cards,
            'sort': sort,   
        }
        return render_view(request, context)
    else:
        getList = []
        topicList = []
        for p in u.follow_Person.objs.all():
            getList.append(p.id)
        for p in u.follow_Bill_objs.all():
            getList.append('%s?current=True' %(p.NumberCode))
        for p in u.follow_Committee_objs.all():
            getList.append(p.code)
        for p in u.get_follow_topics():
            getList.append(p)
            topicList.append(p)
        posts = Post.objects.filter(Country_obj=country).filter(keyword_array__overlap=getList).filter(date_time__lte=datetime.datetime.strftime(datetime.datetime.now() + datetime.timedelta(days=1), '%Y-%m-%d')).select_related('Meeting', 'Statement','Bill').order_by('-date_time')
        setlist = paginate(posts, page, request)
        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None 
        context = {
            'isApp': isApp,
            'view': view,
            'cards': cards,
            'sort': sort,
            'feed_list':setlist,
            'useractions': get_useractions(user, setlist),
            'topicList': topicList,
        }   
        return render_view(request, context, country=country)

def topic_view(request, region, keyword):
    prnt('-topic_view',keyword)
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', 'Newest')
    view = request.GET.get('view', 'Current')
    keyword = request.GET.get('keyword', keyword)
    page = request.GET.get('page', 1)
    getDate = request.GET.get('date', None)
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, None, user)
    chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, country, provState, county, city)
    follow = request.GET.get('follow', '')
    ordering = get_sort_order(sort)
    if follow and keyword:
        prnt('follow')
        fList = user.get_follow_topics()
        if keyword in fList:
            fList.remove(keyword)
            user = set_keywords(user, 'remove', keyword)
            response = 'Unfollow "%s"' %(keyword)
        elif keyword not in fList:
            fList.append(keyword)
            user = set_keywords(user, 'add', keyword)
            response = 'Following "%s"' %(keyword)
        user.set_follow_topics(fList)
        user.save()
        return render(request, "utils/dummy.html", {"result": response})
    if user and keyword in user.follow_topics:
        f = 'following'
    else:
        f = 'follow'
    try:
        isApp = request.COOKIES['fcmDeviceId']
    except:
        isApp = None
    title = 'Topic: %s' %(keyword)
    if style == 'index' and page == 1:
        nav_options = [nav_item('button', f'Chamber:{current_chamber}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'), 
                        nav_item('button', 'follow', f'react', f'"follow2", "{request.path}?keyword={keyword}&follow={f}"'), 
                        nav_item('link', f'Sort: {sort}', f'?keyword={keyword}&sort={sort}', None)]
        context = {
            'isApp': isApp,
            'title': title,
            'nav_bar': nav_options,
            'view': view,
            'keyword': keyword,
            'cards': 'home_list',
            'sort': sort,
            'gov_levels': gov_levels,
            'style':style,
            'sidebarData': get_trending(request, country, provState, county, city, current_chamber, all_chambers)

            # fix all_chambers in get getTrending

        }
        return render_view(request, context, country=country)
    else:
        getList = [keyword]
        topicList = [keyword]
        if getDate:
            firstDate = datetime.datetime.strptime(getDate, '%Y-%m-%d')
            secondDate = firstDate + datetime.timedelta(days=1)
        else: 
            secondDate = datetime.datetime.now() + datetime.timedelta(hours=1)
            firstDate = secondDate - datetime.timedelta(days=1000)
        posts = Post.objects.filter(Country_obj=country, Chamber__in=chambers).filter(keyword_array__overlap=getList).order_by(ordering,'-DateTime')
        
        try:
            setlist = paginate(posts, page, request)
        except:
            setlist = []
        setlist = paginate(posts, page, request)
        context = {
            'isApp': isApp,
            'view': view,
            'cards': 'home_list',
            'sort': sort,
            'feed_list':setlist,      
            'style':style, 
            'topicList': topicList,
            'keyword': keyword,
            'useractions': get_useractions(user, setlist),
            'isMobile': request.user_agent.is_mobile,
        }
        return render_view(request, context, country=country)

def search_view(request, keyword):
    style = request.GET.get('style', 'index')
    view = request.GET.get('view', '')
    sort = request.GET.get('sort', 'Newest')
    keyword = request.GET.get('keyword', keyword)
    keyword = keyword.lower()
    page = request.GET.get('page', 1)
    search = request.POST.get('post_type', '')
    autoComplete = request.GET.get('search')
    follow = request.GET.get('follow', '')
    cards = 'home_list'
    ordering = get_sort_order(sort)
    title = 'Search: %s' %(search)    
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, None, user)
    chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, country, provState, county, city)
    searchform = SearchForm(initial={'post_type': search})
    subtitle = ''
    if follow and follow != 'following' and follow != 'follow':
        if user:
            fList = user.get_follow_topics()
            topic = follow
            if topic in fList:
                fList.remove(topic)
                response = 'Unfollow "%s"' %(topic)
                user = set_keywords(user, 'remove', topic)
            elif topic not in fList:
                fList.append(topic)
                response = 'Following "%s"' %(topic)
                user = set_keywords(user, 'add', topic)
            user.set_follow_topics(fList)
            user.save()
        else:
            response = 'Please login'
        return render(request, "utils/dummy.html", {"result": response})
    if keyword:
        title = 'Search: %s' %(keyword)
        nav_options.append(nav_item('button', 'follow', f'react("follow2", "{keyword}")'))
        posts = Post.objects.filter(keyword_array__icontains=keyword).exclude(date_time=None).order_by(ordering,'-date_time')
        if posts.count() == 0:
            posts = Archive.objects.filter(keyword_array__icontains=keyword).exclude(date_time=None).order_by(ordering,'-date_time')
        if posts.count() == 1:
            response = redirect(posts[0].get_absolute_url())
            return response
    elif autoComplete:
        keyphrases = Keyphrase.objects.filter(Chamber__iexact__in=Chambers).filter(key__icontains=autoComplete)[:500]
        data = []
        for k in keyphrases:
            if k.key not in data:
                data.append(k.key)
        return JsonResponse({'status':200, 'data':data})
    else:
        posts = {}
    try:
        setlist = paginate(posts, page, request)
    except:
        setlist = []
    try:
        isApp = request.COOKIES['fcmDeviceId']
    except:
        isApp = None 
    nav_options = [nav_item('button', f'Chamber:{Chamber}', 'subNavWidget', 'chamberForm'), 
                    nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'),
                    nav_item('button', 'Sort: %s'%(sort), 'subNavWidget', 'sortForm'), 
                    nav_item('button', 'Search', 'subNavWidget', 'searchForm'), 
                    nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
    context = {
        'isApp': isApp,
        'title': title,
        'subtitle': subtitle,
        'nav_bar': nav_options,
        'sort': sort,
        'sortOptions': ['OLdest','Newest','Loudest','Random'],
        'keyword': keyword,
        'view': view,
        'searchForm': searchform,
        'cards': cards,
        'feed_list':setlist,
        'useractions': get_useractions(user, setlist),
        'myRepVotes': getMyRepVotes(user, setlist),
        'topicList': [keyword],
    }
    return render_view(request, context, country=country)

def region_view(request):

    title = 'My Representatives'
    role_idens = request.GET.get('roles', '')
    user_data, user = get_user_data(request)
    prnt(user)
    nav_options = [nav_item('button', 'Set Region', "modalPopPointer", '"Select Region", "/accounts/get_country_modal"'), nav_item('button', 'Save to Account', "save_regions_to_account", user.id)]
    prnt('role_idens',role_idens)
    def process_me(posts, data):
        for p in posts:
            if p.Role_obj.gov_level == 'Federal':
                level = 'Country'
            else:
                level = p.Role_obj.gov_level
            if p.Role_obj.Country_obj:
                data['country'] = p.Role_obj.Country_obj
            if p.Role_obj.ProvState_obj:
                data['provState'] = p.Role_obj.ProvState_obj
            if p.Role_obj.Region_obj:
                data[level]['region'] = p.Role_obj.Region_obj

            if p.Role_obj.District_obj and p.Role_obj.District_obj.Name in data[level]['districts']:
                data[level]['districts'][p.Role_obj.District_obj.Name]['roles'].append(p)
            elif p.Role_obj.District_obj:
                data[level]['districts'][p.Role_obj.District_obj.Name] = {'district':p.Role_obj.District_obj, 'roles':[p]}
            else:
                data[level]['roles'].append(p)
        for key, value in data.items():
            try:
                data[key]['roles'] = [p for p in data[key]['roles'] if p.Role_obj.Chamber == 'Executive'] + [p for p in data[key]['roles'] if p.Role_obj.Chamber == 'House'] + [p for p in data[key]['roles'] if p.Role_obj.Chamber == 'Senate'] + [p for p in data[key]['roles'] if p.Role_obj.Chamber == None]
            except:
                pass
            try:
                for k, v in data[key]['districts'].items():
                    data[key]['districts']['roles'] = [p for p in data[key]['districts']['roles'] if p.Role_obj.Chamber == 'Executive'] + [p for p in data[key]['districts']['roles'] if p.Role_obj.Chamber == 'House'] + [p for p in data[key]['districts']['roles'] if p.Role_obj.Chamber == 'Senate'] + [p for p in data[key]['districts']['roles'] if p.Role_obj.Chamber == None]
            except:
                pass
        return data
    
    data = {
        'country': None,
        'provState': None,
        'Country':{'region':None, 'districts':{}, 'roles':[]},
        'State':{'region':None, 'districts':{}, 'roles':[]},
        'County':{'region':None, 'districts':{}, 'roles':[]},
        'City':{'region':None, 'districts':{}, 'roles':[]},
            }
    if role_idens:
        id_list = []
        id_list = role_idens.split('_')
        posts = Post.objects.filter(pointerType='Role', Role_obj__id__in=id_list)
        data = process_me(posts, data)
        
    elif user and user.localities:
        localities = json.loads(user.localities)
        regions = Region.objects.filter(id__in=localities)
        districts = District.objects.filter(id__in=localities)
        offices = [office for office in [d.Office_array for d in districts]] + [office for office in [r.Office_array for r in regions]]
        posts = Post.objects.filter(pointerType='Role').filter(Role_obj__Position__in=offices, Update_obj__data__contains={'Current': True}).filter(Q(Role_obj__ProvState_obj__id__in=localities)|Q(Role_obj__District_obj__id__in=localities)|Q(Role_obj__Region_obj__id__in=localities)|Q(Role_obj__Country_obj__id__in=localities))

        data = process_me(posts, data)
    else:
        data = None

    context = {
        'title': title,
        'nav_bar': nav_options,
        'cards': 'region_form',
        'data':data,
    }
    return render_view(request, context)

def subregions_modal_view(request, region, regionType, baseLink):
    prnt('-subregions_modal_view',region)
    if baseLink.startswith('/'):
        baseLink = baseLink[1:]
    baseLink = region + '/' + baseLink
    pRegion = Region.supported_objects.filter(Name=region, nameType=regionType).first()
    subRegions = Region.supported_objects.filter(ParentRegion_obj=pRegion)
    context = {
        'title': 'Regions',
        'subRegions': subRegions,
        'baseLink' : baseLink,
    }
    return render(request, "modals/regions_modal.html", context)



def chains_view(request):
    prnt('-chains_view')
    
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'time')
    page = request.GET.get('page', 1)
    view = request.GET.get('view', 'Current')
    date = request.POST.get('date')
    title = 'Blockchains'
    if style == 'preload':
        prnt('preload')
        context = {
            'title': title,
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None
        if style == 'index':
            prnt('index')
            context = {}
            # context = get_index(request, country_dict, gov_dict)
            # context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            
            nav_options = []
            if include_nav == 'True':
                nav_options = [
                    # nav_item('button', f'Chamber: {current_chamber_name}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'),
                        nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                        nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
            subtitle = ''
            user_data, user = get_user_data(request)
            posts = Blockchain.objects.all().defer('queuedData').order_by('-updated_on_node')
            
            setlist = paginate(posts, page, request)
            context = {
                'isApp': isApp,
                'title': title,
                'subtitle': subtitle,
                'view': view,
                'cards': 'chains_list',
                'sort': sort,
                'feed_list':setlist,      
                'style':style, 
                'isMobile': request.user_agent.is_mobile,
                'nav_bar': nav_options,
            }
            return render_view(request, context)


def chain_view(request, chain_id):
    prnt('-chain_view')
    
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'time')
    page = request.GET.get('page', 1)
    view = request.GET.get('view', 'Current')
    date = request.POST.get('date')
    title = Blockchain.objects.filter(id=chain_id).only('genesisName').first().genesisName
    if style == 'preload':
        prnt('preload')
        context = {
            'title': title,
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None
        if style == 'index':
            prnt('index')
            context = {}
            # context = get_index(request, country_dict, gov_dict)
            # context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            
            nav_options = []
            if include_nav == 'True':
                nav_options = [
                    # nav_item('button', f'Chamber: {current_chamber_name}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'),
                        nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                        nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
            subtitle = ''
            user_data, user = get_user_data(request)
            posts = Block.objects.filter(Blockchain_obj__id=chain_id).order_by('-DateTime')
            setlist = paginate(posts, page, request)
            context = {
                'isApp': isApp,
                'title': title,
                'subtitle': subtitle,
                'view': view,
                'cards': 'chain_list',
                'sort': sort,
                'feed_list':setlist,      
                'style':style, 
                'isMobile': request.user_agent.is_mobile,
                'nav_bar': nav_options,
            }
            return render_view(request, context)

