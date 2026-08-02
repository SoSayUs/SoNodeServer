

# from unittest.result import failfast
from django.db import models
from django.db.models import Avg

import django_rq

from accounts.models import *
from legis.models import *
from legis.utils import get_gov, get_region, modify_gov, add_gov_menu_item
from posts.models import *
from posts.views import get_ordinal
from utils.models import (
    timezonify, dt_to_string, open_browser, finishScript, create_share_object, 
    logEvent, logError, testing, declare_var, save_and_return, get_model_prefix,
    save_image
    )



import datetime
# from dateutil.parser import parse
from dateutil import parser
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import pytz
import time
# import re
import json
# import operator

from selenium import webdriver 
from selenium.webdriver.common.by import By 
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

province_list = {
  "Alberta": "AB",
  "British Columbia": "BC",
  "Manitoba": "MB",
  "New Brunswick": "NB",
  "Newfoundland and Labrador": "NL",
  "Northwest Territories": "NT",
  "Nova Scotia": "NS",
  "Nunavut": "NU",
  "Ontario": "ON",
  "Prince Edward Island": "PE",
  "Quebec": "QC",
  "Saskatchewan": "SK",
  "Yukon": "YT"
}
prov_or_terr = {
  "Alberta": "Province",
  "British Columbia": "Province",
  "Manitoba": "Province",
  "New Brunswick": "Province",
  "Newfoundland and Labrador": "Province",
  "Northwest Territories": "Territory",
  "Nova Scotia": "Province",
  "Nunavut": "Territory",
  "Ontario": "Province",
  "Prince Edward Island": "Province",
  "Quebec": "Province",
  "Saskatchewan": "Province",
  "Yukon": "Territory"
}

runTimes = {
    'initialize_region' : 1000,
    'get_bills' : 1000, 'get_senate_bills' : 1000, 'get_house_bills' : 1000, 'get_all_bills' : 7200, 
    'get_house_agendas' : 200, 'get_house_debates' : 1000, 'get_senate_debates' : 600,
    'get_house_persons' : 2000, 'get_senate_persons' : 2000, 'get_senate_agendas' : 200,
    'get_house_motions' : 200, 'get_senate_motions' : 200, 'get_senate_committees' : 200, 'get_house_expenses' : 600,
    'get_todays_xml_agenda' : 1000, 'get_house_committees' : 1000, 'get_upcoming_senate_committees' : 200,
    }

typical = ['get_house_agendas', 'get_senate_agendas', 'get_todays_xml_agenda',
    # 'get_house_committees', 'get_senate_committees',
    ]

functions = { # in gov_region timezone
    "2025-03-13" : [
    # # {'date' : [1], 'dayOfWeek' : ['x'], 'hour' : [2], 'cmds' : ['get_house_expenses']},
    {'date' : ['x'], 'dayOfWeek' : [6,2], 'hour' : [5], 'cmds' : ['get_house_persons', 'get_senate_persons']},
    # {'date' : ['x'], 'dayOfWeek' : [0], 'hour' : [20], 'cmds' : ['get_house_debates']},
    # {'date' : ['x'], 'dayOfWeek' : [3], 'hour' : [20], 'cmds' : ['get_senate_motions']},
    # {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [9,16], 'cmds' : ['get_bills'] },
    # {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [21], 'cmds' : ['get_house_debates']},
    # # mon - sat
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [8, 10, 12, 18, 24], 'cmds' : ['get_house_agendas'] },
    # {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [8, 10, 12, 18, 24], 'cmds' : ['get_house_agendas', 'get_senate_agendas', 'get_todays_xml_agenda'] },
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [3, 7, 10, 12, 13, 15, 17, 20, 23], 'cmds' : ['get_bills'] },
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [2, 6, 12, 18, 22], 'cmds' : ['get_house_debates', 'get_house_motions']},
    {'date' : ['x'], 'dayOfWeek' : [0,1,2,3,4,5], 'hour' : [4, 8, 13, 19, 23], 'cmds' : ['get_senate_debates', 'get_senate_motions']},
    ],
}

approved_models = {
    'initialize_region' : ['Government', 'Agenda', 'AgendaTime', 'AgendaItem', 'Person', 'Party', 'District', 'Region', 'ImageFile'],
    'get_house_agendas' : ['Government', 'Agenda', 'AgendaTime', 'AgendaItem'],
    'get_house_persons' : ['Government', 'Person', 'Party', 'District', 'Region', 'ImageFile'],
    'get_senate_persons' : ['Government', 'Person', 'District', 'Party', 'Region', 'ImageFile'],
    # 'get_bills' : ['Bill', 'BillVersion', 'Role', 'Person', 'Notification'],
    'get_bills' : ['Bill', 'BillText', 'Committee', 'Meeting', 'Government', 'Notification', 'Person'],
    'get_house_bills' : ['Bill', 'BillVersion', 'Role', 'Person', 'Notification'],
    'get_senate_bills' : ['Bill', 'BillVersion', 'Role', 'Person', 'Notification'],
    'get_house_debates' : ['Meeting', 'Statement', 'Agenda', 'Government', 'Person', 'Bill'],
    'get_senate_debates' : ['Meeting', 'Statement', 'Bill'],
    'get_house_motions' : ['Government', 'Motion', 'Vote', 'Interaction', 'Person'],
    'get_senate_motions' : ['Government', 'Motion', 'Vote', 'Interaction'],
    'get_user_region' : ['District', 'Region', 'Role', 'Party', 'Person'],
    }

gov_logo_links = {"House": "img/regions/canada/house.png", "Senate": "img/regions/canada/senate.png"}

get_wiki = not testing()

def initialize_region(special=None, dt=None, iden=None):
    get_persons_commons_uk(special=special, iden=iden)
    get_persons_lords_uk(special=special, iden=iden)


def get_persons_commons_uk(special=None, iden=None):
    func = 'get_persons_commons_uk'
    get_persons_uk(special=special, iden=iden, chamber='Commons', func=func)

def get_persons_lords_uk(special=None, iden=None):
    func = 'get_persons_lords_uk'
    get_persons_uk(special=special, iden=iden, chamber='Commons', func=func)

def get_persons_uk(special=None, chamber=None, value='current', dt=None, iden=None, func='get_persons_uk'):
    prnt(f'--{func} UK', now_utc())
    dt = declare_var(dt, now_utc())
    gov = None
    chamber = declare_var(chamber, 'Commons')
    if chamber == 'Commons':
        office = 'Member of Parliament'
        chamber_num = '1'
    else:
        chamber = 'Lords'
        office = 'Lord'
        chamber_num = '2'
    country = get_region('United Kingdom')
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = get_gov(country)
    gov = modify_gov(gov, [{'Office_array':office},{'Chamber_array':chamber},{'menuItem_array':'Officials'}])
    log.updateShare(gov)
    current_mps = []

    def person_fetcher(url, skip, found, persons, parties):
        fetch_url = url + f'&skip={skip}'
        print('url',fetch_url)
        try:
            again = False
            r = requests.get(fetch_url)
            data = json.loads(r.content)
            for key, val in data.items():
                print('--',key)
                if isinstance(val, list):
                    for i in val:
                        if isinstance(i, dict):
                            for k, v in i.items():
                                print(k)
                                # if k == 'value':

                                if isinstance(v, dict):
                                    person = {}
                                    person['id'] = v['id']
                                    person['nameListAs'] = v['nameListAs']
                                    person['nameDisplayAs'] = v['nameDisplayAs']
                                    person['nameFullTitle'] = v['nameFullTitle']
                                    person['thumbnailUrl'] = v['thumbnailUrl']

                                    person['membershipFrom'] = v['latestHouseMembership']['membershipFrom']
                                    person['membershipFromId'] = v['latestHouseMembership']['membershipFromId']
                                    person['house'] = v['latestHouseMembership']['house']
                                    person['membershipStartDate'] = v['latestHouseMembership']['membershipStartDate']
                                    person['membershipEndDate'] = v['latestHouseMembership']['membershipEndDate']
                                    person['membershipEndReason'] = v['latestHouseMembership']['membershipEndReason']
                                    person['membershipEndReasonId'] = v['latestHouseMembership']['membershipEndReasonId']
                                    person['membershipStatus'] = {'statusIsActive': v['latestHouseMembership']['membershipStatus']['statusIsActive'], 'statusDescription': v['latestHouseMembership']['membershipStatus']['statusDescription'], 'statusId': v['latestHouseMembership']['membershipStatus']['statusId'], 'status': v['latestHouseMembership']['membershipStatus']['status'], 'statusStartDate': v['latestHouseMembership']['membershipStatus']['statusStartDate']}
                                    person['latestParty'] = v['latestParty']['id']

                                    if person['id'] not in persons:
                                        persons[person['id']] = person
                                        found += 1
                                        again = True

                                    if not parties.get(person['latestParty'], None):
                                        party = {}
                                        party['id'] = v['latestParty']['id']
                                        party['name'] = v['latestParty']['name']
                                        party['abbreviation'] = v['latestParty']['abbreviation']
                                        party['backgroundColour'] = v['latestParty']['backgroundColour']
                                        party['foregroundColour'] = v['latestParty']['foregroundColour']
                                        party['governmentType'] = v['latestParty']['governmentType']
                                        party['isIndependentParty'] = v['latestParty']['isIndependentParty']
                                        parties[party['id']] = party

                                # if isinstance(v, dict):
                                #     for a, b in v.items():
                                #         print(a, ':', b)
                                # else:
                                #     print(v)
                #         else:
                #             print(i)
                #         print()
                # else:
                #     print(val)
                print('---')
            print('found', found)
            skip += 20
            if again and skip < 800:
                time.sleep(1.5)
                persons, parties = person_fetcher(url, skip, found, persons, parties)
            else:
                print()
                print()
                # print()
                # print('persons::')
                # for person in persons:
                #     print(person)
                #     print()
                # print()
                # print()
                # print()
                # print('parties::')
                # for party in parties:
                #     print(party)
                #     print()

                # print()
                # print()
                print()
                print('total persons:', len(persons))
                print('total parties:', len(parties))
        except Exception as e:
            print('err1', str(e))
        return persons, parties

    def parse_regions(html, country, region_id, log):
        soup = BeautifulSoup(html, "html.parser")
        links = [
            {"text": a.get_text(), "href": a.get("href")} for a in soup.find_all("a")
        ]

        print()
        parent_region = country
        for link in reversed(links):
            print(link['text'])
            # print(link['href'])
            a = link['href'].find('region/') + len('region/')
            b = link['href'][a:].find('/')
            region_name = link['text']
            region_type = link['href'][a:a+b]
            print('R',region_type)
            if region_type == 'region':
                district = District.objects.filter(AltName=region_id).filter(Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=parent_region, gov_level='Federal', nameType='Federal District').first()
                if district:
                    if not district.Office_array or office not in district.Office_array:
                        modded_district = district.propose_modification()
                        modded_district.add_office(office)
                        district, districtU, district_is_new, log = save_and_return(district, None, log)
                if not district:
                    district = District(func=log.data['func'], Name=region_name, AltName=region_id, Country_obj=log.Region_obj, Region_obj=log.Region_obj, ProvState_obj=parent_region, gov_level='Federal', nameType='Federal District')
                    
                    district.add_office(office)
                if not district.Validator_obj or not district.Validator_obj.is_valid:
                    log.updateShare(district)
            else:
                if region_type == 'country':
                    region_type = 'Constituent Country'
                else:
                    region_type = region_type.capitalize()
                region = Region.objects.filter(Name=region_name, nameType=region_type, ParentRegion_obj=parent_region).first()
                if not region:
                    region = Region(func=func, Name=region_name, nameType=region_type, ParentRegion_obj=parent_region)
                    region.save()
                if not region.Validator_obj or not region.Validator_obj.is_valid:
                    log.updateShare(region)

            parent_region = region
        return log
            
    base = 'https://members-api.parliament.uk/api'
    members_api = base + f'/Members/Search?IsCurrentMember=True&House={chamber_num}'

    persons, parties = person_fetcher(members_api, 0, 0, {}, {})

    # for party in parties:
        
    #     if not parties.get(person['latestParty'], None):
    #         party = {}
    #         party['id'] = v['latestParty']['id']
    #         party['name'] = v['latestParty']['name']
    #         party['abbreviation'] = v['latestParty']['abbreviation']
    #         party['backgroundColour'] = v['latestParty']['backgroundColour']
    #         party['foregroundColour'] = v['latestParty']['foregroundColour']
    #         party['governmentType'] = v['latestParty']['governmentType']
    #         party['isIndependentParty'] = v['latestParty']['isIndependentParty']
    #         parties[party['id']] = party


    for person in persons:
        prnt('person',person)
        # {'id': 5140, 'nameListAs': 'Young, Claire', 'nameDisplayAs': 'Claire Young', 
        # 'nameFullTitle': 'Claire Young MP', 'thumbnailUrl': 'https://members-api.parliament.uk/api/Members/5140/Thumbnail', 
        # 'membershipFrom': 'Thornbury and Yate', 'membershipFromId': 4360, 'house': 1, 
        # 'membershipStartDate': '2024-07-04T00:00:00', 'membershipEndDate': None, 
        # 'membershipEndReason': None, 'membershipEndReasonId': None, 
        # 'membershipStatus': {'statusIsActive': True, 'statusDescription': 'Current Member', 'statusId': 0, 'status': 0, 'statusStartDate': '2024-07-04T00:00:00'}, 
        # 'latestParty': 17}
        
        district = District.objects.filter(AltName=person['membershipFromId']).filter(Country_obj=log.Region_obj, Region_obj=log.Region_obj, gov_level='Federal', nameType='Federal District', Validator_obj__is_valid=True).values('id').first()
        if not district:
            local_synop_api = base + f"/Location/Constituency/{person['membershipFromId']}/Synopsis"
            print('url',local_synop_api)
            try:
                r = requests.get(local_synop_api)
                data = json.loads(r.content)
                print('data:',data)
                for key, val in data.items():
                    if key == 'value':
                        log = parse_regions(val, country, person['membershipFromId'], log)
            except Exception as e:
                print('district err',str(e))

        
        party, partyU, party_is_new = get_model_and_update('Party', AltName=person['latestParty'], Country_obj=log.Region_obj, Region_obj=log.Region_obj, gov_level='Federal')
        if party_is_new:
            party_dict = parties[person['latestParty']]
            party.Name = party_dict['name'],
            party.ShortName = party_dict['abbreviation'],
            party.Chamber = 'House',
            party.Color = party_dict['foregroundColour'],
            party.Color2 = party_dict['backgroundColour'],
            partyU.data['isIndependentParty'] = party_dict['isIndependentParty'],
            party, partyU, party_is_new, log = save_and_return(party, partyU, log)
        
        GovProfilePage = f"https://members.parliament.uk/Members/{person['id']}",
        person, personU, person_is_new = get_model_and_update('Person', GovProfilePage=GovProfilePage, Country_obj=log.Region_obj, Region_obj=log.Region_obj)
        save_person = False
        if person_is_new:
            person.GovIden = person['id']
            personU.data['Position'] = office
            personU.data['Chamber'] = chamber
            split_name = person['nameListAs'].split(', ')
            personU.data['FirstName'] = split_name[-1]
            personU.data['LastName'] = split_name[0]
            personU.data['FullName'] = person['nameDisplayAs']
            personU.data['PhotoLink'] = person['thumbnailUrl']
            personU.data['membershipFrom'] = person['membershipFrom']
            personU.data['membershipFromId'] = person['membershipFromId']
            personU.data['membershipStartDate'] = person['membershipStartDate']
            personU.data['gov_level'] = 'Federal'
            person.update_role(personU, data={'role':office,'gov_level':'Federal','current':True})
            save_person = True

        if district and district['id'] != personU.data.get('District_id', None):
            personU.data['District_id'] = district['id']
            save_person = True
        if party and party.id != personU.data.get('Party_id', None):
            personU.data['Party_id'] = party.id
            save_person = True
        if save_person:
            person, personU, person_is_new, log = save_and_return(person, personU, log)

        if personU.data['PhotoLink'] and not ImageFile.objects.filter(pointerId=person.id, Validator_obj__is_valid=True).exists():
            img_url = personU.data['PhotoLink']
            try:
                time.sleep(1)
                img_obj = save_image(img_url, f'legis/canada/', pointerId=person.id, region=country)
                log.updateShare(img_obj)
            except Exception as e:
                prnt('img err121',str(e))
        

        current_mps.append(person.id)

    prntDebug('len:', len(current_mps))
    if len(current_mps) > 600:
        repUpdates = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Person()), Region_obj=country, extra__roles__contains=[{'role':office,'current':True, 'gov_level':'Federal'}]).exclude(pointerId__in=current_mps)
        prntDebug('repUpdates',repUpdates)
        for u in repUpdates:
            prntDebug('removing:::',u.pointerId)
            update = u.create_next_version()
            if 'Position' in update.data and update.data['Position'] == office:
                del update.data['Position']
            
            data = {'role':office,'current':True,'gov_level':'Federal'}
            # if start_date:
            #     data['StartDate'] = dt_to_string(start_date)
            update.Pointer_obj.update_role(update, data=data)
            update, u_is_new = update.save_if_new(func=func)
            if u_is_new:
                log.updateShare(update)
        prnt('done')


    prntDebug('done gather mps')
    # send_for_validation(log, gov, func)
    return finishScript(log, gov, special)


def get_bills_uk(special=None, value='current', dt=None, iden=None, func='get_bills_uk'):
    prnt(f'--{func} UK', now_utc())
    dt = declare_var(dt, now_utc())
    gov = None
    country = get_region('United Kingdom')
    log = create_share_object(func, country, special=special, dt=dt, iden=iden)
    gov = get_gov(country)
    log.updateShare(gov)


    gov = modify_gov(gov, [{'menuItem_array':['Bills','Debates','Motions','Officials']}])
    log = add_gov_menu_item(gov, 'Bills', log)
    log.updateShare(gov)

    import requests
    import xml.etree.ElementTree as ET

    def fetch_rss(url):
        root = ET.fromstring(requests.get(url).content)
        items = []
        for item in root.findall(".//item"):
            d = {}
            for child in item:
                tag = child.tag.split("}")[-1]  # Remove namespace if present
                d[tag] = child.text

            # Include attributes (e.g. p4:stage="stage 2")
            for key, value in item.attrib.items():
                d[key.split("}")[-1]] = value
            items.append(d)

        return items

    base = 'https://bills-api.parliament.uk/api'
    bills_rss = base + "/v1/Rss/allbills.rss'"
    bills_data = fetch_rss(bills_rss)

    # for item in items[:3]:
    #     print(item)
    #     print("-" * 80)
        # <item
        # p4:stage="Committee stage">
        #     <guid
        #     isPermaLink="true">https://bills.parliament.uk/bills/4128</guid>
        #     <link>https://bills.parliament.uk/bills/4128</link>
        #     <category>Government Bill</category>
        #     <category>Lords</category>
        #     <title>Commercial Payments Bill [HL]</title>
        #     <description>A bill to make provision about payment terms in commercial contracts; to make provision about interest on late payment of commercial debts; to ban retention clauses in the construction sector; to expand the powers of the Small Business Commissioner in relation to payment disputes and poor payment practices; to amend the Enterprise Act 2016 in connection with other functions of the Small Business Commissioner; and for connected purposes.</description>
        #     <a10:updated>2026-07-17T18:05:12+01:00</a10:updated>
        # </item>
        # {'guid': 'https://bills.parliament.uk/bills/4065', 
        # 'link': 'https://bills.parliament.uk/bills/4065', 
        # 'category': 'Commons', 'title': 'Armed Forces Bill', 
        # 'description': 'A Bill to continue the Armed Forces Act 2006; to amend that Act and other enactments relating to the armed forces; to make provision about the reserve forces; to make provision about visiting forces; to make provision about the Ministry of Defence Police; to make provision about the defence functions of the Oil and Pipelines Agency; to make provision about the protection of military remains; and for connected purposes.', 
        # 'updated': '2026-07-17T18:03:14+01:00', 'stage': 'Committee stage'}

    pub_dt = None
    latest_update = Update.valid_objects.filter(pointerKey=ContentType.objects.get_for_model(Bill), Region_obj=country).order_by('-DateTime').values('id','DateTime').first()
    if latest_update:
        pub_dt = string_to_dt(latest_update['DateTime'])
        prnt('latest_update',latest_update['id'])

    for bill_dict in bills_data:
        updated_dt = parser.parse(bill_dict['updated'])
        if not pub_dt or updated_dt > updated_dt:
            ...


    prntDebug('done gather bills')
    # send_for_validation(log, gov, func)
    return finishScript(log, gov, special)
