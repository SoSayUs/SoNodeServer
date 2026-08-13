

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
    'get_house_motions' : ['Government', 'Motion', 'RepVote', 'Interaction', 'Person'],
    'get_senate_motions' : ['Government', 'Motion', 'RepVote', 'Interaction'],
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

    gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Parliament', GovernmentNumber=int(parl), SessionNumber=int(sess), Region_obj=country)
    prnt('gov',gov)


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
    # gov = get_gov(country)
    # log.updateShare(gov)
    # gov = modify_gov(gov, [{'menuItem_array':['Bills','Debates','Motions','Officials']}])
    # log = add_gov_menu_item(gov, 'Bills', log)
    # log.updateShare(gov)


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
    # bills_data = fetch_rss(bills_rss)
    
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
    bills_url = base + '/v1/Bills'

    r = requests.get(bills_url)
    bills_data = json.loads(r.content)
    for bill_data in bills_data['items']:
        billId = bill_data['billId']
        shortTitle = bill_data['shortTitle']
        currentHouse = bill_data['currentHouse']
        originChamber = bill_data['originatingHouse']
        lastUpdate = bill_data['lastUpdate']
        billWithdrawn = bill_data['billWithdrawn']
        isDefeated = bill_data['isDefeated']

        currentStage = bill_data['currentStage']
        stage = currentStage['description']
        abbreviation = currentStage['abbreviation']
        house = currentStage['house']




        # "items": [
        # {
        #   "billId": 3973,
        #   "shortTitle": "A34 Slip Road Safety (East Ilsley and Beedon) Bill",
        #   "formerShortTitle": null,
        #   "currentHouse": "Commons",
        #   "originatingHouse": "Commons",
        #   "lastUpdate": "2025-09-16T17:08:18.2184786",
        #   "billWithdrawn": "2025-09-15T00:00:00",
        #   "isDefeated": false,
        #   "billTypeId": 5,
        #   "introducedSessionId": 39,
        #   "includedSessionIds": [
        #     39
        #   ],
        #   "isAct": false,
        #   "currentStage": {
        #     "id": 19929,
        #     "stageId": 7,
        #     "sessionId": 39,
        #     "description": "2nd reading",
        #     "abbreviation": "2R",
        #     "house": "Commons",
        #     "stageSittings": [
        #       {
        #         "id": 17032,
        #         "stageId": 7,
        #         "billStageId": 19929,
        #         "billId": 3973,
        #         "date": "2025-07-11T00:00:00"
        #       }
        #     ],
        #     "sortOrder": 2
        #   }
        # },
        # {
        #   "billId": 2818,


    # for bill_dict in bills_data:
        updated_dt = parser.parse(lastUpdate)

        if not pub_dt or updated_dt > pub_dt:
            log = add_bill_uk(billId, log, func, special=special, country=country)

    prntDebug('done gather bills')
    # send_for_validation(log, gov, func)
    return finishScript(log, gov, special)

def add_bill_uk(billId, log, func, special=None, country=None):
    prnt(f'--add_bill_uk', func, now_utc())
    if not country:
        country = get_region('United Kingdom')

    lords_list = {'Lords 1/3':{'desc':'1st reading'},'Lords 2/3':{'desc':'2nd reading'},'Lords 3/3':{'desc':'3rd reading'}}
    commons_list = {'Commons 1/3':{'desc':'1st reading'},'Commons 2/3':{'desc':'2nd reading'},'Commons 3/3':{'desc':'3rd reading'}}
    royal_list = {'Royal Assent':{'desc':'Royal Assent'}}

    def get_text(bill, billU):
        pubs_api = f'https://bills-api.parliament.uk/api/v1/Bills/{bill.GovIden}/Publications'

        r = requests.get(pubs_api)
        pub_data = json.loads(r.content)
        for data in pub_data['publications']:
            if data['publicationType']['name'] == 'Bill':
                for file in pub_data['files']:
                    if file['contentType'] == 'text/html':
                        dl_url = f'https://bills-api.parliament.uk/api/v1/Publications/{data["id"]}/Documents/{file["id"]}/Download'
                        # r = requests.get(dl_url)
                        # billtext = BillText.objects.filter()
            #         },
            # {
            #   "house": "Lords",
            #   "id": 66884,
            #   "title": "HL Bill 36 (as brought from the Commons)",
            #   "publicationType": {
            #     "id": 5,
            #     "name": "Bill",
            #     "description": "Full text of the Bill as introduced and further versions of the Bill as it is reprinted to incorporate amendments (proposals for change) made during its passage through Parliament."
            #   },
            #   "displayDate": "2026-06-23T00:00:00",
            #   "links": [],
            #   "files": [
            #     {
            #       "id": 8482,
            #       "filename": "5902036.pdf",
            #       "contentType": "application/pdf",
            #       "contentLength": 7980079
            #     },
            #     {
            #       "id": 8483,
            #       "filename": "5902036.html",
            #       "contentType": "text/html",
            #       "contentLength": 3298405
            #     },
            #     {
            #       "id": 8484,
            #       "filename": "5902036.xml",
            #       "contentType": "text/xml",
            #       "contentLength": 1398453
            #     }
            #   ]
            # },
            # {

        
        return bill, billU

    def get_stages(bill, billU):
        stages_api = f'https://bills-api.parliament.uk/api/v1/Bills/{billId}/Stages'

        stages = lords_list | commons_list | royal_list
        versions = []

        r = requests.get(stages_api)
        stages_data = json.loads(r.content)
        for stage_data in stages_data['items']:
            stage_desc = stage_data['description']
            stage_house = stage_data['house']
            stage_abbr = stage_data['abbreviation']
            stageSittings = stage_data['stageSittings']
            stage_dt = None
            current_stage = None
            for sitting in stageSittings:
                if sitting.get("date",None):
                    dt = parser.parse(sitting['date'])
                    if not stage_dt or dt < stage_dt:
                        stage_dt = dt
                    if not bill.DateTime or dt > bill.DateTime:
                        bill.DateTime = dt
                        billU.data['LatestBillEventDateTime'] = dt_to_string(dt)
            if not bill.Started:
                bill.Started = stage_dt
            for stage in stages:
                if stage_house in stage and stage_desc == stage['desc']:
                    if not any([v for v in versions if v['version'] == stage]):
                        current_stage = stage
                        current_stage_dt = stage_dt
                        versions.append({'version':stage, 'current':False, 'status':None, 'started_dt':dt_to_string(stage_dt), 'completed_dt':None})
                        break
        found_current = False
        for v in versions:
            if v['version'] == current_stage:
                v['current'] = True
                v['status'] = 'current'
                found_current = True
            if not found_current and v['started_dt']:
                v['status'] = 'passed'
        if not found_current:
            latest = None
            for v in reversed(versions):
                if v['started_dt']:
                    latest = v['version']
            if latest:
                new_versions = []
                for v in versions:
                    new_versions.append(v)
                    if v['version'] == latest:
                        c = {'version':current_stage, 'current':True, 'status':'current', 'started_dt':dt_to_string(current_stage_dt), 'completed_dt':None}
                        new_versions.append(c)
                versions = new_versions

        if versions:
            billU.data['billVersions'] = versions
            

        return bill, billU
            


    # gov = get_gov(country, Country_obj=country, gov_level='Federal', gov_type='Parliament', GovernmentNumber=int(ParliamentNumber), SessionNumber=int(SessionNumber), Region_obj=country)
    prnt('gov',gov)
    if not gov.StartDate:
        from utils.models import round_time
        gov.StartDate = timezonify('est', round_time(dt=now_utc(), dir='down', amount='day'))
        gov.migrate_data()
        gov.LogoLinks = gov_logo_links

    gov = get_gov(country)
    log.updateShare(gov)
    gov = modify_gov(gov, [{'menuItem_array':['Bills','Debates','Motions','Officials']}])
    log = add_gov_menu_item(gov, 'Bills', log)
    log.updateShare(gov)

    bill, billU, bill_is_new = get_model_and_update('Bill', Government_obj=gov, Country_obj=country, Region_obj=country, NumberCode=billId, GovIden=billId)
    bill_url = f'https://bills.parliament.uk/bills/{billId}'

    prntDebug('got bill, bill_is_new:', bill_is_new)
    if bill_is_new:
        bill_api = f'https://bills-api.parliament.uk/api/v1/Bills/{billId}'

        # data {'longTitle': 'A Bill to continue the Armed Forces Act 2006; to amend that Act and other enactments relating to the armed forces; to make provision about the reserve forces; to make provision about visiting forces; to make provision about the Ministry of Defence Police; to make provision about the defence functions of the Oil and Pipelines Agency; to make provision about the protection of military remains; and for connected purposes.', 
        # 'summary': None, 
        # 'sponsors': [{'member': {'memberId': 400, 'name': 'John Healey', 'party': 'Labour', 'partyColour': 'd50000', 'house': 'Commons', 'memberPhoto': 'https://members-api.parliament.uk/api/Members/400/Thumbnail', 'memberPage': 'https://members.parliament.uk/member/400/contact', 'memberFrom': 'Rawmarsh and Conisbrough'}, 'organisation': {'name': 'Ministry of Defence', 'url': 'https://www.gov.uk/government/organisations/ministry-of-defence'}, 'sortOrder': 1}, {'member': {'memberId': 360, 'name': 'Lord Coaker', 'party': 'Labour', 'partyColour': 'd50000', 'house': 'Lords', 'memberPhoto': 'https://members-api.parliament.uk/api/Members/360/Thumbnail', 'memberPage': 'https://members.parliament.uk/member/360/contact', 'memberFrom': 'Life peer'}, 'organisation': {'name': 'Ministry of Defence', 'url': 'https://www.gov.uk/government/organisations/ministry-of-defence'}, 'sortOrder': 2}], 
        # 'promoters': [], 'petitioningPeriod': None, 'petitionInformation': None, 'agent': None, 
        # 'billId': 4065, 
        # 'shortTitle': 'Armed Forces Bill', 'formerShortTitle': None, 
        # 'currentHouse': 'Lords', 'originatingHouse': 'Commons', 
        # 'lastUpdate': '2026-07-17T18:03:14.5516835', 
        # 'billWithdrawn': None, 'isDefeated': False, 
        # 'billTypeId': 1, 'introducedSessionId': 39, 'includedSessionIds': [39, 40], 
        # 'isAct': False, 
        # 'currentStage': {'id': 21073, 'stageId': 3, 'sessionId': 40, 'description': 'Committee stage', 'abbreviation': 'CS', 'house': 'Lords', 'stageSittings': [{'id': 18474, 'stageId': 3, 'billStageId': 21073, 'billId': 4065, 'date': '2026-09-02T00:00:00'}, {'id': 18475, 'stageId': 3, 'billStageId': 21073, 'billId': 4065, 'date': '2026-09-08T00:00:00'}], 'sortOrder': 15}}

        r = requests.get(bill_api)
        new_bill_data = json.loads(r.content)
        longTitle = new_bill_data['longTitle']
        summary = new_bill_data['summary']
        originChamber = new_bill_data['originChamber']
        shortTitle = new_bill_data['shortTitle']
        sponsors = new_bill_data['sponsors']
        for sponsor in sponsors:
            member = sponsor['member']
            memberId = member['memberId']
            name = member['name']
            party = member['party']
            partyColour = member['partyColour']
            house = member['house']
            if not bill.Person_obj:
                bill.SponsorPersonName = name
                bill.SponsorCode = memberId
                person = Person.objects.filter(Region_obj=country, GovIden=memberId, Validator_obj__is_valid=True).first()
                bill.Person_obj = person

                try:
                    bill.Party_obj = Party.objects.filter(id=person.get_field('Party_id'), gov_level='Federal', Region_obj=country, Validator_obj__is_valid=True).first()
                except:
                    pass
                try:
                    bill.District_obj = District.objects.filter(id=person.get_field('District_id'), gov_level='Federal', Region_obj=country, Validator_obj__is_valid=True).first()
                except:
                    pass


        # {
        # "longTitle": "A Bill to continue the Armed Forces Act 2006; to amend that Act and other enactments relating to the armed forces; to make provision about the reserve forces; to make provision about visiting forces; to make provision about the Ministry of Defence Police; to make provision about the defence functions of the Oil and Pipelines Agency; to make provision about the protection of military remains; and for connected purposes.",
        # "summary": null,
        # "sponsors": [
        #     {
        #     "member": {
        #         "memberId": 400,
        #         "name": "John Healey",
        #         "party": "Labour",
        #         "partyColour": "d50000",
        #         "house": "Commons",
        #         "memberPhoto": "https://members-api.parliament.uk/api/Members/400/Thumbnail",
        #         "memberPage": "https://members.parliament.uk/member/400/contact",
        #         "memberFrom": "Rawmarsh and Conisbrough"
        #     },
        #     "organisation": {
        #         "name": "Ministry of Defence",
        #         "url": "https://www.gov.uk/government/organisations/ministry-of-defence"
        #     },
        #     "sortOrder": 1
        #     },
        #     {
        #     "member": {
        #         "memberId": 360,
        #         "name": "Lord Coaker",
        #         "party": "Labour",
        #         "partyColour": "d50000",
        #         "house": "Lords",
        #         "memberPhoto": "https://members-api.parliament.uk/api/Members/360/Thumbnail",
        #         "memberPage": "https://members.parliament.uk/member/360/contact",
        #         "memberFrom": "Life peer"
        #     },
        #     "organisation": {
        #         "name": "Ministry of Defence",
        #         "url": "https://www.gov.uk/government/organisations/ministry-of-defence"
        #     },
        #     "sortOrder": 2
        #     }
        # ],
        # "promoters": [],
        # "petitioningPeriod": null,
        # "petitionInformation": null,
        # "agent": null,
        # "billId": 4065,
        # "shortTitle": "Armed Forces Bill",
        # "formerShortTitle": null,
        # "currentHouse": "Lords",
        # "originatingHouse": "Commons",
        # "lastUpdate": "2026-07-23T17:44:57.2584365",
        # "billWithdrawn": null,
        # "isDefeated": false,
        # "billTypeId": 1,
        # "introducedSessionId": 39,
        # "includedSessionIds": [
        #     39,
        #     40
        # ],
        # "isAct": false,
        # "currentStage": {
        #     "id": 21073,
        #     "stageId": 3,
        #     "sessionId": 40,
        #     "description": "Committee stage",
        #     "abbreviation": "CS",
        #     "house": "Lords",
        #     "stageSittings": [
        #     {
        #         "id": 18474,
        #         "stageId": 3,
        #         "billStageId": 21073,
        #         "billId": 4065,
        #         "date": "2026-09-02T00:00:00"
        #     },
        #     {
        #         "id": 18475,
        #         "stageId": 3,
        #         "billStageId": 21073,
        #         "billId": 4065,
        #         "date": "2026-09-08T00:00:00"
        #     }
        #     ],
        #     "sortOrder": 15
        # }
        # }
        # Person_obj = models.ForeignKey('legis.Person', blank=True, null=True, on_delete=models.PROTECT) #sponsor
        # GovIden = models.IntegerField(default=0, blank=True, null=True)
        # LegisLink = models.URLField(null=True, blank=True) #official link to text of bill
        # Started = models.DateTimeField(auto_now=False, auto_now_add=False, blank=True, null=True)
        # Party_obj = models.ForeignKey('legis.Party', blank=True, null=True, on_delete=models.PROTECT)
        # District_obj = models.ForeignKey('legis.District', related_name='%(class)s_district_obj', blank=True, null=True, on_delete=models.PROTECT)
        # BillText_obj = models.ForeignKey('legis.BillText', related_name='%(class)s_billtext_obj', blank=True, null=True, on_delete=models.SET_NULL)
        # NumberCode = models.CharField(max_length=20, default="", blank=True, null=True)
        # amendedNumberCode = models.CharField(max_length=20, default="", blank=True, null=True) #removes dash for search
        # NumberPrefix = models.CharField(max_length=20, default="", blank=True, null=True)
        # Number = models.IntegerField(blank=True, null=True)
        # Subjects = models.CharField(max_length=1000, default="", blank=True, null=True)
        # # Title = models.CharField(max_length=1000, default="", blank=True, null=True)
        # # ShortTitle = models.CharField(max_length=1000, default="", blank=True, null=True)
        # BillDocumentTypeName = models.CharField(max_length=56, default="", blank=True, null=True) # bill / resolution / ...
        # IsGovernmentBill = models.CharField(max_length=10, default="", blank=True, null=True)
        # # SponsorPersonName = models.CharField(max_length=100, default="", blank=True, null=True)
        # # SponsorCode = models.CharField(max_length=100, default="", blank=True, null=True)

        bill.LegisLink = bill_url

        bill.ShortTitle = shortTitle
        bill.Title = longTitle
        bill.Chamber = originChamber

        
        bill.save()


    if 'billVersions' not in billU.data or not billU.data['billVersions']:
        versions = []

        if originChamber == 'Lords':
            for i in lords_list:
                versions.append({'version':i, 'current':None, 'status':None, 'started_dt':None, 'completed_dt':None})
            for i in commons_list:
                versions.append({'version':i, 'current':None, 'status':None, 'started_dt':None, 'completed_dt':None})
            for i in royal_list:
                versions.append({'version':i, 'current':None, 'status':None, 'started_dt':None, 'completed_dt':None})
            billU.data['Status'] = 'Lords 1/3'
            for v in versions:
                if v['version'] == 'Lords 1/3':
                    v['current'] = True
                    v['status'] = 'current'

        elif originChamber == 'Commons':
            for i in commons_list:
                versions.append({'version':i, 'current':None, 'status':None, 'started_dt':None, 'completed_dt':None})
            for i in lords_list:
                versions.append({'version':i, 'current':None, 'status':None, 'started_dt':None, 'completed_dt':None})
            for i in royal_list:
                versions.append({'version':i, 'current':None, 'status':None, 'started_dt':None, 'completed_dt':None})
            billU.data['Status'] = 'Commons 1/3'
            for v in versions:
                if v['version'] == 'Commons 1/3':
                    v['current'] = True
                    v['status'] = 'current'

        billU.data['billVersions'] = versions
        

    bill, billU = get_stages(bill, billU)
    bill, billU = get_text(bill, billU) # needs work here
    bill, billU, bill_is_new, log = save_and_return(bill, billU, log)
    return log