
from django.shortcuts import render

from posts.forms import AgendaForm, SearchForm
from posts.utils import (
    get_cookies, get_regions_and_govs, get_chambers, set_session_data, algorithim, fetch_updated_objs,
    get_index, get_trending, get_user_sending_data, nav_item, get_user_data, getTrendingTop, default_setup,
    algorithim, get_trending_keys, paginate, get_useractions, render_view, get_regions, get_isMobile
    )
from posts.models import Region, Post, Spren
from utils.models import get_operator_obj, skipwords
from legis.models import BillText,Meeting,Statement,Motion,RepVote,Election,Person
from utils.models import prnt, now_utc, is_id

from django.db.models import Q
import datetime
from collections import Counter
import pytz
import json
import string
from operator import itemgetter as _itemgetter
import re



def house_or_senate_hansards_view(request, region):
    prnt('-house/senate hansard view')
    
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'time')
    page = request.GET.get('page', 1)
    view = request.GET.get('view', 'Current')
    date = request.POST.get('date')
    form = AgendaForm()
    title = 'Debates'
    r = default_setup(request, title, region, 'legis')
    if r:
        return r
    
    # # if style == 'preload':
    # #     prnt('preload')
    # #     context = {
    # #         'title': 'Debates',
    # #         'style':style,
    # #     }
    # #     return render(request, "home.html", get_cookies(request,context))
    # # else:
    country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
    current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
    #     prnt('country_dict, gov_dict, subRegions, subGovernments',country_dict, gov_dict, subRegions, subGovernments)
    #     prnt('Chamber', current_chamber_list, current_chamber_name, all_chambers, gov_levels)
    #     request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)

    #     try:
    #         isApp = request.COOKIES['fcmDeviceId']
    #     except:
    #         isApp = None
    #     if style == 'index':
    #         prnt('index')
    #         context = get_index(request, country_dict, gov_dict)
    #         context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
    #         context = get_user_sending_data(user_id, context)
    #         return render(request, "utils/index.html", context)
    #     else:
    if current_chamber_name == 'All':
        title = '%s Debates' %('All')
    else:   
        title = '%s Debates' %(current_chamber_name)
    nav_options = []
    if include_nav == 'True':
        nav_options = [nav_item('button', f'Chamber: {current_chamber_name}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'),
                nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
    subtitle = ''
    user_data, user = get_user_data(request)
    if request.method == 'POST':
        date = datetime.datetime.strptime(date, '%Y-%m-%d')
        subtitle = date
        view = None
        posts = Post.objects.filter(Country_obj__id=country_dict['id'], Meeting_obj__meeting_type='Debate', Meeting_obj__DateTime__gte=date, Meeting_obj__DateTime__lt=date + datetime.timedelta(days=1)).filter(Meeting_obj__Chamber__in=current_chamber_list).select_related('Meeting_obj').order_by('-Meeting_obj__DateTime','Meeting_obj__Title')

    else:
        if view == 'Current':
            # posts = Post.objects.filter(Country_obj=country, Meeting_obj__meeting_type__iexact='Debate', DateTime__lte=now_utc() + datetime.timedelta(hours=12)).filter(Meeting_obj__Chamber__in=Chambers).select_related('Meeting_obj').order_by('-Meeting_obj__DateTime')
            posts = Post.objects.filter(Country_obj__id=country_dict['id'], Meeting_obj__meeting_type__iexact='Debate').filter(Meeting_obj__Chamber__in=current_chamber_list).select_related('Meeting_obj').order_by('-Meeting_obj__DateTime','Meeting_obj__Title')
            
        elif view == 'Recommended':
            include_list = ['Statement']
                        #   algorithim(user, include_list, chamber_list, country_dict, view='Recommended', page=1, provState_name=None)
            posts, view = algorithim(user, include_list, current_chamber_list, country_dict, view, page)
            # posts, view = algorithim(request, include_list, Chamber, region, view, page)
        elif view == 'Trending':
            include_list = ['Meeting']
            posts, view = algorithim(user, include_list, current_chamber_list, country_dict, view, page)
            # posts, view = algorithim(request, include_list, Chamber, region, view, page)
    
    
    if view != 'Trending' and user and user.UserData_obj:
        userKeys = [k for k, value in Counter(user.UserData_obj.get_interests()).most_common()]
    else:
        try:
            dateQuery = Meeting.objects.filter(Country_obj__id=country_dict['id'], meeting_type='Debate', Chamber__in=current_chamber_list).order_by('-DateTime')[12].DateTime
        except:
            dateQuery = now_utc()
        dt = now_utc().replace(tzinfo=pytz.UTC) - dateQuery
        userKeys = get_trending_keys(dt, ['Meeting'], current_chamber_list)
    setlist = paginate(posts, page, request)
    context = {
        # 'isApp': isApp,
        'title': title,
        'subtitle': subtitle,
        'view': view,
        'dateForm': form,
        'cards': 'debates_list',
        'sort': sort,
        'feed_list':setlist,      
        'style':style, 
        'user_keywords': userKeys,
        'useractions': get_useractions(user, setlist),
        'isMobile': request.user_agent.is_mobile,
        'nav_bar': nav_options,
    }
    return render_view(request, context, country_dict, 'legis')

def debate_view(request, region, chamber, govNumber, session, iden, year, month, day, hour, minute):
    prnt('-hansard _view')
    govNumber = re.sub("[^0-9]", "", govNumber)
    session = re.sub("[^0-9]", "", session)
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'Earliest')
    page = request.GET.get('page', 1)
    speaker_id = request.GET.get('speaker', '')
    speaker_name = request.GET.get('speakerName', '')
    topic = request.GET.get('topic', '')
    business = request.GET.get('business', '')
    view = request.GET.get('view', '')
    id = request.GET.get('id', '')
    time = request.GET.get('time', '')
    instruction = None
    userData = None
    if style == 'preload':
        prnt('preload')
        context = {
            'title': 'Debates',
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        # ordering = get_sort_order(sort)
        if sort == 'Earliest':
            ordering = 'Statement_obj__order', 'Statement_obj__created', 'Statement_obj__DateTime'
        else:
            ordering = '-Statement_obj__order', '-Statement_obj__created', '-Statement_obj__DateTime'
        prnt('ordering', ordering)
        user_data, user = get_user_data(request)
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
        prnt('country_dict, gov_dict, subRegions, subGovernments',country_dict, gov_dict, subRegions, subGovernments)
        prnt('Chamber', current_chamber_list, current_chamber_name, all_chambers, gov_levels)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)

        video_link = None
        prnt('topic', topic)
        if '_' in iden or len(iden) < 33:
            p = Post.objects.filter(Meeting_obj__Title__iexact=iden.replace('_',' ')).first()
        else:
            p = Post.objects.filter(Meeting_obj__id=iden).first()
        m = p.Meeting_obj
        meetingUpdate = p.Update_obj
        sprenPost = None
        if style == 'index':
        
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            f = 'follow'
            nav_options = []
            title = None
            title_link = None
            if include_nav == 'True':
                nav_options = [ 
                    nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                    nav_item('button', 'Sort: %s'%(sort), 'subNavWidget', 'sortForm', fields=['Earliest', 'Latest'], key='sort'), 
                    nav_item('link', 'follow', '%s?topic=%s&follow=%s' %(m.get_absolute_url(), topic, f), None), 
                    nav_item('link', 'Transcript', m.GovPage, None, new_tab=True),]

                title = f'{m.meeting_type} {str(m.Title)}'
                for c in current_chamber_list:
                    if c in chamber:
                        title = f'{c} {m.meeting_type} {str(m.Title)}'
                        break
                title_link = m.get_absolute_url(),
            
            if m.Region_obj.timezone:
                tz = m.Region_obj.timezone
            else:
                tz = 'US/Eastern'
            hasContext = True
            # prnt('topic',topic)
            if topic or speaker_id:
                hasContext = False
            elif page == 1 and sort.lower() == 'oldest':
                seconds = '00'
                try:
                    videoUrl = json.loads(meetingUpdate.data)['VideoUrl']
                except:
                    agendaUpdate = Post.objects.filter(Agenda_obj=m.Agenda_obj).first().Update_obj
                    if agendaUpdate:
                        videoUrl = json.loads(agendaUpdate.data)['VideoUrl']
                    else:
                        videoUrl = None
                if videoUrl:
                    ...
            follow = request.GET.get('follow', '')
            if follow and topic and request.user.is_authenticated:
                fList = request.user.get_follow_topics()
                if topic in fList:
                    instruction = 'follow_topics remove "%s"' %(topic)
                elif topic not in fList:
                    instruction = 'follow_topics add "%s"' %(topic)
                return render(request, "utils/dummy.html", {"result": 'success', 'userData': get_user_sending_data(user), 'instruction':instruction})
            wordCloud = None
            if topic:
                hasContext = False
                search = [f'{topic}']
                if speaker_id:
                    if is_id(speaker_id):
                        posts = Post.objects.filter(Statement_obj__Meeting_obj=m).filter(Statement_obj__Person_obj__id=speaker_id).filter(Q(Statement_obj__Terms_array__overlap=search)|Q(Statement_obj__keyword_array__overlap=search)).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
                    else:
                        posts = Post.objects.filter(Statement_obj__Meeting_obj=m).filter(Statement_obj__Person_obj__GovIden=speaker_id).filter(Q(Statement_obj__Terms_array__overlap=search)|Q(Statement_obj__keyword_array__overlap=search)).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
                else:
                    posts = Post.objects.filter(Statement_obj__Meeting_obj=m).filter(Q(Statement_obj__SubjectOfBusiness__icontains=topic)|Q(Statement_obj__Terms_array__overlap=search)|Q(Statement_obj__keyword_array__overlap=search)).order_by(*ordering)

                spren = Spren.objects.filter(pointerId=m.id, re=topic, type='Meeting_topic').first()
                if spren:
                    sprenPost = spren.get_post()
                prnt('sprenPost',sprenPost)
            elif business:
                hasContext = False
                if '___' in business:
                    a = business.find('___')
                    business = business[:a]
                x = business.replace('_',' ').replace('...','')
                posts = Post.objects.filter(Statement_obj__Meeting_obj=m).filter(Q(Statement_obj__OrderOfBusiness__icontains=x.strip())|Q(Statement_obj__SubjectOfBusiness__icontains=x.strip())).order_by(*ordering)

            elif speaker_id:
                if len(speaker_id) > 33:
                    posts = Post.objects.filter(Statement_obj__Meeting_obj=m).filter(Statement_obj__Person_obj__id=speaker_id).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
                else:
                    posts = Post.objects.filter(Statement_obj__Meeting_obj=m).filter(Statement_obj__Person_obj__GovIden=speaker_id).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
            elif speaker_name:
                speaker_name = speaker_name.replace('_',' ')
                posts = Post.objects.filter(Statement_obj__Meeting_obj=m).filter(Statement_obj__PersonName__iexact=speaker_name).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
            
            elif time:
                prnt('time', time)
                date_time = '%s/%s/%s/%s' %(m.DateTime.year, m.DateTime.month, m.DateTime.day, time)
                prnt(date_time)
                dt = datetime.datetime.strptime(date_time, '%Y/%m/%d/%I:%M%p')
                posts = Post.objects.filter(Statement_obj__Meeting_obj=m, Statement_obj__DateTime__gte=dt).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
            elif id and is_id(id):
                statement = Statement.objects.filter(id=id).first()
                prnt('statement',statement)
                if statement and statement.order:
                    order_list = list(range(statement.order - 10, statement.order + 11))
                    posts = Post.objects.filter(Statement_obj__Meeting_obj=m, Statement_obj__order__in=order_list).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
                elif statement:
                    posts = Post.objects.filter(Statement_obj__Meeting_obj=m).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)

            else:
                posts = Post.objects.filter(Statement_obj__Meeting_obj=m).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by(*ordering)
            if id:
                setlist = paginate(posts, 'id=%s' %(id), request)
                statement = setlist[0].Statement_obj
                if statement.order:
                    hasContext = statement.order
                else:
                    hasContext = statement.id
                video_link = None
            else:
                setlist = paginate(posts, page, request)
            prnt('posts len',len(posts))
            try:
                isApp = request.COOKIES['fcmDeviceId']
            except:
                isApp = None
            context = {
                'isApp': isApp,
                'cards': 'debate_view',
                'view': view,
                'sort': sort,
                'page': page,
                'style': style,
                'topic': topic,
                'id': id,
                'time': time,
                'speaker_id': speaker_id,
                'feed_list':setlist,
                'useractions': get_useractions(user, setlist),
                'debate': m,
                'debateUpdate': meetingUpdate,
                'sprenPost': sprenPost,
                'video_link': video_link,
                'hasContext': hasContext,
                'wordCloud': wordCloud,
                'topicList': [topic],
                'nav_bar': nav_options,
                'feed_title': title,
                'title_link': title_link,
            }
            return render_view(request, context, country=country_dict)


def citizenry_view(request, region):
    style = request.GET.get('style', 'index')
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    context = {
        'title': 'Citizenry',
        'cards': 'citizenry',
    }
    return render_view(request, context, country=country)

def citizen_debates_view(request, region):
    style = request.GET.get('style', 'index')
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    context = {
        'title': 'Citizen Debates',
        'cards': 'citizenry',
    }
    return render_view(request, context, country=country)

def citizen_bills_view(request, region):
    style = request.GET.get('style', 'index')
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    context = {
        'title': 'Citizen Bills',
        'cards': 'citizenry',
    }
    return render_view(request, context, country=country)

def polls_view(request, region):
    style = request.GET.get('style', 'index')
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    context = {
        'title': 'Polls',
        'cards': 'citizenry',
    }
    return render_view(request, context, country=country)

def petitions_view(request, region):
    style = request.GET.get('style', 'index')
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    context = {
        'title': 'Petitions',
        'cards': 'citizenry',
    }
    return render_view(request, context, country=country)

def someta_view(request):
    style = request.GET.get('style', 'index')
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, None, user)
    context = {
        'title': 'SoMeta',
        'cards': 'citizenry',
    }
    return render_view(request, context, country=country)

def legislature_view(request, region):
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'recent')
    if sort == 'trending':
        sort_link = '?sort=recent'
        sort_type = '-DateTime'
    else:
        sort_link = '?sort=trending'
        sort_type = '-DateTime'
    view = request.GET.get('view', 'Current')
    page = request.GET.get('page', 1)
    getDate = request.GET.get('date', None)
    date = request.POST.get('date')
    title = 'Legislature'
    r = default_setup(request, title, region, 'legis')
    if r:
        return r
    # if style == 'preload':
    #     prnt('preload')
    #     context = {
    #         'title': 'Legislature',
    #         'style':style,
    #     }
    #     return render(request, "home.html", get_cookies(request,context))
    # else:
    country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
    current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
    # prnt('country_dict, gov_dict, subRegions, subGovernments',country_dict, gov_dict, subRegions, subGovernments)
    # prnt('Chamber', current_chamber_list, current_chamber_name, all_chambers, gov_levels)
    # request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)
    
        # if style == 'index':
        #     context = get_index(request, country_dict, gov_dict)
        #     context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
        #     context = get_user_sending_data(user_id, context)
        #     return render(request, "utils/fetch_index.html", context)
        # else:
    nav_options = []
    if include_nav == 'True':
        nav_options = [
            nav_item('button', f'Chamber: {current_chamber_name}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'),
            nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
            nav_item('link', 'Current', '?view=Current', None), 
            nav_item('link', 'Recommended', '?view=Recommended', None), 
            nav_item('link', 'Trending', '?view=Trending', None)
            ]

    form = AgendaForm()
    title = f'{country_dict["Name"]} Legislature!'
    subtitle = ''
    cards = 'home_list'
    if view == 'Upcoming':
        include_list = ['Bill','Meeting', 'Motion']
        posts = Post.objects.filter(Country_obj__id=country_dict['id'], DateTime__gte=datetime.datetime.now() - datetime.timedelta(hours=1)).filter(pointerType__in=include_list).order_by('date_time', 'id')
    elif view == 'Current':
        prnt('currret')
        include_list = ['Bill','Meeting', 'Motion']
        if getDate:
            firstDate = datetime.datetime.strptime(getDate, '%Y-%m-%d')
            secondDate = firstDate + datetime.timedelta(days=1)
        else: 
            secondDate = datetime.datetime.now() + datetime.timedelta(hours=1)
            firstDate = secondDate - datetime.timedelta(days=1000)
        
        posts = Post.objects.filter(Country_obj__id=country_dict['id'], Chamber__in=current_chamber_list).filter(DateTime__gte=firstDate, DateTime__lt=secondDate).filter(pointerType__in=include_list).order_by(sort_type, 'id')
        prnt('posts len',len(posts))
    elif view == 'Recommended':
        include_list = ['Bill','Meeting']
        posts, view = algorithim(user_id, include_list, current_chamber_list, country_dict, view, page)
    elif view == 'Trending':
        include_list = ['Bill','Meeting']
        posts = getTrendingTop(current_chamber_name, country_dict)
        cards = 'top_cards'
    if view != 'Trending' and False:
        userKeys = [k for k, value in Counter(json.loads(user.localities)).most_common()]
    else:
        try:
            if current_chamber_name == 'All':
                dateQuery = Meeting.objects.filter(meeting_type='Debate', Country_obj__id=country_dict['id'], Chamber__in=current_chamber_list).order_by('-DateTime')[12].DateTime
            else:
                dateQuery = Meeting.objects.filter(meeting_type='Debate', Country_obj__id=country_dict['id'], Chamber=current_chamber_name).order_by('-DateTime')[12].DateTime
            dt = datetime.datetime.now().replace(tzinfo=pytz.UTC) - dateQuery
        except:
            dt = datetime.datetime.now().replace(tzinfo=pytz.UTC) - datetime.datetime.now().replace(tzinfo=pytz.UTC)
        userKeys = get_trending_keys(dt, include_list, current_chamber_list)
    setlist = paginate(posts, page, request)
    daily = None
    if page == 1:
        pass
    try:
        isApp = request.COOKIES['fcmDeviceId']
    except:
        isApp = None
    context = {
        'isApp': isApp,
        'title': title,
        'subtitle': subtitle,
        'nav_bar': nav_options,
        'view': view,
        'region': region,
        'dateForm': form,
        'user_keywords': userKeys,
        'dailyCard': daily,
        'cards': cards,
        'sort': sort,
        'filter': current_chamber_name,
        'feed_list':setlist,
        'useractions': get_useractions(user_id, setlist),
        # 'myRepVotes': getMyRepVotes(user_id, setlist),
    }
    return render_view(request, context, country=country_dict)
        

def agendas_view(request, region, Chamber):
    prnt('-agenda_view')
    cards = 'agenda_list'
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', 'time')
    page = request.GET.get('page', 1)
    view = request.GET.get('view', 'past')
    date = request.POST.get('date')
    search = request.POST.get('post_type')
    dateform = AgendaForm()
    searchform = SearchForm()
    subtitle = ''
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, country, provState, county, city, chamber=Chamber)
    if request.method == 'POST':
        if date:
            date = datetime.datetime.strptime(date, '%Y-%m-%d')
            subtitle = date
            view = None
            posts = Post.objects.filter(Country_obj=country, Agenda__Chamber__in=Chambers, date_time__gte=date, date_time__lt=date + datetime.timedelta(days=1)).filter(pointerType='Agenda').order_by('-date_time')
        elif search:
            subtitle = search
            view = None
            agendaItems = AgendaItem.objects.filter(text__icontains=search)
            search_list = []
            for i in agendaItems:
                search_list.append(i.agendaTime)
            posts = Post.objects.filter(AgendaTime__in=search_list).select_related('AgendaTime').order_by('-date_time')
    else:
        posts = Post.objects.filter(pointerType='Agenda', Agenda__Chamber__in=Chambers).select_related('Agenda').order_by('-date_time')
    if Chamber == 'All':
        title = 'Agendas'
        h = '/House-agendas'
        s = '/Senate-agendas'
    elif Chamber == 'House':
        title = '%s Agendas' %(Chamber)
        h = '/agendas'
        s = '/Senate-agendas'
    elif Chamber == 'Senate':
        title = '%s Agendas' %(Chamber)
        h = '/House-agendas'
        s = '/agendas'
    setlist = paginate(posts, page, request)
    try:
        isApp = request.COOKIES['fcmDeviceId']
    except:
        isApp = None   
    nav_options = [
        nav_item('link', 'House', h, None), 
        nav_item('link', 'Senate', s, None), 
        nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
        nav_item('button', 'Search', 'subNavWidget', 'searchForm'), 
        nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
    context = {
        'isApp': isApp,
        'title': title,
        'subtitle': subtitle,
        'nav_bar': nav_options,
        'view': view,
        'filter': Chamber,
        'dateForm': dateform,
        'searchForm': searchform,
        'cards': cards,
        'sort': sort,
        'feed_list':setlist,
        'useractions': get_useractions(user, setlist),
    }
    return render_view(request, context, country=country)

def bill_view(request, region, chamber, govNumber, session, numcode):
    prnt('-bill_view')
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'new')
    view = request.GET.get('view', 'Overview')
    page = request.GET.get('page', 1)
    reading = request.GET.get('reading', '')
    getSpren = request.GET.get('getSpren', '')

    if style == 'preload':
        context = {
            'title': 'Bill',
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        topicList = []
        user_data, user = get_user_data(request)
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)
        if view == 'LatestText':
            reading = 'LatestText'
        if sort == 'old':
            changeSort = 'new'
            ordering = 'DateTime'
            order2 = 'id'
        else:
            changeSort = 'old'
            ordering = '-DateTime'
            order2 = '-id'
        billPost = Post.objects.filter(Bill_obj__NumberCode=numcode, Bill_obj__Government_obj__GovernmentNumber=govNumber, Bill_obj__Government_obj__SessionNumber=session).first()
        if not billPost:
            billPost = Archive.objects.filter(Bill_obj__NumberCode=numcode, Bill_obj__Government_obj__GovernmentNumber=govNumber, Bill_obj__Government_obj__SessionNumber=session).first()

        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None
        
        if style == 'index':
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            if view.lower() == 'text':
                if billPost.Update_obj and 'billText_obj' in billPost.Update_obj.data:
                    billText = BillText.objects.filter(id=billPost.Update_obj.data['billText_obj']).first()
                    context['billText'] = billText
            return render(request, "utils/fetch_index.html", context)

        else:
            nav_options = []
            title = None
            title_link = None
            billText = None
            if include_nav == 'True':
                nav_options = [nav_item('link', 'Overview', '%s?view=Overview' %(billPost.Bill_obj.get_absolute_url()), None), 
                            nav_item('link', 'Text', '%s?view=Text' %(billPost.Bill_obj.get_absolute_url()), None), 
                            nav_item('link', 'Debates', '%s?view=Debates' %(billPost.Bill_obj.get_absolute_url()), None), 
                            nav_item('link', 'Motions', '%s?view=Motions' %(billPost.Bill_obj.get_absolute_url()), None),
                            nav_item('link', 'Updates', '%s?view=Updates' %(billPost.Bill_obj.get_absolute_url()), None),
                            nav_item('link', 'Work', '%s?view=Work' %(billPost.Bill_obj.get_absolute_url()), None)]
                title =  f"{billPost.Bill_obj.Chamber} {billPost.Bill_obj.BillDocumentTypeName}",
                title_link =  billPost.Bill_obj.get_absolute_url(),
            updatedVersion = None
            if getSpren and user and user.is_superuser:
                billPost.Bill_obj.getSpren(False)
            if view.lower() == 'work':
                posts = Post.objects.filter(pointerType='Meeting', Country_obj__id=country_dict['id'], Update_obj__data__Terms__icontains=billPost.Bill_obj.NumberCode).order_by(ordering)
            elif view.lower() == 'debates':
                posts = Post.objects.filter(**{f"Statement_obj__bill_dict__{billPost.Bill_obj.NumberCode}__obj_id": billPost.Bill_obj.id}).filter(Country_obj__id=country_dict['id']).order_by(ordering, order2)

                topicList = [billPost.Bill_obj.NumberCode]
            elif view.lower() == 'motions':
                posts = Post.objects.filter(pointerType='Motion', Country_obj__id=country_dict['id'], Motion_obj__Bill_obj=billPost.Bill_obj).order_by(ordering)
            elif view.lower() == 'text':
                if billPost.Update_obj and 'billText_obj' in billPost.Update_obj.data:
                    billText = BillText.objects.filter(id=billPost.Update_obj.data['billText_obj']).first()
                prnt('billText',billText)
                posts = {}
            elif view.lower() == 'updates':
                posts = Post.objects.filter(pointerType='GenericModel', Country_obj__id=country_dict['id'], GenericModel_obj__pointerId=billPost.Bill_obj.id).order_by(ordering, order2)
            else:
                posts = Post.objects.filter(Q(Motion_obj__Bill_obj=billPost.Bill_obj)|Q(pointerType='Meeting')&Q(Update_obj__data__Terms__icontains=billPost.Bill_obj.NumberCode)).filter(Country_obj__id=country_dict['id']).order_by(ordering, order2)
                prnt('postsoverview', posts)
                topicList = [billPost.Bill_obj.NumberCode]
            prnt("%s Bill" %(billPost.Bill_obj.Chamber))
            prnt('posts len:',len(posts))
            if posts:
                setlist = paginate(posts, page, request)
            else:
                setlist = {}
            useractions = get_useractions(request.user, setlist) 
            
            context = {
                'isMobile': get_isMobile(request),
                'isApp': isApp,
                'cards': 'bill_view',
                'sort': sort,
                'view': view,
                'post': billPost,
                'billText': billText,
                'page':page,
                'style':style,
                'feed_list': setlist,
                'useractions': useractions,
                'topicList': topicList,
                'nav_bar': nav_options,   
                'feed_title': title,
                'title_link': title_link,
            }
            return render_view(request, context, country=country_dict)
    
def bills_view(request, region):
    prnt('-bills_view')
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'Latest')
    page = request.GET.get('page', 1)
    hasText = request.GET.get('hasText', None)
    getDate = request.GET.get('date', None)
    date = request.GET.get('date', None)
    search = request.GET.get('search', None)
    subtitle = ''
    if style == 'preload':
        context = {
            'title': 'Bills',
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
        prnt('country_dict',country_dict, 'current_chamber_list',current_chamber_list,'current_chamber_name',current_chamber_name)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)

        if sort == 'Latest':
            ordering = '-DateTime'
        elif sort == 'Newest':
            ordering = '-Bill_obj__created'
        else:
            ordering = '-DateTime'

        if not hasText:
            hasText = request.GET.get('billsHaveText', None)
            if not hasText:
                try:
                    hasText = request.session['billsHaveText']
                except Exception as e:
                    hasText = 'True'
        try:
            request.session.setdefault('billsHaveText', hasText)
            request.session['billsHaveText'] = hasText
        except:
            pass
        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None
        
        if style == 'index':
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            nav_options = []
            title = None
            if include_nav == 'True':
                nav_options = [nav_item('button', f'Chamber: {current_chamber_name}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'),
                            nav_item('button', 'Sort: %s'%(sort), 'subNavWidget', 'sortForm', fields=['Latest','For You','Trending','Newest'], key='sort'),  
                            nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                            nav_item('button', 'HasText: %s'%(hasText), 'subNavWidget', 'hasTextForm', fields=['True','False','Either'], key='hasText'),  
                                nav_item('button', 'Search', 'subNavWidget', 'searchForm'), 
                                nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
                if current_chamber_name.lower() == 'all':
                    title = "Government Bills"
                else:
                    title = '%s Bills' %(current_chamber_name.replace('-', ' '))
            if date:
                hasText = 'Either'
                date = datetime.datetime.strptime(date, '%Y-%m-%d')
                subtitle = date
                view = None
                posts = Post.objects.filter(pointerType='Bill', DateTime__gte=date, DateTime__lt=date + datetime.timedelta(days=1)).filter(Country_obj__id=country_dict['id'], Bill_obj__Chamber__in=current_chamber_list).select_related('Bill_obj', 'Bill_obj__Person_obj').order_by(ordering, '-DateTime')
                if title and current_chamber_name.lower() == 'all':
                    title = "Government Bills"
                elif title:
                    title = '%s Bills' %(current_chamber_name.replace('-', ' '))
            elif search:
                hasText = 'Either'
                prnt('search',search)
                subtitle = search
                view = None


                # from django.contrib.contenttypes.models import ContentType
                # ct = ContentType.objects.get_for_model(TargetModel)
                # single DB hit because target_ids is lazy
                # target_ids = TargetModel.objects.filter(datetime=myDT).values_list('id', flat=True)
                # matches = MyModel.objects.filter(content_type=ct, object_id__in=target_ids)


                # if you know in advance which models the GenericFK might point to and want more control (e.g. applying .only() or extra filtering per target model), you can use this:
                
                # from django.contrib.contenttypes.prefetch import GenericPrefetch
                # Comment.objects.prefetch_related(
                #     GenericPrefetch('target', [TargetA.objects.all(), TargetB.objects.all()])
                # )
                # This tells Django explicitly "the target could be one of these querysets," so it prefetches from each and matches by content type — useful when you want to customize the querysets (e.g. TargetA.objects.only('id', 'datetime')) rather than fetching full rows.

                # else

                # bad:
                # Comment.objects.select_related('target')  # FieldError — target is a GenericForeignKey
                # good:
                # comments = Comment.objects.prefetch_related('target')
                # for c in comments:
                #     print(c.target)  # no extra query per row


                # further examples:

                # comments = Comment.objects.prefetch_related(
                #     GenericPrefetch('target', [
                #         Article.objects.select_related('author'),
                #         Product.objects.select_related('manufacturer'),
                #     ])
                # )
                # for c in comments:
                #     t = c.target
                #     if isinstance(t, Article):
                #         print(t.author.name)      # no extra query
                #     elif isinstance(t, Product):
                #         print(t.manufacturer.name)  # no extra query

                # and

                # If you're rendering a list of comments and just need a couple of fields per target, don't pull whole rows:
                # from django.contrib.contenttypes.prefetch import GenericPrefetch

                # comments = Comment.objects.prefetch_related(
                #     GenericPrefetch('target', [
                #         Article.objects.only('id', 'title'),
                #         Product.objects.only('id', 'name', 'price'),
                #     ])
                # )




                posts = Post.objects.filter(pointerType='Bill').filter(Country_obj__id=country_dict['id'], Bill_obj__Chamber__in=current_chamber_list).filter(Q(Bill_obj__amendedNumberCode__icontains=search)|Q(Bill_obj__NumberCode__icontains=search)|Q(Bill_obj__Title__icontains=search)|Q(Bill_obj__ShortTitle__icontains=search)).select_related('Bill_obj', 'Bill_obj__Person_obj').order_by(ordering, '-DateTime')
            else:

                if sort == 'For You':
                    include_list = ['bill']
                    posts, view = algorithim(None, include_list, all_chambers, country_dict, view='Recommended', page=page)
                elif sort == 'Trending':
                    include_list = ['bill']
                    posts, view = algorithim(None, include_list, all_chambers, country_dict, view='Trending', page=page)
                else:
                    if getDate:
                        firstDate = datetime.datetime.strptime(getDate, '%Y-%m-%d')
                        secondDate = firstDate + datetime.timedelta(days=1)
                    else: 
                        secondDate = datetime.datetime.now() + datetime.timedelta(hours=1)
                        firstDate = secondDate - datetime.timedelta(days=1000)

                    if hasText.lower() == 'true':
                        posts = Post.objects.filter(pointerType='Bill', Region_obj__id=country_dict['id'], filters__Chamber__in=current_chamber_list).filter(filters__contains={'has_text': True}).select_related('Bill_obj', 'Bill_obj__Person_obj').order_by(ordering, '-DateTime')
                    elif hasText.lower() == 'false':
                        posts = Post.objects.filter(pointerType='Bill', Region_obj__id=country_dict['id'], filters__Chamber__in=current_chamber_list).exclude(filters__contains={'has_text': True}).select_related('Bill_obj', 'Bill_obj__Person_obj').order_by(ordering, '-DateTime')
                    else:
                        posts = Post.objects.filter(pointerType='Bill').filter(Region_obj__id=country_dict['id'], filters__Chamber__in=current_chamber_list).select_related('Bill_obj', 'Bill_obj__Person_obj').order_by(ordering, '-DateTime')
                    if title and current_chamber_name.lower() == 'all':
                        title = "Government Bills"
                    elif title:
                        title = '%s Bills' %(current_chamber_name.replace('-', ' '))
                    prnt('posts len',posts.count())

            setlist = paginate(posts, page, request)
            context = {
                'isApp': isApp,
                'view': sort,
                'cards': 'bills_list',
                'sort': sort,
                'feed_list':setlist,
                'searchForm': SearchForm(),
                'useractions': get_useractions(request.user, setlist),
                'page':page,
                'style':style,
                'isMobile': get_isMobile(request),
                'nav_bar': nav_options,
                'feed_title': title,
                'self_node': get_operator_obj('self_nodeId'),
            }
            return render_view(request, context, country=country_dict)
    
    
def elections_view(request, region):
    prnt('-elections view')
    title = "Upcoming Elections"
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', '')
    if request.user.is_authenticated:
        view = request.GET.get('view', 'My Elections')
    else:
        view = request.GET.get('view', 'All Elections')
    page = request.GET.get('page', 1)
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, country, provState, county, city, chamber=None)

    if user and view == 'My Elections':
        posts = Post.objects.filter(pointerType='Election').filter(Election_obj__end_date__gte=datetime.datetime.now()-datetime.timedelta(days=30)).exclude(Election_obj__District_obj=None).filter(Q(Election_obj__District_obj=user.Federal_District_obj)|Q(Election_obj__District_obj=user.ProvState_District_obj)|Q(Election_obj__District_obj=user.Greater_Municipal_District_obj)|Q(Election_obj__District_obj=user.Municipal_District_obj)).order_by('DateTime')
        
    elif view == 'My Elections':
        posts = []
    else:
        posts = []
    if user:
        nav_options = [nav_item('link', 'My Elections', '?view=My Elections', None),
                    nav_item('link', 'All Elections', '?view=All Elections', None)]
    else:  
        nav_options = [nav_item('link', 'All Elections', '?view=All Elections', None)]

    setlist = paginate(posts, page, request) 
    try:
        isApp = request.COOKIES['fcmDeviceId']
    except:
        isApp = None
    context = {
        'isApp': isApp,
        'title': title,
        'view': view,
        'nav_bar': nav_options,
        'cards': 'elections_list',
        'sort': sort,
        'feed_list':setlist,
    }
    return render_view(request, context, country=country)
        
def candidates_view(request, organization, region, iden):
    prnt('-candidates view')
    cards = 'candidates_list'
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', '')
    view = request.GET.get('view', '')
    page = request.GET.get('page', 1)
    election = Election.objects.filter(id=iden).first()
    candidates = Role.objects.filter(election=election).order_by('?')
    if election.riding:
        title = "%s %s %s" %(election.province.name, election.riding.name, election.type)
    elif election.district:
        title = "%s %s %s" %(election.province.name, election.district.name, election.type)
    else:
        title = "%s %s %s" %(election.province.name, election.level, election.type)
    setlist = paginate(candidates, page, request)    
    context = {
        'title': title,
        'view': view,
        'cards': cards,
        'sort': sort,
        'feed_list':setlist,
        'country': Country.objects.all().first(),
    }
    return render_view(request, context)
    


def motions_view(request, region, type):
    prnt('-house/senate motions view')
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'Time')
    page = request.GET.get('page', 1)
    view = request.GET.get('view', 'past')
    getDate = request.GET.get('date', None)
    date = request.POST.get('date')

    if style == 'preload':
        context = {
            'title': 'Motions',
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
        prnt('country_dict, gov_dict, subRegions, subGovernments',country_dict, gov_dict, subRegions, subGovernments)
        prnt('Chamber', current_chamber_list, current_chamber_name, all_chambers, gov_levels)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)
        if sort.lower() == 'time':
            sort_option = '-DateTime'
        elif sort.lower() == 'number':
            sort_option = '-Motion_obj__VoteNumber'
        else:
            sort_option = '-DateTime'
        # subtitle = ''
        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None
            if current_chamber_name.lower() == 'all':
                title = type[0].upper() + type[1:] + 's'
            else:
                title = current_chamber_name + ' ' + type[0].upper() + type[1:] + 's'
        
        if style == 'index':
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            if current_chamber_name.lower() == 'all':
                title = type[0].upper() + type[1:] + 's'
            else:
                title = current_chamber_name + ' ' + type[0].upper() + type[1:] + 's'
            nav_options = []
            if include_nav == 'True':
                nav_options = [nav_item('button', f'Chamber: {current_chamber_name}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'), 
                    nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                    nav_item('button', 'Sort: %s'%(sort), 'subNavWidget', 'sortForm', fields=['Time', 'Number', 'Passed', 'Failed'], key='sort'), 
                    nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
    
            if request.method == 'POST':
                date = datetime.datetime.strptime(date, '%Y-%m-%d')
                subtitle = date
                view = None
                posts = Post.objects.filter(pointerType='Motion', Country_obj__id=country_dict['id'], Chamber__in=current_chamber_list).filter(DateTime__gte=date, DateTime__lt=date + datetime.timedelta(days=1)).select_related('Motion_obj').order_by('-DateTime')

            else:
                if getDate:
                    firstDate = datetime.datetime.strptime(getDate, '%Y-%m-%d')
                    secondDate = firstDate + datetime.timedelta(days=1)
                else: 
                    secondDate = now_utc() + datetime.timedelta(hours=1)
                    firstDate = secondDate - datetime.timedelta(days=1000)
                posts = Post.objects.filter(Country_obj__id=country_dict['id'], pointerType='Motion', filters__Chamber__in=current_chamber_list).order_by(sort_option, '-DateTime', 'Motion_obj__VoteNumber')

            if sort.lower() == 'passed':
                posts = posts.filter(Motion_obj__Yeas__gt=F('Motion_obj__Nays'))
            elif sort.lower() == 'failed':
                posts = posts.filter(Motion_obj__Nays__gt=F('Motion_obj__Yeas'))
            setlist = paginate(posts, page, request)        
            context = {
                'isApp': isApp,
                'view': view,
                'cards': 'motions_list',
                'page':page,
                'sort': sort,
                'style':style,
                'feed_list':setlist,
                'useractions': get_useractions(user_id, setlist),
                'myRepVotes': {},
                'nav_bar': nav_options,
                'feed_title': title,
            }
            return render_view(request, context, country=country_dict)

def motion_view(request, region, chamber, govNumber, session, number, type):
    prnt('-vote motion view')
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'All')
    page = request.GET.get('page', 1)
    party = request.GET.get('party', 'All')
    view = request.GET.get('view', '')
    subRegion = request.GET.get('subRegion', 'All')
    vote = request.GET.get('vote', 'All')
    if style == 'preload':
        context = {
            'title': 'Motion',
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
        prnt('country_dict, gov_dict, subRegions, subGovernments',country_dict, gov_dict, subRegions, subGovernments)
        prnt('Chamber', current_chamber_list, current_chamber_name, all_chambers, gov_levels)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)
        motion = Motion.objects.filter(Chamber__in=current_chamber_list, Government_obj__GovernmentNumber=govNumber, Government_obj__SessionNumber=session, VoteNumber=number).first()
        motionPost = Post.objects.filter(pointerId=motion.id).first()
        if type == 'rollcall':
            type = 'Roll Call'
        else:
            type = type[0].upper() + type[1:]
        title = '%s %s No. %s' %(motion.Chamber.replace('-', ' '), type, motion.VoteNumber)
        try:
            isApp = request.COOKIES['fcmDeviceId']
        except:
            isApp = None
        
        if style == 'index':
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            nav_options = []
            title_link = None
            if include_nav == 'True':
                nav_options = [
                        nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                        nav_item('button', 'Party: %s' %(party), 'subNavWidget', 'partyForm', fields=[p['Name'] for p in motion.return_parties()], key='party'), 
                        nav_item('button', 'Vote: %s' %(vote), 'subNavWidget', 'voteForm', fields=['All'] + [v['Vote'] for v in motion.return_votes()], key='vote'),
                        nav_item('button', 'Name: %s'%(sort), 'subNavWidget', 'sortForm', fields=['All'] + list(string.ascii_uppercase), key='sort'),
                        nav_item('button', 'Region: %s' %(subRegion), 'modalPopPointer', f'''"Regions", "/subregions_modal/{country_dict['Name']}/{country_dict['nameType']}/{motion.get_absolute_url()}"''')
                        ]
                title_link =  motion.get_absolute_url(),

            votes = Post.objects.filter(Vote_obj__Motion_obj=motion)
            if party != 'All':
                votes = votes.filter(Vote_obj__CaucusName__iexact=party)
            if vote != 'All':
                votes = votes.filter(Vote_obj__VoteValue__iexact=vote)
            if sort != 'All':
                votes = votes.filter(Vote_obj__PersonFullName__istartswith=sort)
            if subRegion != 'All':
                votes = votes.filter(Vote_obj__ConstituencyProvStateName__icontains=subRegion)
            setlist = paginate(votes, page, request)
            try:
                isApp = request.COOKIES['fcmDeviceId']
            except:
                isApp = None
            context = {
                'isApp': isApp,
                'view': view,
                'cards': 'vote_list',
                'sort': sort,
                'page':page,
                'feed_list':setlist,
                'motion': motion,
                'style':style,
                'nav_bar': nav_options,
                'feed_title': title,
                'title_link': title_link,
            }
            return render_view(request, context, country=country_dict)


    
def latest_committees_view(request, region, Chamber):
    prnt('-latest committees view')
    title = 'Latest Committee Events'
    cards = 'committeeMeeting_list'
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', 'time')
    page = request.GET.get('page', 1)
    view = request.GET.get('view', 'Current')
    # filter = request.GET.get('filter', 'all')
    date = request.POST.get('date')
    form = AgendaForm()
    subtitle = ''
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, region, user)
    chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, country, provState, county, city)
    govs = get_gov(country, gov_levels)

    nav_options = [
            nav_item('button', f'Chamber:{Chamber}', 'subNavWidget', 'chamberForm'), 
            nav_item('link', 'Current', '?view=Current', None), 
            nav_item('link', 'Upcoming', '?view=Upcoming', None),
            nav_item('button', 'Date', 'subNavWidget', 'datePickerForm')]
    committeeList = Committee.objects.exclude(Chamber__in=Chamber).filter(Government_obj__in=govs).order_by('Title')
    if request.method == 'POST':
        date = datetime.datetime.strptime(date, '%Y-%m-%d')
        subtitle = date
        title = 'House Committees'
        view = None
        posts = Post.objects.filter(Meeting_obj__meeting_type='Commitee', Meeting_obj__date_time_start__gte=date, Meeting_obj__date_time_start__lt=date + datetime.timedelta(days=1)).exclude(Meeting_obj=None).order_by('-date_time')
    elif view == 'Upcoming':
        posts = Post.objects.filter(Meeting_obj__meeting_type='Commitee', Meeting_obj__date_time_start__gte=datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d')).exclude(Meeting_obj=None).order_by('-date_time')
        if Chamber.lower() == 'all':
            title = 'Upcoming Committee Events'
        else:
            title = f'Upcoming {Chamber} Committee Events'

    else:
        posts = Post.objects.filter(Meeting_obj__meeting_type='Commitee', Meeting_obj__Chamber__in=Chambers, Meeting_obj__date_time_start__lte=datetime.datetime.strftime(datetime.datetime.now() + datetime.timedelta(days=1), '%Y-%m-%d')).exclude(Meeting_obj=None).order_by('-date_time')
        if Chamber.lower() == 'all':
            title = 'Latest Committee Events'
        else:
            title = f'Latest {Chamber} Committee Events'

    if not request.method == 'POST':
        setlist = paginate(posts, page, request)
    else:
        setlist = posts
    try:
        isApp = request.COOKIES['fcmDeviceId']
    except:
        isApp = None
    context = {
        'isApp': isApp,
        'title': title,
        'subtitle': subtitle,
        'nav_bar': nav_options,
        'view': view,
        'dateForm': form,
        'cards': cards,
        'sort': sort,
        'feed_list':setlist,
        'useractions': get_useractions(user, setlist),
        'committeeList': committeeList,
    }
    return render_view(request, context, country=country)

def committee_view(request, organization, govNumber, session, iden):
    prnt('-latest committee view')
    user_data, user = get_user_data(request)
    country, provState, county, city = get_regions(request, None, user)

    chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, country, provState, county, city)
    govs = get_gov(country, gov_levels, govNumber, session)
    c = Meeting.objects.filter(id=iden, meeting_type='Committee', Government_obj__in=govs, Chamber__in=chambers).select_related('Committee_obj', 'Committee_obj__Chair_obj')[0]
    if 'Subcommittee' in c.Committee_obj.Title:
        title = 'Senate Committee'
    else:
        title = f'{Chamber} Committee'
    subtitle = str(get_ordinal(c.Government_obj__GovernmentNumber)) + ' Num. ' + str(get_ordinal(c.Government_obj__SessionNumber)) + ' Sess.'
    subtitle2 = datetime.datetime.strftime(c.date_time_start, '%B %-d, %Y')
    cards = 'committeeMeeting_view'
    style = request.GET.get('style', 'index')
    sort = request.GET.get('sort', 'time')
    view = request.GET.get('view', '')
    page = request.GET.get('page', 1)
    speaker_id = request.GET.get('speaker', '')
    topic = request.GET.get('topic', '')
    iden = request.GET.get('id', '')
    hasContext = True
    if topic:
        title = topic
        hasContext = False
    elif speaker_id:
        speaker = Person.objects.filter(id=speaker_id)[0]
        title = speaker.get_name()
        hasContext = False
    follow = request.GET.get('follow', '')
    if follow and topic:
        fList = user.get_follow_topics()
        if topic in fList:
            fList.remove(topic)
        elif topic not in fList:
            fList.append(topic)
        user.set_follow_topics(fList)
        user.save()
        return render(request, "utils/dummy.html", {"result": 'Success'}, country=country)
    if speaker_id:
        posts = Post.objects.filter(Statement_obj__Person_obj=speaker, Statement_obj__Meeting_obj=c).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by('Statement_obj__DateTime', 'created')
    elif topic:
        posts = Post.objects.filter(Statement_obj__Terms_array__icontains=topic, Statement_obj__Meeting_obj=c).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by('Statement_obj__DateTime', 'created')
    else:
        posts = Post.objects.filter(Statement_obj__Meeting_obj=c).select_related('Statement_obj__Person_obj', 'Statement_obj').order_by('Statement_obj__DateTime', 'created')

    if iden:
        setlist = paginate(posts, 'id=%s' %(iden), request)
        hasContext = setlist[0].Statement_obj.id
        iden = int(iden)
    else:
        setlist = paginate(posts, page, request)
        if page != 1:
            hasContext = setlist[0].Statement_obj.id
    try:
        isApp = request.COOKIES['fcmDeviceId']
    except:
        isApp = None
    nav_options = [
            nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'),
            nav_item('button', 'Sort: %s'%(sort), 'subNavWidget', 'sortForm'), ]
    if topic:
        if user and topic in user.get_follow_topics():
            f = 'following'
        else:
            f = 'follow'
        follow_link = '%s?topic=%s&follow=%s' %(c.get_absolute_url(), topic, f)
        nav_options.append(nav_item('button', 'follow', f'react("follow2", "{follow_link}")'))
    context = {
        'isApp': isApp,
        'title': title,
        'title_link': c.get_absolute_url(),
        'subtitle': subtitle,
        'subtitle2': subtitle2,        
        'nav_bar': nav_options,
        'view': view,
        'cards': cards,
        'sort': sort,
        'topic': topic,
        'id': iden,
        'hasContext': hasContext,
        'feed_list':setlist,
        'useractions': get_useractions(user, setlist),
        'committee': c,
        'topicList': [topic],
    }
    return render_view(request, context, country=country)


def officials_list(request, region):
    prnt('-officials_list')
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    user_id = request.GET.get('user', None)
    sort = request.GET.get('sort', 'All')
    page = request.GET.get('page', 1)
    subRegion = request.GET.get('subRegion', 'All')
    search = request.POST.get('post_type')
    view = request.GET.get('view', 'Current')    
    searchform = SearchForm()

    if style == 'preload':
        context = {
            'title': 'Legislative Officials',
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        prnt('country_dict, gov_dict',country_dict, gov_dict)
        current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
        prnt('country_dict, gov_dict, subRegions, subGovernments',country_dict, gov_dict, subRegions, subGovernments)
        prnt('Chamber', current_chamber_list, current_chamber_name, all_chambers, gov_levels)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments, current_chamber_name)
        if style == 'index':
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            nav_options = []
            title = None
            if include_nav == 'True':
                nav_options = [
                    nav_item('button', f'Chamber: {current_chamber_name}', 'subNavWidget', 'chamberForm', fields=['All'] + all_chambers, key='chamber'), 
                        nav_item('button', 'Region: %s' %(subRegion), f'modalPopPointer', f'''"Regions", "/subregions_modal/{country_dict['Name']}/{country_dict['nameType']}/officials"'''),
                        nav_item('button', 'Name: %s'%(sort), 'subNavWidget', 'sortForm', fields=['All'] + list(string.ascii_uppercase), key='sort'),
                        nav_item('button', 'Page: %s' %(page), 'subNavWidget', 'pageForm'), 
                        nav_item('button', 'Search', 'subNavWidget', 'searchForm'),
                        ]
            prnt('nav_options',nav_options)
            positions = gov_dict['Office_array']
            prnt('pos',positions)
            if not positions:
                posts = []
            elif subRegion == 'All':
                posts = Post.objects.filter(pointerType='Person', Region_obj__id=country_dict['id'], filters__Chamber__in=current_chamber_list).filter(Q(**{'Update_obj__data__Position__in': positions})).order_by('Update_obj__data__LastName')

            else:
            #     # prnt(subRegion)
                subR = Region.objects.filter(ParentRegion_obj__id=country_dict['id'], Name=subRegion).first()
                posts = Post.objects.filter(pointerType='Person', Region_obj__id=country_dict['id'], Update_obj__data__ProvState_id=subR.id, Chamber__in=current_chamber_list).filter(Q(**{'Update_obj__data__Position__in': positions})).order_by('Update_obj__data__LastName')
            prnt('posts len',len(posts))
            if sort != 'All':
                posts = posts.filter(Update_obj__data__LastName__startswith=sort)
            setlist = paginate(posts, page, request)
            extra_data = fetch_updated_objs(setlist, ['Party', 'District', 'ProvState'])
            context = {
                'cards': 'rep_list',
                'sort': sort,
                'view': view,
                'region': region,
                'page':page,
                'feed_list':setlist,
                'extra_data':extra_data,
                'style':style,
                'nav_bar': nav_options,
                'feed_title': title,
            }
            return render_view(request, context, country=country_dict)

def representative_view(request, region, name, iden):
    prnt('-representative_view')
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    sort = request.GET.get('sort', 'new')
    if sort == 'old':
        ordering = 'DateTime'
        newSort = 'new'
    else:
        ordering = '-DateTime'
        newSort = 'old'
    page = request.GET.get('page', 1)
    view = request.GET.get('view', '')
    topic = request.GET.get('topic', '')
    follow = request.GET.get('follow', '')
    if follow and not request.user.is_authenticated:
        return render(request, "utils/dummy.html", {'result':'Please Login'})
    
    if style == 'preload':
        context = {
            'title': 'Representative',
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    else:
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region)
        request = set_session_data(request, country_dict, gov_dict, subRegions, subGovernments)
        prnt('country',country_dict)
        prnt('iden',iden)
        if is_id(iden):
            personPost = Post.objects.filter(pointerType='Person', Person_obj__id=iden, Country_obj__id=country_dict['id']).first()
        else:
            personPost = Post.objects.filter(pointerType='Person', Person_obj__GovIden=iden, Country_obj__id=country_dict['id']).first()
        title = personPost.Update_obj.data['Position']
        person = personPost.Person_obj
        prnt('person',person, 'title',title)
        if follow and follow != 'following' and follow != 'follow':
            fList = request.user.get_follow_topics()
            topic = follow
            if topic in fList:
                fList.remove(topic)
                response = 'Unfollow "%s"' %(topic)
                user = set_keywords(request.user, 'remove', topic)
            elif topic not in fList:
                fList.append(topic)
                response = 'Following "%s"' %(topic)
                user = set_keywords(request.user, 'add', topic)
            request.user.set_follow_topics(fList)
            request.user.save()
            return render(request, "utils/dummy.html", {"result": response})
        elif follow and follow == 'following' or follow and person in request.user.follow_Person_objs.all():
            request.user.follow_Person_objs.remove(person)
            request.user.save()
            return render(request, "utils/dummy.html", {'result':'Unfollow %s' %(person.FullName)})
        elif follow and follow == 'follow' or follow and person not in request.user.follow_Person_objs.all():
            request.user.follow_Person_objs.add(person)
            request.user.save()
            return render(request, "utils/dummy.html", {'result':'Following %s' %(person.FullName)})
        
        follow = 'follow'
        
        if style == 'index':
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            nav_options = []
            title = None
            if include_nav == 'True':
                nav_options = [
                        nav_item('link', 'Votes', '%s?view=Votes'%(person.get_absolute_url()), None), 
                        nav_item('link', 'Debates', '%s?view=Debates'%(person.get_absolute_url()), None), 
                        nav_item('link', 'Sponsorships', '%s?view=Sponsorships'%(person.get_absolute_url()), None), 
                        nav_item('link', 'Roles', '%s?view=Roles'%(person.get_absolute_url()), None), 
                        ]

            items = Statement.objects.filter(Person_obj=person).order_by('-DateTime')[:200]
            termsDic = {}
            for item in items:
                if item.Terms_array:
                    for t in item.Terms_array:
                        if t not in skipwords:
                            if t in termsDic:
                                termsDic[t] += 1
                            else:
                                termsDic[t] = 1
                if item.keyword_array:
                    loweredTerms = []
                    if item.Terms_array:
                        loweredTerms = [x.lower() for x in item.Terms_array]  
                    for t in item.keyword_array:
                        if t not in skipwords and t not in loweredTerms:
                            if t in termsDic:
                                termsDic[t] += 1
                            else:
                                termsDic[t] = 1
            termsList = sorted(termsDic.items(), key=_itemgetter(1),reverse=True)
            my_votes = {}
            vote_matches = 0
            total_matches = 0
            match_percentage = None
            if view == 'Roles':
                posts = Post.objects.filter(pointerType='Person', Person_obj=person).order_by('-DateTime')

            elif view == 'Votes':
                posts = RepVote.objects.filter(Person_obj=person).order_by('-Motion_obj__DateTime')
            elif view == 'Debates':
                posts = Post.objects.filter(Q(Statement_obj__Person_obj=person)|Q(Statement_obj__PersonName__icontains=personPost.Update_obj['FullName'])).order_by(ordering)
            elif topic:
                search = ['%s'%(topic)]
                posts = Post.objects.filter(Statement_obj__Terms_array__overlap=search, Statement_obj__Person_obj=person).order_by(ordering)
                if posts.count() == 0:
                    posts = Post.objects.filter(Statement_obj__keyword_array__icontains=topic, Statement_obj__Person_obj=person).order_by(ordering)
            elif view == 'Sponsorships':
                posts = Post.objects.filter(Q(Bill_obj__Person_obj=person)|Q(Bill_obj__CoSponsor_objs=person)).order_by(ordering)
            else:
                posts = None
            
            setlist = paginate(posts, page, request)
            context = {
                'title': title,
                'view': view,
                'cards': 'representative_view',
                'sort': sort,
                'personTerms': termsList,
                'page': page,
                'style':style,
                'feed_list':setlist,
                'useractions': get_useractions(request.user, setlist),
                'match': match_percentage,
                'voteMatches': vote_matches,
                'totalMatches': total_matches,
                'myVotes': my_votes,
                'topicList': [topic],
                'nav_bar': nav_options,
                'feed_title': title,
            }
            return render_view(request, context)

