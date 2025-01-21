import requests

import pandas as pd


infile_path = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/refs/heads/master/enterprise-attack/enterprise-attack-16.1.json"

resp = requests.get(infile_path)
data = resp.json()

tactics = []
techniques = []

for o in data['objects']:
    if o['type'] == 'x-mitre-tactic':
        tactic_name= o['name']
        tactic_id = o['external_references'][0]['external_id']
        tactic_description = o['description']
        tactic_name_ref = o['name'].lower().replace(" ","-")
        tactics.append({
            'tactic_name':tactic_name,
            'tactic_id':tactic_id,
            'tactic_description':tactic_description,
            'tactic_name_ref':tactic_name_ref
        })
    if o['type'] == 'attack-pattern':
        technique_name = o['name']
        technique_id = o['external_references'][0]['external_id']
        kill_chain_phases = o['kill_chain_phases']
        for kcp in kill_chain_phases:
            techniques.append({
                'technique_name':technique_name,
                'technique_id': technique_id,
                'tactic_name_ref': kcp['phase_name']
            })
    #
#


t = pd.DataFrame(tactics)
tech = pd.DataFrame(techniques)

pd.merge(left=tech, right=t, left_on='tactic_name_ref', right_on='tactic_name_ref').to_csv("mitre16.csv", index=False)

