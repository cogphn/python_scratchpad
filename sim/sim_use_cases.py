#import polars as pl
import pandas as pd
import random
import uuid 
import json 
import tqdm
import math
from datetime import datetime 
import os 

with open("./data/enterprise-attack-14.1.json") as enterprise_infile:
    enterprise_matrix = json.load(enterprise_infile)
#

def generate_metrics(use_case:dict) -> dict:
    alerts_raised = random.randint(0,1000)
    use_case['alerts_raised'] = alerts_raised
    use_case['false_positives'] = random.randint(0,alerts_raised)
    use_case['true_positives'] = alerts_raised - use_case['false_positives']
    return use_case

if __name__ == "__main__":
    print("[*] starting...")
    numobs = 300
    i=0
    mitre_data = []

    techniques = [x for x in enterprise_matrix['objects'] if x['type'] == 'attack-pattern']

    print("    [*] fixing data")
    for t in tqdm.tqdm(techniques):
        tactic = t['external_references'][0]['url'].replace("https://attack.mitre.org/techniques/","").split("/")[0]
        technique = t['external_references'][0]['url'].replace("https://attack.mitre.org/techniques/","").replace("/",".")
        tactic_names = [x['phase_name'] for x in t['kill_chain_phases']]
        r = {
            "tactic":tactic,
            "technique":technique,
            "tactic_names":tactic_names,
            "name":t['name']
        }
        r = generate_metrics(r)
        mitre_data.append(r)
    #
    
    print("    [*] Generating list of use cases ")
    ## First of all - I want a random subset of techniques to have use cases. Let's say 60% Mitre coverage 
    
    num_techniques = len(techniques)  

    k = math.floor(num_techniques * 0.6)
    indexes = [i for i in range(num_techniques)]
    sample = random.sample(indexes, k)
    use_cases = [mitre_data[i] for i in sample]
    
    print(f"    [i] # use cases: {len(use_cases)}")

    outfile_filename = datetime.now().strftime('%Y%m%d%H%M%S')+"_sample_usecase_data.csv"
    print(f"    [*] writing file to {outfile_filename}")
    data = pd.DataFrame(use_cases)
    data.to_csv("data"+os.sep+outfile_filename, index=False)

    print("[.] done")
    #
