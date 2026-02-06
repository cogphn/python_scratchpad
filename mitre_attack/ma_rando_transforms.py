import requests 
import pandas as pd 
import json 

with open("data/enterprise-attack-18.1.json") as infile:
    mitre_data = json.loads(infile.read())
#


# Courses of Action mapped to attack technique 

coa = []
for obj in mitre_data['objects']:
    if obj['type'] == 'course-of-action' and obj['x_mitre_deprecated'] is False:
        if 'revoked' in obj:
            if obj['revoked'] == True:
                continue
        obj['external_id'] = obj['external_references'][0]['external_id']
        coa.append(obj)
    #
#
attack_patterns = []
for obj in mitre_data['objects']:    
    if obj['type'] == 'attack-pattern' and obj['x_mitre_deprecated'] is False:
        if 'revoked' in obj:
            if obj['revoked'] == True:
                continue
        #obj['external_id'] = obj['external_references'][0]['external_id']
        #
        for extref in obj['external_references']:
            if extref['source_name'] == 'mitre-attack':
                obj['external_id'] = extref['external_id']
        attack_patterns.append(obj)
    #
#

reltable = []
for obj in mitre_data['objects']:
    if obj['type'] == 'relationship' and obj['x_mitre_deprecated'] is False:    
        if 'revoked' in obj:
            if obj['revoked'] == True:
                continue
            #
        #
        if "course-of-action" in obj['source_ref'] or "course-of-action" in obj['target_ref']:
            reltable.append(obj)
        #
    #
#


coadf = pd.json_normalize(coa)
reldf = pd.json_normalize(reltable)
apdf = pd.json_normalize(attack_patterns)


df1 = pd.merge(coadf, reldf, how='inner', left_on='id', right_on='source_ref')
_rpt = pd.merge(df1, apdf, how='inner', left_on='target_ref', right_on='id')

