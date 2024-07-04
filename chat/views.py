from django.shortcuts import render
from django.http import HttpResponse
from django.template import loader
from django.utils.translation import activate, get_language
import requests
import json
import os
from openai import OpenAI
import itertools
import redis
import urllib.parse
import datetime

TWFY_API_KEY = os.environ.get("THEY_WORK_FOR_YOU_API_KEY")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

profile = {}

redis_cli = redis.Redis(host=os.environ.get("REDIS_HOST"),
            username="default",
            ssl=False if os.environ.get("REDIS_NO_SSL") else True,
            password=os.environ.get("REDIS_PASSWORD"))

def system_prompt(name, speech, jurisdiction):
    template = os.environ.get("PROMPT_GB" if jurisdiction == "GB" else "PROMPT_JP")
    return template.replace("{speech}", "\n".join(speech)).replace("{name}", name)

def get_profile(mp_name, jurisdiction):
    quoted_mp_name = urllib.parse.quote(mp_name)
    redis_key = f"{jurisdiction}:{mp_name}".encode('utf-8')
    speech = redis_cli.get(redis_key)
    if speech:
        speech = json.loads(speech)

    if not speech:
        if jurisdiction == 'JP':
            url = f"https://kokkai.ndl.go.jp/api/speech?speaker={quoted_mp_name}&recordPacking=json"
            print(url)
            response = requests.get(url)
            data = response.json()
            speech = list(map(lambda rec: rec["speech"], data["speechRecord"]))
            redis_cli.set(redis_key, json.dumps(speech))
        if jurisdiction == 'GB':
            url = f"https://members-api.parliament.uk/api/Members/Search?Name={quoted_mp_name}&skip=0&take=20"
            print(url)
            response = requests.get(url)
            data = response.json()
            start_date = data["items"][0]["value"]["latestHouseMembership"]["membershipStartDate"][0:10]
            date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            safe_date = (date + datetime.timedelta(days = 5)).date().isoformat()

            url = f"https://www.theyworkforyou.com/api/getMPs?date={safe_date}&search={quoted_mp_name}&output=json&key={TWFY_API_KEY}"
            print(url)
            response = requests.get(url)
            data = response.json()
            mp = list(filter(lambda d: mp_name in d["name"], data))[0]
            person_id = mp["person_id"]

            url = f"https://www.theyworkforyou.com/api/getDebates?person={person_id}&type=commons&output=json&key={TWFY_API_KEY}"
            print(url)
            response = requests.get(url)
            data = response.json()
            commons = map(lambda row: row["extract"], data["rows"])

            url = f"https://www.theyworkforyou.com/api/getDebates?person={person_id}&type=lords&output=json&key={TWFY_API_KEY}"
            print(url)
            response = requests.get(url)
            data = response.json()
            lords = map(lambda row: row["extract"], data["rows"])

            url = f"https://www.theyworkforyou.com/api/getDebates?person={person_id}&type=westminsterhall&output=json&key={TWFY_API_KEY}"
            print(url)
            response = requests.get(url)
            data = response.json()
            westminsterhall = map(lambda row: row["extract"], data["rows"])

            speech = list(itertools.chain(commons, lords, westminsterhall))
            redis_cli.set(redis_key, json.dumps(speech))
    else:
        print("catch hit")
        pass
    return speech

def search_mp_jp(name):
    with open("./chat/jp_mp_hoc.json") as f:
        jp_mp_hoc = json.load(f)
    with open("./chat/jp_mp_hor.json") as f:
        jp_mp_hor = json.load(f)
    all_mp = jp_mp_hoc + jp_mp_hor
    return list(filter(lambda s: name in s, all_mp))

def search_mp_gb(name):
    url = f"https://members-api.parliament.uk/api/Members/Search?Name={name}&skip=0&take=20"
    response = requests.get(url)
    data = response.json()
    return list(map(lambda item: item["value"]["nameDisplayAs"], data["items"]))

# Helpers above

def index(request):
    prefered_jurisdiction = request.GET.get('cc')

    if prefered_jurisdiction:
        jurisdiction = prefered_jurisdiction
    elif request.COOKIES.get('jurisdiction'):
        jurisdiction = request.COOKIES.get('jurisdiction')
    else:
        jurisdiction = "JP"

    cached_keys = redis_cli.keys(f"{jurisdiction}:*")
    recent_mps = list(map(lambda b: b.decode('utf-8')[3:], cached_keys))

    context = { 'jurisdiction': jurisdiction, 'recent': recent_mps }

    template = loader.get_template("chat/index.html")
    jurisdiction_locale_map = { 'JP': 'ja', 'GB': 'en' }
    if prefered_jurisdiction:
      prefered_locale = jurisdiction_locale_map.get(prefered_jurisdiction)
      if prefered_locale:
        activate(prefered_locale)

    resp = HttpResponse(template.render(context, request))

    if prefered_jurisdiction:
      resp.set_cookie('jurisdiction', prefered_jurisdiction)
      if prefered_locale:
        resp.set_cookie('django_language', prefered_locale)
    return resp


def search_mp(request):
    jurisdiction = request.COOKIES.get('jurisdiction')

    template = loader.get_template("chat/search_mp.html")

    name = request.GET.get("mp_name")

    if name == None or name == "":
        return HttpResponse("")

    search = search_mp_gb if jurisdiction == "GB" else search_mp_jp
    resulting_mps = search(name)

    return HttpResponse(template.render({"mps": resulting_mps}, request))


def chat_with(request, mp_name):
    template = loader.get_template("chat/chat_with.html")
    context = {"mp_name": urllib.parse.unquote(mp_name)}
    return HttpResponse(template.render(context, request))


def message(request, mp_name):
    template = loader.get_template("chat/message.html")
    jurisdiction = request.COOKIES.get('jurisdiction')

    if request.POST.get("history_json"):
        recovered_history = json.loads(request.POST.get("history_json"))
    else:
        recovered_history = []
    new_message = request.POST.get("new_message")
    unquoted_mp_name = urllib.parse.unquote(mp_name)
    speech = get_profile(unquoted_mp_name, jurisdiction)

    history = recovered_history + [
        {
            "role": "user",
            "content": new_message,
        },
    ]
    messages = [
        {
            "role": "system",
            "content": system_prompt(unquoted_mp_name, speech, jurisdiction),
        },
    ] + history
    stream = client.chat.completions.create(
        messages=messages,
        model="gpt-4-turbo",
        stream=True,
    )

    buf = ""
    for chunk in stream:
        s = chunk.choices[0].delta.content or ""
        print(".", end="")
        buf += s

    history += [
        {
            "role": "assistant",
            "content": buf,
        },
    ]
    context = {
        "mp_name": unquoted_mp_name,
        "response": buf,
        "new_message": new_message,
        "history": history,
        "history_json": json.dumps(history),
    }
    return HttpResponse(template.render(context, request))

def about(request):
    template = loader.get_template("chat/about.html")
    context = {}
    return HttpResponse(template.render(context, request))
