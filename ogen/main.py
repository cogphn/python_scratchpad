import json

from datetime import datetime, timedelta
import random
from random import randrange
import tqdm
import pandas as pd
import uuid

## Config

numrecords = 100
numusers = 200
domain = "notonmicrosoft.com"

et = datetime.now()
st = et - timedelta(days=90)


'''
refs:
 - https://learn.microsoft.com/en-us/purview/audit-log-activities
 - https://learn.microsoft.com/en-us/purview/audit-log-search
 - https://learn.microsoft.com/en-us/purview/audit-log-detailed-properties
 - https://learn.microsoft.com/en-us/purview/ediscovery-search-for-activities-in-the-audit-log
'''


randoemails = []

applicationAdministrationActivities = [
 'Add delegation entry','Add service principal', 'Add service principal credentials', 'Remove delegation entry', 
 'Remove service principal', 'Remove service principal credentials', 'Set delegation entry'
]

microsoftEntraGroupAdministrationActivities = [
   'Add group', 'Add member to group', 'Delete group', 'Remove member from group', 'Update group'
]

briefingEmailActivities = [
   'UpdatedOrganizationBriefingSettings', 'UpdatedUserBriefingSettings'
]

copilotActivities = [
   'CopilotInteraction'
]

directoryAdministrativeActivities = [
   'Add domain to company', 'Add partner to company', 'Remove domain from company', 'Remove partner from company', 'Set company information', 
   'Set domain authentication', 'Set federation settings on domain', 'Set password policy', 'Set DirSyncEnabled flag', 'Update domain',
   'Verify domain', 'Verify email verified domain'
]

dispositionReviewActivities = [
   'ApproveDisposal', 'ExtendRetention', 'RelabelItem', 'AddReviewer'
]

eDiscoveryActivities = [
   
]


def generateUsers():
   name_data = pd.read_html("https://www.ssa.gov/oact/babynames/decades/century.html")[0]
   name_data.columns = ['rank','male_name','male_number', 'female_name','female_number']
   names = name_data['male_name'].to_list()
   names2 = name_data['female_name'].to_list()
   names.extend(names2)
   c = 0
   while c < numusers:
      r1 = randrange(len(names)-1)
      r2 = randrange(len(names)-1)
      randoemails.append(f"{names[r1]}.{names[r2]}@{domain}")
      c += 1
   return len(randoemails)



def getRandoDate():
   duration = et - st
   duration_seconds = (duration.days * 24 * 60 * 60) + duration.seconds
   rand_duration = randrange(duration_seconds)
   return st + timedelta(seconds=rand_duration) 
#

def getCurrentProtectionType():
   ret = {}
   ret['ProtectionType'] = randrange(4)
   ret['Owner'] = randoemails[randrange(len(randoemails)-1)]
   ret['TemplateId'] = str(uuid.uuid1())
   de = randrange(2)
   if de == 0:
      ret['DocumentEncrypted'] = False
   else:
      ret['DocumentEncrypted'] = True
   #
   return ret

if __name__ == "__main__":
   print("Generating users...")
   num_generated_users = generateUsers()
   print(f"[*] generated {num_generated_users} users")
   generated = 0
   data = []
   while generated < numrecords:
      row = {}
      creationTime = getRandoDate()
      row['CreationTime'] = creationTime.strftime(format="%Y-%m-%d %H:%M:%S")
      row['CurrentProtectionType'] = getCurrentProtectionType()
      row['ModifiedProperties'] = { "Name":"test", "NewValue":"testval","OldValue":"prodval"}              
      row['ObjectId'] = str(uuid.uuid1())
      row['Operation'] = 
      generated += 1
      data.append(row)
   print(data)
   print("[.] Done")

