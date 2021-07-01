#
# wts2.py
#
# Implements two bits of functionality for Jira:
# 1. creates project subdirectories
# 2. renumbers per-PI priorities in the top 10 list.
#
# Expects CGI form data to contain:
#    "cmd"      Either "renumber" or "new"
#    "key"      If cmd == "new", key is the issue key.
#
# Examples:
#    cmd=renumber
#    cmd=new&key=WTS2-10
#
import os
import sys
import math
import cgi
import json
import subprocess
import requests
from requests.auth import HTTPBasicAuth

WTS_DIR = os.environ["WTS_DIR"]
WTS_URL = os.environ["WTS_BASE_URL"] + "/wts2_projects/"
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_USER = os.environ["JIRA_USER"]
JIRA_TOKEN = os.environ["JIRA_TOKEN"]

#
AUTH = HTTPBasicAuth(JIRA_USER, JIRA_TOKEN)
HEADERS = { "Accept": "application/json" }
WTS2_NAME = "Work+Tracking+System+2"
# The following values come from our WTS2 Jira project. Must be kept in sync.
# ID of the top 10 queue. 
TOP10_ID=os.environ["TOP10_ID"]
# ID of the PI custom fields
PI_FIELD = os.environ["PI_FIELD"]
# ID of the PI priority field (called "sort order")
PI_PRI_FIELD = os.environ["PI_PRI_FIELD"]
###


JIRA_REST_URL = JIRA_BASE_URL + '/rest/api/latest'
JIRA_ISSUE_URL= JIRA_REST_URL + '/issue/%s?fields=key'

############################################################################
# Make directory
############################################################################

def isValidIssueId (issueId) :
    url = JIRA_ISSUE_URL % issueId
    args = [ 
      'curl',
      '-u',
      '%s:%s' % (JIRA_USER,JIRA_TOKEN),
      url 
      ]   
    result = subprocess.run(args,capture_output=True)
    obj = json.loads(result.stdout.decode())
    return obj.get("key", None) == issueId
#
def getMidLevelDir (key) :
    keyNum = int(key.split('-')[1])
    return str(100*math.floor(keyNum / 100))
#
def makeDirectory (key) :
        try:
            if not isValidIssueId (key) :
                return { "status" : "error", "message" : "Invalid key: " + key }
            mld = getMidLevelDir(key)
            newdir = os.path.join(WTS_DIR, mld, key)
            url = WTS_URL + mld + "/" + key
            if not os.path.isdir(newdir) :
                os.makedirs(newdir)
                return { "status" : "success", "url" : url, "message" : "Directory created." }
            else:
                return { "status" : "success", "url" : url, "message" : "Directory exists." }
        except Exception as e:
            return { "status" : "error", "message" : "Invalid key: " + str(e) }
#
def makeProjectDirectory (form) :
    if not "key" in form:
        response = { "status" : "error", "message" : "No key." }
    else:
        key = form["key"].value
        response = makeDirectory(key)
    #
    print("Content-type: application/json")
    print()
    print(json.dumps(response))

############################################################################
# Renumber
############################################################################

# Returns the JQL specification of the Top-10 given queue id
def getJQL (qid) :
    url = '%s/rest/servicedeskapi/servicedesk/WTS2/queue/%s' % (JIRA_BASE_URL, qid)
    response = requests.request(
        "GET",
        url,
        headers=HEADERS,
        auth=AUTH
        )
    jobj = json.loads(response.text)
    jql = jobj["jql"]
    return jql

# Returns the current top-10 list. For each issue, just return the issue key, the PI, and the sort order.
# Jira only returns a max of 100 at a time, so have to code for multiple requests.
# (We'll set the max to 50 to force an iteration so we know it works.)
def getTopTenList () :
    startAt = 0
    maxResults = 50
    top10 = []
    while True:
        # Request the next batch
        jql = getJQL(TOP10_ID)
        fields = '%s,%s' % (PI_FIELD, PI_PRI_FIELD)
        url = JIRA_REST_URL + \
            ('/search?jql=%s&fields=%s&startAt=%d&maxResults=%d' % (jql, fields, startAt, maxResults))
        response = requests.request(
           "GET",
           url,
           headers=HEADERS,
           auth=AUTH
        )
        # Parse the json and iterate over the issues
        jobj = json.loads(response.text)
        for i in jobj['issues']:
            key = i['key']
            pi = i['fields'][PI_FIELD]
            if pi:
                sortOrder = i['fields'][PI_PRI_FIELD]
                piName = pi['value']
                rec = {
                    'key' : key,
                    'pi' : piName,
                    'priority': sortOrder
                }
                if sortOrder != None:
                    top10.append(rec)
        # end for
        startAt += maxResults
        if startAt >= jobj['total']:
            break

    #end while True
    return top10

# Sets the sort order field of the given issue to the given value
def setSortOrder (key, pi, newpri, oldpri):
    if newpri == oldpri:
        print("Unchanged:", key, pi, newpri)
        return
    url = JIRA_REST_URL + '/issue/' + key
    args = {
      "fields": {
        PI_PRI_FIELD: newpri
      }
    }
    response = requests.put(
        url,
        data=json.dumps(args),
        headers = {'Content-Type':'application/json; charset=utf8'},
        auth=AUTH
    )
    if response.status_code == 204:
        print("Set:", key, pi, newpri)
    else:
        print("Error:", response.status_code, response.text, response.reason)

# Renumbers the items (for each PI) in the top-10 in sequential order
def renumber (top10, piFilter) :
    top10.sort(key = lambda i: (i['pi'], i['priority']))
    newpri = 1
    lastPi = None
    for issue in top10:
       key = issue['key']
       pi = issue['pi']
       oldpri = issue['priority']
       if pi != lastPi:
           newpri = 1
       else:
           newpri += 1
       lastPi = pi
       if not piFilter or piFilter in pi.lower().split():
           setSortOrder(key, pi, newpri, oldpri)

# 
def renumberTop10 () :
    print("Content-type: text/html")
    print()
    print('<html><body><pre>')
    pi = None
    if len(sys.argv) > 1:
        pi = sys.argv[1].lower()
    top10 = getTopTenList ()
    renumber(top10, pi)
    print('</pre></body></html>')

#
def error (msg) :
    print("Content-type: text/html")
    print()
    print(msg)
    
###
def main ():
    form = cgi.FieldStorage()
    if not "cmd" in form:
        error("No action.")
    cmd = form["cmd"].value
    if cmd == "renumber" :
        renumberTop10()
    elif cmd == "new" :
        makeProjectDirectory(form)
    else:
        error("No action.")

main()
