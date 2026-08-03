
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.template.defaulttags import register
from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,

    )

from .models import User, UserPubKey, UserAction
from .forms import *
from posts.models import Region, Post
from posts.utils import get_user_data
from posts.forms import SearchForm
from posts.views import render_view
from network.models import Sonet
from utils.locked import hash_obj_id, get_signing_data, verify_data
from utils.models import prnt, prntn, now_utc, sync_and_share_object, string_to_dt, dt_to_string, get_operator_obj, is_id, has_method
from django.http import JsonResponse

from django.db.models import Q
import datetime
import json


def privacy_policy_view(request):
    style = request.GET.get('style', 'index')
    context = {
        'title': 'Privacy Policy',
        'cards': 'privacyPolicy',
    }
    return render_view(request, context)
    
def values_view(request):
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    if style == 'preload':
        context = {
            'title': '',
            'style':style,
        }
        from posts.utils import get_cookies

        return render(request, "home.html", get_cookies(request,context))
    else:
        if style == 'index':
            from posts.utils import get_index, get_regions_and_govs, get_chambers, get_trending, get_user_sending_data
            country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(None)
            current_chamber_list, current_chamber_name, all_chambers, gov_levels = get_chambers(request, gov_dict)
            context = get_index(request, country_dict, gov_dict)
            context['sidebarData'] =  get_trending(request, country_dict, current_chamber=current_chamber_name, all_chambers=all_chambers)
            context = get_user_sending_data(user_id, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            context = {
                'title': '',
                'cards': 'values',
            }
            return render_view(request, context)

def hero_view(request):
    style = request.GET.get('style', 'index')
    context = {
        'title': 'So You want to be a Hero?',
        'cards': 'hero',
    }
    return render_view(request, context)

def about_view(request):
    style = request.GET.get('style', 'index')
    context = {
        'title': 'About Us',
        'cards': 'about',
    }
    return render_view(request, context)

def contact_view(request):
    style = request.GET.get('style', 'index')
    context = {
        'title': 'Contact',
        'cards': 'contact',
    }
    return render_view(request, context)

def get_app_view(request):
    style = request.GET.get('style', 'index')
    context = {
        'title': 'Get the App',
        'cards': 'getApp',
    }
    return render_view(request, context)

def login_signup_super_view(request):
    prnt('-super user dev create view')
    if not User.objects.first() and not Sonet.objects.first():
        user_obj = User()
        user_obj.initialize()
        from utils.locked import generate_id
        user_obj.id = 'usrSo' + generate_id('ShardHolder')
        context = {
            'title': 'Login/Signup',
            'user_dict': get_signing_data(user_obj),
        }
        return render(request, "forms/login-signup.html", context)

def rename_setup_view(request):
    prnt('-rename_setup view')
    context = {
        'title': 'Mandatory User Rename',
        'text': 'Unfortunately your username was previously registered and must be replaced.',
    }
    return render(request, "forms/must_rename.html", context)

@csrf_exempt
def receive_rename_view(request):
    prnt('-receive_rename_view')
    if request.method == 'POST':
        userData = request.POST.get('userData')
        userData_json = json.loads(userData)
        try:
            User.objects.filter(username=userData_json['username']).exclude(id=userData_json['id'])[0]
            return JsonResponse({'message':'Username taken'})
        except:
            user = request.user
            user, synced = sync_and_share_object(user, userData)
            prnt('synced',synced)
            user.slug = user.slugger()
            user.save()
            if synced:
                return JsonResponse({'message':'success'})
            else:
                return JsonResponse({'message':'Failed to sync'})
    return JsonResponse({'message':'Failed'})


def signup_view(request):
    prnt('-signup_view')
    user_obj = User()
    user_obj.initialize()
    context = {
        'title': 'Login',
        'user_dict': get_signing_data(user_obj),
    }
    return render(request, "forms/signup.html", context)

# step 1 user login/signup
@csrf_exempt
def login_signup_view(request):
    prnt('-login_signup_view')
    user_obj = User()
    user_obj.initialize()
    context = {
        'title': 'Login',
        'user_dict': get_signing_data(user_obj, sort_data=False),
    }
    return render(request, "forms/login-signup.html", context)

# step 2 of user signup
@csrf_exempt
def user_create_request_view(request):
    prnt('-user_create_request_view')
    from utils.locked import get_signing_data, convert_to_dict
    if request.method == 'POST':
        received_json = request.POST
        prnt(received_json.get('username'))
        if len(received_json.get('username')) < 4:
            return JsonResponse({'message' : 'User exists'})
        user = User.objects.filter(username=received_json.get('username')).first()
        if user:
            prnt('user already exists')
            return JsonResponse({'message' : 'User exists'})
        else:
            ID_LENGTH = 'x'
            user_id = hash_obj_id('User')
            upk_id = hash_obj_id('UserPubKey')
            username = received_json.get('username')
            prnt('new username',username)
            user = User(id=user_id, username=username)
            upk_obj = UserPubKey(id=upk_id, User_obj_id=user_id)
            upk_obj.initialize()
            from transactions.models import Wallet # wallet no longer created at account creation
            wallet_obj = Wallet(User_obj_id=user_id, Name='Main')
            iden = hash_obj_id('Wallet')
            prnt("hash_obj_id('Wallet')'",iden)
            wallet_obj.id = iden
            prnt('wallet_obj.id',wallet_obj.id)
            from network.models import get_self_node
            self_node = get_self_node()
            if not self_node:
                from network.models import Node
                self_node = Node()
                self_node.initialize()
            import random
            user.pattern = random.randint(1, 12)
            user.nodeCreatorId = self_node.id
            sonet = Sonet.objects.first()
            if not sonet:
                sonet = Sonet()
                sonet.initialize()
                if User.objects.all().count() == 0:
                    user.is_superuser = True
                    user.is_staff = True
                    from utils.locked import ID_LENGTH
            sonet = json.dumps(convert_to_dict(sonet))
            # prnt('extra_data',extra_data)
            prnt('return 2')
            return JsonResponse({'message' : 'Create User', 'userData' : get_signing_data(user, sort_data=False), 'upkData' : get_signing_data(upk_obj, sort_data=False), 'walletData' : get_signing_data(wallet_obj, sort_data=False), 'sonet' : sonet, 'nodeData':get_signing_data(self_node, sort_data=False), 'id_len' : ID_LENGTH})

# step 2 of user login
@csrf_exempt
def get_user_login_request_view(request):
    prnt('-get_user login request')
    from utils.locked import get_signing_data, convert_to_dict
    if request.method == 'POST':
        received_json = request.POST
        prnt(received_json.get('username'))
        user = User.objects.filter(Q(username=received_json.get('username'))|Q(id=received_json.get('username'))).first()
        if user:
            prnt(user.username)
            prnt('return 1')
            userData = get_signing_data(user, include_sig=True, sort_data=False)
            try:
                sonet = json.dumps(convert_to_dict(Sonet.objects.first()))
            except:
                sonet = None
            prnt('return sign data', userData)
            return JsonResponse({'message' : 'User found', 'userData' : userData, 'upks' : [get_signing_data(upk_obj, sort_data=False) for upk_obj in user.get_keys(dt=now_utc())], 'sonet' : sonet})
        else:
            
            prnt('return 2')
            return JsonResponse({'message' : 'User not found'})

# step 3 user login/signup
@csrf_exempt
def receive_user_login_view(request):
    prnt('-receive_user_login_view')
    err_code = '-'
    if request.method == 'POST':
        try:
            upk = None
            user = None
            wallet = None
            nodeData = None
            node_upkData = None
            try:
                # javascript browser
                received_data = json.loads(request.body)
                prnt(type(received_data.get('userData')))
                prnt(received_data.get('userData'))
                userData = json.loads(received_data.get('userData', '{}'))

                prnt('userData1',userData)
                upkData_accnt = json.loads(received_data.get('upkData_accnt', '{}'))
                prnt('upkData1',upkData_accnt)
                upkData_sign = json.loads(request.POST.get('upkData_sign', '{}'))
                prnt('upkData_sign',upkData_sign)
                upkData_super = json.loads(request.POST.get('upkData_super', '{}'))
                # prnt('upkData_super',upkData_super)
                upkData_wallet = json.loads(request.POST.get('upkData_wallet', '{}'))
                # prnt('upkData_wallet',upkData_wallet)
                walletData = json.loads(received_data.get('walletData', '{}'))
                # prnt('walletData1',walletData)
                nodeData = json.loads(received_data.get('nodeData', '{}'))
                # prnt('nodeData1',nodeData)
                node_upkData = json.loads(received_data.get('node_upkData', '{}'))
                # prnt('node_upkData1',node_upkData)
                reward_walletData = json.loads(received_data.get('reward_walletData', '{}'))
                # prnt('reward_walletData1',reward_walletData)
                # prnt('data1',received_data)
            except Exception as e:
                # node manager
                userData = json.loads(request.POST.get('userData', '{}'))

                upkData_accnt = json.loads(request.POST.get('upkData_accnt', '{}'))
                prnt('upkData_accnt',upkData_accnt)
                upkData_sign = json.loads(request.POST.get('upkData_sign', '{}'))
                prnt('upkData_sign',upkData_sign)
                upkData_super = json.loads(request.POST.get('upkData_super', '{}'))
                prnt('upkData_super',upkData_super)
                upkData_wallet = json.loads(request.POST.get('upkData_wallet', '{}'))
                prnt('upkData_wallet',upkData_wallet)

                walletData = json.loads(request.POST.get('walletData', '{}'))
                prnt('walletData2',walletData)
                nodeData = json.loads(request.POST.get('nodeData', '{}'))
                prnt('nodeData2',nodeData)
                node_upkData = json.loads(request.POST.get('node_upkData', '{}'))
                prnt('node_upkData2',node_upkData)
                reward_walletData = json.loads(request.POST.get('reward_walletData', '{}'))
                prnt('reward_walletData2',reward_walletData)
                
            prnt('received-userData',type(userData),userData)
            from utils.models import get_sigData
            sig_data = get_sigData(userData, first_key=True)
            userPublicKey = sig_data['pk']
            userSignature = sig_data['sig']
                        
            dt = string_to_dt(userData['lastUpdate'])
            now = now_utc()
            if dt >= now - datetime.timedelta(seconds=10) and dt < now + datetime.timedelta(seconds=10):

                user = User.objects.filter(id=userData['id']).defer('signed').first()
                if user:
                    try:
                        prnt('user found', user)
                        if user.alerts and 'must_rename' in user.alerts:
                            if User.objects.filter(username=userData['username']).exclude(id=userData['id']).count() > 0:
                                return JsonResponse({'message' : 'Username taken'})
                        # x = get_signing_data(userData)
                        if is_id(userPublicKey):
                            iden = userPublicKey
                        else:
                            from utils.models import hash_upk_id
                            iden = hash_upk_id(userPublicKey)
                        prnt('iden',iden)
                        upk = UserPubKey.objects.filter(User_obj__id=user.id, id=iden, end_life_dt=None, keyType='account').only('publicKey').first()
                        if upk:
                            prnt('upk fouund:',upk)
                            is_valid = upk.verify(userData, userSignature, userPublicKey)
                            prnt('Login_is_valid', is_valid)
                            if is_valid:
                                if user.lastUpdate < string_to_dt(userData['lastUpdate']):
                                    user, good = sync_and_share_object(user, userData)
                                    prnt('user-good',good)
                                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                                prnt('user logged in')
                                response = JsonResponse({'message' : 'Valid Username and Password', 'userData' : get_signing_data(user, sort_data=False), 'upk' : get_signing_data(upk, sort_data=False)})
                                # response.set_cookie(key='userData', value=json.dumps(x), expires=datetime.datetime.today()+datetime.timedelta(days=3650))
                                return response
                            else:
                                return JsonResponse({'message' : 'Verification failed'})
                        else:
                            upks = UserPubKey.objects.all()
                            from utils.locked import convert_to_dict
                            for upk in upks:
                                prnt('upk:',convert_to_dict(upk))
                            return JsonResponse({'message' : 'Invalid Passphrase'})
                    except Exception as e:
                            prnt('login err 0852', str(e))
                            return JsonResponse({'message' : f'A Problem Occured: {e}', 'err':str(e)})
                else:
                    try:
                        proceed_to_login = False
                        err_code = 'A'
                        prnt('create user stage 1')
                        from utils.models import register_new_user
                        proceed_to_login, loginData, err_code = register_new_user(userData, upkData_accnt, upkData_sign, walletData, nodeData, node_upkData, reward_walletData, extraData={'upkData_super':upkData_super,'upkData_wallet':upkData_wallet}, return_err_code=err_code)
                        user = loginData['user']
                        upk = loginData['upk']
                        upk_sign = loginData['upk_sign']
                        wallet = loginData['wallet']
                        if proceed_to_login:
                            import traceback
                            try:
                                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                            except Exception as e:
                                traceback.print_exc()
                                raise
                            prnt('user logged in')
                            sonet_obj = Sonet.objects.first()
                            if not sonet_obj:
                                sonet_obj = Sonet()
                                sonet_obj.initialize()
                            sonet = get_signing_data(sonet_obj)
                            return JsonResponse({'message' : 'User Created', 'userData' : get_signing_data(user, sort_data=False), 'upk' : get_signing_data(upk, sort_data=False), 'sonet' : sonet})
                        else:
                            try:
                                from network.models import Blockchain
                                chains = Blockchain.objects.filter(genesisId=user.id)
                                for w in chains:
                                    w.delete()
                            except:
                                pass
                            try:
                                prnt('deleting user...')
                                user.delete()
                            except:
                                pass
                            try:
                                upk.delete()
                            except:
                                pass
                            try:
                                upk_sign.delete()
                            except:
                                pass
                            try:
                                wallet.delete()
                            except:
                                pass
                            prnt('new user data deleted',f'fail2:{err_code}')
                            return JsonResponse({'message' : f'There was a problem creating this user, err:{err_code}', 'error':f'fail2:{err_code}'})
                    except Exception as e:
                        prnt('sign in fail 543', str(e), 'err:',err_code)
                        try:
                            from network.models import Blockchain
                            chains = Blockchain.objects.filter(genesisId=user.id)
                            for w in chains:
                                w.delete()
                        except:
                            pass
                        try:
                            user.delete()
                        except:
                            pass
                        try:
                            upk.delete()
                        except:
                            pass
                        try:
                            upk_sign.delete()
                        except:
                            pass
                        try:
                            wallet.delete()
                        except:
                            pass

                        return JsonResponse({'message' : f'There was a problem creating this user, err:{err_code} - {e}', 'error': f'fail1: {err_code}-{str(e)}'})
        except Exception as e:
            prnt('receive login fail 3467 err_code:',err_code,str(e))
            return JsonResponse({'message' : f'error: {e}'})
    return JsonResponse({'message' : 'failed'})

@csrf_exempt
def deactivate_upk_view(request):
    prnt('-deactivate_upk_view')
    err_code = '-'
    if request.method == 'POST':
        try:
            upk = None
            try:
                received_data = json.loads(request.body)
                upkData = received_data.get('upkData', '{}')
            except Exception as e:
                prnt('deactivate_upk err 88',str(e))
                upkData = json.loads(request.POST.get('upkData', '{}'))
            from utils.models import share_with_network, sync_model, get_sigData
            sig_data = get_sigData(upkData, first_key=True)
            
            upk = UserPubKey.objects.filter(id=upkData['id']).defer('publicKey').first()
            if not upk.end_life_dt:
                from utils.locked import verify_data
                if verify_data(get_signing_data(upkData), upkData['signed']):
                    obj, sigs, valid_obj, updatedDB = sync_model(upk, upkData)
                    if valid_obj:
                        share_with_network(obj)
                        return JsonResponse({'message' : 'Success', 'upk' : get_signing_data(upk, sort_data=False)})

        except Exception as e:
            return JsonResponse({'message' : 'Failed', 'err' : str(e), 'upk' : get_signing_data(upk, sort_data=False)})
    return JsonResponse({'message' : 'Failed', 'err' : 'not post'})  



def username_avail_view(request):
    username = request.GET.get('username', '').strip()
    # prnt(username)
    if len(username) >= 4:
        exists = User.objects.filter(username__iexact=username).exists()
    else:
        exists = True
    # prnt(exists)
    return JsonResponse({'available': not exists})

    # keyword = request.GET.get('keyword', keyword)
    # keyword = keyword.lower()
    # response = User.objects.filter(display_name__iexact=keyword).first()
    # return render(request, "utils/dummy.html", {"result": response})
    
    # page = request.GET.get('page', 1)
    # search = request.POST.get('post_type', '')
    # autoComplete = request.GET.get('search')
    # follow = request.GET.get('follow', '')
    # cards = 'home_list'
    # ordering = get_sort_order(sort)
    # title = 'Search: %s' %(search)    
    # # province, region = get_region(request)
    # user_data, user = get_user_data(request)
    # country, provState, county, city = get_regions(request, None, user)
    # chambers, current_chamber, all_chambers, gov_levels = get_chambers(request, country, provState, county, city)
    # options = {'Chamber: %s' %(Chamber): 'Chamber'}
    # nav_options = [nav_item('button', f'Chamber:{Chamber}', 'subNavWidget("chamberForm")')]
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
        # options['follow'] = '%s' %(keyword)
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
        'sortOptions': ['Oldest','Newest','Loudest','Random'],
        'keyword': keyword,
        'view': view,
        # 'region': region,
        'searchForm': searchform,
        'cards': cards,
        'feed_list':setlist,
        'useractions': get_useractions(user, setlist),
        # 'updates': get_updates(setlist),
        'myRepVotes': getMyRepVotes(user, setlist),
        'topicList': [keyword],
        # 'myRepVotes': my_rep,
        # 'country': Country.objects.all()[0],
    }
    return render_view(request, context, country=country)



def logout_view(request):
    prnt('-logout')
    user = request.GET.get('user', None)
    if user:
        user = User.objects.filter(id=user).first()
    try:    
        fcmDeviceId = request.COOKIES['fcmDeviceId']
        prnt(fcmDeviceId)
        # should use CustomFCM
        devices = FCMDevice.objects.filter(user=request.user, registration_id=fcmDeviceId)
        for d in devices:
            # d.send_message(Message(notification=Notification(title=request.user.username, body="body")))
            d.send_message(Message(data={"logout" : "True"}))
            d.active = False
            d.save()
    except Exception as e:
        prnt('logout error4', str(e))
    logout(request)
    context = {
        "user": None,
    }
    response = render(request, "index.html", context)
    response.set_cookie(key='appToken', value=None)
    response.set_cookie(key='userData', value=None)
    # response.set_cookie(key='userToken', value=userToken)
    return response

def get_index_view(request):
    prnt('-get_index_view')
    user = request.GET.get('user', None)
    if user:
        user = User.objects.filter(id=user).first()
        
    from posts.utils import get_isMobile, get_regions_and_govs
    region_id = request.GET.get('region_id', None)
    if not region_id:
        try:
            region_id = request.session['region_id']
        except Exception as e:
            region_id = None
    country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region_id)
    is_mobile = get_isMobile(request)
    prnt('is_mobile',is_mobile)
    context = {
        "user": user,
        "load_nav": True,
        'self_node': get_operator_obj('self_nodeId'),
        'is_mobile': is_mobile,
        "country": country_dict,
        'gov': gov_dict,
        'sonet': Sonet.objects.values('Title','Subtitle','LogoLink').first(),
    }
    if is_mobile:
        return render(request, "mobile/index_mobile.html", context)
    else:
        return render(request, "index.html", context)

def get_country_modal_view(request):
    prnt('-get_country_modal_view')
    user_data, user = get_user_data(request)
    if not user:
        user_id = hash_obj_id('User')
        user_obj = User(id=user_id)
        context = {
            'title': 'Login/Signup',
            'user_dict': get_signing_data(user_obj),
        }
        return render(request, "forms/login-signup.html", context)
    else:
        return render(request, "forms/region_modal1.html")

def get_region_modal_view(request, country):
    prnt('-get region modal view', country)
    return render(request, "forms/region_modal2.html", {'country': country})

def run_region_modal_view(request):
    prnt('-run region modal')
    if request.method == 'POST':
        u = request.user
        address = request.POST.get('address')
        city = request.POST.get('city')
        state = request.POST.get('state')
        zip_code = request.POST.get('zip_code')
        country = request.POST.get('country')
        prnt('country',country)

        from utils.models import list_all_scrapers
        all_files = list_all_scrapers()
        # prnt(all_files)

        scripts = {}
        for file in all_files:
            try:
                a = file.find('/regions/')+len('/regions/')
                x = file[a:]
                words = x.split('/')
                region = words[-2]
                prnt('regions:',region)
                if region.lower() == country.lower():

                    txt = x.replace('/', '.').replace('.py','')
                    scripts[txt] = []
                    import importlib
                    scraperScripts = importlib.import_module(txt) 
                    approved_models = scraperScripts.approved_models
                    # for f, models in approved_models.items():
                    #     scripts[txt].append({txt:f})

                    cmd = getattr(scraperScripts, 'get_user_region')
                    returnData, shareData = cmd(address=address, city=city, state=state, zip_code=zip_code)
                    return JsonResponse({'message': 'success', 'result':returnData})
            except Exception as e:
                prnt(str(e))
                return JsonResponse({'message' : 'Failed to set region', 'error':str(e)})
                # pass
        return JsonResponse({'message' : 'Failed to set region', 'error':'Country not found'})

@csrf_exempt
def set_user_data_view(request):
    prnt('-set user data view')
    if request.method == 'POST':
        userData = request.POST.get('userData')
        prnt('received', userData)
        user = request.user
        user, synced = sync_and_share_object(user, userData)
        prnt('synced',synced)
        if synced:
            return JsonResponse({'message':'success'})
        else:
            return JsonResponse({'message':'Failed to sync'})
    return JsonResponse({'message':'Failed verification'})


def user_view(request, username):
    prnt('-profile',username)
    username = username.replace('|', '')
    u = User.objects.get(username=username)
    title = u.get_title()
    cards = 'user_view'
    style = request.GET.get('style', 'index')
    page = request.GET.get('page', 1)
    view = request.GET.get('view', 'all')
    topicList = []
    options = {'Votes':'%s?view=Votes'%(u.get_absolute_url()), 'Cheers':'cheer','Statements':'%s?view=Statements'%(u.get_absolute_url()), 'Replies':'%s?view=Replies'%(u.get_absolute_url()),  'Polls':'%s?view=Polls'%(u.get_absolute_url()), 'Petitions':'%s?view=Petitions'%(u.get_absolute_url()), 'Saved': '%s?view=Saved'%(u.get_absolute_url()), 'Following': '%s?view=Following'%(u.get_absolute_url())}
    if style == 'index':
        context = {
            'title': title,
            'cards': cards,
            'view': view,
            'user': u,
            'nav_bar': list(options.items()),
        }
        return render_view(request, context)
    else:
        if view == 'all':
            posts = Reaction.objects.filter(user=u).filter(Q(isYea=True)|Q(isNay=True)|Q(saved=True)).select_related('post').order_by('-updated')
        elif view == 'Votes':
            posts = Reaction.objects.filter(user=u).filter(Q(isYea=True)|Q(isNay=True)).exclude(isPreviousVote=True).select_related('post').order_by('-updated')
        elif view == 'nays': 
            posts = Reaction.objects.filter(user=u).filter(isNay=True).select_related('post').order_by('-updated')
        elif view == 'Saved':
            posts = Reaction.objects.filter(user=u).filter(saved=True).select_related('post').order_by('-updated')
        elif view == 'Following':
            getList = []
            for p in u.follow_person.all():
                getList.append(p)
            for p in u.follow_bill.all():
                getList.append(p.get_latest_version())
            for p in u.follow_committee.all():
                getList.append(p)
            for p in u.get_follow_topics():
                getList.append(p)
            posts = getList
        elif view == 'constituency':
            if not u.riding:  
                response = redirect('/user/%s/set-constituency' %(str(u.username)))
                prnt(response)
                return response
        elif view == 'province':
            pass
        elif view == 'municipality':
            pass
        setlist = paginate(posts, page, request)
        context = {
            'title': title,
            'cards': cards,
            'view': view,
            'user': u,
            'nav_bar': list(options.items()),
            'feed_list':setlist,
            'topicList': topicList,
        }
    return render_view(request, context)

@csrf_exempt
def user_settings_view(request):
    prnt('-user_settings_view')
    user = request.user
    title = 'User Settings'
    style = request.GET.get('style', 'preload')
    user_id = request.GET.get('user', None)
    include_nav = request.GET.get('include_nav', False)
    view = request.GET.get('view', 'Active')
    page = request.GET.get('page', 1)

    if user and user_id and user.id != user_id:
        # request authentication
        return
    if not user and user_id:
        user = User.objects.filter(id=user_id).first()
    if not user:
        return
    from posts.utils import get_cookies, get_index, get_user_sending_data, nav_item, get_regions_and_govs

    if style == 'preload':
        context = {
            'title': title,
            'style':style,
        }
        return render(request, "home.html", get_cookies(request,context))
    elif style == 'popup':
        text = ''
        buttons = []
        cmd = request.GET.get('cmd', None)
        iden = request.GET.get('iden', None)
        prnt('popup',cmd,iden)
        if cmd:
            from utils.models import get_sigData
            if 'new_key' in cmd:
                if '_security' in cmd:
                    # security_upk = UserPubKey.objects.filter(User_obj=user, keyType='security', end_life_dt=None).values('algorithm').first()
                    if '_proceed' in cmd:
                        strength = request.GET.get('var', 'ML_DSA_44')
                        security_upk = UserPubKey.objects.filter(User_obj=user, keyType='security', end_life_dt=None).order_by('created').first()
                        upk_id = hash_obj_id('UserPubKey')
                        upk_obj = UserPubKey(id=upk_id, User_obj_id=user.id)
                        upk_obj.initialize()
                        acct_upk = UserPubKey.objects.filter(User_obj=user, keyType='account', end_life_dt=None).values('id').order_by('created').first()
                        context = {
                            'title': 'Change Security Key' if security_upk else 'Create Security Key',
                            'cmd': 'update_key' if security_upk else 'create_key',
                            'requires': security_upk.algorithm if security_upk else 'account',
                            'new_password': 'security',
                            'keyType': 'security',
                            'strength': strength,
                            'blank_upkData' : get_signing_data(upk_obj, sort_data=False),
                            'extra_data': {'current_upkData' : get_signing_data(security_upk, sort_data=False, include_sig=True) if security_upk else None,
                                        'accnt_upkId': acct_upk['id']}
                        }
                        return render(request, "accounts/templates/edit_key.html", context)
                    else:
                        if UserPubKey.objects.filter(User_obj=user, keyType='security', end_life_dt=None).exists():
                            text = 'This will change your security passphrase.\n' \
                            'Your current security passhprase and current login passphrase are required.\n' \
                            '\n**It is very important to only input your passphrase while on trusted domains.**\n' \
                            '\nThe only officially trusted domain is SoSayUs.com. Not including xxxx.SoSayUs.com.' \
                            '\nPassphrases never leave your device and cannot be retrieved or reset if lost.\n' \
                            'Store your passphrases in a secure place.\n'
                        else:
                            text = 'A security key adds extra protection to your account.\n' \
                            'Editing keys would require your login passphrase AND your security passphrase.\n' \
                            'A security passphrase can be anything you wish. Longer is stronger.\n' \
                            '\n**It is very important to only input your passphrase while on trusted domains.**\n' \
                            '\nThe only officially trusted domain is SoSayUs.com. Not including xxxx.SoSayUs.com.' \
                            '\nPassphrases never leave your device and cannot be retrieved or reset if lost.\n' \
                            'Store your passphrases in a secure place.\n'
                        buttons = [
                            {'action':"modalPopUp",
                            'fields':['','/user/settings?style=popup&cmd=new_key_security_proceed&var=ML_DSA_44'],
                            'text':'Continue Strength 3'},
                            {'action':"modalPopUp",
                            'fields':['','/user/settings?style=popup&cmd=new_key_security_proceed&var=ML_DSA_65'],
                            'text':'Continue Strength 4'},
                            {'action':"modalPopUp",
                            'fields':['','/user/settings?style=popup&cmd=new_key_security_proceed&var=ML_DSA_87'],
                            'text':'Continue Strength 5'},
                        ]
                elif '_account' in cmd:
                    # new account key must rotate signing key at same time
                    current_upk = UserPubKey.objects.filter(User_obj=user, keyType='account', end_life_dt=None).order_by('created').first()
                    if '_proceed' in cmd:
                        if current_upk:
                            current_upk_signing = UserPubKey.objects.filter(User_obj=user, keyType='signing', end_life_dt=None).order_by('created').first()
                            prnt('current_upk_signing',current_upk_signing)
                            strength = request.GET.get('var', 'ML_DSA_44')
                            security_upk = UserPubKey.objects.filter(User_obj=user, keyType='security', end_life_dt=None).values('algorithm').order_by('created').first()
                            upk_id = hash_obj_id('UserPubKey')
                            upk_obj = UserPubKey(id=upk_id, User_obj_id=user.id)
                            upk_obj.initialize()
                            context = {
                                'title': 'Change Account Passphrase',
                                'cmd': 'update_key',
                                'requires': security_upk['algorithm'] if security_upk else 'account',
                                'new_password': 'account',
                                'keyType': 'account',
                                'strength': strength,
                                'blank_upkData' : get_signing_data(upk_obj, sort_data=False),
                                'extra_data': {'current_upkData' : get_signing_data(current_upk, sort_data=False, include_sig=True),
                                            'userData' : get_signing_data(user, sort_data=False, include_sig=True),
                                            'additional_upks' : json.dumps([get_signing_data(current_upk_signing, sort_data=False, return_dict=True)]),
                                            'accnt_upkId': current_upk.id}
                            }
                            return render(request, "accounts/templates/edit_key.html", context)
                    else:
                        text = 'This will change your account passphrase.\n' \
                        'You may change your passphrase to anything you wish.\n' \
                        'It is strongly recommended to use a suggested passphrase. Longer is stronger.\n' \
                        '\n**It is very important to only input your passphrase while on trusted domains.**\n' \
                        '\nThe only officially trusted domain is SoSayUs.com. Not including xxxx.SoSayUs.com.' \
                        '\nPassphrases never leave your device and cannot be retrieved or reset if lost.\n' \
                        'Store your passphrases in a secure place.\n'
                        buttons = [
                            {'action':"modalPopUp",
                            'fields':['',f'/user/settings?style=popup&cmd=new_key_account_proceed&iden={iden}&var=ML_DSA_44'],
                            'text':'Continue Strength 3'},
                            {'action':"modalPopUp",
                            'fields':['',f'/user/settings?style=popup&cmd=new_key_account_proceed&iden={iden}&var=ML_DSA_65'],
                            'text':'Continue Strength 4'},
                            {'action':"modalPopUp",
                            'fields':['',f'/user/settings?style=popup&cmd=new_key_account_proceed&iden={iden}&var=ML_DSA_87'],
                            'text':'Continue Strength 5'},
                        ]
                elif '_signing' in cmd:
                    current_upk = UserPubKey.objects.filter(User_obj=user, keyType='signing', end_life_dt=None).order_by('created').first()
                    if '_proceed' in cmd:
                        if current_upk:
                            sigData = get_sigData(current_upk)
                            signed_by = UserPubKey.objects.filter(id=sigData['pk'], User_obj=user).values('algorithm','keyType').order_by('created').first()
                            if signed_by['algorithm'] == 'secp256k1':
                                requires = 'signing'
                            else:
                                requires = 'account'
                        else:
                            requires = 'account'
                        upk_id = hash_obj_id('UserPubKey')
                        upk_obj = UserPubKey(id=upk_id, User_obj_id=user.id)
                        upk_obj.initialize()
                        acct_upk = UserPubKey.objects.filter(User_obj=user, keyType='account', end_life_dt=None).values('id').order_by('created').first()
                        context = {
                            'title': 'Rotate Signing Key',
                            'cmd': 'update_key',
                            'requires': requires,
                            'new_password': False,
                            'keyType': 'signing',
                            'strength': 'secp256k1',
                            'blank_upkData' : get_signing_data(upk_obj, sort_data=False),
                            'extra_data': {'current_upkData' : get_signing_data(current_upk, sort_data=False, include_sig=True, full_pk=True) if current_upk else '',
                                        'userData' : get_signing_data(user, sort_data=False, include_sig=True, full_pk=True),
                                        'accnt_upkId': acct_upk['id']}
                        }
                        prnt('context',context)
                        return render(request, "accounts/templates/edit_key.html", context)
                    else:
                        text = 'This will rotate your signing key.\n' \
                        'If no signing key exists a new one will be created.\n' \
                        'Signing keys are used for quick interactions like voting and bookmarking.\n' \
                        'Signing keys are automatically rotated periodically.\n' \
                        'Only continue if you think your current signing key has been compromised.\n' \
                        '\n**It is very important to only input your passphrase while on trusted domains.**\n' \
                        '\nThe only officially trusted domain is SoSayUs.com. Not including xxxx.SoSayUs.com.' \
                        '\nPassphrases never leave your device and cannot be retrieved or reset if lost.\n' \
                        'Store your passphrases in a secure place.\n'
                        buttons = [
                            {'action':"modalPopUp",
                            'fields':['',f'/user/settings?style=popup&cmd=new_key_signing_proceed&iden={current_upk.id if current_upk else "None"}&var=secp256k1'],
                            'text':'Continue'},
                        ]
            elif 'disable_key' in cmd:
                if iden:
                    from utils.locked import dt_to_string
                    # obj = get_dynamic_model(iden, id=iden)
                    obj = UserPubKey.objects.filter(id=iden, User_obj=user).first()
                    if obj and obj.end_life_dt:
                        text = f'This key was already disabled on {dt_to_string(obj.end_life_dt)}'
                    elif obj and not obj.end_life_dt:
                        if '_proceed' in cmd:
                            # if obj is 'account' key, disable all active keys 
                            security_upk = UserPubKey.objects.filter(User_obj=user, keyType='security', end_life_dt=None).values('algorithm').order_by('created').first()
                            acct_upk = UserPubKey.objects.filter(User_obj=user, keyType='account', end_life_dt=None).values('id').order_by('created').first()
                            context = {
                                'title': f'Disable {obj.keyType.capitalize()} Key',
                                'cmd': 'update_key',
                                'requires': security_upk['algorithm'] if security_upk else 'account',
                                'keyType': obj.keyType,
                                'iden': obj.id,
                                'extra_data': {'current_upkData' : get_signing_data(obj, sort_data=False, include_sig=True),
                                            'accnt_upkId': acct_upk['id']}
                            }
                            return render(request, "accounts/templates/edit_key.html", context)
                        else:
                            if obj.keyType == 'account':
                                text = 'Disabling your Account Key will permanently lock your account.\n' \
                                'All active keys will be disabled.\n' \
                                'Nobody will ever be able to take action with this account again.\n' \
                                'Think carefully before you continue with this.'
                            elif obj.keyType == 'security':
                                text = 'Disabling your Security Key will weaken your account security.\n' \
                                'If the key has been compromised you can rotate it with\n"Change Security Key" in Account Settings.'
                            elif obj.keyType == 'signing':
                                text = 'This will disable your Signing Key.\n' \
                                'Without a Signing Key user interactions such as voting and bookmarking cannot be done.\n' \
                                'A new one can be created later.'
                            elif obj.keyType == 'node':
                                from network.models import Node
                                node = Node.objects.filter(id=obj.nodeId, User_obj=user).only('activated_dt','node_name','id','lastUpdate').first()
                                if node:
                                    if node.activated_dt:
                                        text = f'This will permanently deactivate your node "{node.node_name}".\n' \
                                        f'ID {node.id}. Last updated {dt_to_string(obj.lastUpdate)}\n' \
                                        "This node is currently active. Disabling it's key will immediately and permanently remove the device from the network.\n" \
                                        "It is recommended to deactivate and uninstall through the SoNode software."
                                    else:
                                        text = f'This will permanently deactivate your node "{node.node_name}".\n' \
                                        f'ID {node.id}. Last updated {dt_to_string(obj.lastUpdate)}\n' \
                                        "Disabling it's key will immediately and permanently remove the device from the network.\n" \
                                        "It is recommended to disable the key by uninstalling the node with the SoNode software."
                                else:
                                    text = 'Node not found.\n' \
                                    'Are you sure want to disable this key?'

                            else:
                                text = 'Are you sure you want to permanently disable this key?'

                            buttons = [
                                {'action':"modalPopUp",
                                'fields':['test',f'/user/settings?style=popup&cmd=revoke_key_proceed&iden={obj.id}'],
                                'text':'Continue'}
                            ]
                    else:
                        text = f'key {iden} not found'
            elif 'update_key' in cmd:
                err = 'no_data'
                # ensure not creating multiples - only 1 key for security, account, signing
                try:
                    received_data = json.loads(request.body)
                    prnt('received_data',received_data)
                    err = 'data1'
                    new_upkData = json.loads(received_data.get('new_upkData', '{}'))
                    prnt('new_upkData',new_upkData)
                    updated_upkData = json.loads(received_data.get('updated_upkData', '{}'))
                    prnt('updated_upkData',updated_upkData)
                    additional_upks = json.loads(received_data.get('additional_upks', '{}'))
                    prnt('additional_upks',additional_upks)
                    updated_userData = json.loads(received_data.get('updated_userData', '{}'))
                    prnt('updated_userData',updated_userData)
                    sig_map = received_data.get('sig_map', {})
                    prnt('sig_map',sig_map)
                    upk_map = {}
                    err = 'data2'

                    if new_upkData and UserPubKey.objects.filter(id=new_upkData['id']).exists():
                        return JsonResponse({'message' : 'Fail', 'msg' : 'New Passphrase Not Accepted'})
                    # if new_upkData and new_upkData['keyType'] in ['security','account','signing']:
                    #     if UserPubKey.objects.filter(User_obj=user, keyType=new_upkData['keyType'], end_life_dt=None).exists():
                    #         return JsonResponse({'message' : 'Fail', 'msg' : f"Active {new_upkData['keyType'].capitalize()} Key Already Exists"})
                    
                    err = 'verify1'
                    good = False
                    

                    sig_idens = []
                    for iden, iden_list in sig_map.items():
                        sig_idens = list(set(sig_idens) | set(iden_list))

                    sign_upks = UserPubKey.objects.filter(id__in=sig_idens, User_obj=user, keyType__in=['account', 'security', 'signing'], end_life_dt=None)

                    if sign_upks and all(i for i in sign_upks if i.id in sig_idens):
                        err = f"verify2_{new_upkData['keyType']}"
                        prnt(err)
                        proceed = verify_data(get_signing_data(new_upkData), sign_upks, new_upkData['signed'])
                        if proceed and additional_upks:
                            prnt("additional_upks['new']",additional_upks['new'])
                            for upkData in additional_upks['new']:
                                if proceed:
                                    err = f"verify3_{upkData['keyType']}"
                                    prnt(err)
                                    proceed = verify_data(get_signing_data(new_upkData), sign_upks, new_upkData['signed'])
                                else:
                                    break
                            if proceed:
                                prnt("additional_upks['previous']",additional_upks['previous'])
                                for upkData in additional_upks['previous']:
                                    if proceed:
                                        err = f"verify4_{upkData['keyType']}"
                                        prnt(err)
                                        proceed = verify_data(get_signing_data(upkData), sign_upks, upkData['signed'])
                                    else:
                                        break
                        prnt('proceed updated_upkData',updated_upkData)
                        if proceed and updated_upkData:
                            err = f"verify5_updatedUPK"
                            prnt(err)
                            proceed = verify_data(get_signing_data(updated_upkData), sign_upks, updated_upkData['signed'])

                        prnt('proceed updated_userData',updated_userData)
                        if proceed and updated_userData:
                            err = f"verify6_userdata"
                            prnt(err)
                            proceed = verify_data(get_signing_data(updated_userData), sign_upks, updated_userData['signed'])

                        from network.models import Signature
                        from utils.models import sync_model, share_with_network, save_sigs
                        def create_key(upkData):
                            upk = UserPubKey()
                            good = False
                            prnt('create new upk')
                            try:
                                sig_objs = []
                                for key, value in upkData.items():
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
                                                    prnt('b')
                                                    signed[dt]['req'] = sig_data['req']
                                                prnt('signed[dt]',signed[dt])

                                                if 'sig' in sig_data:
                                                    sig_obj = Signature.objects.filter(pointerId=upk.id, Upk_obj__id=sig_data['pk'], DateTime=string_to_dt(dt)).exists()
                                                    prnt('sig_objA:',sig_obj,sig_data['pk'])
                                                    if not sig_obj:
                                                        sig_obj = Signature(pointerId=upk.id, Upk_obj_id=sig_data['pk'], sig=sig_data['sig'], DateTime=string_to_dt(dt))
                                                        sig_objs.append(sig_obj)
                                                        from utils.locked import convert_to_dict
                                                        prnt('sig_obj',convert_to_dict(sig_obj))
                                            setattr(upk, key, signed)
                                            prnt('set signed',upk.signed)
                                        else:
                                            setattr(upk, key, value)
                                prnt('save upk')
                                err = 'save1'
                                prnt('upk signed',upk.signed)
                                upk.save(is_new=True)
                                err = 'refresh1'
                                upk.refresh_from_db()
                                prnt('upk signed2',upk.signed)
                                err = 'sigSave1'
                                save_sigs(sig_objs)
                                # err = 'verify7'
                                # for sign_id in sig_map[upk.id]:
                                err = f'verify7_{upk.id[:10]}'
                                if verify_data(get_signing_data(upk), sign_upks):
                                # if upk_map[sign_id].verify(get_signing_data(upk)):
                                    err = f'share1_{upk.id[:10]}'
                                    # upk, good = sync_and_share_object(upk, upkData)
                                    upk, sigs, good, updatedDB = sync_model(upk, upkData, do_save=True, skip_verify=True)
                                    if good and updatedDB:
                                        err = 'final1'
                                    # else:
                                    #     break
                            except Exception as e:
                                prnt('key fail1', str(e))
                                err += f"_{e}"
                            err = f"{upkData['keyType']}_{err}"
                            prnt(err)
                            return upk, good, err
                    
                        if proceed:
                            share_items = []
                            err = 'sync1'
                            new_upk, good, err = create_key(new_upkData)
                            if good:
                                share_items.append(new_upk)
                                if additional_upks:
                                    prnt("additional_upks['new']22",additional_upks['new'])
                                    for upkData in additional_upks['new']:
                                        additional_new_upk, good, err = create_key(upkData)
                                        if not good:
                                            break
                                        else:
                                            share_items.append(additional_new_upk)
                                    if good:
                                        prnt("additional_upks['previous']22",additional_upks['previous'])
                                        for upkData in additional_upks['previous']:
                                            err = f"sync_err_{upkData['keyType']}_{upkData['id']}"
                                            obj = UserPubKey.objects.filter(id=upkData['id']).first()
                                            obj, sigs, good, updatedDB = sync_model(obj, upkData, do_save=True, skip_verify=True)
                                            if not good or not updatedDB:
                                                break
                                            elif good:
                                                share_items.append(obj)
                                prnt('good',good,'updated_upkData',updated_upkData)
                                if good and updated_upkData:
                                    err = f"sync_err_updated_upkData_{updated_upkData['id']}"
                                    obj = UserPubKey.objects.filter(id=updated_upkData['id']).first()
                                    obj, sigs, good, updatedDB = sync_model(obj, updated_upkData, do_save=True, skip_verify=True)
                                    if not updatedDB:
                                        good = False
                                    elif good:
                                        share_items.append(obj)
                                prnt('good',good,'updated_userData',updated_userData)
                                if good and updated_userData:
                                    err = f"sync_err_updated_userData_{updated_userData['id']}"
                                    obj = User.objects.filter(id=updated_userData['id']).first()
                                    # upk, good = sync_and_share_object(upk, upkData)
                                    obj, sigs, good, updatedDB = sync_model(obj, updated_userData, do_save=True, skip_verify=True)
                                    if not updatedDB:
                                        good = False
                                    elif good:
                                        share_items.append(obj)
                                    

                        if good:
                            share_with_network(share_items)
                            return JsonResponse({'message' : 'Valid', 'msg' : 'Accepted'})
                except Exception as e:
                    prnt('key fail2',err, str(e))
                    err += f"_2_{e}"
                return JsonResponse({'message' : 'Invalid', 'error' : err})
            
        context = {
            'text': text,
            'buttons': buttons
        }
        return render(request, "modals/generic_modal.html", context)

    else:
        region_id = request.GET.get('region_id', None)
        country_dict, gov_dict, subRegions, subGovernments = get_regions_and_govs(region_id)
        if style == 'index':
            context = get_index(request, country_dict, gov_dict)
            context = get_user_sending_data(user, context)
            return render(request, "utils/fetch_index.html", context)
        else:
            nav_options = []
            key_types = ['All','Active','Account','Signing','Node','Security','Other']
            if include_nav == 'True':
                nav_options = [
                    nav_item('scrollto', 'Account', var='user'),
                    nav_item('scrollto', 'Keys', var='keys'),
                    nav_item('button', 'Key Type: %s'%(view), 'subNavWidget', 'viewForm', fields=key_types, key='view'),
                    ]
            if view == 'All':
                upks = UserPubKey.objects.filter(User_obj=user).only('id','keyType','algorithm','created','end_life_dt','nodeId', 'Block_obj__id')
            elif view == 'Active':
                upks = UserPubKey.objects.filter(User_obj=user, end_life_dt=None).only('id','keyType','algorithm','created','end_life_dt','nodeId', 'Block_obj__id')
            elif view == 'Other':
                key_types.remove('All')
                key_types.remove('Active')
                key_types.remove('Other')
                upks = UserPubKey.objects.filter(User_obj=user).exclude(keyType__in=[i.lower() for i in key_types]).only('id','keyType','algorithm','created','end_life_dt','nodeId', 'Block_obj__id')
            else:
                upks = UserPubKey.objects.filter(User_obj=user, keyType=view.lower()).only('id','keyType','algorithm','created','end_life_dt','nodeId', 'Block_obj__id')
            context = {
                'cards': 'user_settings',
                'view': view,
                'page':page,
                'style':style,
                'nav_bar': nav_options,   
                'feed_title': title,
                'title': title,
                'upks': upks,
                'security_upk': UserPubKey.objects.filter(User_obj=user, keyType='security', end_life_dt=None).only('id').first()
            }
            return render_view(request, context, country=country_dict)



def user_set_region_view(request):
    prnt('-user_set_region_view')
    u = request.user
    
    title = 'My Region'
    cards = 'region_form'
    style = request.GET.get('style', 'index')
    view = request.GET.get('view', 'constituency')
    address = request.POST.get('address')

    reps = get_reps(request.user)
    context = {
        'u': u,
        'title': title,
        'cards': cards,
        'view': view,
        'form': form,
    }
    context = {**reps, **context}
    return render_view(request, context)


@csrf_exempt
def receive_interaction_data_view(request):
    prnt('-receive_interaction_data_view')
    if request.method == 'POST':
        data = json.loads(request.POST.get('objData'))
        addon = request.POST.get('addon')
        from utils.models import get_sigData
        try:
            sig_data = get_sigData(data)
        except Exception as e:
            prnt('err invalid signature',str(e))
            return JsonResponse({'message' : 'Invalid publicKey'})
        
        publicKey = sig_data['pk']
        signature = sig_data['sig']
        try:
            user_id = data['User_obj']
            user = User.objects.filter(id=user_id).exists()
            if not user:
                prnt('user not found', user_id)
                return JsonResponse({'message' : 'User not found'})
            from utils.models import is_id, get_or_create_model, has_method, hash_upk_id
            from utils.locked import verify_data
            try:
                if is_id(publicKey):
                    iden = publicKey
                else:
                    iden = hash_upk_id(publicKey)
                upk = UserPubKey.objects.filter(id=iden, User_obj__id=user_id, keyType='signing', end_life_dt=None).only('created','Block_obj','Block_obj__validated').first()
                prnt('upk',upk)
                if not upk or not upk.Block_obj or not upk.Block_obj.validated:
                    if not upk or upk.created < now_utc() - datetime.timedelta(hours=5):
                        prnt('Invalid publicKey','upk.created',upk.created)
                        return JsonResponse({'message' : 'Invalid publicKey'})
                if len(data['signed']) == 1:
                    pubKey = upk.publicKey
                else:
                    pubKey = None
                is_valid = verify_data(get_signing_data(data, sort_data=False), pubKey, data['signed'])
                prnt('is_valid',is_valid)
                if addon and is_valid:
                    addon = json.loads(addon)
                    is_valid = verify_data(get_signing_data(addon, sort_data=False), pubKey, addon['signed'])
                    if not is_valid:
                        prnt('addon not valid')
                        return JsonResponse({'message' : 'Invalid addon'})
                    xModel = get_or_create_model(addon['objType'], id=addon['id'])
                    addon, is_valid = sync_and_share_object(addon, addon, skip_verify=True)
                    if not is_valid:
                        prnt('addon not valid2')
                        return JsonResponse({'message' : 'Invalid addon2'})
                if is_valid:
                    xModel = get_or_create_model(data['objType'], id=data['id'])
                    xModel, good = sync_and_share_object(xModel, data, skip_verify=True)
                    prnt('good',good)
                    if good:
                        if has_method(xModel, 'boot'):
                            xModel.boot()
                        if has_method(xModel, 'on_update'):
                            import django_rq
                            queue = django_rq.get_queue('low')
                            queue.enqueue(xModel.on_update, job_timeout=20, result_ttl=3600)
                            prnt('added to low')
                        response = JsonResponse({'message' : 'Success'})
                        return response
                    else:
                        return JsonResponse({'message' : 'Sync failed'})
                else:
                    return JsonResponse({'message' : 'Verification failed'})
            except Exception as e:
                prnt('interaction err 364', str(e))
                return JsonResponse({'message' : 'Invalid publicKey'})
        except Exception as e:
            return JsonResponse({'message' : f'Error {str(e)}'})

@csrf_exempt
def reaction_view(request, iden, item):
    prnt('-reaction_view', iden, item)
    user = request.GET.get('user', None)
    if user:
        user = User.objects.filter(id=user).values('id').first()
    if not user:
        return JsonResponse({'message' : 'login'})
    
    if not 'person' in item:
        post = Post.objects.filter(id=iden).only('id','pointerId','Region_obj__id').first()
    if item.lower() in ['none','yea','nay']:
        prnt('is vote')
        reuse = False
        addon = {}
        addon_fields = {}
        action = UserAction.objects.filter(User_obj__id=user['id'], postId=post.id).first()
        if not action:
            action = UserAction(User_obj_id=user['id'], Post_obj=post, postId=post.id, pointerId=post.pointerId, created=now_utc(), id=hash_obj_id(UserAction, length=UserAction.iden_length, specific_data=f"UserAction_{user['id']}_{dt_to_string(now_utc())}"))

        pointer = post.get_pointer(set_pointer=False)
        if pointer:
            if has_method(pointer, 'user_action_addon'):
                addon = pointer.user_action_addon(user['id'])
                if addon:
                    addon_fields = addon.required_fields()
                    addon = get_signing_data(addon, sort_data=False)
                    if addon and len(addon) > 10:
                        # limited fields allowed in addon
                        addon = {}
            
        return JsonResponse({'message' : 'sign-return', 'data' : get_signing_data(action, sort_data=False), 'addon' : addon, 'addonFields' : json.dumps(addon_fields)})

    elif item == 'saveButton':
        reuse = False
        save = SavePost.objects.filter(User_obj=user, postId=post.id).first()
        if save:
            reuse = check_dataPacket(save)
        if not reuse:
            save = SavePost(User_obj=user, postId=post.id, pointerId=post.pointerId, id=hash_obj_id('SavePost'), created=now_utc())
            
        return JsonResponse({'message' : 'sign-return', 'data' : get_signing_data(save)})

    elif item == 'follow' or item == 'unfollow':
        prnt('follow')
        if not post:
            post = Post.objects.filter(id=iden).first()
            if not post:
                post = Archive.objects.filter(id=iden).first()

        return JsonResponse({'message' : 'Please fill, sign and return', 'data' : get_signing_data(user)})
        
    elif item == 'follow-person':
        person = Person.objects.filter(id=iden).first()
        if person in userOptions.follow_person.all():
            userOptions.follow_person.remove(person)
        else:
            userOptions.follow_person.add(person)
        userOptions.save()
        return render(request, "utils/dummy.html", {'result':item})
    return JsonResponse({'message' : 'sign-return', 'userData' : get_signing_data(user)})


def quick_login_view(request, username=None, password=None):
    print('-quick_login_view user',user,'password',password)
    from accounts.models import User
    from django.contrib.auth import (
        authenticate,
        get_user_model,
        login,
        logout,
        )
    user = User.objects.filter(username=username).first()
    if user:
        try:
            # user = authenticate(username=username, password=password)
            login(request, user)
            return render(request, "utils/dummy.html", {"result": 'Success'})
        except Exception as e:
            print('err:',str(e))
            return render(request, "utils/dummy.html", {"result": 'Fail Auth?2', 'err':str(e)})


@csrf_exempt
def set_sonet_view(request):
    prnt('---set_sonet_view')
    try:
        err = 1
        if request.method == 'POST':
            sonet_exists = Sonet.objects.exists()
            raw_data = request.body.decode('utf-8')
            received_data = json.loads(raw_data)
            sonetData_json = json.loads(received_data.get('sonetData'))
            prnt('sonetData_json',sonetData_json)
            err = 2
            from utils.models import get_or_create_model, sync_model
            sonet = get_or_create_model('Sonet', id=sonetData_json['id'])
            prnt('sonet obj',sonet)
            err = 3
            sonet, sigs, valid_obj, updatedDB = sync_model(sonet, sonetData_json)
            prnt('sonet-good',valid_obj)
            err = 4
            if not valid_obj:
                return JsonResponse({'message' : 'A problem occured - obj not valid'})
            elif updatedDB:
                if not sonet_exists:
                    err = 5
                    from network.models import Node, Plugin
                    node = Node()
                    node.id = hash_obj_id(node)
                    err = 6
                    earth = Region(created=now_utc(), func='super', nameType='Planet', Name='Earth', commitChain='Sonet', ImgLinks={"flag":"img/earth_pic.jpg"})
                    earth.id = hash_obj_id(earth, length=0)
                    err = 7
                    accounts = Plugin(app_name='accounts', Title='Accounts')
                    accounts.initialize()
                    err = 8
                    network = Plugin(app_name='network', Title='Network')
                    network.initialize()
                    err = 9
                    posts = Plugin(app_name='posts', Title='Posts')
                    posts.initialize()
                    err = 10
                    transactions = Plugin(app_name='transactions', Title='SoPay', AbbrTitle='pay', user_facing=True)
                    transactions.initialize()
                    legis = Plugin(app_name='legis', Title='SoVote', AbbrTitle='vote', Subtitle='Decentralized Democracy', user_facing=True)
                    legis.initialize()
                    err = 11
                    return JsonResponse({'message' : 'Success', 'sonet' : get_signing_data(sonet), 'earth' : get_signing_data(earth), 'node' : get_signing_data(node), 'accounts':get_signing_data(accounts),'network':get_signing_data(network),'posts':get_signing_data(posts),'transactions':get_signing_data(transactions),'legis':get_signing_data(legis)})
                else:
                    err = 8
                    return JsonResponse({'message' : 'Success', 'sonet' : get_signing_data(sonet)})
            else:
                return JsonResponse({'message' : 'Not Saved'})
    except Exception as e:
        return JsonResponse({'message' : f'A problem occured, {str(e)} -- err:{err}'})
        
@csrf_exempt
def verify_superuser_view(request):
    prnt('-verify_superuser_view')
    try:
        if request.method == 'POST':
            user_id = request.POST.get('user_id')
            signed_obj = json.loads(request.POST.get('signed_obj'))
            publicKey = request.POST.get('publicKey',{})
            signature = request.POST.get('signed')
            from utils.models import round_time, dt_to_string
            x = dt_to_string(round_time(dt=now_utc(), dir='down', amount='evenhour'))
            proceed = True
            is_super = False
            if proceed and signed_obj['dt'] != x:
                proceed = False
            if proceed:
                user = User.objects.filter(id=user_id).first()
                if not user:
                    proceed = False
                else:
                    if user.assess_super_status():
                        is_super = user.verify_sig(signed_obj, signature)
            return JsonResponse({'message' : 'success', 'is_super':is_super})


    except Exception as e:
        return JsonResponse({'message' : f'A problem occured, {str(e)}'})
        

